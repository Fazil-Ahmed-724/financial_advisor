import hashlib, io, os, re, shutil, uuid, zipfile
from html.parser import HTMLParser
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pypdf import PdfReader
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session
from app.auth import get_current_user, get_session
from app.models import AuditEvent, Book, BookPassage, DecisionPassage, InvestmentDecision, User
from app.schemas_books import AttachPassage, BookResponse, BookUpdate, PassageResponse

router=APIRouter(tags=["book library"]); VERSION=1
ALLOWED={".txt":"text/plain",".pdf":"application/pdf",".epub":"application/epub+zip"}

class TextExtractor(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]
    def handle_data(self,data): self.parts.append(data)
    def value(self): return " ".join(" ".join(self.parts).split())

def root():
    p=Path(os.environ.get("BOOK_STORAGE_ROOT","/data/books")); p.mkdir(parents=True,exist_ok=True); return p
def chunks(value,size=1200):
    paragraphs=[" ".join(x.split()) for x in re.split(r"\n\s*\n",value) if x.strip()]; out=[]; current=""
    for p in paragraphs:
        if current and len(current)+len(p)+2>size: out.append(current); current=""
        while len(p)>size: out.append(p[:size]); p=p[size:]
        current=(current+"\n\n"+p).strip()
    if current: out.append(current)
    return out
def extract(path,ext):
    if ext==".txt": return [("section",f"Section {i+1}",c) for i,c in enumerate(chunks(path.read_text("utf-8")))]
    if ext==".pdf":
        reader=PdfReader(str(path)); rows=[]
        for i,page in enumerate(reader.pages):
            for c in chunks(page.extract_text() or ""): rows.append(("page",f"Page {i+1}",c))
        if not rows: raise ValueError("OCR_REQUIRED")
        return rows
    rows=[]
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if name.lower().endswith((".xhtml",".html",".htm")):
                parser=TextExtractor(); parser.feed(archive.read(name).decode("utf-8",errors="ignore"))
                for c in chunks(parser.value()): rows.append(("chapter",Path(name).stem,c))
    if not rows: raise ValueError("NO_TEXT")
    return rows
def owned(session,user_id,book_id):
    book=session.scalar(select(Book).where(Book.id==book_id,Book.user_id==user_id))
    if not book: raise HTTPException(404,"Book not found")
    return book
def process(session,book,path):
    existing=session.scalar(select(func.count()).select_from(BookPassage).where(BookPassage.book_id==book.id,BookPassage.extraction_version==book.extraction_version))
    if existing: return
    try: rows=extract(path,Path(book.original_filename).suffix.lower())
    except ValueError as e:
        book.ingestion_status="ocr_required" if str(e)=="OCR_REQUIRED" else "extraction_failed"
        book.status_detail="Image-only or scanned PDF detected; OCR is not supported." if str(e)=="OCR_REQUIRED" else "No extractable text was found."
        return
    for i,(kind,label,content) in enumerate(rows):
        p=BookPassage(id=uuid.uuid4(),book_id=book.id,user_id=book.user_id,extraction_version=book.extraction_version,sequence=i,reference_type=kind,reference_label=label,content=content,search_vector="")
        session.add(p); session.flush(); session.execute(update(BookPassage).where(BookPassage.id==p.id).values(search_vector=func.to_tsvector("simple",content)))
    book.ingestion_status="ready";book.status_detail=f"{len(rows)} passages extracted"
def passage_body(book,p):
    return PassageResponse(id=p.id,book_id=book.id,book_title=book.title,author=book.author,reference_type=p.reference_type,reference_label=p.reference_label,excerpt=p.content[:500],extraction_version=p.extraction_version)

