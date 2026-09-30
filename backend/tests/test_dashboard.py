import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
PASSWORD = "correct horse battery staple"


def authenticated_user(label: str):
    response = client.post(
        "/auth/register",
        json={"email": f"{label}-{uuid.uuid4()}@example.com", "password": PASSWORD},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['token']['access_token']}"}


def create_account(headers, name: str, account_type: str):
    response = client.post(
        "/accounts",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"name": name, "type": account_type, "currency": "PKR"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def record_entry(headers, kind: str, first, first_amount: str, second, second_amount: str):
    response = client.post(
        "/journal-entries",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "kind": kind,
            "occurred_at": "2026-09-29T12:00:00+05:00",
            "lines": [
                {"account_id": first["id"], "amount": first_amount},
                {"account_id": second["id"], "amount": second_amount},
            ],
        },
    )
    assert response.status_code == 201, response.text


def update_profile(headers, expenses: str, months: int):
    return client.put(
        "/financial-profile",
        headers=headers,
        json={"monthly_essential_expenses": expenses, "reserve_months": months},
    )


def test_empty_ledger_and_default_profile_are_zero_and_book_labeled():
    headers = authenticated_user("empty-dashboard")
    profile = client.get("/financial-profile", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["monthly_essential_expenses"] == "0.00"
    assert profile.json()["reserve_months"] == 3

    response = client.get("/dashboard", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "currency": "PKR",
        "cash_balance": "0.00",
        "investment_book_value": "0.00",
        "liability_balance": "0.00",
        "net_worth_book_value": "0.00",
        "confirmed_property_value": "0.00",
        "net_worth_with_confirmed_property": "0.00",
        "property_value_basis": "user_confirmed_only",
        "monthly_essential_expenses": "0.00",
        "reserve_months": 3,
        "reserve_target": "0.00",
        "protected_emergency_cash": "0.00",
        "investable_cash": "0.00",
        "valuation_basis": "ledger_book_value",
        "market_values_available": False,
    }
    assert "investment_book_value" in body
    assert "net_worth_book_value" in body
    assert "market_value" not in body


@pytest.mark.parametrize("months", [0, 24])
def test_reserve_month_boundaries_and_zero_expenses(months):
    headers = authenticated_user(f"boundary-{months}")
    response = update_profile(headers, "0.00", months)
    assert response.status_code == 200
    assert response.json()["reserve_months"] == months


@pytest.mark.parametrize(
    ("expenses", "months"),
    [("-0.01", 3), ("1.001", 3), ("100.00", -1), ("100.00", 25)],
)
def test_invalid_profile_values_are_rejected(expenses, months):
    headers = authenticated_user(f"invalid-{months}")
    response = update_profile(headers, expenses, months)
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("cash_amount", "expenses", "months", "target", "protected", "investable"),
    [
        ("1000.00", "500.00", 3, "1500.00", "1000.00", "0.00"),
        ("1000.00", "100.00", 3, "300.00", "300.00", "700.00"),
        ("1000.00", "0.00", 24, "0.00", "0.00", "1000.00"),
    ],
)
def test_reserve_arithmetic_cash_below_and_above_target(
    cash_amount, expenses, months, target, protected, investable
):
    headers = authenticated_user(f"reserve-{expenses}-{months}")
    cash = create_account(headers, "Cash", "cash")
    equity = create_account(headers, "Equity", "equity")
    record_entry(headers, "opening", cash, cash_amount, equity, f"-{cash_amount}")
    assert update_profile(headers, expenses, months).status_code == 200

    dashboard = client.get("/dashboard", headers=headers).json()
    assert dashboard["reserve_target"] == target
    assert dashboard["protected_emergency_cash"] == protected
    assert dashboard["investable_cash"] == investable


def test_book_value_net_worth_liabilities_and_supported_obligations():
    headers = authenticated_user("liabilities")
    cash = create_account(headers, "Cash", "cash")
    investment = create_account(headers, "Investment", "investment")
    liability = create_account(headers, "Loan", "liability")
    equity = create_account(headers, "Equity", "equity")
    record_entry(headers, "opening", cash, "2000.00", equity, "-2000.00")
    record_entry(headers, "opening", investment, "500.00", equity, "-500.00")
    record_entry(headers, "opening", liability, "-400.00", equity, "400.00")
    assert update_profile(headers, "100.00", 3).status_code == 200

    body = client.get("/dashboard", headers=headers).json()
    assert body["cash_balance"] == "2000.00"
    assert body["investment_book_value"] == "500.00"
    assert body["liability_balance"] == "400.00"
    assert body["net_worth_book_value"] == "2100.00"
    assert body["reserve_target"] == "300.00"
    assert body["investable_cash"] == "1300.00"


def test_dashboard_and_profile_are_isolated_by_user():
    first = authenticated_user("dashboard-first")
    second = authenticated_user("dashboard-second")
    cash = create_account(first, "Cash", "cash")
    equity = create_account(first, "Equity", "equity")
    record_entry(first, "opening", cash, "750.00", equity, "-750.00")
    assert update_profile(first, "50.00", 6).status_code == 200

    first_body = client.get("/dashboard", headers=first).json()
    second_body = client.get("/dashboard", headers=second).json()
    assert first_body["cash_balance"] == "750.00"
    assert first_body["monthly_essential_expenses"] == "50.00"
    assert second_body["cash_balance"] == "0.00"
    assert second_body["monthly_essential_expenses"] == "0.00"
    assert second_body["reserve_months"] == 3
