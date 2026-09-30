import re,uuid
from datetime import datetime,timezone
from decimal import Decimal,ROUND_HALF_UP
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth import get_current_user,get_session
from app.models import MarketLocation,MarketplaceAnalysis,MarketplaceCompetitionSignal,MarketplaceProduct,MarketplaceProductAlias,MarketplaceProductObservation,MarketplaceProductRanking,MarketplaceProductWatchlist,MarketplaceSourcingOption,OpportunityAnalysis,User
from app.marketplace_policy import FRESHNESS
from app.schemas_intelligence import CompareRequest,CompetitionCreate,ObservationCreate,ObservationResponse,ProductCreate,ProductResponse,RankingCreate,SourcingCreate,SourcingResponse,WatchlistCreate,WatchlistUpdate

router=APIRouter(prefix="/api/v1/marketplace",tags=["Karachi marketplace intelligence"])
MARKET_ID=uuid.UUID("a7b8a341-59a2-4d8d-9f05-31ea998ef001");Q=Decimal("0.01")
WEIGHTS={"demand":Decimal("0.25"),"margin":Decimal("0.25"),"competition":Decimal("0.15"),"sourcing":Decimal("0.15"),"logistics":Decimal("0.10")}
def key(*parts):return re.sub(r"[^a-z0-9]+"," "," ".join(x or "" for x in parts).lower()).replace(" ml","ml").replace(" kg","kg").strip()
def owned(session,user_id,product_id):
    row=session.scalar(select(MarketplaceProduct).where(MarketplaceProduct.id==product_id,MarketplaceProduct.user_id==user_id))
    if not row:raise HTTPException(404,"Product not found")
    return row
def stale(dt,days=60):return (datetime.now(timezone.utc)-dt).days>days
def product_body(row,status="unmatched",candidates=None):return ProductResponse.model_validate(row).model_copy(update={"match_status":status,"match_candidates":candidates or []})

