import io, os, uuid, zipfile
from pypdf import PdfWriter
from fastapi.testclient import TestClient
from app.main import app
client=TestClient(app); PASSWORD="correct horse battery staple"
def user(label):
 r=client.post("/auth/register",json={"email":f"{label}-{uuid.uuid4()}@example.com","password":PASSWORD});return {"Authorization":f"Bearer {r.json()['token']['access_token']}"}
def upload(h,name,data,mime="application/octet-stream",**fields):
 values={"title":"The Book","author":"Author","topic":"finance","source":"owned copy","language":"en",**fields}
 return client.post("/books",headers=h,data=values,files={"file":(name,data,mime)})
def epub():
 out=io.BytesIO()
 with zipfile.ZipFile(out,"w") as z:z.writestr("chapter1.xhtml","<h1>Margin of safety</h1><p>Protect capital before seeking returns.</p>")
 return out.getvalue()
def decision(h):
 p={"decision_date":"2026-09-30","instrument":"ABC","action_considered":"HOLD","rationale":"Study first","goal":"Learn","expected_holding_period":"One year","risk_factors":"Loss","expected_outcome":"Understanding"}
 return client.post("/decisions",headers={**h,"Idempotency-Key":str(uuid.uuid4())},json=p).json()
def test_txt_epub_search_citations_reprocess_and_delete():
 h=user("books"); txt=upload(h,"safe.txt",b"Cash flow matters.\n\nDebt increases financial risk.","text/plain")
 assert txt.status_code==201 and txt.json()["ingestion_status"]=="ready"
 e=upload(h,"owned.epub",epub(),"application/epub+zip"); assert e.status_code==201
 results=client.get("/book-search",headers=h,params={"q":"financial risk"}).json()
 assert results[0]["book_title"]=="The Book" and results[0]["reference_label"].startswith("Section")
 assert results[0]["learning_support"] is True and results[0]["market_data"] is False
 before=len(results); rp=client.post(f"/books/{txt.json()['id']}/reprocess",headers=h)
 assert rp.status_code==200 and len(client.get("/book-search",headers=h,params={"q":"financial risk"}).json())==before
 assert client.delete(f"/books/{txt.json()['id']}",headers=h).status_code==204
 assert client.get("/book-search",headers=h,params={"q":"financial risk"}).json()==[]
def test_pdf_scanned_status_and_rejected_type_and_size(monkeypatch):
 h=user("formats"); out=io.BytesIO();w=PdfWriter();w.add_blank_page(width=72,height=72);w.write(out)
 pdf=upload(h,"scan.pdf",out.getvalue(),"application/pdf");assert pdf.json()["ingestion_status"]=="ocr_required"
 assert "OCR" in pdf.json()["status_detail"]
 assert upload(h,"bad.exe",b"x").status_code==415
 monkeypatch.setenv("BOOK_MAX_UPLOAD_BYTES","3");assert upload(h,"big.txt",b"1234","text/plain").status_code==413
def test_user_isolation_metadata_and_learning_attachment_separation():
 owner=user("owner-book");other=user("other-book");book=upload(owner,"mine.txt",b"Diversification can reduce concentration risk.","text/plain").json()
 assert client.get(f"/books/{book['id']}",headers=other).status_code==404
 assert client.patch(f"/books/{book['id']}",headers=other,json={"title":"X","author":"X","topic":"X","source":"X","language":"en"}).status_code==404
 result=client.get("/book-search",headers=owner,params={"q":"concentration"}).json()[0]
 assert client.get(f"/book-passages/{result['id']}",headers=other).status_code==404
 d=decision(owner); attached=client.post(f"/decisions/{d['id']}/passages/{result['id']}",headers=owner,json={"note":"Learning context"})
 assert attached.status_code==201 and attached.json()["affects_decision_score"] is False
 other_d=decision(other);assert client.post(f"/decisions/{other_d['id']}/passages/{result['id']}",headers=other,json={}).status_code==404
 assert client.delete(f"/books/{book['id']}",headers=other).status_code==404
def test_empty_search_and_no_downloader_or_execution_routes():
 h=user("empty-book");assert client.get("/book-search",headers=h,params={"q":"unknown"}).json()==[]
 paths=app.openapi()["paths"];assert not any("download" in p.lower() or "order" in p.lower() or "broker" in p.lower() for p in paths)
