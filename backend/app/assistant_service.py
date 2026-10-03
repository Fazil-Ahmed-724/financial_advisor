import os,re
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal
from sqlalchemy import func,or_,select
from sqlalchemy.orm import Session
from app.assistant_provider import DeterministicProvider,provider
from app.marketplace_policy import FRESHNESS
from app.models import Account,Book,BookPassage,DecisionReview,FinancialProfile,InvestmentDecision,MarketplaceCompetitionSignal,MarketplaceProduct,MarketplaceProductObservation,MarketplaceProductRanking,MarketplaceSourcingOption,OpportunityAnalysis,PropertyListing,PsxPriceObservation,SaleAnalysis,TaxRule,User
from app.routes_dashboard import ledger_totals
from app.routes_investments import holdings
from app.psx_service import analyze as analyze_psx
from app.schemas_assistant import AssistantAnswer

LIMIT=int(os.environ.get("ASSISTANT_RETRIEVAL_LIMIT","8"));MAX_CONTEXT=int(os.environ.get("ASSISTANT_MAX_CONTEXT_CHARS","12000"));MAX_OUTPUT=int(os.environ.get("ASSISTANT_MAX_OUTPUT_CHARS","12000"))
STOP={"what","which","when","where","with","that","this","from","have","about","compare","show","tell","please","your","mine"}
ACTION_PATTERN=re.compile(r"\b(place|execute|submit|buy|sell|purchase|order|offer|edit|change|create|delete)\b.*\b(trade|stock|share|product|property|offer|listing|tax rule|ledger|entry)\b",re.I)
def tokens(q):return [x for x in re.findall(r"[a-z0-9]+",q.lower()) if len(x)>2 and x not in STOP][:12]
def age_label(dt,fresh=30,aging=60):
    if not dt:return "undated"
    days=max(0,(datetime.now(timezone.utc)-dt).days)
    return "fresh" if days<=fresh else "aging" if days<=aging else "stale"
