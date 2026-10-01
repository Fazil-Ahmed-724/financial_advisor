import os,time,uuid
from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.assistant_service import answer_with_meta
from app.auth import get_current_user,get_session
from app.models import AssistantConversation,AssistantMessage,AuditEvent,User
from app.schemas_assistant import AssistantAnswer,ChatRequest,ConversationCreate,ConversationResponse,FeedbackCreate,MessageResponse,MetricsResponse

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
    assistant=AssistantMessage(conversation_id=conversation.id,user_id=user.id,sequence=count+2,role="assistant",content=result["answer"],response_data=jsonable_encoder(result));conversation.updated_at=datetime.now(timezone.utc);session.add(assistant);session.flush();meta["latency_ms"]=round((time.perf_counter()-started)*1000,2);session.add(AuditEvent(user_id=user.id,event_type="assistant_request",entity_type="assistant_message",entity_id=assistant.id,details=meta));session.commit();session.refresh(assistant);return message_body(assistant)
@router.post("/messages/{message_id}/feedback",status_code=201)
def feedback(message_id:uuid.UUID,payload:FeedbackCreate,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    message=session.scalar(select(AssistantMessage).where(AssistantMessage.id==message_id,AssistantMessage.user_id==user.id,AssistantMessage.role=="assistant"))
    if not message:raise HTTPException(404,"Assistant message not found")
    event=AuditEvent(user_id=user.id,event_type="assistant_response_reported",entity_type="assistant_message",entity_id=message.id,details={"category":payload.category,"contains_prompt_or_answer":False,"financial_action":False});session.add(event);session.commit();session.refresh(event);return {"id":event.id,"category":payload.category,"financial_action":False}
@router.get("/metrics",response_model=MetricsResponse)
def metrics(user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    events=session.scalars(select(AuditEvent).where(AuditEvent.user_id==user.id,AuditEvent.event_type=="assistant_request")).all();outcomes={x:0 for x in ("success","refused","abstained","failed")};modes={};latency=0.0;citations=0;fallbacks=0
    for event in events:
        d=event.details;outcomes[d.get("outcome","failed")]=outcomes.get(d.get("outcome","failed"),0)+1;modes[d.get("response_mode","none")]=modes.get(d.get("response_mode","none"),0)+1;latency+=float(d.get("latency_ms",0));citations+=int(d.get("citation_count",0));fallbacks+=bool(d.get("fallback",False))
    total=len(events);return MetricsResponse(total_requests=total,successful=outcomes["success"],refused=outcomes["refused"],abstained=outcomes["abstained"],failed=outcomes["failed"],fallbacks=fallbacks,average_latency_ms=round(latency/total,2) if total else 0,total_citations=citations,provider_modes=modes)