@router.get("/market")
def market(user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    row=session.get(MarketLocation,MARKET_ID);return {"id":row.id,"country_code":row.country_code,"country_name":row.country_name,"region_name":row.region_name,"city_name":row.city_name,"currency_code":row.currency_code,"timezone":row.timezone,"is_active":row.is_active}
@router.post("/products",response_model=ProductResponse,status_code=201)
def create_product(payload:ProductCreate,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    match_key=key(payload.normalized_name,payload.brand,payload.model);existing=session.scalars(select(MarketplaceProduct).where(MarketplaceProduct.user_id==user.id,MarketplaceProduct.is_archived.is_(False))).all();aliases=session.scalars(select(MarketplaceProductAlias).where(MarketplaceProductAlias.user_id==user.id,MarketplaceProductAlias.normalized_alias==match_key)).all();exact=list({x.id for x in existing if x.match_key==match_key}|{x.product_id for x in aliases});tokens=set(match_key.split());probable=[x.id for x in existing if not exact and tokens and len(tokens&set(x.match_key.split()))/len(tokens|set(x.match_key.split()))>=Decimal("0.6")];status="exact_match" if len(exact)==1 else "probable_match" if probable else "unmatched";row=MarketplaceProduct(user_id=user.id,match_key=match_key,is_archived=False,**payload.model_dump());session.add(row);session.flush();session.add(MarketplaceProductAlias(user_id=user.id,product_id=row.id,alias=payload.normalized_name,normalized_alias=key(payload.normalized_name),source="user"));session.commit();session.refresh(row);return product_body(row,status,exact or probable)
@router.get("/products")
def products(marketplace:str|None=None,category:str|None=None,minimum_net_margin:Decimal|None=None,minimum_roi:Decimal|None=None,maximum_inventory_capital:Decimal|None=None,minimum_research_score:Decimal|None=None,minimum_evidence_confidence:Decimal|None=None,sourcing_available:bool|None=None,source_age_days:int|None=None,price_min:Decimal|None=None,price_max:Decimal|None=None,demand_data_available:bool|None=None,sort_by:str="research_score",user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    rows=session.scalars(select(MarketplaceProduct).where(MarketplaceProduct.user_id==user.id,MarketplaceProduct.is_archived.is_(False))).all();result=[]
    for p in rows:
        if category and p.category!=category:continue
        obs=session.scalars(select(MarketplaceProductObservation).where(MarketplaceProductObservation.product_id==p.id,MarketplaceProductObservation.user_id==user.id).order_by(MarketplaceProductObservation.observed_at.desc())).all();sources=session.scalars(select(MarketplaceSourcingOption).where(MarketplaceSourcingOption.product_id==p.id,MarketplaceSourcingOption.user_id==user.id).order_by(MarketplaceSourcingOption.observed_at.desc())).all();rank=session.scalar(select(MarketplaceProductRanking).where(MarketplaceProductRanking.product_id==p.id,MarketplaceProductRanking.user_id==user.id).order_by(MarketplaceProductRanking.calculated_at.desc()))
        if marketplace and not any(x.marketplace==marketplace for x in obs):continue
        if source_age_days is not None and not any((datetime.now(timezone.utc)-x.observed_at).days<=source_age_days for x in obs):continue
        if price_min is not None and not any(x.currency_code=="PKR" and x.observed_price>=price_min for x in obs):continue
        if price_max is not None and not any(x.currency_code=="PKR" and x.observed_price<=price_max for x in obs):continue
        if demand_data_available is not None and bool(any(x.sold_count is not None or x.review_count is not None for x in obs))!=demand_data_available:continue
        if sourcing_available is not None and bool(any(x.stock_available is not False for x in sources))!=sourcing_available:continue
        metrics={} if not rank or not rank.marketplace_analysis_id else session.get(OpportunityAnalysis,rank.marketplace_analysis_id).calculated_metrics
        if minimum_net_margin is not None and (metrics.get("net_margin_per_unit") is None or Decimal(metrics["net_margin_per_unit"])<minimum_net_margin):continue
        if minimum_roi is not None and (metrics.get("inventory_cash_roi_percent") is None or Decimal(metrics["inventory_cash_roi_percent"])<minimum_roi):continue
        if maximum_inventory_capital is not None and (metrics.get("estimated_total_inventory_cash") is None or Decimal(metrics["estimated_total_inventory_cash"])>maximum_inventory_capital):continue
        if minimum_research_score is not None and (not rank or rank.overall_research_score is None or rank.overall_research_score<minimum_research_score):continue
        if minimum_evidence_confidence is not None and (not rank or rank.evidence_confidence_score<minimum_evidence_confidence):continue
        result.append({"product":product_body(p),"latest_observation":observation_body(obs[0],obs) if obs else None,"sourcing_available":bool(sources),"latest_ranking":ranking_body(rank) if rank else None,"margin":metrics})
    sort_keys={"research_score":lambda x:Decimal(str((x["latest_ranking"]or{}).get("overall_research_score")or-1)),"margin":lambda x:Decimal(str(x["margin"].get("net_margin_per_unit")or-1)),"roi":lambda x:Decimal(str(x["margin"].get("inventory_cash_roi_percent")or-1)),"demand":lambda x:Decimal(str((x["latest_ranking"]or{}).get("demand_score")or-1))};result.sort(key=sort_keys.get(sort_by,sort_keys["research_score"]),reverse=True);return result
@router.get("/products/{product_id}")
def product(product_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    p=owned(session,user.id,product_id);return {"product":product_body(p),"observations":observations(product_id,user,session),"sourcing":sourcing(product_id,user,session),"competition":competition(product_id,user,session),"rankings":[ranking_body(x) for x in session.scalars(select(MarketplaceProductRanking).where(MarketplaceProductRanking.product_id==p.id,MarketplaceProductRanking.user_id==user.id).order_by(MarketplaceProductRanking.calculated_at.desc())).all()]}
def observation_body(row,history):
    previous=next((x for x in history if x.id!=row.id and x.marketplace==row.marketplace and x.currency_code==row.currency_code),None);change=None if not previous else ((row.observed_price-previous.observed_price)/previous.observed_price*100).quantize(Q,rounding=ROUND_HALF_UP)
    age=max(0,(datetime.now(timezone.utc)-row.observed_at).days);p=FRESHNESS["marketplace_price"];status="fresh" if age<=p["fresh"] else "aging" if age<=p["aging"] else "stale";return ObservationResponse.model_validate(row).model_copy(update={"stale":status=="stale","freshness_status":status,"age_days":age,"threshold_days":p,"price_change_percent":change})
@router.post("/products/{product_id}/observations",response_model=ObservationResponse,status_code=201)
def add_observation(product_id:uuid.UUID,payload:ObservationCreate,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    owned(session,user.id,product_id)
    if payload.observed_at>datetime.now(timezone.utc):raise HTTPException(422,"observed_at cannot be in the future")
    row=MarketplaceProductObservation(user_id=user.id,product_id=product_id,**payload.model_dump());session.add(row);session.commit();session.refresh(row);return observation_body(row,[row])
@router.get("/products/{product_id}/observations",response_model=list[ObservationResponse])
def observations(product_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    owned(session,user.id,product_id);rows=session.scalars(select(MarketplaceProductObservation).where(MarketplaceProductObservation.product_id==product_id,MarketplaceProductObservation.user_id==user.id).order_by(MarketplaceProductObservation.observed_at.desc())).all();return [observation_body(x,rows) for x in rows]
@router.post("/products/{product_id}/sourcing",response_model=SourcingResponse,status_code=201)
def add_sourcing(product_id:uuid.UUID,payload:SourcingCreate,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    owned(session,user.id,product_id);row=MarketplaceSourcingOption(user_id=user.id,product_id=product_id,market_location_id=MARKET_ID,**payload.model_dump());session.add(row);session.commit();session.refresh(row);age=max(0,(datetime.now(timezone.utc)-row.observed_at).days);p=FRESHNESS["sourcing"];status="fresh" if age<=p["fresh"] else "aging" if age<=p["aging"] else "stale";return SourcingResponse.model_validate(row).model_copy(update={"stale":status=="stale","freshness_status":status,"age_days":age,"threshold_days":p})
@router.get("/products/{product_id}/sourcing",response_model=list[SourcingResponse])
def sourcing(product_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    owned(session,user.id,product_id);rows=session.scalars(select(MarketplaceSourcingOption).where(MarketplaceSourcingOption.product_id==product_id,MarketplaceSourcingOption.user_id==user.id).order_by(MarketplaceSourcingOption.observed_at.desc())).all();result=[]
    for x in rows:
        age=max(0,(datetime.now(timezone.utc)-x.observed_at).days);p=FRESHNESS["sourcing"];status="fresh" if age<=p["fresh"] else "aging" if age<=p["aging"] else "stale";result.append(SourcingResponse.model_validate(x).model_copy(update={"stale":status=="stale","freshness_status":status,"age_days":age,"threshold_days":p}))
    return result
@router.post("/products/{product_id}/competition",status_code=201)
def add_competition(product_id:uuid.UUID,payload:CompetitionCreate,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    owned(session,user.id,product_id);row=MarketplaceCompetitionSignal(user_id=user.id,product_id=product_id,market_location_id=MARKET_ID,**payload.model_dump());session.add(row);session.commit();session.refresh(row);return {"id":row.id,"stale":stale(row.observed_at),**payload.model_dump()}
@router.get("/products/{product_id}/competition")
def competition(product_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    owned(session,user.id,product_id);return session.scalars(select(MarketplaceCompetitionSignal).where(MarketplaceCompetitionSignal.product_id==product_id,MarketplaceCompetitionSignal.user_id==user.id).order_by(MarketplaceCompetitionSignal.observed_at.desc())).all()

def cap(v):return max(Decimal("0"),min(Decimal("100"),v)).quantize(Q,rounding=ROUND_HALF_UP)
def ranking_body(x):
    return {"id":x.id,"product_id":x.product_id,"market_location_id":x.market_location_id,"demand_score":x.demand_score,"margin_score":x.margin_score,"competition_score":x.competition_score,"sourcing_score":x.sourcing_score,"logistics_score":x.logistics_score,"evidence_confidence_score":x.evidence_confidence_score,"overall_research_score":x.overall_research_score,"ranking_version":x.ranking_version,"explanation":x.explanation,"calculated_at":x.calculated_at,"label":"Research Score"}
@router.post("/products/{product_id}/rank",status_code=201)
def rank(product_id:uuid.UUID,payload:RankingCreate,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    owned(session,user.id,product_id);obs=session.scalars(select(MarketplaceProductObservation).where(MarketplaceProductObservation.product_id==product_id,MarketplaceProductObservation.user_id==user.id).order_by(MarketplaceProductObservation.observed_at.desc())).all();source=session.scalar(select(MarketplaceSourcingOption).where(MarketplaceSourcingOption.product_id==product_id,MarketplaceSourcingOption.user_id==user.id).order_by(MarketplaceSourcingOption.observed_at.desc()));comp=session.scalar(select(MarketplaceCompetitionSignal).where(MarketplaceCompetitionSignal.product_id==product_id,MarketplaceCompetitionSignal.user_id==user.id).order_by(MarketplaceCompetitionSignal.observed_at.desc()));analysis=None;metrics={}
    if payload.marketplace_analysis_id:
        analysis=session.scalar(select(MarketplaceAnalysis).where(MarketplaceAnalysis.analysis_id==payload.marketplace_analysis_id,MarketplaceAnalysis.user_id==user.id))
        if not analysis:raise HTTPException(404,"Owned Part 9 margin estimate not found")
        metrics=session.get(OpportunityAnalysis,payload.marketplace_analysis_id).calculated_metrics
    demand_values=[]
    for x in obs:
        if x.sold_count is not None:demand_values.append(cap(Decimal(x.sold_count)))
        if x.review_count is not None:demand_values.append(cap(Decimal(x.review_count)*Decimal("2")))
        if x.rating_count is not None:demand_values.append(cap(Decimal(x.rating_count)))
        if x.rating is not None:demand_values.append(cap(x.rating*20))
    demand=None if not demand_values else (sum(demand_values)/len(demand_values)).quantize(Q)
    margin_values=[]
    if metrics.get("net_margin_percent") is not None:margin_values.append(cap(Decimal(metrics["net_margin_percent"])*4))
    if metrics.get("inventory_cash_roi_percent") is not None:margin_values.append(cap(Decimal(metrics["inventory_cash_roi_percent"])*2))
    margin=None if not margin_values else (sum(margin_values)/len(margin_values)).quantize(Q)
    competition_score=None
    if comp and (comp.seller_count is not None or comp.comparable_listing_count is not None):
        vals=[]
        if comp.seller_count is not None:vals.append(cap(100-Decimal(comp.seller_count)*5))
        if comp.comparable_listing_count is not None:vals.append(cap(100-Decimal(comp.comparable_listing_count)*2))
        competition_score=(sum(vals)/len(vals)).quantize(Q)
    sourcing_score=None if not source or source.stock_available is None else Decimal("100.00") if source.stock_available else Decimal("0.00")
    logistics_score=None if not source or source.lead_time_days is None else cap(100-Decimal(source.lead_time_days)*3)
    components={"demand":demand,"margin":margin,"competition":competition_score,"sourcing":sourcing_score,"logistics":logistics_score};missing=[x for x,v in components.items() if v is None];available=[x for x in components if components[x] is not None];fresh=sum(1 for x in obs[:3] if not stale(x.observed_at))+(1 if source and not stale(source.observed_at) else 0)+(1 if comp and not stale(comp.observed_at) else 0);evidence_items=len(obs[:3])+(1 if source else 0)+(1 if comp else 0);coverage=Decimal(len(available))/Decimal(5)*100;fresh_ratio=Decimal(fresh)/Decimal(evidence_items)*100 if evidence_items else Decimal(0);confidence=cap(coverage*Decimal("0.7")+fresh_ratio*Decimal("0.3"));den=sum(WEIGHTS[x] for x in available)+Decimal("0.10");overall=None if not available else cap((sum(components[x]*WEIGHTS[x] for x in available)+confidence*Decimal("0.10"))/den)
    explanation={"label":"Research Score","components":{x:{"score":None if v is None else format(v,"f"),"reason":({"demand":"Observed sold/review/rating signals; missing values were not invented","margin":"Reused saved Part 9 net margin and inventory ROI","competition":"Inverse of observed seller and comparable-listing counts","sourcing":"Observed Karachi stock availability","logistics":"Observed lead time; shorter lead time scores higher"}[x])} for x,v in components.items()},"weights":{**{x:format(v,"f") for x,v in WEIGHTS.items()},"evidence_confidence":"0.10"},"missing_inputs":missing,"limitations":["Research score is not a success prediction or guarantee","Only user-entered or authorized evidence is used"],"missing_data_behavior":"Unavailable components are excluded, while their absence lowers the separately weighted evidence-confidence score"}
    row=MarketplaceProductRanking(user_id=user.id,product_id=product_id,market_location_id=MARKET_ID,marketplace_analysis_id=payload.marketplace_analysis_id,demand_score=demand,margin_score=margin,competition_score=competition_score,sourcing_score=sourcing_score,logistics_score=logistics_score,evidence_confidence_score=confidence,overall_research_score=overall,ranking_version="karachi-research-v1",explanation=explanation,calculated_at=datetime.now(timezone.utc));session.add(row);session.commit();session.refresh(row);return ranking_body(row)
@router.get("/rankings")
def rankings(user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    return [ranking_body(x) for x in session.scalars(select(MarketplaceProductRanking).where(MarketplaceProductRanking.user_id==user.id).order_by(MarketplaceProductRanking.calculated_at.desc())).all()]
@router.post("/compare")
def compare(payload:CompareRequest,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    if len(set(payload.product_ids))!=len(payload.product_ids):raise HTTPException(422,"product_ids must be unique")
    return {"market":{"country":"Pakistan","region":"Sindh","city":"Karachi","currency":"PKR"},"products":[product(x,user,session) for x in payload.product_ids],"comparison_limitations":["Missing values remain unavailable","Research scores are not guaranteed outcomes"]}
@router.get("/watchlist")
def watchlist(user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    rows=session.scalars(select(MarketplaceProductWatchlist).where(MarketplaceProductWatchlist.user_id==user.id,MarketplaceProductWatchlist.is_active.is_(True)).order_by(MarketplaceProductWatchlist.updated_at.desc())).all();return [{"id":x.id,"product_id":x.product_id,"notes":x.notes,"is_active":x.is_active,"product":product(x.product_id,user,session)} for x in rows]
@router.post("/watchlist",status_code=201)
def add_watchlist(payload:WatchlistCreate,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    owned(session,user.id,payload.product_id);row=MarketplaceProductWatchlist(user_id=user.id,product_id=payload.product_id,market_location_id=MARKET_ID,notes=payload.notes);session.add(row)
    try:session.commit();session.refresh(row)
    except Exception:session.rollback();raise HTTPException(409,"Product is already on this watchlist") from None
    return {"id":row.id,"product_id":row.product_id,"notes":row.notes,"is_active":row.is_active}
@router.put("/watchlist/{entry_id}")
def update_watchlist(entry_id:uuid.UUID,payload:WatchlistUpdate,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    row=session.scalar(select(MarketplaceProductWatchlist).where(MarketplaceProductWatchlist.id==entry_id,MarketplaceProductWatchlist.user_id==user.id));
    if not row:raise HTTPException(404,"Watchlist entry not found")
    row.notes=payload.notes;row.is_active=payload.is_active;session.commit();session.refresh(row);return {"id":row.id,"product_id":row.product_id,"notes":row.notes,"is_active":row.is_active}
@router.delete("/watchlist/{entry_id}",status_code=204)
def delete_watchlist(entry_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    row=session.scalar(select(MarketplaceProductWatchlist).where(MarketplaceProductWatchlist.id==entry_id,MarketplaceProductWatchlist.user_id==user.id));
    if not row:raise HTTPException(404,"Watchlist entry not found")
    session.delete(row);session.commit()