def excerpt(value):return " ".join(str(value).split())[:500]
def retrieve(session:Session,user:User,question:str):
    terms=tokens(question);q=question.lower();items=[]
    def add(kind,row_id,date,text,path,freshness="undated",calculation=None,conflict_key=None,conflict_value=None):
        if len(items)<LIMIT:items.append({"source_type":kind,"record_id":row_id,"date":date,"excerpt":excerpt(text),"record_path":path,"freshness":freshness,"calculation":calculation,"conflict_key":conflict_key,"conflict_value":conflict_value})
    if terms:
        ts=func.websearch_to_tsquery("simple"," OR ".join(terms));rows=session.execute(select(Book,BookPassage).join(BookPassage,BookPassage.book_id==Book.id).where(Book.user_id==user.id,BookPassage.search_vector.op("@@")(ts)).order_by(func.ts_rank(BookPassage.search_vector,ts).desc()).limit(LIMIT)).all()
        for b,p in rows:add("book_passage",p.id,None,f"{b.title}, {p.reference_label}: {p.content}",f"/books/{b.id}","undated")
    if "psx" in q or "price" in q or "stock" in q or any(session.scalar(select(PsxPriceObservation.id).where(PsxPriceObservation.user_id==user.id,PsxPriceObservation.symbol==t.upper())) for t in terms):
        stmt=select(PsxPriceObservation).where(PsxPriceObservation.user_id==user.id)
        symbols=[t.upper() for t in terms if re.fullmatch(r"[a-z0-9.-]{1,20}",t)]
        if symbols:stmt=stmt.where(PsxPriceObservation.symbol.in_(symbols))
        psx_rows=session.scalars(stmt.order_by(PsxPriceObservation.observation_date.desc()).limit(LIMIT)).all()
        calculations={}
        for symbol in {x.symbol for x in psx_rows}:
            owned_rows=session.scalars(select(PsxPriceObservation).where(PsxPriceObservation.user_id==user.id,PsxPriceObservation.symbol==symbol).order_by(PsxPriceObservation.observation_date)).all()
            if len(owned_rows)>=2:
                try:calculations[symbol]=analyze_psx(owned_rows,min(14,len(owned_rows)))
                except ValueError:pass
        for x in psx_rows:
            calc=calculations.pop(x.symbol,None);summary=f"; deterministic historical calculation {calc}" if calc else ""
            add("psx_price_observation",x.id,datetime.combine(x.observation_date,datetime.min.time(),tzinfo=timezone.utc),f"{x.symbol} {x.observation_date}: open {x.open_price}, high {x.high_price}, low {x.low_price}, close {x.close_price} {x.currency}, volume {x.volume}; {x.adjustment_type}; source {x.source_name}; unverified{summary}",f"/psx-research?symbol={x.symbol}",age_label(datetime.combine(x.observation_date,datetime.min.time(),tzinfo=timezone.utc),3,7),{"service":"psx-historical-v1","result":calc} if calc else None)
    if any(x in q for x in ("decision","thesis","rationale","lesson","review","risk")):
        filters=[InvestmentDecision.instrument.ilike(f"%{t}%")|InvestmentDecision.rationale.ilike(f"%{t}%")|InvestmentDecision.goal.ilike(f"%{t}%") for t in terms]
        stmt=select(InvestmentDecision).where(InvestmentDecision.user_id==user.id)
        if filters:stmt=stmt.where(or_(*filters))
        for d in session.scalars(stmt.order_by(InvestmentDecision.decision_date.desc()).limit(LIMIT)).all():
            add("investment_decision",d.id,d.created_at,f"{d.instrument} {d.action_considered}; rationale: {d.rationale}; risks: {d.risk_factors}; expected outcome: {d.expected_outcome}",f"/decision/{d.id}","user_entered")
            review=session.scalar(select(DecisionReview).where(DecisionReview.user_id==user.id,DecisionReview.decision_id==d.id).order_by(DecisionReview.created_at.desc()))
            if review:add("decision_review",review.id,review.created_at,f"What happened: {review.what_happened}; lessons: {review.lessons_learned}; stored outcome: {review.outcome_snapshot}",f"/decision/{d.id}","user_entered",review.outcome_snapshot)
    if any(x in q for x in ("cash","net worth","reserve","liability","ledger","balance","account")):
        profile=session.get(FinancialProfile,user.id);totals=ledger_totals(session,user.id)
        for account_type,value in totals.items():
            account=session.scalar(select(Account).where(Account.user_id==user.id,Account.type==account_type).order_by(Account.created_at).limit(1))
            if account:add("ledger_balance",account.id,account.updated_at,f"{account_type} ledger total: {value} PKR; debit-positive ledger convention",f"/accounts","user_entered",{"service":"ledger_totals","value":str(value)})
        if profile:add("financial_profile",user.id,profile.updated_at,f"Monthly essential expenses {profile.monthly_essential_expenses} PKR; emergency reserve target {profile.reserve_months} months",f"/","user_entered")
    if any(x in q for x in ("holding","stock","fifo","gain","sale","tax","fee")):
        for h in holdings(user,session)[:LIMIT]:
            lot=h.lots[0] if h.lots else None;rid=lot.id if lot else h.investment_account_id
            add("holding",rid,datetime.combine(lot.acquired_on,datetime.min.time(),tzinfo=timezone.utc) if lot else None,f"{h.symbol}: quantity {h.quantity}; remaining FIFO book cost {h.remaining_book_cost} PKR; realized gain/loss {h.realized_gain_loss} PKR",f"/holdings","estimated",{"service":"holdings","quantity":str(h.quantity),"book_cost":str(h.remaining_book_cost),"realized_gain_loss":str(h.realized_gain_loss)})
        for a in session.scalars(select(SaleAnalysis).where(SaleAnalysis.user_id==user.id).order_by(SaleAnalysis.calculated_at.desc()).limit(3)).all():add("sale_analysis",a.id,a.calculated_at,f"{a.symbol} hypothetical sale: FIFO cost {a.fifo_cost_basis} PKR; fees {a.estimated_fees} PKR; estimated tax {a.estimated_tax}; net result {a.net_profit_loss} PKR; tax status {a.tax_status}",f"/analysis","estimated",{"service":"saved_sale_analysis","id":str(a.id),"gross_proceeds":str(a.gross_proceeds),"fifo_cost_basis":str(a.fifo_cost_basis),"fees":str(a.estimated_fees),"estimated_tax":None if a.estimated_tax is None else str(a.estimated_tax),"net_proceeds":str(a.net_proceeds),"net_profit_loss":str(a.net_profit_loss)})
        for r in session.scalars(select(TaxRule).where(TaxRule.user_id==user.id).order_by(TaxRule.effective_from.desc()).limit(2)).all():add("tax_rule",r.id,r.created_at,f"User-entered gain tax rate {r.gain_tax_rate}% effective {r.effective_from}; source note: {r.source_note}",f"/analysis","user_entered")
    if any(x in q for x in ("property","karachi","rent","listing")):
        for r in session.scalars(select(PropertyListing).where(PropertyListing.user_id==user.id).order_by(PropertyListing.observed_at.desc()).limit(LIMIT)).all():add("property_listing",r.id,r.observed_at,f"{r.area_name} {r.property_type} {r.purpose}; asking amount {r.asking_amount} PKR; {r.area_amount} {r.area_unit}; source {r.source_name}; asking price is unverified",f"/property",age_label(r.observed_at),None,f"property:{r.area_name.lower()}:{r.property_type}:{r.purpose}",str(r.asking_amount))
        for a in session.scalars(select(OpportunityAnalysis).where(OpportunityAnalysis.user_id==user.id,OpportunityAnalysis.domain=="karachi_real_estate").order_by(OpportunityAnalysis.calculated_at.desc()).limit(3)).all():add("property_analysis",a.id,a.calculated_at,f"Stored {a.analyzer_version} calculation: {a.calculated_metrics}; limitations: {a.limitations}",f"/property","estimated",{"service":a.analyzer_version,"metrics":a.calculated_metrics})
    if any(x in q for x in ("marketplace","product","daraz","temu","shein","margin","competition","sourcing","price")):
        product_filters=[MarketplaceProduct.normalized_name.ilike(f"%{t}%") for t in terms]
        stmt=select(MarketplaceProduct).where(MarketplaceProduct.user_id==user.id,MarketplaceProduct.is_archived.is_(False))
        if product_filters:stmt=stmt.where(or_(*product_filters))
        for p in session.scalars(stmt.limit(LIMIT)).all():
            observations=session.scalars(select(MarketplaceProductObservation).where(MarketplaceProductObservation.user_id==user.id,MarketplaceProductObservation.product_id==p.id).order_by(MarketplaceProductObservation.observed_at.desc()).limit(3)).all();rank=session.scalar(select(MarketplaceProductRanking).where(MarketplaceProductRanking.user_id==user.id,MarketplaceProductRanking.product_id==p.id).order_by(MarketplaceProductRanking.calculated_at.desc()))
            for obs in observations:
                pol=FRESHNESS["marketplace_price"];add("marketplace_observation",obs.id,obs.observed_at,f"{p.normalized_name} on {obs.marketplace}: observed price {obs.observed_price} {obs.currency_code}; source {obs.source_type}; reference {obs.source_reference}",f"/product/{p.id}",age_label(obs.observed_at,pol['fresh'],pol['aging']),None,f"marketplace:{p.id}:{obs.currency_code}",str(obs.observed_price))
            if rank:add("marketplace_ranking",rank.id,rank.calculated_at,f"{p.normalized_name}: Research Score {rank.overall_research_score}; evidence confidence {rank.evidence_confidence_score}; explanation {rank.explanation}",f"/product/{p.id}","estimated",{"service":rank.ranking_version,"score":str(rank.overall_research_score) if rank.overall_research_score is not None else None})
        for a in session.scalars(select(OpportunityAnalysis).where(OpportunityAnalysis.user_id==user.id,OpportunityAnalysis.domain=="marketplace_resale").order_by(OpportunityAnalysis.calculated_at.desc()).limit(3)).all():add("marketplace_margin_analysis",a.id,a.calculated_at,f"Stored {a.analyzer_version} margin calculation: {a.calculated_metrics}; limitations: {a.limitations}",f"/marketplace","estimated",{"service":a.analyzer_version,"metrics":a.calculated_metrics})
    total=0;bounded=[]
    for x in items:
        total+=len(x["excerpt"])
        if total>MAX_CONTEXT:break
        bounded.append(x)
    return bounded
