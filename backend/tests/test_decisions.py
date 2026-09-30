import uuid
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
PASSWORD = "correct horse battery staple"


def user(label):
    r = client.post("/auth/register", json={"email": f"{label}-{uuid.uuid4()}@example.com", "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['token']['access_token']}"}


def account(h, name, kind):
    r = client.post("/accounts", headers={**h, "Idempotency-Key": str(uuid.uuid4())}, json={"name": name, "type": kind})
    assert r.status_code == 201
    return r.json()


def trade(h, inv, cash, side, qty, price, fees="0.00"):
    r = client.post("/investment-trades", headers={**h, "Idempotency-Key": str(uuid.uuid4())}, json={
        "side": side, "symbol": "ABC", "trade_date": "2026-09-20", "quantity": qty,
        "execution_price": price, "fees": fees, "investment_account_id": inv["id"], "cash_account_id": cash["id"]})
    assert r.status_code == 201, r.text
    return r.json()


def decision_payload(**extra):
    return {"decision_date": "2026-09-19", "instrument": "ABC", "action_considered": "BUY",
            "rationale": "Durable earnings thesis", "goal": "Long-term growth",
            "expected_holding_period": "Three years", "risk_factors": "Concentration and execution",
            "expected_outcome": "Earnings growth", "confidence": "70.00",
            "planned_review_date": "2026-12-31", "exit_conditions": "Thesis invalidated", **extra}


def create_decision(h, payload):
    return client.post("/decisions", headers={**h, "Idempotency-Key": str(uuid.uuid4())}, json=payload)


def portfolio(label):
    h = user(label); return h, account(h, "Investments", "investment"), account(h, "Cash", "cash")


def test_decision_links_are_owned_and_original_snapshot_is_preserved():
    owner, inv, cash = portfolio("decision-owner")
    other = user("decision-other")
    buy = trade(owner, inv, cash, "BUY", "1", "100", "1")
    denied = create_decision(other, decision_payload(trade_id=buy["id"]))
    assert denied.status_code == 404
    created = create_decision(owner, decision_payload(trade_id=buy["id"]))
    assert created.status_code == 201, created.text
    decision_id = created.json()["id"]
    assert created.json()["rationale"] == "Durable earnings thesis"
    assert client.patch(f"/decisions/{decision_id}", headers=owner, json={"rationale": "Changed"}).status_code == 405
    review = client.post(f"/decisions/{decision_id}/reviews",
        headers={**owner, "Idempotency-Key": str(uuid.uuid4())}, json={
            "what_happened": "Price fell", "assumptions_held": "Revenue held",
            "assumptions_failed": "Margins fell", "lessons_learned": "Track margins",
            "thesis_written_before_trade": True, "risks_considered": True,
            "concentration_considered": False, "within_recorded_limits": True,
            "followed_original_plan": False})
    assert review.status_code == 201
    assert review.json()["process_snapshot"]["positive_count"] == 3
    assert review.json()["process_snapshot"]["financial_outcome_used_in_score"] is False
    detail = client.get(f"/decisions/{decision_id}", headers=owner).json()
    assert detail["rationale"] == "Durable earnings thesis"
    assert detail["process_and_outcome_are_separate"] is True
    assert len(detail["reviews"]) == 1
    assert client.get("/decisions", headers=other).json() == []


def test_open_outcome_has_no_invented_market_value_or_zero_tax():
    h, inv, cash = portfolio("open")
    buy = trade(h, inv, cash, "BUY", "2", "100", "2")
    result = create_decision(h, decision_payload(trade_id=buy["id"])).json()["outcome"]
    assert result["state"] == "unrealized_open"
    assert result["market_value_available"] is False
    assert result["unrealized_result"] is None
    assert result["estimated_tax"] is None
    assert result["tax_status"] == "unavailable_open_position"


def test_closed_fifo_outcome_fee_and_tax_breakdown_and_rule_version():
    h, inv, cash = portfolio("closed")
    buy = trade(h, inv, cash, "BUY", "2", "100", "10")
    rule = client.post("/tax-rules", headers={**h, "Idempotency-Key": str(uuid.uuid4())}, json={
        "effective_from": "2026-01-01", "gain_tax_rate": "10", "source_note": "Configured assumption"})
    assert rule.status_code == 201
    trade(h, inv, cash, "SELL", "2", "150", "5")
    outcome = create_decision(h, decision_payload(trade_id=buy["id"])).json()["outcome"]
    assert outcome["state"] == "realized_closed"
    assert outcome["fees"] == "15.00"
    assert outcome["realized_result_before_tax"] == "85.00"
    assert outcome["gross_result_before_fees_and_tax"] == "100.00"
    assert outcome["estimated_tax"] == "8.50"
    assert outcome["net_result"] == "76.50"
    assert outcome["tax_rule_versions"][0]["id"] == rule.json()["id"]
    assert outcome["official_tax_determination"] is False


def test_closed_tax_unconfigured_is_unavailable_not_zero():
    h, inv, cash = portfolio("tax-missing")
    buy = trade(h, inv, cash, "BUY", "1", "100")
    trade(h, inv, cash, "SELL", "1", "120")
    outcome = create_decision(h, decision_payload(trade_id=buy["id"])).json()["outcome"]
    assert outcome["estimated_tax"] is None
    assert outcome["net_result"] is None
    assert outcome["tax_status"] == "not_configured"


def test_audit_events_and_scoped_export_include_history_and_boundaries():
    h, inv, cash = portfolio("export")
    other = user("export-other")
    buy = trade(h, inv, cash, "BUY", "1", "100", "1")
    created = create_decision(h, decision_payload(trade_id=buy["id"])).json()
    report = client.post("/compliance-reports", headers={**h, "Idempotency-Key": str(uuid.uuid4())})
    assert report.status_code == 201, report.text
    body = report.json()
    assert len(body["trades"]) == 1 and len(body["decisions"]) == 1
    assert body["dividends"] == {"supported": False, "records": []}
    assert body["official_tax_determination"] is False
    assert body["order_execution_supported"] is False
    event_types = [x["event_type"] for x in body["audit_events"]]
    assert {"decision_created", "decision_link_created", "compliance_report_generated"} <= set(event_types)
    other_report = client.post("/compliance-reports", headers={**other, "Idempotency-Key": str(uuid.uuid4())}).json()
    assert other_report["trades"] == [] and other_report["decisions"] == []
    assert all(x["entity_id"] != created["id"] for x in other_report["audit_events"])


def test_no_execution_or_broker_routes():
    assert not any("order" in path.lower() or "broker" in path.lower() for path in app.openapi()["paths"])
