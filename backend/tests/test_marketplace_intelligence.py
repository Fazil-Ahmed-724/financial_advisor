import uuid
from datetime import datetime,timedelta,timezone
from fastapi.testclient import TestClient
from app.main import app
client=TestClient(app);PASSWORD="correct horse battery staple";BASE="/api/v1/marketplace"
def auth(label):
    r=client.post("/auth/register",json={"email":f"{label}-{uuid.uuid4()}@example.com","password":PASSWORD});return {"Authorization":f"Bearer {r.json()['token']['access_token']}"}
def product(h,name="USB-C Cable",**kw):
    body={"normalized_name":name,"brand":"Acme","model":"C-100","category":"Accessories","canonical_attributes":{"length":"1m"}};body.update(kw);r=client.post(f"{BASE}/products",headers=h,json=body);assert r.status_code==201,r.text;return r.json()
def observe(h,p,price="1000",when=None,**kw):
    body={"marketplace":"Daraz","source_type":"user_entered","source_reference":str(uuid.uuid4()),"observed_name":"Acme USB C Cable 1 m","observed_price":price,"currency_code":"PKR","observed_at":when or datetime.now(timezone.utc).isoformat(),"raw_attributes":{},"evidence":{"note":"manual observation"}};body.update(kw);return client.post(f"{BASE}/products/{p['id']}/observations",headers=h,json=body)
def source(h,p,**kw):
    body={"source_type":"user_entered","supplier_name":"Karachi supplier","source_channel":"local_wholesaler","source_reference":"visit notes","unit_cost":"600","currency_code":"PKR","minimum_order_quantity":"10","local_transport_cost":"20","packaging_cost":"10","lead_time_days":3,"stock_available":True,"observed_at":datetime.now(timezone.utc).isoformat(),"evidence":{"receipt":"user note"}};body.update(kw);return client.post(f"{BASE}/products/{p['id']}/sourcing",headers=h,json=body)
def competition(h,p,**kw):
    body={"source_type":"user_entered","source_reference":"manual comparison","comparable_listing_count":10,"seller_count":4,"lowest_price":"900","median_price":"1100","highest_price":"1400","price_dispersion":"0.20","observed_at":datetime.now(timezone.utc).isoformat(),"evidence":{"listing_ids":["a","b"]}};body.update(kw);return client.post(f"{BASE}/products/{p['id']}/competition",headers=h,json=body)

def test_seeded_karachi_market_and_authentication():
    assert client.get(f"{BASE}/market").status_code==401;body=client.get(f"{BASE}/market",headers=auth("market-seed")).json();assert body=={"id":"a7b8a341-59a2-4d8d-9f05-31ea998ef001","country_code":"PK","country_name":"Pakistan","region_name":"Sindh","city_name":"Karachi","currency_code":"PKR","timezone":"Asia/Karachi","is_active":True}
def test_deterministic_product_matching_keeps_records_separate():
    h=auth("matching");first=product(h);second=product(h,"  acme USB-C cable, 1 m  ",brand="ACME",model="C 100");assert first["match_status"]=="unmatched";assert second["match_status"] in ("exact_match","probable_match");assert first["id"]!=second["id"];assert first["id"] in second["match_candidates"]
def test_append_only_price_history_staleness_and_change_percentage():
    h=auth("history");p=product(h);old=(datetime.now(timezone.utc)-timedelta(days=61)).isoformat();assert observe(h,p,"1000",old).status_code==201;assert observe(h,p,"1200").status_code==201;rows=client.get(f"{BASE}/products/{p['id']}/observations",headers=h).json();assert len(rows)==2;assert rows[0]["price_change_percent"]=="20.00";assert rows[1]["stale"] is True
def test_sourcing_competition_validation_and_user_isolation():
    a,b=auth("intel-a"),auth("intel-b");p=product(a);assert source(a,p).status_code==201;assert competition(a,p).status_code==201;assert client.get(f"{BASE}/products/{p['id']}",headers=b).status_code==404;assert source(a,p,currency_code="USD").status_code==422;assert competition(a,p,lowest_price="1500",median_price="1000",highest_price="900").status_code==422
