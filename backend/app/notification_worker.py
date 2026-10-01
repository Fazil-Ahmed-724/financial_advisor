import argparse,time
from datetime import datetime,timedelta,timezone
from sqlalchemy import select
from app.database import SessionLocal
from app.models import NotificationDelivery,NotificationDevice,NotificationEvent
from app.notification_provider import ExpoProvider,ProviderPermanentError,ProviderTemporaryError
from app.notification_service import safe_payload

MAX_ATTEMPTS=4
TRANSIENT={"MessageRateExceeded"};PERMANENT={"DeviceNotRegistered","MessageTooBig","MismatchSenderId","InvalidCredentials"}
def backoff(attempt):return timedelta(seconds=min(300,2**max(1,attempt)))
def fail(delivery,code,temporary,now):
    delivery.last_error_code=code
    if temporary and delivery.attempt_count<MAX_ATTEMPTS:delivery.status="retry";delivery.next_attempt_at=now+backoff(delivery.attempt_count)
    else:delivery.status="dead_letter" if temporary else "permanent_failure"
def run_once(provider=None,now=None):
    provider=provider or ExpoProvider();now=now or datetime.now(timezone.utc);processed=0
    with SessionLocal() as session:
        rows=session.scalars(select(NotificationDelivery).where(NotificationDelivery.status.in_(["pending","retry"]),NotificationDelivery.next_attempt_at<=now).order_by(NotificationDelivery.created_at).with_for_update(skip_locked=True).limit(100)).all()
        for delivery in rows:
            device=session.get(NotificationDevice,delivery.device_id);event=session.get(NotificationEvent,delivery.event_id)
            if not device or device.revoked_at or device.push_status!="active" or not device.expo_push_token:fail(delivery,"DeviceInactive",False,now);processed+=1;continue
            delivery.attempt_count+=1
            try:
                result=provider.send(safe_payload(event,device.expo_push_token));ticket=(result.get("data") or [{}])[0]
                if ticket.get("status")=="ok" and ticket.get("id"):delivery.status="accepted";delivery.expo_ticket_id=ticket["id"];delivery.accepted_at=now;delivery.next_attempt_at=now+timedelta(minutes=15)
                else:
                    code=(ticket.get("details") or {}).get("error") or "ProviderRejected";fail(delivery,code,code in TRANSIENT,now)
                    if code=="DeviceNotRegistered":device.push_status="invalid";device.expo_push_token=None;device.notifications_enabled=False
            except ProviderTemporaryError:fail(delivery,"ProviderUnavailable",True,now)
            except ProviderPermanentError:fail(delivery,"ProviderRejected",False,now)
            processed+=1
        session.commit()
    return processed
def poll_receipts(provider=None,now=None):
    provider=provider or ExpoProvider();now=now or datetime.now(timezone.utc);processed=0
    with SessionLocal() as session:
        rows=session.scalars(select(NotificationDelivery).where(NotificationDelivery.status=="accepted",NotificationDelivery.next_attempt_at<=now,NotificationDelivery.expo_ticket_id.is_not(None)).with_for_update(skip_locked=True).limit(100)).all()
        if not rows:return 0
        try:data=(provider.receipts([x.expo_ticket_id for x in rows]).get("data") or {})
        except ProviderTemporaryError:
            for x in rows:fail(x,"ReceiptUnavailable",True,now)
            session.commit();return len(rows)
        for delivery in rows:
            receipt=data.get(delivery.expo_ticket_id);delivery.receipt_checked_at=now
            if not receipt:delivery.status="unknown";delivery.last_error_code="ReceiptMissing"
            elif receipt.get("status")=="ok":delivery.status="delivered"
            else:
                code=(receipt.get("details") or {}).get("error") or "ReceiptRejected";fail(delivery,code,code in TRANSIENT,now)
                if code=="DeviceNotRegistered":
                    device=session.get(NotificationDevice,delivery.device_id);device.push_status="invalid";device.expo_push_token=None;device.notifications_enabled=False
            processed+=1
        session.commit()
    return processed
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("mode",choices=["send","receipts","loop"]);args=parser.parse_args()
    if args.mode=="loop":
        while True:
            run_once();poll_receipts();time.sleep(10)
    else:print(run_once() if args.mode=="send" else poll_receipts())
