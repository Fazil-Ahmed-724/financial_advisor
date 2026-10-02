import json,logging,uuid
from datetime import datetime,timedelta,timezone
from fastapi.testclient import TestClient
from sqlalchemy import func,select
from app.database import SessionLocal
from app.main import app
from app.models import Account,AssistantConversation,InvestmentTrade,MarketplaceProduct,NotificationDelivery,NotificationDevice,PropertyListing,TaxRule
from app.notification_provider import ProviderTemporaryError
from app.notification_worker import poll_receipts,run_once

client=TestClient(app);PASSWORD="correct horse battery staple"
def auth(email,installation=None):
    body={"email":email,"password":PASSWORD}
    if installation:body|={"installation_id":str(installation),"platform":"android","device_name":"Test phone"}
    response=client.post("/auth/register",json=body);token=response.json()["token"]["access_token"];return {"Authorization":f"Bearer {token}"},response.json()["user"]["id"]
def register_device(headers,installation,n):
    token=f"ExponentPushToken[test-{n}-{uuid.uuid4()}]";response=client.post("/notifications/devices",headers=headers,json={"installation_id":str(installation),"platform":"android","display_name":f"Phone {n}","expo_push_token":token,"notifications_enabled":True});assert response.status_code==200;return response.json(),token
def enable(headers,event,device=None):assert client.put("/notifications/preferences",headers=headers,json={"event_type":event,"enabled":True,"device_id":device}).status_code==200
def counts():
    with SessionLocal() as s:return {m.__tablename__:s.scalar(select(func.count()).select_from(m)) for m in (Account,InvestmentTrade,TaxRule,PropertyListing,MarketplaceProduct,AssistantConversation)}
class Provider:
    def __init__(self,tickets=None,receipts=None,timeout=False):self.tickets=list(tickets or []);self.receipt_data=receipts or {};self.timeout=timeout;self.payloads=[]
    def send(self,payload):
        self.payloads.append(payload)
        if self.timeout:raise ProviderTemporaryError()
        return {"data":[self.tickets.pop(0)]}
    def receipts(self,ids):return {"data":self.receipt_data}

def test_multi_device_opt_in_fanout_idempotency_privacy_and_isolation(caplog):
    h,uid=auth("notify-fanout@example.com");other,_=auth("notify-other@example.com");d1,t1=register_device(h,uuid.uuid4(),1);d2,t2=register_device(h,uuid.uuid4(),2);disabled,_=register_device(h,uuid.uuid4(),3);client.put(f"/notifications/devices/{disabled['id']}",headers=h,json={"notifications_enabled":False})
    enable(h,"reminder_due");enable(h,"reminder_due",d1["id"]);enable(h,"reminder_due",d2["id"])
    payload={"dedupe_key":"monthly-review","deep_link":"/"};first=client.post("/notifications/reminders",headers=h,json=payload);second=client.post("/notifications/reminders",headers=h,json=payload);assert first.json()["created"] is True and second.json()["created"] is False
    assert len(client.get("/notifications/history",headers=h).json())==2;assert client.get("/notifications/history",headers=other).json()==[]
    provider=Provider([{"status":"ok","id":"ticket-1"},{"status":"ok","id":"ticket-2"}])
    with caplog.at_level(logging.INFO):assert run_once(provider)==2
    assert {x["to"] for x in provider.payloads}=={t1,t2};serialized=json.dumps(provider.payloads);assert "PKR" not in serialized and "balance" not in serialized and "tax" not in serialized and "assistant answer" not in serialized;assert t1 not in caplog.text and t2 not in caplog.text

def test_retry_recovery_dead_letter_invalid_token_and_receipts():
    h,_=auth("notify-worker@example.com");d,_=register_device(h,uuid.uuid4(),4);enable(h,"reminder_due");enable(h,"reminder_due",d["id"]);client.post("/notifications/reminders",headers=h,json={"dedupe_key":"retry","deep_link":"/"})
    now=datetime.now(timezone.utc);assert run_once(Provider(timeout=True),now)==1
    with SessionLocal() as s:row=s.scalar(select(NotificationDelivery).order_by(NotificationDelivery.created_at.desc()));assert row.status=="retry";row.next_attempt_at=now;s.commit()
    assert run_once(Provider([{"status":"ok","id":"receipt-invalid"}]),now)==1
    assert poll_receipts(Provider(receipts={"receipt-invalid":{"status":"error","details":{"error":"DeviceNotRegistered"}}}),now+timedelta(minutes=16))>=1
    with SessionLocal() as s:row=s.scalar(select(NotificationDelivery).order_by(NotificationDelivery.created_at.desc()));device=s.get(NotificationDevice,row.device_id);assert row.status=="permanent_failure" and device.push_status=="invalid" and device.expo_push_token is None

def test_bounded_timeout_retries_become_dead_letter():
    h,_=auth("notify-dead@example.com");d,_=register_device(h,uuid.uuid4(),5);enable(h,"reminder_due");enable(h,"reminder_due",d["id"]);client.post("/notifications/reminders",headers=h,json={"dedupe_key":"dead","deep_link":"/"});now=datetime.now(timezone.utc)
    for _ in range(4):
        run_once(Provider(timeout=True),now)
        with SessionLocal() as s:row=s.scalar(select(NotificationDelivery).order_by(NotificationDelivery.created_at.desc()));row.next_attempt_at=now;s.commit()
    with SessionLocal() as s:assert s.scalar(select(NotificationDelivery).order_by(NotificationDelivery.created_at.desc())).status=="dead_letter"