@router.post("/books",response_model=BookResponse,status_code=201)
async def add_book(title:str=Form(),author:str=Form(),topic:str=Form(),source:str=Form(),language:str=Form("en"),edition:str|None=Form(None),publication_year:int|None=Form(None),file:UploadFile=File(),user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    ext=Path(file.filename or "").suffix.lower(); max_size=int(os.environ.get("BOOK_MAX_UPLOAD_BYTES","20971520"))
    if ext not in ALLOWED: raise HTTPException(415,"Supported file types are TXT, EPUB, and text-based PDF")
    data=await file.read(max_size+1)
    if len(data)>max_size: raise HTTPException(413,"Book file exceeds the configured upload limit")
    if not data: raise HTTPException(422,"Book file is empty")
    book_id=uuid.uuid4(); key=f"{user.id}/{book_id}{ext}"; path=root()/key; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
    book=Book(id=book_id,user_id=user.id,title=" ".join(title.split()),author=" ".join(author.split()),edition=edition,publication_year=publication_year,topic=" ".join(topic.split()),source=" ".join(source.split()),language=language.strip().lower(),original_filename=Path(file.filename or f"book{ext}").name,media_type=ALLOWED[ext],storage_key=key,file_size=len(data),checksum_sha256=hashlib.sha256(data).hexdigest(),extraction_version=VERSION,ingestion_status="processing")
    session.add(book)
    try: process(session,book,path);session.commit();session.refresh(book)
    except Exception: session.rollback();path.unlink(missing_ok=True);raise
    return book
@router.get("/books",response_model=list[BookResponse])
def books(user:User=Depends(get_current_user),session:Session=Depends(get_session)): return session.scalars(select(Book).where(Book.user_id==user.id).order_by(Book.title)).all()
@router.get("/books/{book_id}",response_model=BookResponse)
def get_book(book_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)): return owned(session,user.id,book_id)
@router.patch("/books/{book_id}",response_model=BookResponse)
def edit_book(book_id:uuid.UUID,payload:BookUpdate,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    book=owned(session,user.id,book_id)
    for k,v in payload.model_dump().items(): setattr(book,k,v)
    session.commit();session.refresh(book);return book
@router.post("/books/{book_id}/reprocess",response_model=BookResponse)
def reprocess(book_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    book=owned(session,user.id,book_id); path=root()/book.storage_key
    if not path.exists(): raise HTTPException(409,"Private source file is missing")
    checksum=hashlib.sha256(path.read_bytes()).hexdigest()
    if checksum!=book.checksum_sha256: book.checksum_sha256=checksum;book.extraction_version+=1
    process(session,book,path);session.commit();session.refresh(book);return book
@router.delete("/books/{book_id}",status_code=204)
def remove_book(book_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    book=owned(session,user.id,book_id); path=root()/book.storage_key;session.delete(book);session.commit();path.unlink(missing_ok=True)
@router.get("/book-search",response_model=list[PassageResponse])
def search_books(q:str,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    if not q.strip(): return []
    rows=session.execute(select(Book,BookPassage).join(BookPassage,BookPassage.book_id==Book.id).where(Book.user_id==user.id,BookPassage.search_vector.op("@@")(func.websearch_to_tsquery("simple",q))).order_by(func.ts_rank(BookPassage.search_vector,func.websearch_to_tsquery("simple",q)).desc()).limit(20)).all()
    return [passage_body(b,p) for b,p in rows]
@router.get("/book-passages/{passage_id}",response_model=PassageResponse)
def get_passage(passage_id:uuid.UUID,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    row=session.execute(select(Book,BookPassage).join(BookPassage,BookPassage.book_id==Book.id).where(BookPassage.id==passage_id,BookPassage.user_id==user.id)).first()
    if not row: raise HTTPException(404,"Passage not found")
    return passage_body(*row)
@router.post("/decisions/{decision_id}/passages/{passage_id}",status_code=201)
def attach_passage(decision_id:uuid.UUID,passage_id:uuid.UUID,payload:AttachPassage,user:User=Depends(get_current_user),session:Session=Depends(get_session)):
    if not session.scalar(select(InvestmentDecision).where(InvestmentDecision.id==decision_id,InvestmentDecision.user_id==user.id)): raise HTTPException(404,"Decision not found")
    if not session.scalar(select(BookPassage).where(BookPassage.id==passage_id,BookPassage.user_id==user.id)): raise HTTPException(404,"Passage not found")
    link=DecisionPassage(user_id=user.id,decision_id=decision_id,passage_id=passage_id,note=payload.note);session.add(link);session.add(AuditEvent(user_id=user.id,event_type="learning_passage_attached",entity_type="investment_decision",entity_id=decision_id,details={"passage_id":str(passage_id),"affects_decision_score":False,"learning_support_only":True}));session.commit()
    return {"id":str(link.id),"learning_support_only":True,"affects_decision_score":False,"order_placed":False}
