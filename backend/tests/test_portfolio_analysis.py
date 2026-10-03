import uuid
from copy import deepcopy
from fastapi.testclient import TestClient
from sqlalchemy import func,select
from app.database import SessionLocal
from app.main import app
from app.models import AuditEvent,InvestmentLot,InvestmentTrade,JournalEntry,PortfolioInstrumentMapping,SaleAnalysis,TaxRule
client=TestClient(app);PASSWORD="correct horse battery staple";BASE="/api/v1/portfolio-analysis"
def auth(label):
 r=client.post("/auth/register",json={"email":f"{label}-{uuid.uuid4()}@example.com","password":PASSWORD});return {"Authorization":f"Bearer {r.json()['token']['access_token']}"}
def account(h,name,kind):
 r=client.post("/accounts",headers={**h,"Idempotency-Key":str(uuid.uuid4())},json={"name":name,"type":kind,"currency":"PKR"});assert r.status_code==201;return r.json()
def trade(h,inv,cash,side,qty,price,day,symbol="HBL",fees="0"):
 r=client.post("/investment-trades",headers={**h,"Idempotency-Key":str(uuid.uuid4())},json={"side":side,"symbol":symbol,"trade_date":day,"quantity":qty,"execution_price":price,"fees":fees,"investment_account_id":inv["id"],"cash_account_id":cash["id"],"external_reference":"statement"});assert r.status_code==201,r.text;return r.json()
def import_prices(h,rows):
 data="symbol,observation_date,open,high,low,close,volume,currency,source,adjustment_type\n"+"\n".join(rows)+"\n";r=client.post("/api/v1/psx/imports",headers=h,data={"source_name":"Authorized fixture","idempotency_key":str(uuid.uuid4())},files={"file":("prices.csv",data,"text/csv")});assert r.status_code==201,r.text;bid=r.json()["id"];c=client.post(f"/api/v1/psx/imports/{bid}/commit",headers=h);assert c.status_code==200,c.text
def setup(label="portfolio"):
 h=auth(label);inv=account(h,"PSX Broker","investment");cash=account(h,"Cash","cash");trade(h,inv,cash,"BUY","10","100","2026-09-10",fees="10");trade(h,inv,cash,"BUY","5","120","2026-09-20",fees="5")
 import_prices(h,["HBL,2026-09-15,105,111,104,110,1000,PKR,Authorized fixture,raw","HBL,2026-09-25,120,126,119,125,1000,PKR,Authorized fixture,raw","HBL,2026-09-10,99,101,98,100,1000,PKR,Authorized fixture,adjusted","HBL,2026-09-20,109,111,108,110,1000,PKR,Authorized fixture,adjusted","HBL,2026-09-25,88,91,87,90,1000,PKR,Authorized fixture,adjusted"])
 return h,inv,cash
def map_holding(h,inv):
 return client.put(BASE+"/mappings",headers=h,json={"investment_account_id":inv["id"],"holding_symbol":"HBL","psx_symbol":"HBL","confirmed":True,"confirmation_note":"Reviewed broker symbol"} )
def mutation_counts():
 with SessionLocal() as s:return {x.__tablename__:s.scalar(select(func.count()).select_from(x)) for x in (InvestmentTrade,InvestmentLot,JournalEntry,TaxRule,SaleAnalysis)}

def test_mapping_is_owned_confirmed_and_auditable():
 owner,inv,_=setup("map-owner");other,_,_=setup("map-other");created=map_holding(owner,inv);assert created.status_code==200,created.text
 assert client.get(BASE+"/mappings",headers=other).json()==[];assert client.put(BASE+"/mappings",headers=other,json={"investment_account_id":inv["id"],"holding_symbol":"HBL","psx_symbol":"HBL","confirmed":True}).status_code==404
 assert client.get(f"{BASE}/mappings/{created.json()['id']}/audit",headers=other).status_code==404;history=client.get(f"{BASE}/mappings/{created.json()['id']}/audit",headers=owner).json();assert history[0]["details"]["user_confirmed"] is True
 with SessionLocal() as s:
  mapping=s.scalar(select(PortfolioInstrumentMapping).where(PortfolioInstrumentMapping.id==created.json()["id"]));audit=s.scalar(select(AuditEvent).where(AuditEvent.entity_id==mapping.id,AuditEvent.event_type=="portfolio_mapping_confirmed"));assert mapping.user_id==audit.user_id and audit.details["user_confirmed"] is True

