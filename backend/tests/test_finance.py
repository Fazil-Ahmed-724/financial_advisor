import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.auth import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import Account, JournalEntry, JournalLine, User

client = TestClient(app)
PASSWORD = "correct horse battery staple"


def authenticated_user(label: str):
    response = client.post(
        "/auth/register",
        json={"email": f"{label}-{uuid.uuid4()}@example.com", "password": PASSWORD},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['token']['access_token']}"}


def create_account(headers, name: str, account_type: str, key: str | None = None):
    request_headers = {**headers, "Idempotency-Key": key or str(uuid.uuid4())}
    response = client.post(
        "/accounts",
        headers=request_headers,
        json={"name": name, "type": account_type, "currency": "pkr"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def entry_payload(kind: str, first: dict, first_amount: str, second: dict, second_amount: str):
    return {
        "kind": kind,
        "description": f"Test {kind}",
        "occurred_at": "2026-09-29T12:00:00+05:00",
        "lines": [
            {"account_id": first["id"], "amount": first_amount},
            {"account_id": second["id"], "amount": second_amount},
        ],
    }


def test_account_types_normalization_scoping_and_idempotency():
    first = authenticated_user("accounts-one")
    second = authenticated_user("accounts-two")
    key = str(uuid.uuid4())

    created = create_account(first, "  Main   Cash  ", "cash", key)
    repeated = client.post(
        "/accounts",
        headers={**first, "Idempotency-Key": key},
        json={"name": "  Main   Cash  ", "type": "cash", "currency": "pkr"},
    )
    assert repeated.status_code == 201
    assert repeated.json() == created
    assert created["name"] == "Main Cash"
    assert created["currency"] == "PKR"

    for account_type in ["investment", "income", "expense", "liability", "equity"]:
        create_account(first, account_type.title(), account_type)

    assert len(client.get("/accounts", headers=first).json()) == 6
    assert client.get("/accounts", headers=second).json() == []

    conflict = client.post(
        "/accounts",
        headers={**first, "Idempotency-Key": key},
        json={"name": "Different", "type": "cash", "currency": "PKR"},
    )
    assert conflict.status_code == 409


def test_balanced_opening_income_expense_and_account_balances():
    headers = authenticated_user("balanced")
    cash = create_account(headers, "Cash", "cash")
    equity = create_account(headers, "Opening Equity", "equity")
    income = create_account(headers, "Salary", "income")
    expense = create_account(headers, "Food", "expense")

    payloads = [
        entry_payload("opening", cash, "1000.00", equity, "-1000.00"),
        entry_payload("income", cash, "500.25", income, "-500.25"),
        entry_payload("expense", expense, "125.10", cash, "-125.10"),
    ]
    for payload in payloads:
        response = client.post(
            "/journal-entries",
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            json=payload,
        )
        assert response.status_code == 201, response.text
        assert sum(float(line["amount"]) for line in response.json()["lines"]) == 0

    entries = client.get("/journal-entries", headers=headers)
    assert entries.status_code == 200
    assert len(entries.json()) == 3

    balances = {
        row["account"]["name"]: row["balance"]
        for row in client.get("/accounts/balances", headers=headers).json()
    }
    assert balances == {
        "Cash": "1375.15",
        "Food": "125.10",
        "Opening Equity": "1000.00",
        "Salary": "500.25",
    }


def test_unbalanced_zero_and_excess_precision_leave_no_partial_entry():
    headers = authenticated_user("invalid-money")
    cash = create_account(headers, "Cash", "cash")
    equity = create_account(headers, "Equity", "equity")

    invalid_payloads = [
        entry_payload("opening", cash, "100.00", equity, "-99.00"),
        entry_payload("opening", cash, "0.00", equity, "0.00"),
        entry_payload("opening", cash, "100.001", equity, "-100.001"),
    ]
    for payload in invalid_payloads:
        response = client.post(
            "/journal-entries",
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            json=payload,
        )
        assert response.status_code == 422
    assert client.get("/journal-entries", headers=headers).json() == []
    assert all(
        row["balance"] == "0.00"
        for row in client.get("/accounts/balances", headers=headers).json()
    )


def test_account_ownership_is_enforced_for_entries_and_reads():
    owner = authenticated_user("owner")
    attacker = authenticated_user("attacker")
    owner_cash = create_account(owner, "Owner Cash", "cash")
    attacker_equity = create_account(attacker, "Attacker Equity", "equity")

    response = client.post(
        "/journal-entries",
        headers={**attacker, "Idempotency-Key": str(uuid.uuid4())},
        json=entry_payload(
            "opening", owner_cash, "50.00", attacker_equity, "-50.00"
        ),
    )
    assert response.status_code == 404
    assert client.get("/journal-entries", headers=attacker).json() == []
    assert all(
        row["account"]["id"] != owner_cash["id"]
        for row in client.get("/accounts/balances", headers=attacker).json()
    )


def test_journal_idempotency_replay_and_conflict():
    headers = authenticated_user("entry-idempotency")
    cash = create_account(headers, "Cash", "cash")
    equity = create_account(headers, "Equity", "equity")
    key = str(uuid.uuid4())
    payload = entry_payload("opening", cash, "250.00", equity, "-250.00")

    first = client.post(
        "/journal-entries",
        headers={**headers, "Idempotency-Key": key},
        json=payload,
    )
    second = client.post(
        "/journal-entries",
        headers={**headers, "Idempotency-Key": key},
        json=payload,
    )
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert len(client.get("/journal-entries", headers=headers).json()) == 1

    changed = entry_payload("opening", cash, "300.00", equity, "-300.00")
    conflict = client.post(
        "/journal-entries",
        headers={**headers, "Idempotency-Key": key},
        json=changed,
    )
    assert conflict.status_code == 409
    assert len(client.get("/journal-entries", headers=headers).json()) == 1


def test_invalid_account_types_roll_back_and_write_requires_idempotency_key():
    headers = authenticated_user("rollback")
    cash = create_account(headers, "Cash", "cash")
    expense = create_account(headers, "Expense", "expense")

    missing_key = client.post(
        "/accounts", headers=headers, json={"name": "No Key", "type": "cash"}
    )
    assert missing_key.status_code == 422

    wrong_types = client.post(
        "/journal-entries",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json=entry_payload("income", cash, "20.00", expense, "-20.00"),
    )
    assert wrong_types.status_code == 422
    assert client.get("/journal-entries", headers=headers).json() == []


def test_database_constraint_rejects_unbalanced_entry_and_rolls_back():
    with SessionLocal() as session:
        user = User(
            email=f"database-guard-{uuid.uuid4()}@example.com",
            password_hash=hash_password(PASSWORD),
        )
        session.add(user)
        session.flush()
        cash = Account(user_id=user.id, name="Guard Cash", type="cash", currency="PKR")
        session.add(cash)
        session.commit()

        entry_id = uuid.uuid4()
        entry = JournalEntry(
            id=entry_id,
            user_id=user.id,
            kind="opening",
            description="Must roll back",
            occurred_at=datetime.now(timezone.utc),
            lines=[JournalLine(user_id=user.id, account_id=cash.id, amount=Decimal("10.00"))],
        )
        session.add(entry)
        with pytest.raises(DBAPIError):
            session.commit()
        session.rollback()

        assert session.scalar(
            select(func.count()).select_from(JournalEntry).where(JournalEntry.id == entry_id)
        ) == 0
