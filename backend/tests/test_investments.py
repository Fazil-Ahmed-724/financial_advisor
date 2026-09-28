import uuid
from copy import deepcopy

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
PASSWORD = "correct horse battery staple"


def user(label):
    response = client.post("/auth/register", json={
        "email": f"{label}-{uuid.uuid4()}@example.com", "password": PASSWORD,
    })
    return {"Authorization": f"Bearer {response.json()['token']['access_token']}"}


def account(headers, name, kind):
    response = client.post("/accounts", headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                           json={"name": name, "type": kind, "currency": "PKR"})
    assert response.status_code == 201, response.text
    return response.json()


def trade(headers, investment, cash, side, quantity, price, fees="0.00", key=None, symbol="ABC"):
    payload = {"side": side, "symbol": symbol, "trade_date": "2026-09-20",
               "quantity": quantity, "execution_price": price, "fees": fees,
               "investment_account_id": investment["id"], "cash_account_id": cash["id"],
               "external_reference": "Broker statement"}
    response = client.post("/investment-trades",
                           headers={**headers, "Idempotency-Key": key or str(uuid.uuid4())}, json=payload)
    return response, payload


def setup_portfolio(label="fifo"):
    headers = user(label)
    investment = account(headers, "Broker Book Value", "investment")
    cash = account(headers, "Settlement Cash", "cash")
    return headers, investment, cash


def test_fifo_multiple_lots_partial_sale_fees_and_dashboard_consistency():
    headers, investment, cash = setup_portfolio()
    first, _ = trade(headers, investment, cash, "BUY", "10.00000000", "100.0000", "10.00")
    second, _ = trade(headers, investment, cash, "BUY", "5", "120", "5.00")
    sale, _ = trade(headers, investment, cash, "SELL", "12", "150", "20.00")
    assert first.status_code == second.status_code == sale.status_code == 201
    assert sale.json()["fifo_cost_basis"] == "1252.00"
    assert sale.json()["net_proceeds"] == "1780.00"
    assert sale.json()["realized_gain_loss"] == "528.00"

    holding = client.get("/holdings", headers=headers).json()[0]
    assert holding["quantity"] == "3.00000000"
    assert holding["remaining_book_cost"] == "363.00"
    assert holding["realized_gain_loss"] == "528.00"
    assert len(holding["lots"]) == 1
    dashboard = client.get("/dashboard", headers=headers).json()
    assert dashboard["investment_book_value"] == "363.00"
    assert dashboard["cash_balance"] == "165.00"


def test_realized_loss_and_purchase_and_sale_fee_rules():
    headers, investment, cash = setup_portfolio("loss")
    trade(headers, investment, cash, "BUY", "2", "100", "10.00")
    sale, _ = trade(headers, investment, cash, "SELL", "2", "80", "5.00")
    assert sale.status_code == 201
    assert sale.json()["fifo_cost_basis"] == "210.00"
    assert sale.json()["net_proceeds"] == "155.00"
    assert sale.json()["realized_gain_loss"] == "-55.00"
    assert client.get("/holdings", headers=headers).json() == []


def test_insufficient_sale_rolls_back_and_invalid_precision():
    headers, investment, cash = setup_portfolio("rollback")
    trade(headers, investment, cash, "BUY", "1", "100", "1.00")
    before_trades = deepcopy(client.get("/investment-trades", headers=headers).json())
    before_balances = deepcopy(client.get("/accounts/balances", headers=headers).json())
    failed, _ = trade(headers, investment, cash, "SELL", "2", "120", "1.00")
    assert failed.status_code == 422
    assert client.get("/investment-trades", headers=headers).json() == before_trades
    assert client.get("/accounts/balances", headers=headers).json() == before_balances
    bad, _ = trade(headers, investment, cash, "BUY", "1.000000001", "1.00001", "0.001")
    assert bad.status_code == 422


def test_trade_ownership_idempotent_replay_and_conflict():
    owner, investment, cash = setup_portfolio("owner")
    attacker = user("attacker")
    attacker_cash = account(attacker, "Other Cash", "cash")
    denied, _ = trade(attacker, investment, attacker_cash, "BUY", "1", "100")
    assert denied.status_code == 404
    key = str(uuid.uuid4())
    first, payload = trade(owner, investment, cash, "BUY", "1", "100", key=key)
    repeated = client.post("/investment-trades", headers={**owner, "Idempotency-Key": key}, json=payload)
    assert first.status_code == repeated.status_code == 201, first.text
    assert first.json() == repeated.json()
    payload["quantity"] = "2"
    conflict = client.post("/investment-trades", headers={**owner, "Idempotency-Key": key}, json=payload)
    assert conflict.status_code == 409
    assert len(client.get("/investment-trades", headers=owner).json()) == 1


def test_hypothetical_analysis_does_not_mutate_and_tax_unconfigured_or_configured():
    headers, investment, cash = setup_portfolio("analysis")
    trade(headers, investment, cash, "BUY", "5", "100", "5.00")
    holdings_before = deepcopy(client.get("/holdings", headers=headers).json())
    balances_before = deepcopy(client.get("/accounts/balances", headers=headers).json())
    base = {"investment_account_id": investment["id"], "symbol": "abc", "quantity": "2",
            "hypothetical_price": "80", "estimated_fees": "10.00",
            "calculation_date": "2026-09-25"}
    loss = client.post("/sale-analyses", headers={**headers, "Idempotency-Key": str(uuid.uuid4())}, json=base)
    assert loss.status_code == 201, loss.text
    assert loss.json()["tax_status"] == "not_configured"
    assert loss.json()["estimated_tax"] is None
    assert loss.json()["net_profit_loss"] == "-52.00"
    assert loss.json()["order_placed"] is False
    assert client.get("/holdings", headers=headers).json() == holdings_before
    assert client.get("/accounts/balances", headers=headers).json() == balances_before

    rule = client.post("/tax-rules", headers={**headers, "Idempotency-Key": str(uuid.uuid4())}, json={
        "effective_from": "2026-01-01", "gain_tax_rate": "10.0000",
        "source_note": "User-configured verified rule", "loss_treatment_note": "Review loss carry-forward eligibility",
    })
    assert rule.status_code == 201
    gain_payload = {**base, "hypothetical_price": "200"}
    gain = client.post("/sale-analyses", headers={**headers, "Idempotency-Key": str(uuid.uuid4())}, json=gain_payload)
    assert gain.json()["gross_proceeds"] == "400.00"
    assert gain.json()["fifo_cost_basis"] == "202.00"
    assert gain.json()["gross_profit_loss"] == "198.00"
    assert gain.json()["estimated_tax"] == "18.80"
    assert gain.json()["net_proceeds"] == "371.20"
    assert gain.json()["net_profit_loss"] == "169.20"

    configured_loss = client.post("/sale-analyses", headers={**headers, "Idempotency-Key": str(uuid.uuid4())}, json=base)
    assert configured_loss.json()["estimated_tax"] == "0.00"
    assert configured_loss.json()["tax_status"] == "configured_no_automatic_loss_credit"
    assert configured_loss.json()["assumptions"]["potential_loss_treatment"] == "Review loss carry-forward eligibility"


def test_no_broker_order_execution_routes_exist_and_reads_are_isolated():
    first, investment, cash = setup_portfolio("routes")
    second = user("isolated")
    trade(first, investment, cash, "BUY", "1", "100")
    assert client.get("/investment-trades", headers=second).json() == []
    assert client.get("/holdings", headers=second).json() == []
    paths = app.openapi()["paths"]
    assert not any("order" in path.lower() or "broker" in path.lower() for path in paths)