def test_exposure_decimal_values_raw_valuation_and_adjusted_risk():
 h,inv,_=setup("exposure");map_holding(h,inv);r=client.get(BASE+"?as_of_date=2026-09-25&lookback=3",headers=h);assert r.status_code==200,r.text;p=r.json()["positions"][0]
 assert p["quantity"]=="15.00000000" and p["book_cost"]=="1615.00" and p["observed_price"]=="125.0000" and p["observed_market_value"]=="1875.00" and p["unrealized_gain_loss"]=="260.00"
 assert p["price_adjustment_type"]=="raw" and p["position_weight_percent"]=="100.0000";risk=p["historical_adjusted_analysis"];assert risk["adjustment_type"]=="adjusted" and risk["period_return_percent"]=="-10.0000" and risk["maximum_drawdown_percent"]=="-18.1818"
 assert r.json()["totals"]["concentration_hhi"]=="1.0000" and r.json()["financial_records_changed"] is False

def test_missing_stale_price_and_no_lookahead_trades_or_prices():
 h,inv,cash=setup("scenario");map_holding(h,inv);trade(h,inv,cash,"BUY","100","1","2026-09-30")
 before=client.get(BASE+"?as_of_date=2026-09-19",headers=h).json();p=before["positions"][0];assert p["quantity"]=="10.00000000" and p["observed_price"]=="110.0000"
 after=client.get(BASE+"?as_of_date=2026-09-30",headers=h).json()["positions"][0];assert after["quantity"]=="115.00000000" and after["observed_price"]=="125.0000" and after["price_freshness"]=="aging"
 other,other_inv,_=setup("missing");r=client.get(BASE+"?as_of_date=2026-09-25",headers=other).json()["positions"][0];assert r["observed_market_value"] is None and r["price_freshness"]=="missing";assert other_inv["id"]==r["investment_account_id"]

def test_partial_sale_tax_and_missing_tax_do_not_mutate():
 h,inv,_=setup("sale-tax");map_holding(h,inv);before=deepcopy(mutation_counts());rule=client.post("/tax-rules",headers={**h,"Idempotency-Key":str(uuid.uuid4())},json={"effective_from":"2026-01-01","gain_tax_rate":"10","source_note":"User assumption"});assert rule.status_code==201
 baseline=mutation_counts();r=client.post(BASE+"/sale-estimate",headers=h,json={"investment_account_id":inv["id"],"holding_symbol":"HBL","quantity":"5","estimated_fees":"5","as_of_date":"2026-09-25"});assert r.status_code==200,r.text;x=r.json();assert x["gross_proceeds"]=="625.00" and x["fifo_cost_basis"]=="505.00" and x["taxable_gain_loss"]=="115.00" and x["estimated_tax"]=="11.50" and x["net_proceeds"]=="608.50";assert mutation_counts()==baseline
 other,other_inv,_=setup("sale-no-tax");map_holding(other,other_inv);missing=client.post(BASE+"/sale-estimate",headers=other,json={"investment_account_id":other_inv["id"],"holding_symbol":"HBL","quantity":"1","estimated_fees":"0","as_of_date":"2026-09-25"}).json();assert missing["estimated_tax"] is None and missing["tax_status"]=="not_configured"

def test_assistant_portfolio_citations_numeric_preservation_and_isolation():
 h,inv,_=setup("assistant-portfolio");map_holding(h,inv);snapshot=client.get(BASE+"?as_of_date=2026-10-03",headers=h).json();c=client.post("/assistant/conversations",headers=h,json={"title":"Exposure"}).json();answer=client.post(f"/assistant/conversations/{c['id']}/messages",headers=h,json={"message":"Explain my portfolio exposure and concentration"}).json()["response"]
 types={x["source_type"] for x in answer["citations"]};assert "holding" in types and "portfolio_mapping" in types and "psx_price_observation" in types
 ref=next(x for x in answer["evidence_references"] if x["source_type"]=="psx_price_observation");assert ref["calculation"]["position"]["observed_market_value"]==snapshot["positions"][0]["observed_market_value"]
 other=auth("assistant-isolated");c2=client.post("/assistant/conversations",headers=other,json={"title":"Other"}).json();response=client.post(f"/assistant/conversations/{c2['id']}/messages",headers=other,json={"message":"Explain my portfolio exposure"}).json()["response"];assert not any(x["source_type"] in ("portfolio_mapping","psx_price_observation") for x in response["citations"])
