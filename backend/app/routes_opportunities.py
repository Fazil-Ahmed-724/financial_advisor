import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlsplit, urlunsplit
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth import get_current_user, get_session
from app.models import MarketplaceAnalysis, OpportunityAnalysis, PropertyAnalysis, PropertyListing, User
from app.opportunity_registry import AnalysisContext, registry
from app.routes_finance import existing_idempotency, request_hash, save_idempotency
from app.schemas_opportunities import AnalysisResponse, PropertyFilters, PropertyListingCreate, PropertyListingResponse, YieldInput

router=APIRouter(prefix="/opportunities",tags=["opportunity analysis"])
UNIT_TO_SQFT={"sq_ft":Decimal("1"),"sq_yd":Decimal("9"),"marla_225_sq_ft":Decimal("225"),"marla_272_25_sq_ft":Decimal("272.25"),"kanal_4500_sq_ft":Decimal("4500"),"kanal_5445_sq_ft":Decimal("5445")}
def canonical_url(value):
    if not value:return None
    p=urlsplit(value.strip())
    if p.scheme.lower() not in {"http","https"} or not p.netloc:raise HTTPException(422,"canonical_url must be an HTTP(S) URL")
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip("/") or "/","",""))
def listing_response(row):
    age=(datetime.now(timezone.utc)-row.observed_at).days
    return PropertyListingResponse.model_validate(row).model_copy(update={"stale":age>90})
class ManualAuthorizedAdapter:
    domain="karachi_real_estate";name="manual_authorized"
    def normalize(self,payload):
        data=payload.model_dump();data["canonical_url"]=canonical_url(payload.canonical_url)
        data["source_name"]=" ".join(payload.source_name.split());data["area_name"]=" ".join(payload.area_name.split());data["property_type"]=" ".join(payload.property_type.split())
        data["information_quality"]="user_entered" if payload.source_type=="user_entered" else ("incomplete" if not payload.canonical_url and not payload.source_id else "authorized_source")
        return data
