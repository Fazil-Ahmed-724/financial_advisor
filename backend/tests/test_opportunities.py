import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
PASSWORD = "correct horse battery staple"


def auth(label: str):
    response = client.post("/auth/register", json={"email": f"{label}-{uuid.uuid4()}@example.com", "password": PASSWORD})
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['token']['access_token']}"}


def listing(headers, *, key=None, **overrides):
    payload = {
        "city": "Karachi", "source_type": "user_entered", "source_name": "User research",
        "canonical_url": f"https://www.zameen.com/property/{uuid.uuid4()}?tracking=ignored",
        "observed_at": datetime.now(timezone.utc).isoformat(), "purpose": "sale",
        "property_type": "Apartment", "area_name": "Clifton", "area_amount": "1000",
        "area_unit": "sq_ft", "asking_amount": "10000000.00", "attributes": {"beds": 2},
    }
    payload.update(overrides)
    return client.post("/opportunities/karachi-real-estate/listings", headers={**headers, "Idempotency-Key": key or str(uuid.uuid4())}, json=payload)


def analyze(headers, kind, payload, key=None, domain="karachi_real_estate"):
    return client.post(f"/opportunities/analyze/{domain}/{kind}", headers={**headers, "Idempotency-Key": key or str(uuid.uuid4())}, json=payload)


def test_registry_unknown_domain_and_no_execution_or_scraping_routes():
    headers = auth("registry")
    domains = client.get("/opportunities/domains", headers=headers)
    assert domains.status_code == 200
    assert domains.json()["registered_domains"] == ["karachi_real_estate", "marketplace_resale"]
    assert analyze(headers, "comparables", {}, domain="unknown").status_code == 404
    paths = app.openapi()["paths"]
    assert not any(any(term in path for term in ("scrape", "crawl", "offer", "order", "broker")) for path in paths)


def test_listing_validation_provenance_staleness_dedup_and_user_isolation():
    first, second = auth("listing-first"), auth("listing-second")
    assert listing(first, city="Lahore").status_code == 422
    assert listing(first, area_unit="marla").status_code == 422
    assert listing(first, observed_at="2026-01-01T00:00:00").status_code == 422

    old = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat()
    url = "https://WWW.ZAMEEN.COM/property/example/?utm_source=test"
    created = listing(first, canonical_url=url, observed_at=old)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["canonical_url"] == "https://www.zameen.com/property/example"
    assert body["information_quality"] == "user_entered"
    assert body["asking_price_status"] == "unverified_asking_price"
    assert body["confirmed_transaction_price"] is False
    assert body["stale"] is True
    assert client.get("/opportunities/karachi-real-estate/listings", headers=second).json() == []

    duplicate = listing(first, canonical_url="https://www.zameen.com/property/example?different=1")
    assert duplicate.status_code == 409
    assert len(client.get("/opportunities/karachi-real-estate/listings", headers=first).json()) == 1


def test_listing_idempotency_and_conflicting_payload():
    headers, key = auth("listing-idempotency"), str(uuid.uuid4())
    url = f"https://example.test/{uuid.uuid4()}"
    observed_at = datetime.now(timezone.utc).isoformat()
    first = listing(headers, key=key, canonical_url=url, observed_at=observed_at)
    repeat = listing(headers, key=key, canonical_url=url, observed_at=observed_at)
    assert first.status_code == repeat.status_code == 201
    assert first.json() == repeat.json()
    assert listing(headers, key=key, canonical_url=f"{url}-changed").status_code == 409


def test_comparables_filter_units_median_and_minimum_sample():
    headers = auth("comparables")
    for area, unit, price in [("1000", "sq_ft", "9000000"), ("111.1111", "sq_yd", "10000000"), ("4.4444", "marla_225_sq_ft", "11000000")]:
        assert listing(headers, area_amount=area, area_unit=unit, asking_amount=price).status_code == 201
    assert listing(headers, property_type="House", asking_amount="50000000").status_code == 201
    filters = {"area_name": "Clifton", "property_type": "Apartment", "purpose": "sale", "area_min": "999", "area_max": "1001", "area_unit": "sq_ft"}
    response = analyze(headers, "comparables", filters)
    assert response.status_code == 201, response.text
    metrics = response.json()["calculated_metrics"]
    assert metrics["status"] == "sufficient"
    assert metrics["record_count"] == 3
    assert metrics["minimum_asking_amount"] == "9000000.00"
    assert metrics["median_asking_amount"] == "10000000.00"
    assert metrics["maximum_asking_amount"] == "11000000.00"
    assert metrics["asking_price_status"] == "unverified_asking_price"
    assert len(response.json()["source_evidence"]["source_dates"]) == 3
    assert response.json()["recommendation"] is None

    insufficient = analyze(headers, "comparables", {**filters, "asking_min": "10500000"})
    assert insufficient.json()["calculated_metrics"]["status"] == "insufficient_comparables"
    assert insufficient.json()["calculated_metrics"]["median_asking_amount"] is None


def test_yield_decimal_math_and_missing_cost_assumptions():
    headers = auth("yield")
    gross = analyze(headers, "yield", {"purchase_price": "12000000.00", "monthly_rent": "100000.00"})
    assert gross.status_code == 201, gross.text
    metrics = gross.json()["calculated_metrics"]
    assert metrics["gross_annual_yield_percent"] == "10.0000"
    assert metrics["net_annual_yield_percent"] is None
    assert metrics["net_yield_status"] == "unavailable_missing_expense_or_tax_assumptions"

    net = analyze(headers, "yield", {"purchase_price": "12000000.00", "monthly_rent": "100000.00", "annual_expenses": {"maintenance": "120000.00", "vacancy": "60000.00"}, "annual_property_tax": "20000.00"})
    assert net.status_code == 201, net.text
    assert net.json()["calculated_metrics"]["net_annual_yield_percent"] == "8.3333"
    assert analyze(headers, "yield", {"purchase_price": "0", "monthly_rent": "100"}).status_code == 422
    assert analyze(headers, "yield", {"purchase_price": "100", "monthly_rent": "10", "annual_expenses": {"invented": "-1"}}).status_code == 422


def test_property_is_separate_from_ledger_and_only_confirmed_owned_value_is_added():
    headers = auth("property-dashboard")
    before = client.get("/dashboard", headers=headers).json()
    assert listing(headers, owned_by_user=False).status_code == 201
    after_unconfirmed = client.get("/dashboard", headers=headers).json()
    for field in ("cash_balance", "investment_book_value", "net_worth_book_value", "investable_cash", "confirmed_property_value", "net_worth_with_confirmed_property"):
        assert after_unconfirmed[field] == before[field]

    confirmed = listing(headers, owned_by_user=True, confirmed_valuation="25000000.00", valuation_confirmed_at=datetime.now(timezone.utc).isoformat())
    assert confirmed.status_code == 201, confirmed.text
    dashboard = client.get("/dashboard", headers=headers).json()
    assert dashboard["net_worth_book_value"] == "0.00"
    assert dashboard["confirmed_property_value"] == "25000000.00"
    assert dashboard["net_worth_with_confirmed_property"] == "25000000.00"
    assert dashboard["investable_cash"] == "0.00"
    assert dashboard["property_value_basis"] == "user_confirmed_only"