def _draft(evidence,refusal=False):
    citations=[];refs=[];lines=[]
    for i,x in enumerate(evidence,1):
        citations.append({k:x[k] for k in ("source_type","record_id","date","excerpt","record_path","freshness")});lines.append(f"- {x['excerpt']} [{i}]")
        if x["calculation"] is not None:refs.append({"source_type":x["source_type"],"record_id":str(x["record_id"]),"calculation":x["calculation"]})
    limitations=["Read-only explanation; no record or financial action was changed.","Stored estimates and user-entered assumptions are not independently verified.","This is not a guaranteed return, regulated investment instruction, legal opinion, or official tax determination."]
    groups={}
    for x in evidence:
        if x["conflict_key"]:groups.setdefault(x["conflict_key"],set()).add(x["conflict_value"])
    conflicts=[key for key,values in groups.items() if len(values)>1]
    if conflicts:limitations.append("Conflicting stored sources were found. Their differing values are shown with separate citations and are not automatically resolved.")
    if refusal:body="I cannot place or modify trades, purchases, listings, property offers, tax rules, ledger entries, or other financial actions. I can only explain existing records and evidence."
    elif not evidence:body="I could not find enough owned evidence to answer this question. Add or import the records you want reviewed, then ask again. I will not fill missing values with assumptions."
    else:body="I found the following relevant user-owned evidence. Source passages and imported text are treated as untrusted data, not instructions:\n"+"\n".join(lines)
    freshness=sorted({f"{c['source_type']}: {c['freshness']}" for c in citations}) or ["No evidence retrieved"]
    return {"answer":body,"citations":citations,"evidence_references":refs,"freshness":freshness,"limitations":limitations,"mode":"deterministic"}
