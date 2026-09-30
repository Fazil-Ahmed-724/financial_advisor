import uuid
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_session
from app.models import (AuditEvent, DecisionReview, InvestmentDecision, InvestmentLot,
                        InvestmentTrade, LotConsumption, SaleAnalysis, TaxRule, User)
from app.routes_finance import existing_idempotency, request_hash, save_idempotency
from app.schemas_decisions import (AuditEventResponse, DecisionCreate, DecisionDetail,
                                   DecisionResponse, ReviewCreate, ReviewResponse)

router = APIRouter(tags=["decision journal"])
ZERO = Decimal("0.00")


def audit(session, user_id, event_type, entity_type, entity_id=None, details=None):
    session.add(AuditEvent(user_id=user_id, event_type=event_type, entity_type=entity_type,
                           entity_id=entity_id, details=details or {}))


def applicable_rule(session, user_id, on_date):
    return session.scalar(select(TaxRule).where(
        TaxRule.user_id == user_id, TaxRule.effective_from <= on_date,
        or_(TaxRule.effective_to.is_(None), TaxRule.effective_to >= on_date),
    ).order_by(TaxRule.effective_from.desc(), TaxRule.created_at.desc()).limit(1))


def outcome_for(session: Session, decision: InvestmentDecision) -> dict:
    if decision.sale_analysis_id:
        analysis = session.scalar(select(SaleAnalysis).where(
            SaleAnalysis.id == decision.sale_analysis_id, SaleAnalysis.user_id == decision.user_id))
        if not analysis:
            return {"state": "unavailable_incomplete_history", "reason": "linked analysis unavailable"}
        return {"state": "hypothetical_estimate", "gross_result_before_tax": str(analysis.gross_profit_loss),
                "fees": str(analysis.estimated_fees), "estimated_tax": None if analysis.estimated_tax is None else str(analysis.estimated_tax),
                "tax_status": analysis.tax_status, "net_result": str(analysis.net_profit_loss),
                "tax_rule_versions": [] if analysis.tax_rule_id is None else [str(analysis.tax_rule_id)],
                "market_value_available": False, "official_tax_determination": False}
    if not decision.trade_id:
        return {"state": "unavailable_incomplete_history", "reason": "no recorded trade or analysis linked",
                "estimated_tax": None, "tax_status": "unavailable", "market_value_available": False}
    linked = session.scalar(select(InvestmentTrade).where(
        InvestmentTrade.id == decision.trade_id, InvestmentTrade.user_id == decision.user_id))
    if not linked:
        return {"state": "unavailable_incomplete_history", "reason": "linked trade unavailable"}
    trades = session.scalars(select(InvestmentTrade).where(
        InvestmentTrade.user_id == decision.user_id,
        InvestmentTrade.investment_account_id == linked.investment_account_id,
        InvestmentTrade.symbol == linked.symbol).order_by(InvestmentTrade.trade_date, InvestmentTrade.created_at)).all()
    has_buy = any(x.side == "BUY" for x in trades)
    sells = [x for x in trades if x.side == "SELL"]
    open_quantity = session.scalar(select(func.coalesce(func.sum(InvestmentLot.remaining_quantity), Decimal("0"))).where(
        InvestmentLot.user_id == decision.user_id,
        InvestmentLot.investment_account_id == linked.investment_account_id,
        InvestmentLot.symbol == linked.symbol))
    if not has_buy:
        return {"state": "unavailable_incomplete_history", "reason": "purchase history is incomplete",
                "estimated_tax": None, "tax_status": "unavailable", "market_value_available": False}
    realized = sum((x.realized_gain_loss or ZERO for x in sells), ZERO)
    fees = sum((x.fees for x in trades), ZERO)
    state = "realized_closed" if sells and open_quantity == 0 else "unrealized_open"
    rules = []
    tax = ZERO
    missing_tax = False
    for sale in sells:
        rule = applicable_rule(session, decision.user_id, sale.trade_date)
        if rule is None:
            missing_tax = True
        else:
            rules.append({"id": str(rule.id), "effective_from": rule.effective_from.isoformat(),
                          "effective_to": None if rule.effective_to is None else rule.effective_to.isoformat(),
                          "gain_tax_rate": str(rule.gain_tax_rate), "source_note": rule.source_note})
            if sale.realized_gain_loss and sale.realized_gain_loss > 0:
                tax += (sale.realized_gain_loss * rule.gain_tax_rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    tax_value = None if not sells or missing_tax or (sells and not rules) else tax
    tax_status = "unavailable_open_position" if not sells else ("not_configured" if tax_value is None else "configured_estimate")
    return {"state": state, "gross_result_before_fees_and_tax": str(realized + fees),
            "fees": str(fees), "realized_result_before_tax": str(realized),
            "estimated_tax": None if tax_value is None else str(tax_value),
            "tax_status": tax_status,
            "net_result": None if tax_value is None else str(realized - tax_value),
            "open_quantity": str(open_quantity), "unrealized_result": None,
            "market_value_available": False, "tax_rule_versions": rules,
            "official_tax_determination": False,
            "outcome_note": "Profit or loss does not determine decision-process quality."}


def detail(session, decision):
    reviews = session.scalars(select(DecisionReview).where(
        DecisionReview.user_id == decision.user_id, DecisionReview.decision_id == decision.id)
        .order_by(DecisionReview.created_at, DecisionReview.id)).all()
    base = DecisionResponse.model_validate(decision).model_dump()
    return DecisionDetail(**base, outcome=outcome_for(session, decision), reviews=reviews)


@router.post("/decisions", response_model=DecisionDetail, status_code=201)
def create_decision(payload: DecisionCreate,
    idempotency_key: str = Header(min_length=1, max_length=200, alias="Idempotency-Key"),
    user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    operation = "POST /decisions"; digest = request_hash(payload)
    cached = existing_idempotency(session, user.id, idempotency_key, operation, digest)
    if cached is not None: return cached
    if payload.trade_id:
        linked = session.scalar(select(InvestmentTrade).where(InvestmentTrade.id == payload.trade_id, InvestmentTrade.user_id == user.id))
        if not linked: raise HTTPException(404, "Linked trade not found")
        if linked.symbol != payload.instrument: raise HTTPException(422, "Instrument must match linked trade")
    if payload.sale_analysis_id:
        linked = session.scalar(select(SaleAnalysis).where(SaleAnalysis.id == payload.sale_analysis_id, SaleAnalysis.user_id == user.id))
        if not linked: raise HTTPException(404, "Linked sale analysis not found")
        if linked.symbol != payload.instrument: raise HTTPException(422, "Instrument must match linked analysis")
    decision = InvestmentDecision(user_id=user.id, **payload.model_dump())
    session.add(decision); session.flush()
    audit(session, user.id, "decision_created", "investment_decision", decision.id,
          {"original_snapshot_preserved": True, "trade_id": str(payload.trade_id) if payload.trade_id else None,
           "sale_analysis_id": str(payload.sale_analysis_id) if payload.sale_analysis_id else None})
    if payload.trade_id or payload.sale_analysis_id:
        audit(session, user.id, "decision_link_created", "investment_decision", decision.id,
              {"trade_id": str(payload.trade_id) if payload.trade_id else None,
               "sale_analysis_id": str(payload.sale_analysis_id) if payload.sale_analysis_id else None})
    body = detail(session, decision).model_dump(mode="json")
    save_idempotency(session, user.id, idempotency_key, operation, digest, body); session.commit()
    return body


@router.get("/decisions", response_model=list[DecisionResponse])
def list_decisions(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return session.scalars(select(InvestmentDecision).where(InvestmentDecision.user_id == user.id)
                           .order_by(InvestmentDecision.decision_date.desc(), InvestmentDecision.created_at.desc())).all()


@router.get("/decisions/{decision_id}", response_model=DecisionDetail)
def get_decision(decision_id: uuid.UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    decision = session.scalar(select(InvestmentDecision).where(InvestmentDecision.id == decision_id, InvestmentDecision.user_id == user.id))
    if not decision: raise HTTPException(404, "Decision not found")
    return detail(session, decision)


@router.post("/decisions/{decision_id}/reviews", response_model=ReviewResponse, status_code=201)
def review_decision(decision_id: uuid.UUID, payload: ReviewCreate,
    idempotency_key: str = Header(min_length=1, max_length=200, alias="Idempotency-Key"),
    user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    operation = f"POST /decisions/{decision_id}/reviews"; digest = request_hash(payload)
    cached = existing_idempotency(session, user.id, idempotency_key, operation, digest)
    if cached is not None: return cached
    decision = session.scalar(select(InvestmentDecision).where(InvestmentDecision.id == decision_id, InvestmentDecision.user_id == user.id))
    if not decision: raise HTTPException(404, "Decision not found")
    checks = {name: getattr(payload, name) for name in ("thesis_written_before_trade", "risks_considered",
              "concentration_considered", "within_recorded_limits", "followed_original_plan")}
    answered = [v for v in checks.values() if v is not None]
    process = {"checklist": checks, "positive_count": sum(v is True for v in answered),
               "answered_count": len(answered), "explanation": "Counts documented yes answers among answered process checks only.",
               "not_predictive_or_suitability_certification": True, "financial_outcome_used_in_score": False}
    review = DecisionReview(user_id=user.id, decision_id=decision.id, outcome_snapshot=outcome_for(session, decision),
                            process_snapshot=process, **payload.model_dump())
    session.add(review); session.flush()
    audit(session, user.id, "decision_review_added", "decision_review", review.id,
          {"decision_id": str(decision.id), "append_only": True})
    body = ReviewResponse.model_validate(review).model_dump(mode="json")
    save_idempotency(session, user.id, idempotency_key, operation, digest, body); session.commit()
    return body


@router.get("/audit-events", response_model=list[AuditEventResponse])
def audit_events(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return session.scalars(select(AuditEvent).where(AuditEvent.user_id == user.id)
                           .order_by(AuditEvent.created_at, AuditEvent.id)).all()


@router.post("/compliance-reports", status_code=201)
def compliance_report(idempotency_key: str = Header(min_length=1, max_length=200, alias="Idempotency-Key"),
    user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    operation = "POST /compliance-reports"
    class EmptyPayload:
        def model_dump(self, mode="json"): return {}
    digest = request_hash(EmptyPayload())
    cached = existing_idempotency(session, user.id, idempotency_key, operation, digest)
    if cached is not None: return cached
    report_id = uuid.uuid4()
    audit(session, user.id, "compliance_report_generated", "compliance_report", report_id,
          {"format": "application/json", "official_tax_determination": False})
    session.flush()
    trades = session.scalars(select(InvestmentTrade).where(InvestmentTrade.user_id == user.id).order_by(InvestmentTrade.trade_date, InvestmentTrade.id)).all()
    lots = session.scalars(select(InvestmentLot).where(InvestmentLot.user_id == user.id).order_by(InvestmentLot.acquired_on, InvestmentLot.id)).all()
    consumptions = session.scalars(select(LotConsumption).where(LotConsumption.user_id == user.id)).all()
    rules = session.scalars(select(TaxRule).where(TaxRule.user_id == user.id).order_by(TaxRule.effective_from, TaxRule.id)).all()
    decisions = session.scalars(select(InvestmentDecision).where(InvestmentDecision.user_id == user.id)).all()
    reviews = session.scalars(select(DecisionReview).where(DecisionReview.user_id == user.id)).all()
    events = session.scalars(select(AuditEvent).where(AuditEvent.user_id == user.id).order_by(AuditEvent.created_at, AuditEvent.id)).all()
    def rows(items):
        return [{c.name: getattr(x, c.name) for c in x.__table__.columns if c.name != "user_id"} for x in items]
    body = jsonable_encoder({"report_id": report_id, "generated_at": events[-1].created_at,
        "scope": "authenticated_user_only", "informational_only": True, "official_tax_determination": False,
        "order_execution_supported": False, "dividends": {"supported": False, "records": []},
        "trades": rows(trades), "fifo_lots": rows(lots), "fifo_consumptions": rows(consumptions),
        "tax_rules": rows(rules), "decisions": rows(decisions), "decision_reviews": rows(reviews),
        "audit_events": rows(events)})
    save_idempotency(session, user.id, idempotency_key, operation, digest, body); session.commit()
    return body
