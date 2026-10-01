import os,time,uuid
from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.assistant_service import answer_with_meta
from app.auth import get_current_user,get_session
from app.models import AssistantConversation,AssistantMessage,AuditEvent,User
from app.notification_service import enqueue_event
from app.schemas_assistant import AssistantAnswer,ChatRequest,ConversationCreate,ConversationResponse,FeedbackCreate,FeedbackExportRequest,FeedbackResponse,FeedbackUpdate,MessageResponse,MetricsResponse

router=APIRouter(prefix="/assistant",tags=["read-only research assistant"])
MAX_CONVERSATIONS=int(os.environ.get("ASSISTANT_MAX_CONVERSATIONS","20"));MAX_MESSAGES=int(os.environ.get("ASSISTANT_MAX_MESSAGES_PER_CONVERSATION","50"))
def owned(session,user_id,conversation_id):
    row=session.scalar(select(AssistantConversation).where(AssistantConversation.id==conversation_id,AssistantConversation.user_id==user_id))
    if not row:raise HTTPException(404,"Conversation not found")
    return row
def message_body(row):
    response=AssistantAnswer.model_validate(row.response_data) if row.response_data else None
    return MessageResponse(id=row.id,role=row.role,content=row.content,created_at=row.created_at,response=response)
def conversation_body(session,row,include_messages=False):
    messages=[] if not include_messages else [message_body(x) for x in session.scalars(select(AssistantMessage).where(AssistantMessage.conversation_id==row.id,AssistantMessage.user_id==row.user_id).order_by(AssistantMessage.sequence)).all()]
    return ConversationResponse(id=row.id,title=row.title,created_at=row.created_at,updated_at=row.updated_at,messages=messages)
