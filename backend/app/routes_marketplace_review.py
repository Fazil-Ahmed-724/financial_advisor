import csv,io,json,uuid
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
from fastapi import APIRouter,Depends,File,Form,HTTPException,UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth import get_current_user,get_session
from app.marketplace_policy import BATCH_RANK_MAX,FRESHNESS,IMPORT_MAX_BYTES,IMPORT_MAX_ROWS,SUPPORTED_FILTERS,SUPPORTED_SORTS
from app.models import MarketplaceCompetitionSignal,MarketplaceImportBatch,MarketplaceImportRow,MarketplaceProduct,MarketplaceProductAlias,MarketplaceProductMergeEvent,MarketplaceProductObservation,MarketplaceProductRanking,MarketplaceProductSplitEvent,MarketplaceProductWatchlist,MarketplaceResearchPreset,MarketplaceSourcingOption,User
from app.routes_intelligence import MARKET_ID,key,owned,product,products,rank,ranking_body
from app.schemas_intelligence import BatchRankingRequest,ImportMapping,ImportRowUpdate,MergeRequest,PresetPayload,RankingCreate,SplitRequest
router=APIRouter(prefix="/api/v1/marketplace",tags=["marketplace review workflow"])
ALIASES={"product":"observed_name","product_name":"observed_name","item_name":"observed_name","title":"observed_name","price":"observed_price","currency":"currency_code","observation_date":"observed_at","observed_date":"observed_at","source":"source_reference","url":"source_url","supplier":"supplier_name","moq":"minimum_order_quantity","transport_cost":"local_transport_cost","lead_time":"lead_time_days"}
REQUIRED={"product_observations":{"observed_name","marketplace","observed_price","currency_code","observed_at","source_reference"},"sourcing_options":{"observed_name","source_channel","unit_cost","currency_code","observed_at"},"competition_observations":{"observed_name","comparable_listing_count","seller_count","lowest_price","median_price","highest_price","observed_at"}}
def batch_owned(s,u,bid):
    b=s.scalar(select(MarketplaceImportBatch).where(MarketplaceImportBatch.id==bid,MarketplaceImportBatch.user_id==u))
    if not b:raise HTTPException(404,"Import batch not found")
    return b
def match(s,u,name,brand=None,model=None):
    k=key(name,brand,model);rows=s.scalars(select(MarketplaceProduct).where(MarketplaceProduct.user_id==u,MarketplaceProduct.is_archived.is_(False))).all();by_id={x.id:x for x in rows};aliases=s.scalars(select(MarketplaceProductAlias).where(MarketplaceProductAlias.user_id==u)).all();exact_ids={x.id for x in rows if x.match_key==k}|{a.product_id for a in aliases if a.normalized_alias==k and a.product_id in by_id};exact=[by_id[x] for x in exact_ids];tokens=set(k.split());prob=[x for x in rows if tokens and len(tokens&set(x.match_key.split()))/len(tokens|set(x.match_key.split()))>=.6 and x.id not in exact_ids];return ("exact_match",exact) if len(exact)==1 else ("ambiguous",exact) if len(exact)>1 else ("probable_match",prob) if len(prob)==1 else ("ambiguous",prob) if len(prob)>1 else ("unmatched",[])
def normalize(raw,mapping,kind,s,u):
    data={target:raw.get(source) for target,source in mapping.items() if raw.get(source) not in (None,"")};errors=[];warnings=[]
    for f in REQUIRED[kind]:
        if f not in data:errors.append(f"Missing {f}")
    for f in ("observed_price","unit_cost","minimum_order_quantity","local_transport_cost","packaging_cost","rating","lowest_price","median_price","highest_price"):
        if f in data:
            try:data[f]=format(Decimal(str(data[f])),"f")
            except InvalidOperation:errors.append(f"Invalid decimal: {f}")
    for f in ("rating_count","review_count","sold_count","lead_time_days","comparable_listing_count","seller_count"):
        if f in data:
            try:data[f]=int(data[f])
            except (ValueError,TypeError):errors.append(f"Invalid integer: {f}")
    if "currency_code" in data:data["currency_code"]=str(data["currency_code"]).upper()
    if kind!="product_observations" and data.get("currency_code")!="PKR":errors.append("Karachi sourcing/competition currency must be PKR")
    if "observed_at" in data:
        try:
            d=datetime.fromisoformat(str(data["observed_at"]).replace("Z","+00:00"))
            if d.tzinfo is None:raise ValueError()
            data["observed_at"]=d.isoformat()
        except ValueError:errors.append("Invalid timezone-aware observed_at")
    name=data.get("observed_name","");state,candidates=match(s,u,name,data.get("brand"),data.get("model"));action="attach_to_existing_product" if state=="exact_match" else "create_product" if state=="unmatched" else "requires_review";warnings+=[] if state in ("exact_match","unmatched") else [f"{state} requires review"]
    return data,errors,warnings,state,(candidates[0].id if len(candidates)==1 else None),action
