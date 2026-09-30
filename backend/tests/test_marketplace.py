import uuid
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.database import SessionLocal
from app.main import app
from app.models import OpportunityAnalysis

client=TestClient(app);PASSWORD="correct horse battery staple"
def auth(label):
    r=client.post("/auth/register",json={"email":f"{label}-{uuid.uuid4()}@example.com","password":PASSWORD});assert r.status_code==201;return {"Authorization":f"Bearer {r.json()['token']['access_token']}"}
def listing(headers,key=None,**updates):
    body={"source_method":"user_entered","source_platform":"Temu","product_name":"Reusable bottle","sku":"RB-1","source_listing_id":str(uuid.uuid4()),"canonical_url":f"https://example.test/item/{uuid.uuid4()}?track=1","observed_at":datetime.now(timezone.utc).isoformat(),"currency":"USD","source_price":"10.0000","attributes":{"color":"blue"},"evidence":{"note":"manually observed"},"expected_karachi_selling_price":"5000.00","local_sales_channel":"Local marketplace"};body.update(updates)
    return client.post("/marketplace/listings",headers={**headers,"Idempotency-Key":key or str(uuid.uuid4())},json=body)
def analyze(headers,listing_id,key=None,**updates):
    body={"listing_id":listing_id,"quantity":"2","expected_selling_price_pkr":"5000","exchange_rate_to_pkr":"280","exchange_rate_observed_at":datetime.now(timezone.utc).isoformat(),"exchange_rate_source":"User-entered dated bank quote","shipping_per_unit":"200","customs_per_unit":"100","conversion_fee_per_unit":"50","marketplace_fee_per_unit":"300","payment_fee_per_unit":"100","packaging_per_unit":"50","delivery_per_unit":"150","other_costs_per_unit":"50","returns_allowance_per_unit":"100","damage_allowance_per_unit":"50","unsold_allowance_per_unit":"100"};body.update(updates)
    return client.post("/opportunities/analyze/marketplace_resale/margin",headers={**headers,"Idempotency-Key":key or str(uuid.uuid4())},json=body)

def test_platform_adapters_provenance_staleness_dedup_idempotency_and_isolation():
    first,second=auth("market-first"),auth("market-second")
    assert listing(first,source_platform="Amazon").status_code==422
    old=(datetime.now(timezone.utc)-timedelta(days=61)).isoformat();key=str(uuid.uuid4());source_id=str(uuid.uuid4());url=f"https://example.test/{uuid.uuid4()}"
    created=listing(first,key=key,source_platform="Daraz",source_listing_id=source_id,canonical_url=url,observed_at=old)
    assert created.status_code==201,created.text;body=created.json();assert body["stale"] is True;assert body["source_data_status"]=="user_or_authorized_unverified";assert body["purchase_executed"] is False
    repeat=listing(first,key=key,source_platform="Daraz",source_listing_id=source_id,canonical_url=url,observed_at=old);assert repeat.json()==body
    assert listing(first,source_platform="Daraz",source_listing_id=source_id).status_code==409
    assert client.get("/marketplace/listings",headers=second).json()==[]

def test_decimal_cost_margin_roi_and_missing_exchange_rate():
    headers=auth("market-math");item=listing(headers).json();result=analyze(headers,item["id"])
    assert result.status_code==201,result.text;m=result.json()["calculated_metrics"]
    assert m["status"]=="available";assert m["landed_cost_per_unit"]=="3150.0000";assert m["break_even_selling_price_per_unit"]=="4050.0000";assert m["gross_margin_per_unit"]=="1850.0000";assert m["net_margin_per_unit"]=="950.0000";assert m["net_margin_percent"]=="19.0000";assert m["inventory_cash_roi_percent"]=="23.4568"
    assert "formula_landed" in result.json()["assumptions"];assert result.json()["recommendation"] is None
    missing=analyze(headers,item["id"],exchange_rate_to_pkr=None,exchange_rate_observed_at=None,exchange_rate_source=None)
    mm=missing.json()["calculated_metrics"];assert mm["status"]=="unavailable_missing_inputs";assert "dated_exchange_rate" in mm["missing_inputs"];assert mm["landed_cost_per_unit"] is None

def test_missing_costs_are_unavailable_and_listing_ownership_is_enforced():
    first,second=auth("market-owner-a"),auth("market-owner-b");item=listing(first,currency="PKR",source_price="1000").json()
    missing=analyze(first,item["id"],exchange_rate_to_pkr=None,exchange_rate_observed_at=None,exchange_rate_source=None,shipping_per_unit=None)
    assert missing.json()["calculated_metrics"]["status"]=="unavailable_missing_inputs";assert "shipping_per_unit" in missing.json()["calculated_metrics"]["missing_inputs"]
    assert analyze(second,item["id"]).status_code==404

def test_outcome_preserves_estimate_snapshot_and_reports_forecast_error_without_success_label():
    headers=auth("market-outcome");item=listing(headers).json();estimate=analyze(headers,item["id"]).json()
    with SessionLocal() as session:before=session.scalar(select(OpportunityAnalysis.input_snapshot).where(OpportunityAnalysis.id==uuid.UUID(estimate["id"])))
    payload={"analysis_id":estimate["id"],"recorded_at":datetime.now(timezone.utc).isoformat(),"purchased_quantity":"2","actual_purchase_cost":"6000","actual_other_costs":"1000","sold_quantity":"2","actual_sales_revenue":"9000","actual_sales_fees":"500","returned_quantity":"0","return_costs":"100","remaining_quantity":"0","notes":"Transactions completed outside app"}
    key=str(uuid.uuid4());created=client.post("/marketplace/outcomes",headers={**headers,"Idempotency-Key":key},json=payload);assert created.status_code==201,created.text;body=created.json();assert body["actual_net_result"]=="1400.00";assert body["forecast_error"]=="-500.00";assert body["success_label"]=="not_assigned";assert body["external_transactions_only"] is True
    assert client.post("/marketplace/outcomes",headers={**headers,"Idempotency-Key":key},json=payload).json()==body
    with SessionLocal() as session:after=session.scalar(select(OpportunityAnalysis.input_snapshot).where(OpportunityAnalysis.id==uuid.UUID(estimate["id"])))
    assert before==after

def test_marketplace_inventory_is_separate_from_ledger_and_only_confirmed_value_affects_separate_total():
    headers=auth("market-dashboard");before=client.get("/dashboard",headers=headers).json();assert listing(headers).status_code==201;unconfirmed=client.get("/dashboard",headers=headers).json()
    for field in ("cash_balance","investment_book_value","net_worth_book_value","investable_cash","confirmed_resale_inventory_value","net_worth_with_confirmed_assets"):assert unconfirmed[field]==before[field]
    confirmed=listing(headers,confirmed_inventory_value="25000",inventory_valued_at=datetime.now(timezone.utc).isoformat());assert confirmed.status_code==201
    after=client.get("/dashboard",headers=headers).json();assert after["cash_balance"]=="0.00";assert after["investable_cash"]=="0.00";assert after["net_worth_book_value"]=="0.00";assert after["confirmed_resale_inventory_value"]=="25000.00";assert after["net_worth_with_confirmed_assets"]=="25000.00"

def test_no_automation_or_unauthorized_collection_routes():
    paths=app.openapi()["paths"]
    assert not any(any(term in path for term in ("scrape","crawl","purchase","advertis","fulfil","broker","execute-order","create-listing")) for path in paths)