@router.post("/conversations",response_model=ConversationResponse,status_code=201)
def create_conversation(payload:ConversationCreate,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    count=session.scalar(select(func.count()).select_from(AssistantConversation).where(AssistantConversation.user_id==user.id))
    if count>=MAX_CONVERSATIONS:raise HTTPException(429,"Conversation limit reached; delete an old conversation first")
    title=" ".join((payload.title or "Research conversation").split()) or "Research conversation";row=AssistantConversation(user_id=user.id,title=title);session.add(row);session.commit();session.refresh(row);return conversation_body(session,row)
@router.get("/conversations",response_model=list[ConversationResponse])
def conversations(user:User=Depends(get_current_user),session:Session=Depends(get_session)):return [conversation_body(session,x) for x in session.scalars(select(AssistantConversation).where(AssistantConversation.user_id==user.id).order_by(AssistantConversation.updated_at.desc())).all()]
@router.get("/conversations/{conversation_id}",response_model=ConversationResponse)
def conversation(conversation_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):return conversation_body(session,owned(session,user.id,conversation_id),True)
@router.delete("/conversations/{conversation_id}",status_code=204)
def delete_conversation(conversation_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    row=owned(session,user.id,conversation_id);session.delete(row);session.commit()
@router.post("/conversations/{conversation_id}/messages",response_model=MessageResponse,status_code=201)
def chat(conversation_id:uuid.UUID,payload:ChatRequest,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    conversation=session.scalar(select(AssistantConversation).where(AssistantConversation.id==conversation_id,AssistantConversation.user_id==user.id).with_for_update())
    if not conversation:raise HTTPException(404,"Conversation not found")
    count=session.scalar(select(func.count()).select_from(AssistantMessage).where(AssistantMessage.conversation_id==conversation.id,AssistantMessage.user_id==user.id))
    if count+2>MAX_MESSAGES:raise HTTPException(429,"Message limit reached; start a new conversation")
    question=" ".join(payload.message.split());user_message=AssistantMessage(conversation_id=conversation.id,user_id=user.id,sequence=count+1,role="user",content=question);session.add(user_message);session.flush();started=time.perf_counter()
    try:result,meta=answer_with_meta(session,user,question)
    except Exception:
        session.rollback();latency=round((time.perf_counter()-started)*1000,2);session.add(AuditEvent(user_id=user.id,event_type="assistant_request",entity_type="assistant_conversation",entity_id=conversation_id,details={"outcome":"failed","provider_mode":"unknown","response_mode":"none","latency_ms":latency,"citation_count":0,"validation_status":"failed","fallback":True}));session.commit();raise HTTPException(503,"Assistant response failed safely") from None
    assistant=AssistantMessage(conversation_id=conversation.id,user_id=user.id,sequence=count+2,role="assistant",content=result["answer"],response_data=jsonable_encoder(result));conversation.updated_at=datetime.now(timezone.utc);session.add(assistant);session.flush();meta["latency_ms"]=round((time.perf_counter()-started)*1000,2);session.add(AuditEvent(user_id=user.id,event_type="assistant_request",entity_type="assistant_message",entity_id=assistant.id,details=meta))
    if payload.notify_when_ready:enqueue_event(session,user.id,"assistant_response_ready",str(assistant.id),f"/assistant?conversationId={conversation.id}")
    session.commit();session.refresh(assistant);return message_body(assistant)
@router.post("/messages/{message_id}/feedback",status_code=201)
def feedback(message_id:uuid.UUID,payload:FeedbackCreate,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    message=session.scalar(select(AssistantMessage).where(AssistantMessage.id==message_id,AssistantMessage.user_id==user.id,AssistantMessage.role=="assistant").with_for_update())
    if not message:raise HTTPException(404,"Assistant message not found")
    duplicate=session.scalar(select(AuditEvent.id).where(AuditEvent.user_id==user.id,AuditEvent.event_type=="assistant_response_reported",AuditEvent.entity_type=="assistant_message",AuditEvent.entity_id==message.id))
    if duplicate:raise HTTPException(409,"Feedback already exists for this response; update the existing report")
    response=AssistantAnswer.model_validate(message.response_data);request_event=session.scalar(select(AuditEvent).where(AuditEvent.user_id==user.id,AuditEvent.event_type=="assistant_request",AuditEvent.entity_id==message.id).order_by(AuditEvent.created_at.desc()))
    calculation_services=sorted({str(x.get("calculation",{}).get("service")) for x in response.evidence_references if x.get("calculation",{}).get("service")})
    metadata=request_event.details if request_event else {}
    now=datetime.now(timezone.utc);details={"category":payload.category,"comment":payload.comment,"status":"submitted","review_note":None,"fixture_selected":False,"response_mode":response.mode,"citation_ids":[str(x.record_id) for x in response.citations],"source_dates":[x.date.isoformat() for x in response.citations if x.date],"source_types":sorted({x.source_type for x in response.citations}),"freshness":response.freshness,"calculation_services":calculation_services,"evaluation_metadata":{key:metadata.get(key) for key in ("provider_mode","response_mode","validation_status","fallback","citation_count")},"contains_prompt_or_answer":False,"contains_source_text":False,"financial_action":False,"updated_at":now.isoformat()};event=AuditEvent(user_id=user.id,event_type="assistant_response_reported",entity_type="assistant_message",entity_id=message.id,details=details);session.add(event);session.commit();session.refresh(event);return feedback_body(event)
def feedback_owned(session,user_id,feedback_id):
    event=session.scalar(select(AuditEvent).where(AuditEvent.id==feedback_id,AuditEvent.user_id==user_id,AuditEvent.event_type=="assistant_response_reported",AuditEvent.entity_type=="assistant_message"))
    if not event:raise HTTPException(404,"Feedback not found")
    return event
def feedback_category(value):return {"incorrect_citation":"inaccurate","unsupported_claim":"unsupported","stale_or_missing":"stale","calculation_error":"inaccurate","other":"confusing"}.get(value,value or "confusing")
def feedback_body(event):
    d=event.details;category=feedback_category(d.get("category"));updated=d.get("updated_at")
    try:updated_at=datetime.fromisoformat(updated) if updated else event.created_at
    except (TypeError,ValueError):updated_at=event.created_at
    return FeedbackResponse(id=event.id,message_id=event.entity_id,category=category,comment=d.get("comment"),status=d.get("status","submitted"),review_note=d.get("review_note"),fixture_selected=bool(d.get("fixture_selected",False)),response_mode=d.get("response_mode","unknown"),citation_ids=[uuid.UUID(x) for x in d.get("citation_ids",[])],source_dates=[datetime.fromisoformat(x) for x in d.get("source_dates",[])],freshness=d.get("freshness",[]),evaluation_metadata=d.get("evaluation_metadata",{}),created_at=event.created_at,updated_at=updated_at,financial_action=False)
@router.get("/feedback",response_model=list[FeedbackResponse])
def feedback_list(user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    rows=session.scalars(select(AuditEvent).where(AuditEvent.user_id==user.id,AuditEvent.event_type=="assistant_response_reported",AuditEvent.entity_type=="assistant_message").order_by(AuditEvent.created_at.desc())).all();return [feedback_body(x) for x in rows]
@router.post("/feedback/export")
def feedback_export(payload:FeedbackExportRequest,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    rows=session.scalars(select(AuditEvent).where(AuditEvent.id.in_(payload.feedback_ids),AuditEvent.user_id==user.id,AuditEvent.event_type=="assistant_response_reported",AuditEvent.entity_type=="assistant_message")).all()
    if len(rows)!=len(payload.feedback_ids):raise HTTPException(404,"One or more feedback reports were not found")
    by_id={x.id:x for x in rows};ordered=[by_id[x] for x in payload.feedback_ids]
    if any(x.details.get("status","submitted")!="reviewed" or not x.details.get("fixture_selected",False) for x in ordered):raise HTTPException(422,"Every exported report must be reviewed and explicitly selected")
    behavior={"helpful":"preserve_supported_behavior","inaccurate":"reject_inaccurate_claim","unsupported":"abstain_without_support","stale":"label_stale_evidence","confusing":"improve_explanation_clarity","missing_evidence":"identify_missing_evidence"};cases=[]
    for index,event in enumerate(ordered,1):
        d=event.details;meta=d.get("evaluation_metadata",{});category=feedback_category(d.get("category"));cases.append({"case_id":f"reviewed-case-{index:03d}","category":category,"expected_behavior":behavior[category],"response_mode":d.get("response_mode","unknown"),"source_types":d.get("source_types",[]),"freshness":d.get("freshness",[]),"citation_count":len(d.get("citation_ids",[])),"calculation_services":d.get("calculation_services",[]),"validation_status":meta.get("validation_status"),"fallback":bool(meta.get("fallback",False))})
    return {"format_version":"assistant-feedback-regression-v1","sanitized":True,"confirmed":True,"automatic_training":False,"automatic_prompt_or_provider_change":False,"requires_manual_test_implementation":True,"cases":cases}
@router.put("/feedback/{feedback_id}",response_model=FeedbackResponse)
def feedback_update(feedback_id:uuid.UUID,payload:FeedbackUpdate,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    event=feedback_owned(session,user.id,feedback_id);details=dict(event.details);previous_status=details.get("status","submitted");changes=payload.model_dump(exclude_unset=True);effective_status=changes.get("status",previous_status)
    if changes.get("fixture_selected") is True and effective_status!="reviewed":raise HTTPException(422,"Review the report before selecting it for fixture export")
    if effective_status!="reviewed":changes["fixture_selected"]=False
    details.update(changes);details["updated_at"]=datetime.now(timezone.utc).isoformat();details["contains_prompt_or_answer"]=False;details["contains_source_text"]=False;details["financial_action"]=False;event.details=details
    if effective_status!=previous_status and effective_status in ("reviewed","dismissed"):enqueue_event(session,user.id,"feedback_review_status_changed",f"{event.id}:{effective_status}","/assistant-feedback")
    session.commit();session.refresh(event);return feedback_body(event)
@router.delete("/feedback/{feedback_id}",status_code=204)
def feedback_delete(feedback_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    event=feedback_owned(session,user.id,feedback_id);session.delete(event);session.commit()
@router.get("/metrics",response_model=MetricsResponse)
def metrics(user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    events=session.scalars(select(AuditEvent).where(AuditEvent.user_id==user.id,AuditEvent.event_type=="assistant_request")).all();outcomes={x:0 for x in ("success","refused","abstained","failed")};modes={};latency=0.0;citations=0;fallbacks=0
    for event in events:
        d=event.details;outcomes[d.get("outcome","failed")]=outcomes.get(d.get("outcome","failed"),0)+1;modes[d.get("response_mode","none")]=modes.get(d.get("response_mode","none"),0)+1;latency+=float(d.get("latency_ms",0));citations+=int(d.get("citation_count",0));fallbacks+=bool(d.get("fallback",False))
    total=len(events);return MetricsResponse(total_requests=total,successful=outcomes["success"],refused=outcomes["refused"],abstained=outcomes["abstained"],failed=outcomes["failed"],fallbacks=fallbacks,average_latency_ms=round(latency/total,2) if total else 0,total_citations=citations,provider_modes=modes)
