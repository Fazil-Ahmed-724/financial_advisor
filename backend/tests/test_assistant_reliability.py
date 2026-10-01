import json,uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.assistant_service import validate_response
import app.assistant_service as assistant_service
from app.database import SessionLocal
from evaluation.runner import DATASET,run
from app.main import app
from app.models import AuditEvent

client=TestClient(app);PASSWORD="correct horse battery staple"
def user(label):
    r=client.post("/auth/register",json={"email":f"{label}-{uuid.uuid4()}@example.com","password":PASSWORD});return uuid.UUID(r.json()["user"]["id"]),{"Authorization":f"Bearer {r.json()['token']['access_token']}"}
def conversation(headers):return client.post("/assistant/conversations",headers=headers,json={}).json()["id"]

def test_versioned_evaluation_dataset_and_offline_runner(tmp_path):
    dataset=json.loads(DATASET.read_text("utf-8"));assert dataset["dataset_version"]=="part13-v1" and len(dataset["cases"])>=14
    report,markdown=run(tmp_path/"report.json",tmp_path/"report.md")
    assert report["provider"]=="disabled" and report["network_access"] is False
    assert report["failed_cases"]==0 and report["passed_cases"]==report["total_cases"]
    assert (tmp_path/"report.json").exists() and "Part 13 assistant evaluation" in markdown
    for metric in ("citation_coverage","citation_ownership","abstained","stale_labeled","conflict_labeled","calculation_agreement","read_only_refusal","read_only_boundary","cross_user_blocked","injection_ignored"):assert metric in report["metrics"]

def test_malformed_provider_output_falls_back_and_metrics_are_private(monkeypatch,caplog):
    class BadProvider:
        mode="llm"
        def explain(self,*args):return "Fabricated answer without required citation markers"
    monkeypatch.setattr(assistant_service,"provider",lambda:BadProvider());uid,headers=user("fallback");cid=conversation(headers);secret="PRIVATE-PROMPT-998877"
    # No evidence means the provider is not called; seed an assistant-visible financial profile query.
    response=client.post(f"/assistant/conversations/{cid}/messages",headers=headers,json={"message":f"Explain my cash balance {secret}"});assert response.status_code==201
    body=response.json()["response"];assert body["mode"]=="deterministic" and any("failed validation" in x for x in body["limitations"])
    metrics=client.get("/assistant/metrics",headers=headers).json();assert metrics["total_requests"]==1 and metrics["fallbacks"]==1
    with SessionLocal() as session:event=session.scalar(select(AuditEvent).where(AuditEvent.user_id==uid,AuditEvent.event_type=="assistant_request"));serialized=json.dumps(event.details)
    assert secret not in serialized and "cash balance" not in serialized and set(event.details)=={"outcome","provider_mode","response_mode","validation_status","fallback","citation_count","latency_ms"}
    assert secret not in caplog.text and "PRIVATE-PROMPT" not in caplog.text

def test_fabricated_citation_and_calculation_are_rejected():
    rid=uuid.uuid4();evidence=[{"source_type":"book_passage","record_id":rid,"date":None,"excerpt":"Owned excerpt","record_path":"/books/x","freshness":"undated","calculation":None}]
    valid={"answer":"Owned excerpt [1]","citations":[{"source_type":"book_passage","record_id":rid,"date":None,"excerpt":"Owned excerpt","record_path":"/books/x","freshness":"undated"}],"evidence_references":[],"freshness":["book_passage: undated"],"limitations":["limited"],"mode":"deterministic"}
    validate_response(evidence,valid)
    fabricated={**valid,"citations":[{**valid["citations"][0],"record_id":uuid.uuid4()}]}
    with pytest.raises(ValueError,match="Citation set"):validate_response(evidence,fabricated)
    calc_evidence=[{**evidence[0],"calculation":{"service":"trusted","value":"1"}}];bad_calc={**valid,"evidence_references":[{"record_id":str(rid),"calculation":{"service":"invented","value":"2"}}]}
    with pytest.raises(ValueError,match="Calculation reference"):validate_response(calc_evidence,bad_calc)

def test_feedback_is_scoped_and_contains_no_answer_text():
    owner_id,owner=user("feedback-owner");_,other=user("feedback-other");cid=conversation(owner);message=client.post(f"/assistant/conversations/{cid}/messages",headers=owner,json={"message":"Unknown evidence request"}).json();mid=message["id"]
    assert client.post(f"/assistant/messages/{mid}/feedback",headers=other,json={"category":"unsupported_claim"}).status_code==404
    saved=client.post(f"/assistant/messages/{mid}/feedback",headers=owner,json={"category":"unsupported_claim"});assert saved.status_code==201 and saved.json()["financial_action"] is False
    with SessionLocal() as session:event=session.scalar(select(AuditEvent).where(AuditEvent.user_id==owner_id,AuditEvent.event_type=="assistant_response_reported"));details=json.dumps(event.details)
    assert "Unknown evidence request" not in details and event.details["contains_prompt_or_answer"] is False