def mapping_for(headers):return {ALIASES.get(str(h).strip().lower(),str(h).strip().lower()):h for h in headers}
def refresh_batch(s,b):
    rows=s.scalars(select(MarketplaceImportRow).where(MarketplaceImportRow.import_batch_id==b.id)).all();b.total_rows=len(rows);b.valid_rows=sum(x.validation_status=="valid" for x in rows);b.invalid_rows=sum(x.validation_status=="invalid" for x in rows);b.warning_rows=sum(bool(x.warnings) for x in rows)
def batch_body(b,s):return {"id":b.id,"import_type":b.import_type,"source_classification":b.source_classification,"original_filename":b.original_filename,"status":b.status,"column_mapping":b.column_mapping,"total_rows":b.total_rows,"valid_rows":b.valid_rows,"invalid_rows":b.invalid_rows,"warning_rows":b.warning_rows,"committed_rows":b.committed_rows,"created_at":b.created_at,"committed_at":b.committed_at}
@router.post("/imports",status_code=201)
async def upload_import(import_type:str=Form(),source_classification:str=Form(),file:UploadFile=File(),user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    if import_type not in REQUIRED or source_classification not in {"user_entered","authorized_export","permitted_api"}:raise HTTPException(422,"Unsupported import type or source classification")
    name=(file.filename or "upload").split("/")[-1].split("\\")[-1];ext=name.lower().rsplit(".",1)[-1] if "." in name else "";allowed={"csv":"text/csv","json":"application/json"}
    if ext not in allowed or file.content_type not in {allowed[ext],"text/plain","application/octet-stream"}:raise HTTPException(415,"Only CSV and JSON files are supported")
    content=await file.read(IMPORT_MAX_BYTES+1)
    if len(content)>IMPORT_MAX_BYTES:raise HTTPException(413,"Import file exceeds configured size limit")
    try:
        text=content.decode("utf-8-sig")
        if ext=="csv":
            reader=csv.DictReader(io.StringIO(text));raw=list(reader);headers=reader.fieldnames or []
        else:
            raw=json.loads(text);headers=list(raw[0]) if isinstance(raw,list) and raw else []
            if not isinstance(raw,list) or any(not isinstance(x,dict) for x in raw):raise ValueError()
    except (UnicodeDecodeError,csv.Error,json.JSONDecodeError,ValueError):raise HTTPException(422,"File could not be parsed safely") from None
    if len(raw)>IMPORT_MAX_ROWS:raise HTTPException(413,"Import row count exceeds configured limit")
    mapping=mapping_for(headers);b=MarketplaceImportBatch(user_id=user.id,import_type=import_type,source_classification=source_classification,original_filename=name,status="parsed",column_mapping=mapping,total_rows=0,valid_rows=0,invalid_rows=0,warning_rows=0,committed_rows=0);session.add(b);session.flush()
    for i,x in enumerate(raw,1):
        data,errors,warnings,state,pid,action=normalize(x,mapping,import_type,session,user.id)
        session.add(MarketplaceImportRow(import_batch_id=b.id,row_number=i,raw_data=x,normalized_data=data,validation_status="invalid" if errors else "valid",warnings=warnings,errors=errors,duplicate_status=state,proposed_product_id=pid,action="requires_review" if errors else action))
    session.flush();refresh_batch(session,b);session.commit();session.refresh(b);return batch_body(b,session)
@router.get("/imports")
def imports(user:User=Depends(get_current_user),session:Session=Depends(get_session)):return [batch_body(x,session) for x in session.scalars(select(MarketplaceImportBatch).where(MarketplaceImportBatch.user_id==user.id).order_by(MarketplaceImportBatch.created_at.desc())).all()]
@router.get("/imports/{batch_id}")
def get_import(batch_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):return batch_body(batch_owned(session,user.id,batch_id),session)
@router.post("/imports/{batch_id}/mapping")
def set_mapping(batch_id:uuid.UUID,payload:ImportMapping,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    b=batch_owned(session,user.id,batch_id)
    if b.status in ("committed","cancelled"):raise HTTPException(409,"Batch is closed")
    rows=session.scalars(select(MarketplaceImportRow).where(MarketplaceImportRow.import_batch_id==b.id)).all();b.column_mapping=payload.mapping
    for r in rows:
        r.normalized_data,r.errors,r.warnings,r.duplicate_status,r.proposed_product_id,r.action=normalize(r.raw_data,payload.mapping,b.import_type,session,user.id)
        r.validation_status="invalid" if r.errors else "valid"
        if r.errors:r.action="requires_review"
    refresh_batch(session,b);b.status="reviewed";session.commit();return batch_body(b,session)
@router.get("/imports/{batch_id}/preview")
def preview(batch_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    b=batch_owned(session,user.id,batch_id);rows=session.scalars(select(MarketplaceImportRow).where(MarketplaceImportRow.import_batch_id==b.id).order_by(MarketplaceImportRow.row_number)).all();return {"batch":batch_body(b,session),"rows":[{"id":x.id,"row_number":x.row_number,"raw_data":x.raw_data,"normalized_data":x.normalized_data,"validation_status":x.validation_status,"warnings":x.warnings,"errors":x.errors,"duplicate_status":x.duplicate_status,"proposed_product_id":x.proposed_product_id,"action":x.action} for x in rows]}
@router.put("/imports/{batch_id}/rows/{row_id}")
def row_action(batch_id:uuid.UUID,row_id:uuid.UUID,payload:ImportRowUpdate,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    b=batch_owned(session,user.id,batch_id);r=session.scalar(select(MarketplaceImportRow).where(MarketplaceImportRow.id==row_id,MarketplaceImportRow.import_batch_id==b.id));
    if not r:raise HTTPException(404,"Import row not found")
    if payload.action=="attach_to_existing_product":owned(session,user.id,payload.proposed_product_id);r.proposed_product_id=payload.proposed_product_id
    r.action=payload.action;b.status="reviewed";session.commit();return {"id":r.id,"action":r.action,"proposed_product_id":r.proposed_product_id}
def import_product(session,user,row):
    d=row.normalized_data;name=d["observed_name"]
    if row.action=="attach_to_existing_product":return owned(session,user.id,row.proposed_product_id)
    p=MarketplaceProduct(user_id=user.id,normalized_name=name,match_key=key(name,d.get("brand"),d.get("model")),brand=d.get("brand"),model=d.get("model"),category=d.get("category"),canonical_attributes={},is_archived=False);session.add(p);session.flush();row.proposed_product_id=p.id;session.add(MarketplaceProductAlias(user_id=user.id,product_id=p.id,alias=name,normalized_alias=key(name),source="import"));return p
@router.post("/imports/{batch_id}/commit")
def commit_import(batch_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    b=batch_owned(session,user.id,batch_id)
    if b.status in ("committed","cancelled"):raise HTTPException(409,"Batch is closed")
    rows=session.scalars(select(MarketplaceImportRow).where(MarketplaceImportRow.import_batch_id==b.id).order_by(MarketplaceImportRow.row_number)).all();blocking=[x for x in rows if x.validation_status!="valid" and x.action!="skip" or x.action=="requires_review"]
    if blocking:raise HTTPException(422,{"message":"Every invalid or uncertain row must be resolved or skipped","row_ids":[str(x.id) for x in blocking]})
    count=0
    try:
        for r in rows:
            if r.action=="skip":continue
            p=import_product(session,user,r);d=dict(r.normalized_data);d.pop("brand",None);d.pop("model",None);d.pop("category",None);name=d.pop("observed_name");d["observed_at"]=datetime.fromisoformat(d["observed_at"])
            if b.import_type=="product_observations":session.add(MarketplaceProductObservation(user_id=user.id,product_id=p.id,source_type=b.source_classification,observed_name=name,raw_attributes={},evidence={"import_batch_id":str(b.id),"row_number":r.row_number},**d))
            elif b.import_type=="sourcing_options":session.add(MarketplaceSourcingOption(user_id=user.id,product_id=p.id,market_location_id=MARKET_ID,source_type=b.source_classification,supplier_name=d.get("supplier_name"),source_channel=d["source_channel"],source_reference=d.get("source_reference"),unit_cost=d["unit_cost"],currency_code=d["currency_code"],minimum_order_quantity=d.get("minimum_order_quantity"),local_transport_cost=d.get("local_transport_cost"),packaging_cost=d.get("packaging_cost"),lead_time_days=d.get("lead_time_days"),stock_available=str(d.get("stock_available","")).lower() in ("true","1","yes") if "stock_available" in d else None,observed_at=d["observed_at"],evidence={"import_batch_id":str(b.id),"row_number":r.row_number}))
            else:session.add(MarketplaceCompetitionSignal(user_id=user.id,product_id=p.id,market_location_id=MARKET_ID,source_type=b.source_classification,source_reference=d.get("source_reference") or f"import:{b.id}:{r.row_number}",comparable_listing_count=d.get("comparable_listing_count"),seller_count=d.get("seller_count"),lowest_price=d.get("lowest_price"),median_price=d.get("median_price"),highest_price=d.get("highest_price"),price_dispersion=None,observed_at=d["observed_at"],evidence={"import_batch_id":str(b.id),"row_number":r.row_number}))
            count+=1
        b.status="committed";b.committed_rows=count;b.committed_at=datetime.now(timezone.utc);session.commit()
    except Exception:session.rollback();raise
    return batch_body(b,session)
@router.post("/imports/{batch_id}/cancel")
def cancel_import(batch_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    b=batch_owned(session,user.id,batch_id)
    if b.status=="committed":raise HTTPException(409,"Committed batch cannot be cancelled")
    b.status="cancelled";session.commit();return batch_body(b,session)
@router.post("/products/merge")
def merge_products(payload:MergeRequest,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    if payload.source_product_id==payload.target_product_id:raise HTTPException(422,"Source and target must differ")
    source=owned(session,user.id,payload.source_product_id);target=owned(session,user.id,payload.target_product_id)
    if source.is_archived or target.is_archived:raise HTTPException(409,"Archived products cannot be merged")
    moved={}
    for model,name in ((MarketplaceProductObservation,"observations"),(MarketplaceSourcingOption,"sourcing"),(MarketplaceCompetitionSignal,"competition")):
        rows=session.scalars(select(model).where(model.user_id==user.id,model.product_id==source.id)).all();moved[name]=[str(x.id) for x in rows]
        for x in rows:x.product_id=target.id
    watch=session.scalar(select(MarketplaceProductWatchlist).where(MarketplaceProductWatchlist.user_id==user.id,MarketplaceProductWatchlist.product_id==source.id))
    if watch:
        existing=session.scalar(select(MarketplaceProductWatchlist).where(MarketplaceProductWatchlist.user_id==user.id,MarketplaceProductWatchlist.product_id==target.id))
        if existing:session.delete(watch)
        else:watch.product_id=target.id
    session.add(MarketplaceProductAlias(user_id=user.id,product_id=target.id,alias=source.normalized_name,normalized_alias=source.match_key,source="merge"));source.is_archived=True;source.merged_into_id=target.id;event=MarketplaceProductMergeEvent(user_id=user.id,source_product_id=source.id,target_product_id=target.id,reason=payload.reason,snapshot={"source":{"name":source.normalized_name,"brand":source.brand,"model":source.model},"moved":moved,"ranking_snapshots_preserved":True});session.add(event);session.commit();session.refresh(event);return {"event_id":event.id,"source_product_id":source.id,"target_product_id":target.id,"source_archived":True,"moved":moved}
@router.post("/products/{product_id}/split",status_code=201)
def split_product(product_id:uuid.UUID,payload:SplitRequest,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    original=owned(session,user.id,product_id);new=MarketplaceProduct(user_id=user.id,match_key=key(payload.new_product.normalized_name,payload.new_product.brand,payload.new_product.model),is_archived=False,**payload.new_product.model_dump());session.add(new);session.flush()
    moved=[]
    for oid in payload.observation_ids:
        row=session.scalar(select(MarketplaceProductObservation).where(MarketplaceProductObservation.id==oid,MarketplaceProductObservation.user_id==user.id,MarketplaceProductObservation.product_id==original.id))
        if not row:session.rollback();raise HTTPException(422,f"Observation {oid} does not belong to original product")
        row.product_id=new.id;moved.append(str(oid))
    for model,ids in ((MarketplaceSourcingOption,payload.sourcing_ids),(MarketplaceCompetitionSignal,payload.competition_ids)):
        for rid in ids:
            row=session.scalar(select(model).where(model.id==rid,model.user_id==user.id,model.product_id==original.id))
            if not row:session.rollback();raise HTTPException(422,"Selected reassignment does not belong to original product")
            row.product_id=new.id
    event=MarketplaceProductSplitEvent(user_id=user.id,original_product_id=original.id,new_product_id=new.id,moved_observation_ids=moved,reason=payload.reason,snapshot={"new_product":payload.new_product.model_dump(mode="json"),"sourcing_ids":[str(x) for x in payload.sourcing_ids],"competition_ids":[str(x) for x in payload.competition_ids]});session.add(event);session.commit();return {"event_id":event.id,"original_product_id":original.id,"new_product_id":new.id,"moved_observation_ids":moved}
def validate_preset(payload):
    unknown=set(payload.filters)-SUPPORTED_FILTERS
    if unknown:raise HTTPException(422,f"Unsupported filter keys: {sorted(unknown)}")
    field=payload.sorting.get("field","research_score");direction=payload.sorting.get("direction","desc")
    if set(payload.sorting)-{"field","direction"} or field not in SUPPORTED_SORTS or direction not in {"asc","desc"}:raise HTTPException(422,"Unsupported sorting configuration")
@router.get("/research-presets")
def presets(user:User=Depends(get_current_user),session:Session=Depends(get_session)):return session.scalars(select(MarketplaceResearchPreset).where(MarketplaceResearchPreset.user_id==user.id).order_by(MarketplaceResearchPreset.name)).all()
@router.post("/research-presets",status_code=201)
def create_preset(payload:PresetPayload,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    validate_preset(payload)
    if payload.is_default:
        for x in session.scalars(select(MarketplaceResearchPreset).where(MarketplaceResearchPreset.user_id==user.id)).all():x.is_default=False
    row=MarketplaceResearchPreset(user_id=user.id,market_location_id=MARKET_ID,**payload.model_dump());session.add(row)
    try:session.commit();session.refresh(row)
    except IntegrityError:session.rollback();raise HTTPException(409,"Preset name already exists") from None
    return row
@router.put("/research-presets/{preset_id}")
def update_preset(preset_id:uuid.UUID,payload:PresetPayload,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    validate_preset(payload);row=session.scalar(select(MarketplaceResearchPreset).where(MarketplaceResearchPreset.id==preset_id,MarketplaceResearchPreset.user_id==user.id))
    if not row:raise HTTPException(404,"Preset not found")
    if payload.is_default:
        for x in session.scalars(select(MarketplaceResearchPreset).where(MarketplaceResearchPreset.user_id==user.id)).all():x.is_default=False
    for k,v in payload.model_dump().items():setattr(row,k,v)
    session.commit();session.refresh(row);return row
@router.delete("/research-presets/{preset_id}",status_code=204)
def delete_preset(preset_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    row=session.scalar(select(MarketplaceResearchPreset).where(MarketplaceResearchPreset.id==preset_id,MarketplaceResearchPreset.user_id==user.id))
    if not row:raise HTTPException(404,"Preset not found")
    session.delete(row);session.commit()
@router.post("/research-presets/{preset_id}/run")
def run_preset(preset_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    row=session.scalar(select(MarketplaceResearchPreset).where(MarketplaceResearchPreset.id==preset_id,MarketplaceResearchPreset.user_id==user.id))
    if not row:raise HTTPException(404,"Preset not found")
    args={k:None for k in SUPPORTED_FILTERS};args.update(row.filters);args["sort_by"]=row.sorting.get("field","research_score");result=products(**args,user=user,session=session)
    if row.sorting.get("direction")=="asc":result.reverse()
    return {"preset_id":row.id,"name":row.name,"results":result}
@router.post("/rankings/batch")
def batch_rank(payload:BatchRankingRequest,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    if len(payload.product_ids)>BATCH_RANK_MAX:raise HTTPException(413,"Batch ranking exceeds configured product limit")
    if len(set(payload.product_ids))!=len(payload.product_ids):raise HTTPException(422,"Product IDs must be unique")
    result=[]
    for pid in payload.product_ids:
        try:result.append({"product_id":pid,"status":"ranked","ranking":rank(pid,RankingCreate(),user,session)})
        except HTTPException as e:result.append({"product_id":pid,"status":"failed","error":e.detail})
    return {"market":"Karachi","results":result,"partial_failures":sum(x["status"]=="failed" for x in result)}
def freshness(dt,kind):
    age=max(0,(datetime.now(timezone.utc)-dt).days);p=FRESHNESS[kind];return {"status":"fresh" if age<=p["fresh"] else "aging" if age<=p["aging"] else "stale","age_days":age,"observed_at":dt,"threshold_days":p}
@router.get("/products/{product_id}/data-quality")
def quality(product_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    p=owned(session,user.id,product_id);obs=session.scalars(select(MarketplaceProductObservation).where(MarketplaceProductObservation.user_id==user.id,MarketplaceProductObservation.product_id==p.id).order_by(MarketplaceProductObservation.observed_at.desc())).all();src=session.scalars(select(MarketplaceSourcingOption).where(MarketplaceSourcingOption.user_id==user.id,MarketplaceSourcingOption.product_id==p.id).order_by(MarketplaceSourcingOption.observed_at.desc())).all();comp=session.scalars(select(MarketplaceCompetitionSignal).where(MarketplaceCompetitionSignal.user_id==user.id,MarketplaceCompetitionSignal.product_id==p.id).order_by(MarketplaceCompetitionSignal.observed_at.desc())).all();ranking=session.scalar(select(MarketplaceProductRanking).where(MarketplaceProductRanking.user_id==user.id,MarketplaceProductRanking.product_id==p.id).order_by(MarketplaceProductRanking.calculated_at.desc()));unresolved=session.scalar(select(MarketplaceImportRow).join(MarketplaceImportBatch).where(MarketplaceImportBatch.user_id==user.id,MarketplaceImportRow.proposed_product_id==p.id,MarketplaceImportRow.action=="requires_review"))
    fresh_obs=bool(obs and freshness(obs[0].observed_at,"marketplace_price")["status"]!="stale");fresh_src=bool(src and freshness(src[0].observed_at,"sourcing")["status"]!="stale");stale_count=sum(freshness(x.observed_at,"marketplace_price")["status"]=="stale" for x in obs)+sum(freshness(x.observed_at,"sourcing")["status"]=="stale" for x in src)+sum(freshness(x.observed_at,"competition")["status"]=="stale" for x in comp);identity=bool(p.normalized_name and (p.brand or p.model or p.category));margin=bool(ranking and ranking.margin_score is not None);missing=[]
    for field,ok in (("product_identity",identity),("recent_price",fresh_obs),("current_sourcing",fresh_src),("competition",bool(comp)),("demand",any(x.sold_count is not None or x.review_count is not None or x.rating_count is not None for x in obs)),("margin",margin)):
        if not ok:missing.append(field)
    state="review_required" if unresolved else "stale" if stale_count else "ready" if identity and fresh_obs and fresh_src and margin else "incomplete"
    return {"product_identity_complete":identity,"recent_price_available":fresh_obs,"sourcing_available":bool(src),"competition_available":bool(comp),"demand_available":any(x.sold_count is not None or x.review_count is not None for x in obs),"margin_available":margin,"stale_evidence_count":stale_count,"unresolved_match_count":1 if unresolved else 0,"missing_fields":missing,"warnings":(["Stale evidence exists"] if stale_count else []),"research_readiness":state,"freshness":{"price":freshness(obs[0].observed_at,"marketplace_price") if obs else None,"sourcing":freshness(src[0].observed_at,"sourcing") if src else None,"competition":freshness(comp[0].observed_at,"competition") if comp else None}}
@router.get("/products/{product_id}/history")
def history(product_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    p=owned(session,user.id,product_id);events=[{"type":"product_created","at":p.created_at,"data":{"name":p.normalized_name}}]
    specs=((MarketplaceProductAlias,"alias",MarketplaceProductAlias.product_id),(MarketplaceProductObservation,"observation",MarketplaceProductObservation.product_id),(MarketplaceSourcingOption,"sourcing",MarketplaceSourcingOption.product_id),(MarketplaceCompetitionSignal,"competition",MarketplaceCompetitionSignal.product_id),(MarketplaceProductRanking,"ranking",MarketplaceProductRanking.product_id))
    for model,kind,column in specs:
        for x in session.scalars(select(model).where(column==p.id,model.user_id==user.id)).all():events.append({"type":kind,"at":getattr(x,"created_at",getattr(x,"calculated_at",None)),"data":{"id":str(x.id)}})
    for x in session.scalars(select(MarketplaceProductMergeEvent).where(MarketplaceProductMergeEvent.user_id==user.id,(MarketplaceProductMergeEvent.source_product_id==p.id)|(MarketplaceProductMergeEvent.target_product_id==p.id))).all():events.append({"type":"merge","at":x.created_at,"data":x.snapshot})
    for x in session.scalars(select(MarketplaceProductSplitEvent).where(MarketplaceProductSplitEvent.user_id==user.id,(MarketplaceProductSplitEvent.original_product_id==p.id)|(MarketplaceProductSplitEvent.new_product_id==p.id))).all():events.append({"type":"split","at":x.created_at,"data":x.snapshot})
    for x in session.scalars(select(MarketplaceImportRow).join(MarketplaceImportBatch).where(MarketplaceImportBatch.user_id==user.id,MarketplaceImportRow.proposed_product_id==p.id)).all():events.append({"type":"import","at":x.created_at,"data":{"batch_id":str(x.import_batch_id),"row_number":x.row_number,"action":x.action}})
    watch=session.scalar(select(MarketplaceProductWatchlist).where(MarketplaceProductWatchlist.user_id==user.id,MarketplaceProductWatchlist.product_id==p.id));
    if watch:events.append({"type":"watchlist","at":watch.updated_at,"data":{"active":watch.is_active,"notes":watch.notes}})
    events.sort(key=lambda x:x["at"],reverse=True);return events
def safe_cell(value):
    text="" if value is None else str(value)
    return "'"+text if text.startswith(("=","+","-","@")) else text
@router.get("/exports/{kind}")
def export(kind:str,format:str="json",user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    if kind=="products":rows=[{"name":x.normalized_name,"brand":x.brand,"model":x.model,"category":x.category,"archived":x.is_archived} for x in session.scalars(select(MarketplaceProduct).where(MarketplaceProduct.user_id==user.id)).all()]
    elif kind=="rankings":rows=[{"product_id":str(x.product_id),"research_score":x.overall_research_score,"confidence":x.evidence_confidence_score,"version":x.ranking_version,"calculated_at":x.calculated_at.isoformat()} for x in session.scalars(select(MarketplaceProductRanking).where(MarketplaceProductRanking.user_id==user.id)).all()]
    elif kind=="watchlist":rows=[{"product_id":str(x.product_id),"notes":x.notes,"active":x.is_active} for x in session.scalars(select(MarketplaceProductWatchlist).where(MarketplaceProductWatchlist.user_id==user.id)).all()]
    elif kind=="observations":rows=[{"product_id":str(x.product_id),"marketplace":x.marketplace,"price":x.observed_price,"currency":x.currency_code,"observed_at":x.observed_at.isoformat(),"source_reference":x.source_reference,"evidence":x.evidence} for x in session.scalars(select(MarketplaceProductObservation).where(MarketplaceProductObservation.user_id==user.id)).all()]
    else:raise HTTPException(404,"Unsupported export")
    if format=="json":return rows
    if format!="csv":raise HTTPException(422,"Format must be csv or json")
    headers=list(rows[0]) if rows else ["empty"];out=io.StringIO(newline="");writer=csv.DictWriter(out,fieldnames=headers,lineterminator="\r\n");writer.writeheader()
    for row in rows:writer.writerow({k:safe_cell(json.dumps(v) if isinstance(v,(dict,list)) else v) for k,v in row.items()})
    return Response(out.getvalue(),media_type="text/csv",headers={"Content-Disposition":f'attachment; filename="{kind}.csv"'})