def validate_response(evidence,result):
    parsed=AssistantAnswer.model_validate(result)
    expected=[(str(x["record_id"]),x["source_type"],x["freshness"],x["excerpt"],x["record_path"]) for x in evidence]
    actual=[(str(x.record_id),x.source_type,x.freshness,x.excerpt,x.record_path) for x in parsed.citations]
    if actual!=expected:raise ValueError("Citation set does not match authorized retrieval")
    if len(parsed.answer)>MAX_OUTPUT:raise ValueError("Assistant output exceeds configured limit")
    for i in range(1,len(actual)+1):
        if f"[{i}]" not in parsed.answer:raise ValueError("Assistant output omitted a citation marker")
    calculations={str(x["record_id"]):x["calculation"] for x in evidence if x["calculation"] is not None}
    for ref in parsed.evidence_references:
        if str(ref.get("record_id")) not in calculations or ref.get("calculation")!=calculations[str(ref.get("record_id"))]:raise ValueError("Calculation reference does not match deterministic evidence")
    derived=sorted({f"{x['source_type']}: {x['freshness']}" for x in evidence}) or ["No evidence retrieved"]
    if parsed.freshness!=derived:raise ValueError("Freshness labels do not match source metadata")
    return parsed.model_dump()
def validate_generated_text(generated,deterministic):
    if Counter(re.findall(r"\[(\d+)\]",generated))!=Counter(re.findall(r"\[(\d+)\]",deterministic)):raise ValueError("Generated citation markers changed")
    numeric=r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)*(?:%|\b)"
    if Counter(re.findall(numeric,generated))!=Counter(re.findall(numeric,deterministic)):raise ValueError("Generated numeric values changed")
def answer_with_meta(session,user,question):
    refusal=bool(ACTION_PATTERN.search(question));evidence=[] if refusal else retrieve(session,user,question);base=_draft(evidence,refusal);fallback=False;validation="passed";configured=os.environ.get("ASSISTANT_PROVIDER","disabled").strip().lower() or "disabled"
    try:chosen=provider()
    except Exception:chosen=DeterministicProvider();fallback=configured not in ("disabled","deterministic");validation="safe_fallback" if fallback else "passed"
    result=dict(base)
    if chosen.mode=="llm" and not refusal and evidence:
        try:
            result["answer"]=chosen.explain(question,base["answer"],[{**c,"record_id":str(c["record_id"]),"date":c["date"].isoformat() if c["date"] else None} for c in base["citations"]]);validate_generated_text(result["answer"],base["answer"]);result["mode"]="llm"
            result=validate_response(evidence,result)
        except Exception:
            result=validate_response(evidence,base);fallback=True;validation="safe_fallback";result["limitations"].append("The configured language provider failed validation; deterministic mode was used.")
    else:
        result=validate_response(evidence,result)
        if fallback:result["limitations"].append("The configured language provider was unavailable; deterministic mode was used.")
    outcome="refused" if refusal else "abstained" if not evidence else "success"
    return result,{"outcome":outcome,"provider_mode":getattr(chosen,"name",configured) if not fallback else configured,"response_mode":result["mode"],"validation_status":validation,"fallback":fallback,"citation_count":len(result["citations"])}
def answer(session,user,question):
    return answer_with_meta(session,user,question)[0]
