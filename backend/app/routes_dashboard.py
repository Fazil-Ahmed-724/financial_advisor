from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_session
from app.models import Account, FinancialProfile, JournalLine, User
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
    )
