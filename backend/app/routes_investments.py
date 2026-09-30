import uuid
from datetime import datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_session
from app.models import (
    Account, AuditEvent, InvestmentLot, InvestmentTrade, JournalEntry, JournalLine,
    LotConsumption, SaleAnalysis, TaxRule, User,
)
from app.routes_finance import existing_idempotency, request_hash, save_idempotency
from app.schemas_investments import (
    HoldingResponse, LotResponse, SaleAnalysisCreate, SaleAnalysisResponse,
    TaxRuleCreate, TaxRuleResponse, TradeCreate, TradeResponse,
)

router = APIRouter(tags=["investments"])
CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def owned_active_account(session: Session, user_id, account_id, expected_type: str) -> Account:
    account = session.scalar(select(Account).where(Account.id == account_id, Account.user_id == user_id))
    if account is None:
        raise HTTPException(404, "Account not found")
    if not account.is_active or account.type != expected_type:
        raise HTTPException(422, f"A current active {expected_type} account is required")
    return account


def fifo_plan(session: Session, user_id, investment_account_id, symbol, quantity, through_date=None, lock=False):
    query = select(InvestmentLot).where(
        InvestmentLot.user_id == user_id,
        InvestmentLot.investment_account_id == investment_account_id,
        InvestmentLot.symbol == symbol,
        InvestmentLot.remaining_quantity > 0,
    )
    if through_date is not None:
        query = query.where(InvestmentLot.acquired_on <= through_date)
    query = query.order_by(InvestmentLot.acquired_on, InvestmentLot.created_at, InvestmentLot.id)
    if lock:
        query = query.with_for_update()
    lots = session.scalars(query).all()
    available = sum((lot.remaining_quantity for lot in lots), Decimal("0"))
    if available < quantity:
        raise HTTPException(422, "Insufficient owned quantity for this symbol and investment account")
    remaining = quantity
    allocations = []
    for lot in lots:
        if remaining <= 0:
            break
        taken = min(remaining, lot.remaining_quantity)
        allocated_cost = lot.remaining_cost if taken == lot.remaining_quantity else money(
            lot.remaining_cost * taken / lot.remaining_quantity
        )
        allocations.append((lot, taken, allocated_cost))
        remaining -= taken
    return allocations


def internal_result_account(session: Session, user_id, account_type: str) -> Account:
    name = "Realized Investment Gains" if account_type == "income" else "Realized Investment Losses"
    account = session.scalar(select(Account).where(Account.user_id == user_id, Account.name == name))
    if account is None:
        account = Account(user_id=user_id, name=name, type=account_type, currency="PKR")
        session.add(account)
        session.flush()
    elif account.type != account_type or not account.is_active:
        raise HTTPException(422, f"The system account '{name}' must be an active {account_type} account")
    return account


