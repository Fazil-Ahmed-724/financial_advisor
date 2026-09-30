from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_session
from app.models import Account, FinancialProfile, JournalLine, MarketplaceListing, PropertyListing, User
from app.schemas_dashboard import (
    DashboardResponse,
    FinancialProfileResponse,
    FinancialProfileUpdate,
)

router = APIRouter(tags=["dashboard"])
ZERO = Decimal("0.00")


def get_profile(session: Session, user_id) -> FinancialProfile:
    profile = session.get(FinancialProfile, user_id)
    if profile is None:
        # Compatibility fallback for users created outside the API.
        profile = FinancialProfile(user_id=user_id)
        session.add(profile)
        session.commit()
        session.refresh(profile)
    return profile


def ledger_totals(session: Session, user_id) -> dict[str, Decimal]:
    rows = session.execute(
        select(Account.type, func.coalesce(func.sum(JournalLine.amount), ZERO))
        .outerjoin(
            JournalLine,
            (JournalLine.account_id == Account.id)
            & (JournalLine.user_id == user_id),
        )
        .where(Account.user_id == user_id)
        .group_by(Account.type)
    ).all()
    return {account_type: Decimal(total) for account_type, total in rows}


@router.get("/financial-profile", response_model=FinancialProfileResponse)
def read_financial_profile(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    return get_profile(session, user.id)


@router.put("/financial-profile", response_model=FinancialProfileResponse)
def update_financial_profile(
    payload: FinancialProfileUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    profile = get_profile(session, user.id)
    profile.monthly_essential_expenses = payload.monthly_essential_expenses
    profile.reserve_months = payload.reserve_months
    session.commit()
    session.refresh(profile)
    return profile


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    profile = get_profile(session, user.id)
    totals = ledger_totals(session, user.id)

    cash = totals.get("cash", ZERO)
    investment = totals.get("investment", ZERO)
    # Liability lines normally carry credits (negative); expose obligations positively.
    liabilities = -totals.get("liability", ZERO)
    positive_liabilities = max(liabilities, ZERO)
    reserve_target = profile.monthly_essential_expenses * profile.reserve_months
    positive_cash = max(cash, ZERO)
    protected_cash = min(positive_cash, reserve_target)
    investable_cash = max(
        positive_cash - protected_cash - positive_liabilities,
        ZERO,
    )
    confirmed_property = session.scalar(select(func.coalesce(func.sum(PropertyListing.confirmed_valuation), ZERO)).where(
        PropertyListing.user_id == user.id,
        PropertyListing.owned_by_user.is_(True),
        PropertyListing.confirmed_valuation.is_not(None),
        PropertyListing.valuation_confirmed_at.is_not(None),
    ))
    confirmed_inventory = session.scalar(select(func.coalesce(func.sum(MarketplaceListing.confirmed_inventory_value), ZERO)).where(
        MarketplaceListing.user_id == user.id,
        MarketplaceListing.confirmed_inventory_value.is_not(None),
        MarketplaceListing.inventory_valued_at.is_not(None),
    ))

    return DashboardResponse(
        cash_balance=cash,
        investment_book_value=investment,
        liability_balance=liabilities,
        net_worth_book_value=cash + investment - liabilities,
        monthly_essential_expenses=profile.monthly_essential_expenses,
        reserve_months=profile.reserve_months,
        reserve_target=reserve_target,
        protected_emergency_cash=protected_cash,
        investable_cash=investable_cash,
        confirmed_property_value=confirmed_property,
        net_worth_with_confirmed_property=cash + investment - liabilities + confirmed_property,
        confirmed_resale_inventory_value=confirmed_inventory,
        net_worth_with_confirmed_assets=cash + investment - liabilities + confirmed_property + confirmed_inventory,
    )
