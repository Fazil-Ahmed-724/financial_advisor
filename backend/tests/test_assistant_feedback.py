import json,os,uuid
from fastapi.testclient import TestClient
from sqlalchemy import func,select
from app.database import SessionLocal
from app.main import app
from app.models import Account,InvestmentTrade,JournalEntry,MarketplaceListing,MarketplaceProduct,OpportunityAnalysis,PropertyListing,TaxRule

client=TestClient(app);PASSWORD="correct horse battery staple"
def auth(label):
    response=client.post("/auth/register",json={"email":f"feedback-{label}-{uuid.uuid4()}@example.com","password":PASSWORD});return {"Authorization":f"Bearer {response.json()['token']['access_token']}"}
def assistant_message(headers,secret="PRIVATE-SOURCE-TEXT-778899"):
    listing={"city":"Karachi","source_type":"user_entered","source_name":secret,"observed_at":"2026-09-30T00:00:00Z","purpose":"sale","property_type":"flat","area_name":"Clifton","area_amount":"1000","area_unit":"sq_ft","asking_amount":"987654.00","attributes":{"description":secret}}
    created=client.post("/opportunities/karachi-real-estate/listings",headers={**headers,"Idempotency-Key":str(uuid.uuid4())},json=listing);assert created.status_code==201,created.text
    cid=client.post("/assistant/conversations",headers=headers,json={}).json()["id"]
    response=client.post(f"/assistant/conversations/{cid}/messages",headers=headers,json={"message":"Explain my Karachi property listing"});assert response.status_code==201,response.text
    return response.json()
def domain_counts():
    with SessionLocal() as session:
        models=(Account,JournalEntry,InvestmentTrade,TaxRule,PropertyListing,MarketplaceListing,MarketplaceProduct,OpportunityAnalysis)
        return {model.__tablename__:session.scalar(select(func.count()).select_from(model)) for model in models}

def test_feedback_categories_bounds_duplicate_and_personal_inbox():
    owner,other=auth("owner"),auth("other");message=assistant_message(owner);mid=message["id"]
    assert client.post(f"/assistant/messages/{mid}/feedback",headers=other,json={"category":"helpful"}).status_code==404
    assert client.post(f"/assistant/messages/{mid}/feedback",headers=owner,json={"category":"invalid"}).status_code==422
    assert client.post(f"/assistant/messages/{mid}/feedback",headers=owner,json={"category":"helpful","comment":"x"*501}).status_code==422
    created=client.post(f"/assistant/messages/{mid}/feedback",headers=owner,json={"category":"inaccurate","comment":"  Needs   review  "});assert created.status_code==201,created.text
    body=created.json();assert body["comment"]=="Needs review" and body["status"]=="submitted" and body["fixture_selected"] is False
    assert body["response_mode"]==message["response"]["mode"] and body["citation_ids"]==[x["record_id"] for x in message["response"]["citations"]]
    assert body["source_dates"] and body["financial_action"] is False
    assert client.post(f"/assistant/messages/{mid}/feedback",headers=owner,json={"category":"helpful"}).status_code==409
    assert [x["id"] for x in client.get("/assistant/feedback",headers=owner).json()]==[body["id"]]
    assert client.get("/assistant/feedback",headers=other).json()==[]

def test_personal_review_update_selection_export_sanitization_and_delete(caplog):
    owner,other=auth("review-owner"),auth("review-other");secret="PRIVATE-SOURCE-TEXT-778899";message=assistant_message(owner,secret);mid=message["id"]
    feedback=client.post(f"/assistant/messages/{mid}/feedback",headers=owner,json={"category":"unsupported","comment":"Balance 999999 and account PK00SECRET"}).json();fid=feedback["id"]
    assert client.put(f"/assistant/feedback/{fid}",headers=other,json={"status":"reviewed"}).status_code==404
    assert client.delete(f"/assistant/feedback/{fid}",headers=other).status_code==404
    assert client.put(f"/assistant/feedback/{fid}",headers=owner,json={"fixture_selected":True}).status_code==422
    reviewed=client.put(f"/assistant/feedback/{fid}",headers=owner,json={"status":"reviewed","review_note":"Confirmed for a sanitized regression case","fixture_selected":True});assert reviewed.status_code==200,reviewed.text
    assert reviewed.json()["status"]=="reviewed" and reviewed.json()["fixture_selected"] is True
    assert client.post("/assistant/feedback/export",headers=owner,json={"feedback_ids":[fid],"confirm_sanitized_export":False}).status_code==422
    assert client.post("/assistant/feedback/export",headers=other,json={"feedback_ids":[fid],"confirm_sanitized_export":True}).status_code==404
    exported=client.post("/assistant/feedback/export",headers=owner,json={"feedback_ids":[fid],"confirm_sanitized_export":True});assert exported.status_code==200,exported.text
    payload=exported.json();serialized=json.dumps(payload);case=payload["cases"][0]
    assert payload["sanitized"] is True and payload["automatic_training"] is False and payload["requires_manual_test_implementation"] is True
    assert case["category"]=="unsupported" and case["expected_behavior"]=="abstain_without_support"
    for forbidden in (secret,"999999","PK00SECRET",fid,mid,"987654"):assert forbidden not in serialized
    assert secret not in caplog.text and "PK00SECRET" not in caplog.text
    assert client.delete(f"/assistant/feedback/{fid}",headers=owner).status_code==204
    assert client.get("/assistant/feedback",headers=owner).json()==[]

def test_feedback_workflow_does_not_mutate_finance_research_or_provider_config():
    headers=auth("readonly");message=assistant_message(headers);baseline=domain_counts();provider_before=os.environ.get("ASSISTANT_PROVIDER")
    feedback=client.post(f"/assistant/messages/{message['id']}/feedback",headers=headers,json={"category":"missing_evidence","comment":"Please review"}).json();fid=feedback["id"]
    client.put(f"/assistant/feedback/{fid}",headers=headers,json={"status":"dismissed","review_note":"No fixture"})
    assert domain_counts()==baseline and os.environ.get("ASSISTANT_PROVIDER")==provider_before

def test_legacy_part13_category_is_canonicalized():
    headers=auth("legacy");message=assistant_message(headers)
    response=client.post(f"/assistant/messages/{message['id']}/feedback",headers=headers,json={"category":"unsupported_claim"})
    assert response.status_code==201 and response.json()["category"]=="unsupported"
