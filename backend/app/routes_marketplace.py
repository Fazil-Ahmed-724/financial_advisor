import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth import get_current_user, get_session
from app.models import MarketplaceAnalysis, MarketplaceListing, MarketplaceOutcome, OpportunityAnalysis, User
from app.opportunity_registry import AnalysisContext, registry
from app.routes_finance import existing_idempotency, request_hash, save_idempotency
from app.routes_opportunities import canonical_url, exact_json
from app.schemas_marketplace import MarketplaceListingCreate, MarketplaceListingResponse, MarketplaceOutcomeCreate, MarketplaceOutcomeResponse, ResaleAnalysisInput
from app.schemas_opportunities import AnalysisResponse

router=APIRouter(prefix="/marketplace",tags=["marketplace resale research"])
ZERO=Decimal("0");FOUR=Decimal("0.0001")

class MarketplaceSourceAdapter:
    domain="marketplace_resale"
    def __init__(self,platform):self.name=platform.lower();self.platform=platform
    def normalize(self,payload):
        if payload.source_platform!=self.platform:raise HTTPException(422,"Source platform does not match adapter")
        data=payload.model_dump();data["canonical_url"]=canonical_url(payload.canonical_url);data["product_name"]=" ".join(payload.product_name.split());data["currency"]=payload.currency.upper();data["information_quality"]="incomplete" if not payload.canonical_url and not payload.source_listing_id and not payload.evidence else payload.source_method
        return data

class ResaleMarginAnalyzer:
    domain="marketplace_resale";analysis_type="margin";version="marketplace-margin-v1"
    cost_fields=("shipping_per_unit","customs_per_unit","conversion_fee_per_unit","marketplace_fee_per_unit","payment_fee_per_unit","packaging_per_unit","delivery_per_unit","other_costs_per_unit","returns_allowance_per_unit","damage_allowance_per_unit","unsold_allowance_per_unit")
    def analyze(self,context,payload):
        p=ResaleAnalysisInput.model_validate(payload);listing=context.session.scalar(select(MarketplaceListing).where(MarketplaceListing.id==p.listing_id,MarketplaceListing.user_id==context.user_id))
        if not listing:raise HTTPException(404,"Marketplace source listing not found")
        missing=[];rate=Decimal("1")
        if listing.currency!="PKR":
            if p.exchange_rate_to_pkr is None or p.exchange_rate_observed_at is None or not p.exchange_rate_source:missing.append("dated_exchange_rate")
            else:rate=p.exchange_rate_to_pkr
        selling=p.expected_selling_price_pkr or listing.expected_karachi_selling_price
        if selling is None:missing.append("expected_selling_price_pkr")
        for field in self.cost_fields:
            if getattr(p,field) is None:missing.append(field)
        metrics={"status":"unavailable_missing_inputs" if missing else "available","missing_inputs":missing,"currency":"PKR","landed_cost_per_unit":None,"break_even_selling_price_per_unit":None,"gross_margin_per_unit":None,"net_margin_per_unit":None,"net_margin_percent":None,"inventory_cash_roi_percent":None}
        landed=break_even=gross=net=roi=None
        if not missing:
            source=(listing.source_price*rate).quantize(FOUR,rounding=ROUND_HALF_UP)
            landed=(source+p.shipping_per_unit+p.customs_per_unit+p.conversion_fee_per_unit).quantize(FOUR,rounding=ROUND_HALF_UP)
            selling_costs=sum((getattr(p,x) for x in self.cost_fields[3:]),ZERO)
            break_even=(landed+selling_costs).quantize(FOUR,rounding=ROUND_HALF_UP);gross=(selling-landed).quantize(FOUR,rounding=ROUND_HALF_UP);net=(selling-break_even).quantize(FOUR,rounding=ROUND_HALF_UP);roi=(net/break_even*100).quantize(FOUR,rounding=ROUND_HALF_UP)
            metrics.update({"landed_cost_per_unit":landed,"break_even_selling_price_per_unit":break_even,"gross_margin_per_unit":gross,"net_margin_per_unit":net,"net_margin_percent":(net/selling*100).quantize(FOUR,rounding=ROUND_HALF_UP),"inventory_cash_roi_percent":roi,"estimated_total_inventory_cash":(break_even*p.quantity).quantize(FOUR,rounding=ROUND_HALF_UP),"estimated_total_net_margin":(net*p.quantity).quantize(FOUR,rounding=ROUND_HALF_UP)})
        assumptions=p.model_dump();assumptions.update({"source_price":listing.source_price,"source_currency":listing.currency,"formula_landed":"source_price × exchange_rate + shipping + customs + conversion_fee","formula_break_even":"landed_cost + selling_fee + payment_fee + packaging + delivery + other + returns + damage + unsold allowances","formula_net_margin":"expected_selling_price - break_even","formula_inventory_roi":"net_margin / break_even × 100"})
        excluded=[x for x in self.cost_fields if getattr(p,x) is None]
        return {"payload":p,"source":listing.source_platform,"source_reference":listing.canonical_url or listing.source_listing_id,"evidence":{"listing_id":str(listing.id),"source_observed_at":listing.observed_at.isoformat(),"exchange_rate_observed_at":p.exchange_rate_observed_at.isoformat() if p.exchange_rate_observed_at else None,"exchange_rate_source":p.exchange_rate_source,"listing_evidence":listing.evidence},"assumptions":assumptions,"metrics":metrics,"recommendation":None,"limitations":["Estimate from user-entered or authorized source data","Demand, customs, fees, returns, and sales are not independently verified","No purchase or marketplace listing is created"],"typed":{"kind":"marketplace","listing_id":listing.id,"quantity":p.quantity,"landed_cost_per_unit":landed,"break_even_per_unit":break_even,"gross_margin_per_unit":gross,"net_margin_per_unit":net,"inventory_cash_roi_percent":roi}}