def test_revocation_invalidates_device_token_and_prevents_future_fanout():
    installation=uuid.uuid4();h,_=auth("notify-revoke@example.com",installation);d,_=register_device(h,installation,6);enable(h,"reminder_due");enable(h,"reminder_due",d["id"]);assert client.delete(f"/notifications/devices/{d['id']}",headers=h).status_code==204;assert client.get("/auth/me",headers=h).status_code==401
    login=client.post("/auth/login",json={"email":"notify-revoke@example.com","password":PASSWORD,"installation_id":str(installation),"platform":"android","device_name":"Test phone"});assert login.status_code==401

def test_validation_and_notifications_do_not_mutate_finance_or_assistant_configuration(monkeypatch):
    monkeypatch.setenv("ASSISTANT_PROVIDER","disabled");before=counts();h,_=auth("notify-safe@example.com");assert client.put("/notifications/preferences",headers=h,json={"event_type":"buy_signal","enabled":True}).status_code==422;assert client.post("/notifications/reminders",headers=h,json={"dedupe_key":"x","deep_link":"/trade"}).status_code==422;assert counts()==before;assert __import__('os').environ["ASSISTANT_PROVIDER"]=="disabled"

def test_assistant_ready_is_explicit_and_payload_opens_only_owned_conversation():
    h,_=auth("notify-chat@example.com");device,_=register_device(h,uuid.uuid4(),7);enable(h,"assistant_response_ready");enable(h,"assistant_response_ready",device["id"])
    conversation=client.post("/assistant/conversations",headers=h,json={"title":"Private research"}).json();question="Explain my private balance and citations"
    assert client.post(f"/assistant/conversations/{conversation['id']}/messages",headers=h,json={"message":question}).status_code==201
    assert client.get("/notifications/history",headers=h).json()==[]
    response=client.post(f"/assistant/conversations/{conversation['id']}/messages",headers=h,json={"message":question,"notify_when_ready":True});assert response.status_code==201;answer=response.json()["content"]
    provider=Provider([{"status":"ok","id":"chat-ticket"}]);assert run_once(provider)>=1
    payload=next(x for x in provider.payloads if x["data"]["event_type"]=="assistant_response_ready")
    assert payload["data"]=={"notification_id":payload["data"]["notification_id"],"event_type":"assistant_response_ready","path":"/assistant","conversation_id":conversation["id"]}
    serialized=json.dumps(payload);assert question not in serialized and answer not in serialized and "citations" not in serialized and "PKR" not in serialized

def test_diagnostics_and_confirmed_test_send_are_scoped_idempotent_and_private():
    h,_=auth("notify-diagnostic@example.com");other,_=auth("notify-diagnostic-other@example.com");d1,t1=register_device(h,uuid.uuid4(),8);d2,t2=register_device(h,uuid.uuid4(),9);foreign,_=register_device(other,uuid.uuid4(),10)
    diagnostics=client.get("/notifications/diagnostics",headers=h);assert diagnostics.status_code==200 and len(diagnostics.json())==2
    assert all(x["token_exposed"] is False and "expo_push_token" not in x for x in diagnostics.json())
    body={"device_ids":[d1["id"],d2["id"]],"idempotency_key":"explicit-test-001","confirm_send":True}
    first=client.post("/notifications/test",headers=h,json=body);second=client.post("/notifications/test",headers=h,json=body)
    assert first.status_code==202 and first.json()["queued_devices"]==2 and second.json()["created"] is False
    assert client.post("/notifications/test",headers=h,json=body|{"confirm_send":False}).status_code==422
    assert client.post("/notifications/test",headers=h,json=body|{"device_ids":[foreign["id"]],"idempotency_key":"foreign-test"}).status_code==404
    provider=Provider([{"status":"ok","id":"test-ticket-1"},{"status":"ok","id":"test-ticket-2"}]);run_once(provider)
    payloads=[x for x in provider.payloads if x["data"]["event_type"]=="test_notification"];assert {x["to"] for x in payloads}=={t1,t2}
    serialized=json.dumps(payloads);assert "question" not in serialized and "answer" not in serialized and "PKR" not in serialized
    assert all(x["data"]["path"]=="/notification-settings" for x in payloads)

def test_test_notification_rate_limit_and_inactive_device():
    h,_=auth("notify-rate@example.com");d,_=register_device(h,uuid.uuid4(),11)
    for n in range(3):assert client.post("/notifications/test",headers=h,json={"device_ids":[d["id"]],"idempotency_key":f"rate-test-{n}","confirm_send":True}).status_code==202
    assert client.post("/notifications/test",headers=h,json={"device_ids":[d["id"]],"idempotency_key":"rate-test-four","confirm_send":True}).status_code==429
    h2,_=auth("notify-inactive@example.com");inactive,_=register_device(h2,uuid.uuid4(),12);client.put(f"/notifications/devices/{inactive['id']}",headers=h2,json={"notifications_enabled":False})
    assert client.post("/notifications/test",headers=h2,json={"device_ids":[inactive["id"]],"idempotency_key":"inactive-test","confirm_send":True}).status_code==422