class ComparableAnalyzer:
    domain="karachi_real_estate";analysis_type="comparables";version="karachi-comparables-v1"
    def analyze(self,context,payload):
        f=PropertyFilters.model_validate(payload);q=select(PropertyListing).where(PropertyListing.user_id==context.user_id,PropertyListing.city=="Karachi",PropertyListing.purpose==f.purpose,PropertyListing.property_type==f.property_type)
        if f.area_name:q=q.where(PropertyListing.area_name.ilike(f.area_name))
        rows=context.session.scalars(q.order_by(PropertyListing.observed_at.desc())).all();factor=UNIT_TO_SQFT[f.area_unit];selected=[]
        for r in rows:
            area_sqft=r.area_amount*UNIT_TO_SQFT[r.area_unit];requested=area_sqft/factor
            if f.area_min is not None and requested<f.area_min:continue
            if f.area_max is not None and requested>f.area_max:continue
            if f.asking_min is not None and r.asking_amount<f.asking_min:continue
            if f.asking_max is not None and r.asking_amount>f.asking_max:continue
            selected.append(r)
        prices=sorted(r.asking_amount for r in selected);count=len(prices);median=None
        if count>=3:median=prices[count//2] if count%2 else (prices[count//2-1]+prices[count//2])/2
        return {"payload":f,"source":"user-recorded Karachi listings","source_reference":None,"evidence":{"listing_ids":[str(r.id) for r in selected],"source_dates":[r.observed_at.isoformat() for r in selected]},"assumptions":{"explicit_unit_conversion":UNIT_TO_SQFT,"asking_prices_are_transactions":False},"metrics":{"status":"sufficient" if count>=3 else "insufficient_comparables","record_count":count,"median_asking_amount":median,"minimum_asking_amount":prices[0] if prices else None,"maximum_asking_amount":prices[-1] if prices else None,"asking_price_status":"unverified_asking_price"},"recommendation":None,"limitations":["Asking prices are not confirmed transaction prices","Legal status, title, condition, and exact comparability are unverified"],"typed":{"analysis_type":"comparables","comparable_count":count,"median_asking_amount":median,"minimum_asking_amount":prices[0] if prices else None,"maximum_asking_amount":prices[-1] if prices else None}}
class YieldAnalyzer:
    domain="karachi_real_estate";analysis_type="yield";version="karachi-yield-v1"
    def analyze(self,context,payload):
        p=YieldInput.model_validate(payload);annual=p.monthly_rent*12;gross=(annual/p.purchase_price*100).quantize(Decimal("0.0001"),rounding=ROUND_HALF_UP);expenses=None if p.annual_expenses is None else sum(p.annual_expenses.values(),Decimal("0"));net=None
        if expenses is not None and p.annual_property_tax is not None:net=((annual-expenses-p.annual_property_tax)/p.purchase_price*100).quantize(Decimal("0.0001"),rounding=ROUND_HALF_UP)
        included=[] if expenses is None else list(p.annual_expenses.keys());included+=[] if p.annual_property_tax is None else ["annual_property_tax"]
        excluded=[x for x in ["maintenance","vacancy","insurance","management","property_tax","legal_and_transaction_costs"] if x not in included]
        return {"payload":p,"source":"user assumptions","source_reference":p.source_reference,"evidence":{},"assumptions":{"purchase_price":p.purchase_price,"monthly_rent":p.monthly_rent,"annual_expenses":p.annual_expenses,"annual_property_tax":p.annual_property_tax},"metrics":{"gross_annual_yield_percent":gross,"net_annual_yield_percent":net,"net_yield_status":"available" if net is not None else "unavailable_missing_expense_or_tax_assumptions","included_costs":included,"excluded_costs":excluded},"recommendation":None,"limitations":["Estimate based only on user-supplied values","No valuation, title, legal, tax, vacancy, or rent verification"],"typed":{"analysis_type":"yield","purchase_price":p.purchase_price,"monthly_rent":p.monthly_rent,"annual_expenses":expenses,"annual_tax_assumption":p.annual_property_tax,"gross_yield_percent":gross,"net_yield_percent":net}}
registry.register_adapter(ManualAuthorizedAdapter());registry.register_analyzer(ComparableAnalyzer());registry.register_analyzer(YieldAnalyzer())

def exact_json(value):
    return jsonable_encoder(value, custom_encoder={Decimal: lambda amount: format(amount, "f")})

@router.get("/domains")
def domains(user:User=Depends(get_current_user)):return {"registered_domains":registry.domains()}
@router.post("/karachi-real-estate/listings",response_model=PropertyListingResponse,status_code=201)
def create_listing(payload:PropertyListingCreate,idempotency_key:str=Header(min_length=1,max_length=200,alias="Idempotency-Key"),user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    operation="POST /opportunities/karachi-real-estate/listings";digest=request_hash(payload);cached=existing_idempotency(session,user.id,idempotency_key,operation,digest)
    if cached is not None:return cached
    if payload.observed_at>datetime.now(timezone.utc):raise HTTPException(422,"observed_at cannot be in the future")
    data=registry.adapter("karachi_real_estate","manual_authorized").normalize(payload);row=PropertyListing(user_id=user.id,**data);session.add(row)
    try:session.flush();body=listing_response(row).model_dump(mode="json");save_idempotency(session,user.id,idempotency_key,operation,digest,body);session.commit();return body
    except IntegrityError:session.rollback();raise HTTPException(409,"Listing already exists for this source URL or source ID") from None
@router.get("/karachi-real-estate/listings",response_model=list[PropertyListingResponse])
def list_listings(area_name:str|None=None,property_type:str|None=None,purpose:str|None=None,area_min:Decimal|None=None,area_max:Decimal|None=None,area_unit:str|None=None,asking_min:Decimal|None=None,asking_max:Decimal|None=None,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    q=select(PropertyListing).where(PropertyListing.user_id==user.id)
    if area_name:q=q.where(PropertyListing.area_name.ilike(area_name))
    if property_type:q=q.where(PropertyListing.property_type==property_type)
    if purpose:q=q.where(PropertyListing.purpose==purpose)
    if asking_min is not None:q=q.where(PropertyListing.asking_amount>=asking_min)
    if asking_max is not None:q=q.where(PropertyListing.asking_amount<=asking_max)
    rows=session.scalars(q.order_by(PropertyListing.observed_at.desc())).all()
    if area_min is not None or area_max is not None:
        if area_unit not in UNIT_TO_SQFT:raise HTTPException(422,"An explicit supported area_unit is required for area filters")
        factor=UNIT_TO_SQFT[area_unit];rows=[r for r in rows if (area_min is None or r.area_amount*UNIT_TO_SQFT[r.area_unit]/factor>=area_min) and (area_max is None or r.area_amount*UNIT_TO_SQFT[r.area_unit]/factor<=area_max)]
    return [listing_response(r) for r in rows]
@router.post("/analyze/{domain}/{analysis_type}",response_model=AnalysisResponse,status_code=201)
def analyze(domain:str,analysis_type:str,payload:dict,idempotency_key:str=Header(min_length=1,max_length=200,alias="Idempotency-Key"),user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    analyzer=registry.analyzer(domain,analysis_type)
    class Wrapper:
        def model_dump(self,mode="json"):return payload
    operation=f"POST /opportunities/analyze/{domain}/{analysis_type}";digest=request_hash(Wrapper());cached=existing_idempotency(session,user.id,idempotency_key,operation,digest)
    if cached is not None:return cached
    try:
        result=analyzer.analyze(AnalysisContext(session,user.id),payload)
    except ValidationError as exc:
        raise HTTPException(422, exact_json(exc.errors())) from None
    now=datetime.now(timezone.utc);base=OpportunityAnalysis(user_id=user.id,domain=domain,source=result["source"],source_reference=result["source_reference"],observed_at=now,input_snapshot=exact_json(payload),source_evidence=exact_json(result["evidence"]),assumptions=exact_json(result["assumptions"]),calculated_metrics=exact_json(result["metrics"]),recommendation=result["recommendation"],limitations=result["limitations"],analyzer_version=analyzer.version);session.add(base);session.flush();typed=result["typed"]
    kind=typed.pop("kind","property")
    session.add(MarketplaceAnalysis(analysis_id=base.id,user_id=user.id,**typed) if kind=="marketplace" else PropertyAnalysis(analysis_id=base.id,user_id=user.id,**typed));session.flush();body=AnalysisResponse(id=base.id,domain=domain,analysis_type=analysis_type,source_evidence=base.source_evidence,assumptions=base.assumptions,calculated_metrics=base.calculated_metrics,recommendation=base.recommendation,limitations=base.limitations,analyzer_version=base.analyzer_version,calculated_at=base.calculated_at).model_dump(mode="json");save_idempotency(session,user.id,idempotency_key,operation,digest,body);session.commit();return body
