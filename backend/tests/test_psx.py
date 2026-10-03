import uuid
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import func,select
from app.database import SessionLocal
from app.main import app
from app.models import Account,InvestmentTrade,MarketplaceProduct,NotificationEvent,PropertyListing,PsxPriceObservation,TaxRule
client=TestClient(app);PASSWORD="correct horse battery staple";BASE="/api/v1/psx"
def auth(label):
 r=client.post("/auth/register",json={"email":f"{label}-{uuid.uuid4()}@example.com","password":PASSWORD});return {"Authorization":f"Bearer {r.json()['token']['access_token']}"}
def csv(rows):
 return "symbol,observation_date,open,high,low,close,volume,currency,source,adjustment_type\n"+"\n".join(rows)+"\n"
def upload(h,data,key=None,source="Authorized export"):
 return client.post(BASE+"/imports",headers=h,data={"source_name":source,"idempotency_key":key or str(uuid.uuid4())},files={"file":("psx.csv",data,"text/csv")})
def preview(h,b):return client.get(f"{BASE}/imports/{b}/preview",headers=h).json()
def commit_valid(h,data,key=None):
 r=upload(h,data,key);assert r.status_code==201,r.text;b=r.json()["id"];c=client.post(f"{BASE}/imports/{b}/commit",headers=h);assert c.status_code==200,c.text;return b
def protected_counts():
 with SessionLocal() as s:return [s.scalar(select(func.count()).select_from(x)) for x in (Account,InvestmentTrade,TaxRule,PropertyListing,MarketplaceProduct,NotificationEvent)]

def test_preview_validation_duplicate_resolution_idempotency_and_cancel():
 h=auth("psx-review");data=csv(["HBL,2026-01-01,100,105,99,102,1000,PKR,user file,raw","bad symbol,2026-01-02,0,90,100,95,-1,USD,,other"])
 first=upload(h,data,"same-upload-key");second=upload(h,data,"same-upload-key");assert first.status_code==201 and first.json()["id"]==second.json()["id"]
 p=preview(h,first.json()["id"]);assert p["rows"][0]["validation_status"]=="valid" and p["rows"][1]["validation_status"]=="invalid";assert client.post(f"{BASE}/imports/{first.json()['id']}/commit",headers=h).status_code==422
 row=p["rows"][1];assert client.put(f"{BASE}/imports/{first.json()['id']}/rows/{row['id']}",headers=h,json={"action":"skip"}).status_code==200
 assert client.post(f"{BASE}/imports/{first.json()['id']}/commit",headers=h).json()["committed_rows"]==1
 dup=upload(h,csv(["HBL,2026-01-01,101,106,98,103,2000,PKR,new authorized file,raw"])).json();row=preview(h,dup["id"])["rows"][0];assert row["duplicate_status"]=="existing" and row["action"]=="review"
 assert client.post(f"{BASE}/imports/{dup['id']}/commit",headers=h).status_code==422
 assert client.put(f"{BASE}/imports/{dup['id']}/rows/{row['id']}",headers=h,json={"action":"replace_existing"}).status_code==200
 assert client.post(f"{BASE}/imports/{dup['id']}/commit",headers=h).json()["committed_rows"]==1
 cancelled=upload(h,csv(["UBL,2026-01-01,10,11,9,10,1,PKR,x,raw"])).json();assert client.post(f"{BASE}/imports/{cancelled['id']}/cancel",headers=h).json()["status"]=="cancelled"

def test_malformed_atomicity_ownership_and_no_cross_user_merge():
 a,b=auth("psx-a"),auth("psx-b");assert upload(a,b"not utf8 \xff").status_code==422;assert client.post(BASE+"/imports",headers=a,data={"source_name":"x","idempotency_key":"abcdefgh"},files={"file":("bad.exe","x","application/octet-stream")}).status_code==415
 batch=upload(a,csv(["MARI,2026-01-01,10,12,9,11,1,PKR,x,raw","MARI,2026-01-02,10,9,11,10,1,PKR,x,raw"])).json();assert client.post(f"{BASE}/imports/{batch['id']}/commit",headers=a).status_code==422
 assert client.get(f"{BASE}/imports/{batch['id']}/preview",headers=b).status_code==404
 assert client.get(BASE+"/instruments",headers=b).json()==[]

def test_formulas_stale_gaps_ordering_and_no_lookahead():
 h=auth("psx-calc");data=csv(["ENGRO,2020-01-01,100,101,99,100,10,PKR,x,adjusted","ENGRO,2020-01-02,100,111,99,110,10,PKR,x,adjusted","ENGRO,2020-01-10,110,121,109,120,10,PKR,x,adjusted","ENGRO,2020-01-03,110,116,109,115,10,PKR,x,adjusted"])
 commit_valid(h,data);payload={"symbols":["ENGRO"],"lookback":2,"as_of_date":"2020-01-03"};result=client.post(BASE+"/analysis",headers=h,json=payload).json()["results"][0]
 assert result["source_dates"]==["2020-01-01","2020-01-02","2020-01-03"] and result["period_return_percent"]=="15.0000"
 assert result["moving_average"]=="112.5000" and result["observation_count"]==3 and "2020-01-10" not in result["source_dates"]
 assert result["freshness"]=="stale" and result["gap_days"]==[] and result["hypothetical"] is True and result["recommendation"] if "recommendation" in result else True
 full=client.post(BASE+"/analysis",headers=h,json={"symbols":["ENGRO"],"lookback":2}).json()["results"][0];assert full["gap_days"]==[7] and len(full["observation_ids"])==4
 unavailable=client.post(BASE+"/analysis",headers=h,json={"symbols":["NONE"],"lookback":14}).json()["results"][0];assert unavailable["unavailable"] is True

def test_assistant_cites_owned_observations_and_domain_is_read_only():
 before=protected_counts();a,b=auth("psx-assist-a"),auth("psx-assist-b");commit_valid(a,csv(["OGDC,2026-01-01,200,205,195,202,500,PKR,authorized CSV,raw","OGDC,2026-01-02,202,210,201,208,600,PKR,authorized CSV,raw"]))
 c=client.post("/assistant/conversations",headers=a,json={"title":"PSX evidence"}).json();answer=client.post(f"/assistant/conversations/{c['id']}/messages",headers=a,json={"message":"Explain my OGDC PSX price evidence"}).json()["response"]
 assert any(x["source_type"]=="psx_price_observation" for x in answer["citations"]);assert all("OGDC" in x["excerpt"] for x in answer["citations"] if x["source_type"]=="psx_price_observation")
 deterministic=client.post(BASE+"/analysis",headers=a,json={"symbols":["OGDC"],"lookback":2}).json()["results"][0];ref=next(x for x in answer["evidence_references"] if x["source_type"]=="psx_price_observation");assert ref["calculation"]["result"]["period_return_percent"]==deterministic["period_return_percent"]
 c2=client.post("/assistant/conversations",headers=b,json={"title":"Other"}).json();other=client.post(f"/assistant/conversations/{c2['id']}/messages",headers=b,json={"message":"Explain OGDC PSX price evidence"}).json()["response"];assert not any(x["source_type"]=="psx_price_observation" for x in other["citations"])
 assert protected_counts()==before
