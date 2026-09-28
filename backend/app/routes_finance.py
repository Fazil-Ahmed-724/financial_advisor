import hashlib
import json
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_session
from app.models import Account, IdempotencyRecord, JournalEntry, JournalLine, User
from app.schemas_finance import (
    AccountBalanceResponse,
    AccountCreate,
    AccountResponse,
    JournalEntryCreate,
    JournalEntryResponse,
)

router = APIRouter(tags=["finance"])
NORMAL_CREDIT_TYPES = {"income", "liability", "equity"}


def request_hash(payload) -> str:
    canonical = json.dumps(
        payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def existing_idempotency(
    session: Session, user_id, key: str, operation: str, digest: str
) -> dict | None:
    record = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == user_id, IdempotencyRecord.key == key
        )
    )
    if record is None:
        return None
    if record.operation != operation or record.request_hash != digest:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key was already used with a different request",
        )
    return record.response_body


def save_idempotency(
    session: Session, user_id, key: str, operation: str, digest: str, body: dict
) -> None:
    session.add(
        IdempotencyRecord(
            user_id=user_id,
            key=key,
            operation=operation,
            request_hash=digest,
            response_body=body,
        )
    )


@router.post("/accounts", response_model=AccountResponse, status_code=201)
def create_account(
    payload: AccountCreate,
    idempotency_key: str = Header(min_length=1, max_length=200, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    operation = "POST /accounts"
    digest = request_hash(payload)
    cached = existing_idempotency(session, user.id, idempotency_key, operation, digest)
    if cached is not None:
        return cached

    account = Account(
        user_id=user.id,
        name=payload.name,
        type=payload.type.value,
        currency=payload.currency,
    )
    session.add(account)
    try:
        session.flush()
        session.refresh(account)
        body = AccountResponse.model_validate(account).model_dump(mode="json")
        save_idempotency(session, user.id, idempotency_key, operation, digest, body)
        session.commit()
    except DBAPIError:
        session.rollback()
        cached = existing_idempotency(session, user.id, idempotency_key, operation, digest)
        if cached is not None:
            return cached
        raise HTTPException(
            status_code=409, detail="An account with this name already exists"
        ) from None
    return body


@router.get("/accounts", response_model=list[AccountResponse])
def list_accounts(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    return session.scalars(
        select(Account)
        .where(Account.user_id == user.id)
        .order_by(Account.name, Account.id)
    ).all()


@router.get("/accounts/balances", response_model=list[AccountBalanceResponse])
def account_balances(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    signed_total = func.coalesce(func.sum(JournalLine.amount), Decimal("0.00"))
    rows = session.execute(
        select(Account, signed_total)
        .outerjoin(
            JournalLine,
            (JournalLine.account_id == Account.id)
            & (JournalLine.user_id == user.id),
        )
        .where(Account.user_id == user.id)
        .group_by(Account.id)
        .order_by(Account.name, Account.id)
    ).all()
    return [
        AccountBalanceResponse(
            account=account,
            balance=(-total if account.type in NORMAL_CREDIT_TYPES else total),
        )
        for account, total in rows
    ]


def validate_entry_types(payload: JournalEntryCreate, accounts: dict) -> None:
    typed = [(accounts[line.account_id].type, line.amount) for line in payload.lines]
    if any(not accounts[line.account_id].is_active for line in payload.lines):
        raise HTTPException(status_code=422, detail="Journal accounts must be active")

    if payload.kind.value == "income":
        valid = any(t in {"cash", "investment"} and a > 0 for t, a in typed) and any(
            t == "income" and a < 0 for t, a in typed
        )
    elif payload.kind.value == "expense":
        valid = any(t == "expense" and a > 0 for t, a in typed) and any(
            t in {"cash", "investment"} and a < 0 for t, a in typed
        )
    else:
        valid = any(t == "equity" for t, _ in typed) and any(
            (t in {"cash", "investment"} and a > 0) or (t == "liability" and a < 0)
            for t, a in typed
        )
    if not valid:
        raise HTTPException(
            status_code=422,
            detail=f"Account types and amount signs are invalid for {payload.kind.value}",
        )


@router.post("/journal-entries", response_model=JournalEntryResponse, status_code=201)
def create_journal_entry(
    payload: JournalEntryCreate,
    idempotency_key: str = Header(min_length=1, max_length=200, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    operation = "POST /journal-entries"
    digest = request_hash(payload)
    cached = existing_idempotency(session, user.id, idempotency_key, operation, digest)
    if cached is not None:
        return cached

    account_ids = [line.account_id for line in payload.lines]
    owned_accounts = session.scalars(
        select(Account).where(
            Account.user_id == user.id, Account.id.in_(account_ids)
        )
    ).all()
    accounts = {account.id: account for account in owned_accounts}
    if len(accounts) != len(account_ids):
        raise HTTPException(status_code=404, detail="One or more accounts were not found")
    validate_entry_types(payload, accounts)

    entry = JournalEntry(
        user_id=user.id,
        kind=payload.kind.value,
        description=payload.description,
        occurred_at=payload.occurred_at,
        lines=[
            JournalLine(
                user_id=user.id, account_id=line.account_id, amount=line.amount
            )
            for line in payload.lines
        ],
    )
    session.add(entry)
    try:
        session.flush()
        session.refresh(entry)
        body = JournalEntryResponse.model_validate(entry).model_dump(mode="json")
        save_idempotency(session, user.id, idempotency_key, operation, digest, body)
        session.commit()
    except DBAPIError:
        session.rollback()
        cached = existing_idempotency(session, user.id, idempotency_key, operation, digest)
        if cached is not None:
            return cached
        raise HTTPException(status_code=422, detail="Journal entry could not be saved") from None
    return body


@router.get("/journal-entries", response_model=list[JournalEntryResponse])
def list_journal_entries(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    return session.scalars(
        select(JournalEntry)
        .where(JournalEntry.user_id == user.id)
        .order_by(JournalEntry.occurred_at.desc(), JournalEntry.id.desc())
    ).all()
