import uuid
from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException,status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth import get_current_user,get_session
from app.models import DeviceNotificationPreference,NotificationDelivery,NotificationDevice,NotificationEvent,NotificationPreference,User
from app.notification_service import enqueue_event
from app.schemas_notifications import DeliveryResponse,DeviceRegister,DeviceResponse,DeviceUpdate,PreferenceResponse,PreferenceUpdate,ReminderCreate

router=APIRouter(prefix="/notifications",tags=["informational notifications"])
EVENTS=("reminder_due","assistant_response_ready","feedback_review_status_changed")
def owned_device(session,user_id,device_id):
    row=session.scalar(select(NotificationDevice).where(NotificationDevice.id==device_id,NotificationDevice.user_id==user_id))
    if not row:raise HTTPException(404,"Device not found")
    return row
def preference_map(session,user_id,device_id):
    rows=session.scalars(select(DeviceNotificationPreference).where(DeviceNotificationPreference.user_id==user_id,DeviceNotificationPreference.device_id==device_id)).all();return {e:next((x.enabled for x in rows if x.event_type==e),False) for e in EVENTS}
def device_body(session,row):return DeviceResponse(id=row.id,installation_id=row.installation_id,platform=row.platform,display_name=row.display_name,push_status=row.push_status,notifications_enabled=row.notifications_enabled,last_seen_at=row.last_seen_at,revoked_at=row.revoked_at,preferences=preference_map(session,row.user_id,row.id))
@router.post("/devices",response_model=DeviceResponse)
def register_device(payload:DeviceRegister,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    row=session.scalar(select(NotificationDevice).where(NotificationDevice.user_id==user.id,NotificationDevice.installation_id==payload.installation_id))
    if not row:row=NotificationDevice(user_id=user.id,installation_id=payload.installation_id,platform=payload.platform,display_name=payload.display_name);session.add(row)
    row.platform=payload.platform;row.display_name=payload.display_name;row.last_seen_at=datetime.now(timezone.utc)
    if row.revoked_at:raise HTTPException(409,"This device was revoked; sign in again with a new installation")
    row.expo_push_token=payload.expo_push_token;row.notifications_enabled=payload.notifications_enabled and payload.expo_push_token is not None;row.push_status="active" if row.notifications_enabled else ("disabled" if payload.expo_push_token else "unregistered")
    try:session.commit()
    except IntegrityError:session.rollback();raise HTTPException(409,"Push token is already registered to another device") from None
    session.refresh(row);return device_body(session,row)
@router.get("/devices",response_model=list[DeviceResponse])
def devices(user:User=Depends(get_current_user),session:Session=Depends(get_session)):return [device_body(session,x) for x in session.scalars(select(NotificationDevice).where(NotificationDevice.user_id==user.id).order_by(NotificationDevice.last_seen_at.desc())).all()]
@router.put("/devices/{device_id}",response_model=DeviceResponse)
def update_device(device_id:uuid.UUID,payload:DeviceUpdate,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    row=owned_device(session,user.id,device_id)
    if row.revoked_at:raise HTTPException(409,"Device is revoked")
    if payload.notifications_enabled and not row.expo_push_token:raise HTTPException(422,"Register a push token before enabling notifications")
    row.notifications_enabled=payload.notifications_enabled;row.push_status="active" if payload.notifications_enabled else "disabled";session.commit();session.refresh(row);return device_body(session,row)
@router.delete("/devices/{device_id}",status_code=204)
def revoke_device(device_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    row=owned_device(session,user.id,device_id);row.revoked_at=datetime.now(timezone.utc);row.notifications_enabled=False;row.push_status="revoked";row.expo_push_token=None;row.session_version+=1
    for d in session.scalars(select(NotificationDelivery).where(NotificationDelivery.user_id==user.id,NotificationDelivery.device_id==row.id,NotificationDelivery.status.in_(["pending","retry","accepted"]))).all():d.status="permanent_failure";d.last_error_code="DeviceRevoked"
    session.commit()
@router.get("/preferences",response_model=list[PreferenceResponse])
def preferences(user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    rows=session.scalars(select(NotificationPreference).where(NotificationPreference.user_id==user.id)).all();return [PreferenceResponse(event_type=e,enabled=next((x.enabled for x in rows if x.event_type==e),False)) for e in EVENTS]
@router.put("/preferences",response_model=PreferenceResponse)
def update_preference(payload:PreferenceUpdate,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    if payload.device_id:
        owned_device(session,user.id,payload.device_id);row=session.scalar(select(DeviceNotificationPreference).where(DeviceNotificationPreference.user_id==user.id,DeviceNotificationPreference.device_id==payload.device_id,DeviceNotificationPreference.event_type==payload.event_type))
        if not row:row=DeviceNotificationPreference(user_id=user.id,device_id=payload.device_id,event_type=payload.event_type);session.add(row)
    else:
        row=session.scalar(select(NotificationPreference).where(NotificationPreference.user_id==user.id,NotificationPreference.event_type==payload.event_type))
        if not row:row=NotificationPreference(user_id=user.id,event_type=payload.event_type);session.add(row)
    row.enabled=payload.enabled;session.commit();return PreferenceResponse(event_type=payload.event_type,enabled=row.enabled,device_id=payload.device_id)
@router.post("/reminders",status_code=202)
def reminder(payload:ReminderCreate,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    try:event,created=enqueue_event(session,user.id,"reminder_due",payload.dedupe_key,payload.deep_link);session.commit()
    except IntegrityError:
        session.rollback();event=session.scalar(select(NotificationEvent).where(NotificationEvent.user_id==user.id,NotificationEvent.event_type=="reminder_due",NotificationEvent.dedupe_key==payload.dedupe_key));created=False
        if not event:raise HTTPException(409,"Reminder request conflicted; retry with the same key") from None
    return {"event_id":event.id,"created":created,"informational_only":True,"financial_action":False}
def delivery_body(session,row):
    event=session.scalar(select(NotificationEvent).where(NotificationEvent.id==row.event_id,NotificationEvent.user_id==row.user_id));return DeliveryResponse(id=row.id,event_id=row.event_id,device_id=row.device_id,event_type=event.event_type,status=row.status,attempt_count=row.attempt_count,last_error_code=row.last_error_code,created_at=row.created_at,updated_at=row.updated_at,acknowledged_at=row.acknowledged_at)
@router.get("/history",response_model=list[DeliveryResponse])
def history(user:User=Depends(get_current_user),session:Session=Depends(get_session)):return [delivery_body(session,x) for x in session.scalars(select(NotificationDelivery).where(NotificationDelivery.user_id==user.id).order_by(NotificationDelivery.created_at.desc()).limit(200)).all()]
@router.post("/history/{delivery_id}/acknowledge",response_model=DeliveryResponse)
def acknowledge(delivery_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    row=session.scalar(select(NotificationDelivery).where(NotificationDelivery.id==delivery_id,NotificationDelivery.user_id==user.id))
    if not row:raise HTTPException(404,"Notification not found")
    row.acknowledged_at=datetime.now(timezone.utc);session.commit();session.refresh(row);return delivery_body(session,row)
