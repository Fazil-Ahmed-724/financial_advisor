from datetime import date
import uuid
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth import get_current_user,get_session
from app.models import Account,AuditEvent,InvestmentTrade,PortfolioInstrumentMapping,PsxPriceObservation,User
from app.portfolio_service import adjusted_risk,positions,sale_estimate
from app.schemas_portfolio import MappingPayload,SaleEstimatePayload
router=APIRouter(prefix="/api/v1/portfolio-analysis",tags=["portfolio-analysis"])
def body(x):return {"id":x.id,"investment_account_id":x.investment_account_id,"holding_symbol":x.holding_symbol,"psx_symbol":x.psx_symbol,"confirmation_note":x.confirmation_note,"confirmed_at":x.confirmed_at,"updated_at":x.updated_at}
@router.get("/mappings")
def mappings(user:User=Depends(get_current_user),session:Session=Depends(get_session)):return [body(x) for x in session.scalars(select(PortfolioInstrumentMapping).where(PortfolioInstrumentMapping.user_id==user.id).order_by(PortfolioInstrumentMapping.holding_symbol)).all()]
@router.get("/mappings/{mapping_id}/audit")
def mapping_audit(mapping_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    row=session.scalar(select(PortfolioInstrumentMapping).where(PortfolioInstrumentMapping.id==mapping_id,PortfolioInstrumentMapping.user_id==user.id))
    if not row:raise HTTPException(404,"Mapping not found")
    events=session.scalars(select(AuditEvent).where(AuditEvent.user_id==user.id,AuditEvent.entity_type=="portfolio_instrument_mapping",AuditEvent.entity_id==row.id).order_by(AuditEvent.created_at)).all()
    return [{"id":x.id,"event_type":x.event_type,"details":x.details,"created_at":x.created_at} for x in events]
@router.put("/mappings")
def confirm_mapping(payload:MappingPayload,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    account=session.scalar(select(Account).where(Account.id==payload.investment_account_id,Account.user_id==user.id,Account.type=="investment"))
    if not account:raise HTTPException(404,"Investment account not found")
    if not session.scalar(select(InvestmentTrade.id).where(InvestmentTrade.user_id==user.id,InvestmentTrade.investment_account_id==account.id,InvestmentTrade.symbol==payload.holding_symbol).limit(1)):raise HTTPException(422,"The holding symbol has no owned external trade records")
    if not session.scalar(select(PsxPriceObservation.id).where(PsxPriceObservation.user_id==user.id,PsxPriceObservation.symbol==payload.psx_symbol).limit(1)):raise HTTPException(422,"The PSX symbol has no owned imported observations")
    row=session.scalar(select(PortfolioInstrumentMapping).where(PortfolioInstrumentMapping.user_id==user.id,PortfolioInstrumentMapping.investment_account_id==account.id,PortfolioInstrumentMapping.holding_symbol==payload.holding_symbol));old=row.psx_symbol if row else None
    if row:row.psx_symbol=payload.psx_symbol;row.confirmation_note=payload.confirmation_note
    else:row=PortfolioInstrumentMapping(user_id=user.id,investment_account_id=account.id,holding_symbol=payload.holding_symbol,psx_symbol=payload.psx_symbol,confirmation_note=payload.confirmation_note);session.add(row);session.flush()
    session.add(AuditEvent(user_id=user.id,event_type="portfolio_mapping_confirmed",entity_type="portfolio_instrument_mapping",entity_id=row.id,details={"investment_account_id":str(account.id),"holding_symbol":payload.holding_symbol,"previous_psx_symbol":old,"psx_symbol":payload.psx_symbol,"user_confirmed":True}));session.commit();session.refresh(row);return body(row)
@router.get("")
def portfolio(as_of_date:date|None=Query(None),lookback:int=Query(30,ge=2,le=252),user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    selected=as_of_date or date.today();items,totals=positions(session,user,selected,as_of_date is not None)
    for item in items:item["historical_adjusted_analysis"]=adjusted_risk(session,user.id,item["psx_symbol"],selected,lookback) if item["psx_symbol"] else {"available":False,"reason":"No confirmed PSX mapping","observation_ids":[]}
    return {"as_of_date":selected,"scenario_type":"hypothetical_historical" if as_of_date else "latest_recorded_evidence","positions":items,"totals":totals,"methodology":{"holdings":"External BUY/SELL records replayed chronologically with FIFO through as_of_date.","valuation":"Quantity × latest owned raw closing observation on or before as_of_date.","weight":"Available observed position value / total available observed portfolio value × 100.","concentration_hhi":"Sum of squared available position weights.","adjusted_risk":"Only adjusted observations on or before as_of_date; no later trades or prices."},"limitations":["Last observed values are not live market values.","Missing or stale prices remain labeled and are not represented as current.","Historical results exclude unrepresented dividends, corporate actions, taxes, fees, liquidity, and survivorship effects.","No ledger, trade, lot, tax rule, or holding is changed."],"financial_records_changed":False}
@router.post("/sale-estimate")
def estimate(payload:SaleEstimatePayload,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    selected=payload.as_of_date or date.today()
    try:return sale_estimate(session,user,payload.investment_account_id,payload.holding_symbol,payload.quantity,payload.estimated_fees,selected,payload.as_of_date is not None)
    except ValueError as e:raise HTTPException(422,str(e))