@router.post("/investment-trades", response_model=TradeResponse, status_code=201)
def record_trade(
    payload: TradeCreate,
    idempotency_key: str = Header(min_length=1, max_length=200, alias="Idempotency-Key"),
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    operation = "POST /investment-trades"
    digest = request_hash(payload)
    cached = existing_idempotency(session, user.id, idempotency_key, operation, digest)
    if cached is not None:
        return cached
    owned_active_account(session, user.id, payload.investment_account_id, "investment")
    owned_active_account(session, user.id, payload.cash_account_id, "cash")
    gross = money(payload.quantity * payload.execution_price)
    occurred_at = datetime.combine(payload.trade_date, time.min, tzinfo=timezone.utc)
    trade_id = uuid.uuid4()
    entry_id = uuid.uuid4()
    trade = InvestmentTrade(
        id=trade_id, journal_entry_id=entry_id,
        user_id=user.id, side=payload.side.value, symbol=payload.symbol,
        trade_date=payload.trade_date, quantity=payload.quantity,
        execution_price=payload.execution_price, fees=payload.fees,
        gross_amount=gross, investment_account_id=payload.investment_account_id,
        cash_account_id=payload.cash_account_id, external_reference=payload.external_reference,
    )
    try:
        if payload.side.value == "BUY":
            total_cost = gross + payload.fees
            entry = JournalEntry(id=entry_id, user_id=user.id, kind="trade", occurred_at=occurred_at,
                description=f"External BUY {payload.quantity} {payload.symbol}", lines=[
                    JournalLine(user_id=user.id, account_id=payload.investment_account_id, amount=total_cost),
                    JournalLine(user_id=user.id, account_id=payload.cash_account_id, amount=-total_cost),
                ])
            trade.net_proceeds = None
            trade.fifo_cost_basis = None
            trade.realized_gain_loss = None
            session.add(entry); session.flush()
            session.add(trade); session.flush()
            session.add(InvestmentLot(
                user_id=user.id, buy_trade_id=trade.id,
                investment_account_id=payload.investment_account_id, symbol=payload.symbol,
                acquired_on=payload.trade_date, original_quantity=payload.quantity,
                remaining_quantity=payload.quantity, original_cost=total_cost, remaining_cost=total_cost,
            ))
        else:
            allocations = fifo_plan(session, user.id, payload.investment_account_id, payload.symbol,
                                    payload.quantity, payload.trade_date, lock=True)
            cost_basis = sum((cost for _, _, cost in allocations), ZERO)
            net_proceeds = gross - payload.fees
            realized = net_proceeds - cost_basis
            lines = []
            if net_proceeds != 0:
                lines.append(JournalLine(user_id=user.id, account_id=payload.cash_account_id, amount=net_proceeds))
            lines.append(JournalLine(user_id=user.id, account_id=payload.investment_account_id, amount=-cost_basis))
            if realized > 0:
                result_account = internal_result_account(session, user.id, "income")
                lines.append(JournalLine(user_id=user.id, account_id=result_account.id, amount=-realized))
            elif realized < 0:
                result_account = internal_result_account(session, user.id, "expense")
                lines.append(JournalLine(user_id=user.id, account_id=result_account.id, amount=-realized))
            entry = JournalEntry(id=entry_id, user_id=user.id, kind="trade", occurred_at=occurred_at,
                description=f"External SELL {payload.quantity} {payload.symbol}", lines=lines)
            trade.net_proceeds = net_proceeds
            trade.fifo_cost_basis = cost_basis
            trade.realized_gain_loss = realized
            session.add(entry); session.flush()
            session.add(trade); session.flush()
            for lot, qty, cost in allocations:
                lot.remaining_quantity -= qty
                lot.remaining_cost -= cost
                session.add(LotConsumption(user_id=user.id, sell_trade_id=trade.id,
                                           lot_id=lot.id, quantity=qty, cost_basis=cost))
        session.flush(); session.refresh(trade)
        body = TradeResponse.model_validate(trade).model_dump(mode="json")
        save_idempotency(session, user.id, idempotency_key, operation, digest, body)
        session.commit()
    except HTTPException:
        session.rollback(); raise
    except DBAPIError:
        session.rollback()
        cached = existing_idempotency(session, user.id, idempotency_key, operation, digest)
        if cached is not None:
            return cached
        raise HTTPException(422, "External trade could not be recorded") from None
    return body


@router.get("/investment-trades", response_model=list[TradeResponse])
def list_trades(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return session.scalars(select(InvestmentTrade).where(InvestmentTrade.user_id == user.id)
                           .order_by(InvestmentTrade.trade_date.desc(), InvestmentTrade.created_at.desc())).all()


@router.get("/holdings", response_model=list[HoldingResponse])
def holdings(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    lots = session.scalars(select(InvestmentLot).where(
        InvestmentLot.user_id == user.id, InvestmentLot.remaining_quantity > 0
    ).order_by(InvestmentLot.symbol, InvestmentLot.acquired_on, InvestmentLot.id)).all()
    realized_rows = session.execute(select(
        InvestmentTrade.investment_account_id, InvestmentTrade.symbol,
        func.coalesce(func.sum(InvestmentTrade.realized_gain_loss), ZERO)
    ).where(InvestmentTrade.user_id == user.id, InvestmentTrade.side == "SELL")
      .group_by(InvestmentTrade.investment_account_id, InvestmentTrade.symbol)).all()
    realized = {(a, s): value for a, s, value in realized_rows}
    groups = {}
    for lot in lots:
        groups.setdefault((lot.investment_account_id, lot.symbol), []).append(lot)
    return [HoldingResponse(
        investment_account_id=account_id, symbol=symbol,
        quantity=sum((x.remaining_quantity for x in group), Decimal("0")),
        remaining_book_cost=sum((x.remaining_cost for x in group), ZERO),
        realized_gain_loss=realized.get((account_id, symbol), ZERO),
        lots=[LotResponse.model_validate(x) for x in group],
    ) for (account_id, symbol), group in groups.items()]


@router.post("/tax-rules", response_model=TaxRuleResponse, status_code=201)
def create_tax_rule(payload: TaxRuleCreate,
    idempotency_key: str = Header(min_length=1, max_length=200, alias="Idempotency-Key"),
    user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    operation = "POST /tax-rules"; digest = request_hash(payload)
    cached = existing_idempotency(session, user.id, idempotency_key, operation, digest)
    if cached is not None: return cached
    rule = TaxRule(user_id=user.id, **payload.model_dump())
    session.add(rule); session.flush(); session.refresh(rule)
    session.add(AuditEvent(user_id=user.id, event_type="tax_rule_created",
        entity_type="tax_rule", entity_id=rule.id,
        details={"effective_from": rule.effective_from.isoformat(),
                 "effective_to": None if rule.effective_to is None else rule.effective_to.isoformat(),
                 "gain_tax_rate": str(rule.gain_tax_rate), "append_only": True}))
    body = TaxRuleResponse.model_validate(rule).model_dump(mode="json")
    save_idempotency(session, user.id, idempotency_key, operation, digest, body); session.commit()
    return body


@router.get("/tax-rules", response_model=list[TaxRuleResponse])
def list_tax_rules(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return session.scalars(select(TaxRule).where(TaxRule.user_id == user.id)
                           .order_by(TaxRule.effective_from.desc(), TaxRule.created_at.desc())).all()


@router.post("/sale-analyses", response_model=SaleAnalysisResponse, status_code=201)
def analyze_sale(payload: SaleAnalysisCreate,
    idempotency_key: str = Header(min_length=1, max_length=200, alias="Idempotency-Key"),
    user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    operation = "POST /sale-analyses"; digest = request_hash(payload)
    cached = existing_idempotency(session, user.id, idempotency_key, operation, digest)
    if cached is not None: return cached
    owned_active_account(session, user.id, payload.investment_account_id, "investment")
    allocations = fifo_plan(session, user.id, payload.investment_account_id, payload.symbol,
                            payload.quantity, payload.calculation_date)
    cost = sum((x[2] for x in allocations), ZERO)
    gross = money(payload.quantity * payload.hypothetical_price)
    gross_profit = gross - cost
    before_tax_profit = gross_profit - payload.estimated_fees
    rule = session.scalar(select(TaxRule).where(
        TaxRule.user_id == user.id, TaxRule.effective_from <= payload.calculation_date,
        or_(TaxRule.effective_to.is_(None), TaxRule.effective_to >= payload.calculation_date),
    ).order_by(TaxRule.effective_from.desc(), TaxRule.created_at.desc()).limit(1))
    estimated_tax = None; tax_status = "not_configured"; tax_rule_id = None
    potential_loss_treatment = None
    if rule is not None:
        tax_rule_id = rule.id
        if before_tax_profit > 0:
            estimated_tax = money(before_tax_profit * rule.gain_tax_rate / Decimal("100"))
            tax_status = "configured_gain_estimate"
        else:
            estimated_tax = ZERO
            tax_status = "configured_no_automatic_loss_credit"
            potential_loss_treatment = rule.loss_treatment_note
    net_proceeds = gross - payload.estimated_fees - (estimated_tax or ZERO)
    analysis = SaleAnalysis(
        user_id=user.id, investment_account_id=payload.investment_account_id,
        symbol=payload.symbol, quantity=payload.quantity,
        hypothetical_price=payload.hypothetical_price, estimated_fees=payload.estimated_fees,
        gross_proceeds=gross, fifo_cost_basis=cost, gross_profit_loss=gross_profit,
        estimated_tax=estimated_tax, net_proceeds=net_proceeds,
        net_profit_loss=net_proceeds - cost, tax_status=tax_status, tax_rule_id=tax_rule_id,
        assumptions={"calculation_date": payload.calculation_date.isoformat(),
                     "price_source": "user_entered_hypothetical", "fifo": True,
                     "taxable_gain_basis": "gross proceeds minus FIFO cost and estimated fees",
                     "potential_loss_treatment": potential_loss_treatment,
                     "no_order_placed": True},
        fifo_allocations=[{"lot_id": str(lot.id), "quantity": str(qty), "cost_basis": str(cost_part)}
                          for lot, qty, cost_part in allocations],
        excluded_items=["market price verification", "broker charges beyond entered fees",
                        "withholding and other taxes not represented by the configured rule",
                        "order execution, slippage, and liquidity"],
    )
    session.add(analysis); session.flush(); session.refresh(analysis)
    body = SaleAnalysisResponse.model_validate(analysis).model_dump(mode="json")
    save_idempotency(session, user.id, idempotency_key, operation, digest, body); session.commit()
    return body


@router.get("/sale-analyses", response_model=list[SaleAnalysisResponse])
def list_analyses(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return session.scalars(select(SaleAnalysis).where(SaleAnalysis.user_id == user.id)
                           .order_by(SaleAnalysis.calculated_at.desc(), SaleAnalysis.id.desc())).all()