for platform in ("Daraz","Temu","SHEIN","Other"):registry.register_adapter(MarketplaceSourceAdapter(platform))
registry.register_analyzer(ResaleMarginAnalyzer())

def response(row):
    return MarketplaceListingResponse.model_validate(row).model_copy(update={"stale":(datetime.now(timezone.utc)-row.observed_at).days>60})

@router.post("/listings",response_model=MarketplaceListingResponse,status_code=201)
def create_listing(payload:MarketplaceListingCreate,idempotency_key:str=Header(alias="Idempotency-Key",min_length=1,max_length=200),user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    operation="POST /marketplace/listings";digest=request_hash(payload);cached=existing_idempotency(session,user.id,idempotency_key,operation,digest)
    if cached is not None:return cached
    if payload.observed_at>datetime.now(timezone.utc):raise HTTPException(422,"observed_at cannot be in the future")
    data=registry.adapter("marketplace_resale",payload.source_platform.lower()).normalize(payload);row=MarketplaceListing(user_id=user.id,**data);session.add(row)
    try:session.flush();body=response(row).model_dump(mode="json");save_idempotency(session,user.id,idempotency_key,operation,digest,body);session.commit();return body
    except IntegrityError:session.rollback();raise HTTPException(409,"Listing already exists for this source URL or platform listing ID") from None

@router.get("/listings",response_model=list[MarketplaceListingResponse])
def listings(platform:str|None=None,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    q=select(MarketplaceListing).where(MarketplaceListing.user_id==user.id)
    if platform:q=q.where(MarketplaceListing.source_platform==platform)
    return [response(x) for x in session.scalars(q.order_by(MarketplaceListing.observed_at.desc())).all()]

@router.post("/outcomes",response_model=MarketplaceOutcomeResponse,status_code=201)
def create_outcome(payload:MarketplaceOutcomeCreate,idempotency_key:str=Header(alias="Idempotency-Key",min_length=1,max_length=200),user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    operation="POST /marketplace/outcomes";digest=request_hash(payload);cached=existing_idempotency(session,user.id,idempotency_key,operation,digest)
    if cached is not None:return cached
    analysis=session.scalar(select(MarketplaceAnalysis).where(MarketplaceAnalysis.analysis_id==payload.analysis_id,MarketplaceAnalysis.user_id==user.id))
    if not analysis:raise HTTPException(404,"Owned marketplace estimate not found")
    estimate=session.get(OpportunityAnalysis,payload.analysis_id);actual=(payload.actual_sales_revenue-payload.actual_purchase_cost-payload.actual_other_costs-payload.actual_sales_fees-payload.return_costs).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
    forecast=None;differences={"actual_purchase_cost":format(payload.actual_purchase_cost,"f"),"actual_other_costs":format(payload.actual_other_costs,"f"),"actual_sales_revenue":format(payload.actual_sales_revenue,"f"),"actual_sales_fees":format(payload.actual_sales_fees,"f"),"returned_quantity":format(payload.returned_quantity,"f"),"remaining_quantity":format(payload.remaining_quantity,"f")}
    expected=estimate.calculated_metrics.get("net_margin_per_unit")
    if expected is not None:forecast=(actual-(Decimal(expected)*payload.purchased_quantity)).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
    row=MarketplaceOutcome(user_id=user.id,actual_net_result=actual,forecast_error=forecast,assumption_differences=differences,**payload.model_dump());session.add(row);session.flush();body=MarketplaceOutcomeResponse.model_validate(row).model_dump(mode="json");save_idempotency(session,user.id,idempotency_key,operation,digest,body);session.commit();return body

@router.get("/outcomes",response_model=list[MarketplaceOutcomeResponse])
def outcomes(user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    return session.scalars(select(MarketplaceOutcome).where(MarketplaceOutcome.user_id==user.id).order_by(MarketplaceOutcome.recorded_at.desc())).all()

@router.get("/analyses",response_model=list[AnalysisResponse])
def analyses(user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    rows=session.scalars(select(OpportunityAnalysis).join(MarketplaceAnalysis,MarketplaceAnalysis.analysis_id==OpportunityAnalysis.id).where(MarketplaceAnalysis.user_id==user.id).order_by(OpportunityAnalysis.calculated_at.desc())).all()
    return [AnalysisResponse(id=x.id,domain=x.domain,analysis_type="margin",source_evidence=x.source_evidence,assumptions=x.assumptions,calculated_metrics=x.calculated_metrics,recommendation=x.recommendation,limitations=x.limitations,analyzer_version=x.analyzer_version,calculated_at=x.calculated_at) for x in rows]
