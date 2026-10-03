import csv,io,os,uuid
from datetime import date,datetime,timezone
from fastapi import APIRouter,Depends,File,Form,HTTPException,UploadFile,status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth import get_current_user,get_session
from app.models import PsxImportBatch,PsxImportRow,PsxPriceObservation,User
from app.psx_service import analyze,normalize
from app.schemas_psx import AnalysisRequest,RowAction
router=APIRouter(prefix="/api/v1/psx",tags=["psx"])
MAX_BYTES=int(os.environ.get("PSX_IMPORT_MAX_BYTES","5242880"));MAX_ROWS=int(os.environ.get("PSX_IMPORT_MAX_ROWS","10000"))
def batch_body(b):return {k:getattr(b,k) for k in ("id","status","source_name","original_filename","total_rows","valid_rows","invalid_rows","warning_rows","committed_rows","created_at")}
def owned(session,user,bid):
    b=session.scalar(select(PsxImportBatch).where(PsxImportBatch.id==bid,PsxImportBatch.user_id==user.id))
    if not b:raise HTTPException(404,"Import batch not found")
    return b
@router.post("/imports",status_code=201)
async def upload(file:UploadFile=File(...),source_name:str=Form(...,min_length=1,max_length=200),idempotency_key:str=Form(...,min_length=8,max_length=120),user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    existing=session.scalar(select(PsxImportBatch).where(PsxImportBatch.user_id==user.id,PsxImportBatch.idempotency_key==idempotency_key))
    if existing:return batch_body(existing)
    name=os.path.basename(file.filename or "prices.csv")
    if not name.lower().endswith(".csv") or file.content_type not in ("text/csv","application/csv","application/vnd.ms-excel"):raise HTTPException(415,"CSV files only")
    raw=await file.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise HTTPException(413,"CSV exceeds configured size limit")
    try:rows=list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    except Exception:raise HTTPException(422,"CSV must be valid UTF-8")
    if not rows or len(rows)>MAX_ROWS:raise HTTPException(422,"CSV must contain between 1 and the configured row limit")
    b=PsxImportBatch(user_id=user.id,idempotency_key=idempotency_key,original_filename=name,source_name=source_name.strip(),status="review",total_rows=len(rows),valid_rows=0,invalid_rows=0,warning_rows=0,committed_rows=0);session.add(b);session.flush();seen=set()
    for number,raw_row in enumerate(rows,2):
        data,errors,warnings=normalize(raw_row,b.source_name);key=(data.get("symbol"),data.get("observation_date"),data.get("adjustment_type"));duplicate="none"
        if not errors and key in seen:errors.append("duplicate symbol/date/adjustment row in file");duplicate="within_file"
        seen.add(key)
        if not errors and session.scalar(select(PsxPriceObservation.id).where(PsxPriceObservation.user_id==user.id,PsxPriceObservation.symbol==key[0],PsxPriceObservation.observation_date==date.fromisoformat(key[1]),PsxPriceObservation.adjustment_type==key[2])):duplicate="existing";warnings.append("matching saved observation requires explicit skip or replace")
        valid=not errors;b.valid_rows+=int(valid);b.invalid_rows+=int(not valid);b.warning_rows+=int(bool(warnings))
        session.add(PsxImportRow(import_batch_id=b.id,row_number=number,raw_data=raw_row,normalized_data=data or None,validation_status="valid" if valid else "invalid",warnings=warnings,errors=errors,duplicate_status=duplicate,action="review" if duplicate!="none" or errors else "import"))
    session.commit();session.refresh(b);return batch_body(b)
@router.get("/imports")
def imports(user:User=Depends(get_current_user),session:Session=Depends(get_session)):return [batch_body(x) for x in session.scalars(select(PsxImportBatch).where(PsxImportBatch.user_id==user.id).order_by(PsxImportBatch.created_at.desc())).all()]
@router.get("/imports/{bid}/preview")
def preview(bid:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    b=owned(session,user,bid);rows=session.scalars(select(PsxImportRow).where(PsxImportRow.import_batch_id==b.id).order_by(PsxImportRow.row_number)).all()
    return {"batch":batch_body(b),"rows":[{"id":x.id,"row_number":x.row_number,"raw_data":x.raw_data,"normalized_data":x.normalized_data,"validation_status":x.validation_status,"warnings":x.warnings,"errors":x.errors,"duplicate_status":x.duplicate_status,"action":x.action} for x in rows]}
@router.put("/imports/{bid}/rows/{rid}")
def resolve(bid:uuid.UUID,rid:uuid.UUID,payload:RowAction,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    b=owned(session,user,bid);row=session.scalar(select(PsxImportRow).where(PsxImportRow.id==rid,PsxImportRow.import_batch_id==b.id))
    if not row:raise HTTPException(404,"Import row not found")
    if payload.action!="skip" and row.validation_status!="valid":raise HTTPException(422,"Invalid rows may only be skipped")
    if payload.action=="replace_existing" and row.duplicate_status!="existing":raise HTTPException(422,"Only saved duplicates can be replaced")
    row.action=payload.action;session.commit();return {"id":row.id,"action":row.action}
@router.post("/imports/{bid}/cancel")
def cancel(bid:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    b=owned(session,user,bid)
    if b.status=="committed":raise HTTPException(409,"Committed imports cannot be cancelled")
    b.status="cancelled";session.commit();return batch_body(b)
@router.post("/imports/{bid}/commit")
def commit(bid:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    b=owned(session,user,bid)
    if b.status=="committed":return batch_body(b)
    if b.status!="review":raise HTTPException(409,"Import is not available for commit")
    rows=session.scalars(select(PsxImportRow).where(PsxImportRow.import_batch_id==b.id).order_by(PsxImportRow.row_number)).all()
    if any(x.action=="review" for x in rows):raise HTTPException(422,"Resolve or skip every invalid or duplicate row")
    try:
        count=0
        for row in rows:
            if row.action=="skip":continue
            d=row.normalized_data
            existing=session.scalar(select(PsxPriceObservation).where(PsxPriceObservation.user_id==user.id,PsxPriceObservation.symbol==d["symbol"],PsxPriceObservation.observation_date==date.fromisoformat(d["observation_date"]),PsxPriceObservation.adjustment_type==d["adjustment_type"]))
            if row.action=="replace_existing":
                if not existing:raise HTTPException(409,"Duplicate disappeared; preview again")
                session.delete(existing);session.flush()
            session.add(PsxPriceObservation(user_id=user.id,import_batch_id=b.id,symbol=d["symbol"],observation_date=date.fromisoformat(d["observation_date"]),open_price=d["open"],high_price=d["high"],low_price=d["low"],close_price=d["close"],volume=d["volume"],currency=d["currency"],source_name=d["source"],adjustment_type=d["adjustment_type"],verification_status="unverified"));count+=1
        b.status="committed";b.committed_rows=count;b.committed_at=datetime.now(timezone.utc);session.commit()
    except Exception:session.rollback();raise
    return batch_body(b)
@router.get("/instruments")
def instruments(user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    rows=session.scalars(select(PsxPriceObservation).where(PsxPriceObservation.user_id==user.id).order_by(PsxPriceObservation.symbol,PsxPriceObservation.observation_date)).all();out={}
    for x in rows:out.setdefault(x.symbol,[]).append(x)
    return [{"symbol":k,"start_date":v[0].observation_date,"end_date":v[-1].observation_date,"observations":len(v),"sources":sorted({x.source_name for x in v}),"adjustment_types":sorted({x.adjustment_type for x in v}),"verification_status":"unverified"} for k,v in out.items()]
@router.get("/instruments/{symbol}/history")
def history(symbol:str,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    return session.scalars(select(PsxPriceObservation).where(PsxPriceObservation.user_id==user.id,PsxPriceObservation.symbol==symbol.upper()).order_by(PsxPriceObservation.observation_date)).all()
@router.post("/analysis")
def analysis(payload:AnalysisRequest,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    results=[]
    for symbol in payload.symbols:
        stmt=select(PsxPriceObservation).where(PsxPriceObservation.user_id==user.id,PsxPriceObservation.symbol==symbol)
        if payload.start_date:stmt=stmt.where(PsxPriceObservation.observation_date>=payload.start_date)
        if payload.end_date:stmt=stmt.where(PsxPriceObservation.observation_date<=payload.end_date)
        rows=session.scalars(stmt.order_by(PsxPriceObservation.observation_date)).all()
        try:results.append(analyze(rows,payload.lookback,payload.as_of_date))
        except ValueError as e:results.append({"symbol":symbol,"unavailable":True,"reason":str(e)})
    return {"results":results,"comparison_label":"Historical evidence comparison","recommendation":None,"trade_created":False}
