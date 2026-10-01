from datetime import datetime,timezone
from urllib.parse import parse_qs,urlparse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models import DeviceNotificationPreference,NotificationDelivery,NotificationDevice,NotificationEvent,NotificationPreference

EVENT_LINKS={"reminder_due":"/","assistant_response_ready":"/assistant","feedback_review_status_changed":"/assistant-feedback"}
GENERIC_MESSAGES={"reminder_due":("Wealth Manager reminder","Open the app to review your reminder."),"assistant_response_ready":("Research update ready","Open the app to review your research update."),"feedback_review_status_changed":("Review status updated","Open the app to review the status update.")}

def eligible_devices(session,user_id,event_type):
    user_pref=session.scalar(select(NotificationPreference.enabled).where(NotificationPreference.user_id==user_id,NotificationPreference.event_type==event_type))
    if user_pref is not True:return []
    devices=session.scalars(select(NotificationDevice).where(NotificationDevice.user_id==user_id,NotificationDevice.notifications_enabled.is_(True),NotificationDevice.push_status=="active",NotificationDevice.revoked_at.is_(None),NotificationDevice.expo_push_token.is_not(None))).all()
    result=[]
    for device in devices:
        override=session.scalar(select(DeviceNotificationPreference.enabled).where(DeviceNotificationPreference.user_id==user_id,DeviceNotificationPreference.device_id==device.id,DeviceNotificationPreference.event_type==event_type))
        if override is True:result.append(device)
    return result

def enqueue_event(session,user_id,event_type,dedupe_key,deep_link=None):
    existing=session.scalar(select(NotificationEvent).where(NotificationEvent.user_id==user_id,NotificationEvent.event_type==event_type,NotificationEvent.dedupe_key==dedupe_key))
    if existing:return existing,False
    event=NotificationEvent(user_id=user_id,event_type=event_type,dedupe_key=dedupe_key,deep_link=deep_link or EVENT_LINKS[event_type]);session.add(event);session.flush()
    for device in eligible_devices(session,user_id,event_type):session.add(NotificationDelivery(user_id=user_id,event_id=event.id,device_id=device.id))
    return event,True

def safe_payload(event,token):
    title,body=GENERIC_MESSAGES[event.event_type]
    parsed=urlparse(event.deep_link);data={"notification_id":str(event.id),"event_type":event.event_type,"path":parsed.path}
    conversation_id=parse_qs(parsed.query).get("conversationId",[None])[0]
    if event.event_type=="assistant_response_ready" and conversation_id:data["conversation_id"]=conversation_id
    return {"to":token,"title":title,"body":body,"data":data,"priority":"default"}
