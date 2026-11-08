"""HTTP API for the React frontend. Thin layer: every route calls a function in core.py or ingest.py."""
from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import core, storage
from .config import settings
from .ingest import IngestError, fetch_pdf_from_url, register_upload, run_ingestion

app = FastAPI(title="PaperLens API", version="2.0")


@app.exception_handler(core.UserInputError)
async def user_error(_, exc: core.UserInputError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(IngestError)
async def ingest_error(_, exc: IngestError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


class UrlUpload(BaseModel):
    url: str


class SessionCreate(BaseModel):
    paper_id: str
    reading_goal: str = ""
    research_context: str = ""
    language: str = "English"


class SessionPatch(BaseModel):
    reading_goal: str | None = None
    research_context: str | None = None
    language: str | None = None


class MessageIn(BaseModel):
    message: str


class JudgmentIn(BaseModel):
    verdict: str
    rationale: str


@app.get("/api/health")
def health():
    return {"ok": True, "api_key_configured": bool(settings.api_key), "config": settings.public()}


# ------------------------------------------------------------------ papers

def _start_ingestion(meta: dict, background: BackgroundTasks) -> dict:
    if meta.get("status") != "ready":
        storage.update_paper_meta(meta["paper_id"], status="queued", error=None)
        background.add_task(run_ingestion, meta["paper_id"])
    return storage.load_paper_meta(meta["paper_id"])


@app.post("/api/papers")
async def upload_paper(background: BackgroundTasks, file: UploadFile = File(...)):
    data = await file.read()
    meta = register_upload(data, file.filename or "paper.pdf")
    return _start_ingestion(meta, background)


@app.post("/api/papers/from-url")
def upload_paper_url(body: UrlUpload, background: BackgroundTasks):
    data, name = fetch_pdf_from_url(body.url)
    meta = register_upload(data, name)
    return _start_ingestion(meta, background)


@app.get("/api/papers/{paper_id}")
def paper_status(paper_id: str):
    meta = storage.load_paper_meta(paper_id)
    if not meta:
        raise HTTPException(404, "Unknown paper")
    meta.pop("trace", None)
    return meta


@app.post("/api/papers/{paper_id}/retry")
def retry_paper(paper_id: str, background: BackgroundTasks):
    meta = storage.load_paper_meta(paper_id)
    if not meta or not storage.paper_pdf_path(paper_id).exists():
        raise HTTPException(404, "Unknown paper; please upload it again.")
    storage.update_paper_meta(paper_id, status="queued", error=None, failed_stage=None)
    background.add_task(run_ingestion, paper_id)
    return storage.load_paper_meta(paper_id)


@app.get("/api/papers/{paper_id}/pdf")
def paper_pdf(paper_id: str):
    path = storage.paper_pdf_path(paper_id)
    if not path.exists():
        raise HTTPException(404, "Unknown paper")
    return FileResponse(path, media_type="application/pdf")


# ------------------------------------------------------------------ sessions

@app.get("/api/sessions")
def sessions():
    return [{"session_id": s["session_id"], "paper_id": s["paper_id"], "paper_title": s.get("paper_title", ""),
             "reading_goal": s.get("reading_goal", ""), "updated_at": s.get("updated_at"),
             "first_question": next((m["text"] for m in s.get("messages", []) if m["role"] == "user"), "")}
            for s in storage.list_sessions()]


@app.post("/api/sessions")
def create_session(body: SessionCreate):
    return core.create_session(body.paper_id, body.reading_goal, body.research_context, body.language)


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    session = storage.load_session(session_id)
    if not session:
        raise HTTPException(404, "Unknown session")
    return session


@app.patch("/api/sessions/{session_id}")
def patch_session(session_id: str, body: SessionPatch):
    return core.update_session(session_id, body.reading_goal, body.research_context, body.language)


@app.post("/api/sessions/{session_id}/messages")
def send_message(session_id: str, body: MessageIn):
    return core.run_turn(session_id, body.message)


@app.post("/api/sessions/{session_id}/critical-review")
def critical_review(session_id: str):
    return core.run_critical_review(session_id)


@app.post("/api/sessions/{session_id}/judgment")
def judgment(session_id: str, body: JudgmentIn):
    return core.submit_judgment(session_id, body.verdict, body.rationale)


@app.post("/api/sessions/{session_id}/note")
def note(session_id: str):
    return core.generate_note(session_id)


@app.put("/api/sessions/{session_id}/note")
def edit_note(session_id: str, body: dict):
    return core.save_note(session_id, body)


@app.get("/api/sessions/{session_id}/export")
def export(session_id: str):
    data = core.export_session(session_id)
    return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="paperlens-{session_id}.json"'})