def part9_margin(h):
    listing={"source_method":"user_entered","source_platform":"Daraz","product_name":"USB Cable","observed_at":datetime.now(timezone.utc).isoformat(),"currency":"PKR","source_price":"600","attributes":{},"evidence":{"note":"manual"},"expected_karachi_selling_price":"1200","local_sales_channel":"Karachi local"};r=client.post("/marketplace/listings",headers={**h,"Idempotency-Key":str(uuid.uuid4())},json=listing);assert r.status_code==201,r.text
    costs={x:"0" for x in ("shipping_per_unit","customs_per_unit","conversion_fee_per_unit","marketplace_fee_per_unit","payment_fee_per_unit","packaging_per_unit","delivery_per_unit","other_costs_per_unit","returns_allowance_per_unit","damage_allowance_per_unit","unsold_allowance_per_unit")};body={"listing_id":r.json()["id"],"quantity":"10","expected_selling_price_pkr":"1200",**costs};a=client.post("/opportunities/analyze/marketplace_resale/margin",headers={**h,"Idempotency-Key":str(uuid.uuid4())},json=body);assert a.status_code==201,a.text;return a.json()["id"]
def test_deterministic_explainable_ranking_snapshot_and_missing_confidence():
    h=auth("ranking");p=product(h);missing=client.post(f"{BASE}/products/{p['id']}/rank",headers=h,json={}).json();assert missing["overall_research_score"] is None;assert len(missing["explanation"]["missing_inputs"])==5
    observe(h,p,sold_count=80,review_count=20,rating_count=50,rating="4.5");source(h,p);competition(h,p);analysis_id=part9_margin(h);one=client.post(f"{BASE}/products/{p['id']}/rank",headers=h,json={"marketplace_analysis_id":analysis_id});two=client.post(f"{BASE}/products/{p['id']}/rank",headers=h,json={"marketplace_analysis_id":analysis_id});assert one.status_code==two.status_code==201
    a,b=one.json(),two.json();assert a["label"]=="Research Score";assert a["overall_research_score"]==b["overall_research_score"];assert all(a[x] is not None for x in ("demand_score","margin_score","competition_score","sourcing_score","logistics_score"));assert a["explanation"]["components"]["margin"]["reason"];assert len(client.get(f"{BASE}/rankings",headers=h).json())==3
def test_filters_sort_comparison_and_watchlist_ownership():
    a,b=auth("filters-a"),auth("filters-b");p1=product(a,"Cable A");p2=product(a,"Cable B");observe(a,p1,"1000",sold_count=10);observe(a,p2,"2000");source(a,p1);client.post(f"{BASE}/products/{p1['id']}/rank",headers=a,json={});client.post(f"{BASE}/products/{p2['id']}/rank",headers=a,json={})
    rows=client.get(f"{BASE}/products?marketplace=Daraz&price_min=900&price_max=1500&demand_data_available=true&sort_by=demand",headers=a).json();assert len(rows)==1;assert rows[0]["product"]["id"]==p1["id"]
    compare=client.post(f"{BASE}/compare",headers=a,json={"product_ids":[p1["id"],p2["id"]]});assert compare.status_code==200;assert len(compare.json()["products"])==2
    added=client.post(f"{BASE}/watchlist",headers=a,json={"product_id":p1["id"],"notes":"Review supplier"});assert added.status_code==201;wid=added.json()["id"];assert client.get(f"{BASE}/watchlist",headers=b).json()==[];assert client.put(f"{BASE}/watchlist/{wid}",headers=b,json={"notes":"x","is_active":True}).status_code==404;assert client.put(f"{BASE}/watchlist/{wid}",headers=a,json={"notes":"Updated","is_active":True}).json()["notes"]=="Updated";assert client.delete(f"{BASE}/watchlist/{wid}",headers=a).status_code==204
def test_no_collection_or_execution_endpoints():
    paths=app.openapi()["paths"];assert not any(any(x in p for x in ("scrape","crawl","login-automation","auto-purchase","fulfil","execute-order","advertis")) for p in paths)
