"""Text-to-STL Agent Studio - FastAPI server."""

import asyncio
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

from app import config
from app.config import (
    ALLOWED_IMAGE_TYPES, BED_X, BED_Y, BED_Z, DATA_DIR, FRONTEND_DIST,
    MAX_IMAGE_MB, MAX_REFERENCE_IMAGES, MAX_VISUAL_REVISIONS,
)
from app.llm import LLMError, backend_status, invalidate_status_cache, verify_api_key
from app.orchestrator import run_job
from app.state import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="PrintForge AI - Text-to-STL Agent Studio")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
executor = ThreadPoolExecutor(max_workers=2)


@app.get("/api/health")
def health():
    status = backend_status()
    return {
        "ok": True,
        "llm_backend": config.LLM_BACKEND,
        "llm_ready": status["ready"],
        "llm_detail": status.get("detail", ""),
        "model": config.MODEL if config.LLM_BACKEND == "api" else (config.CLAUDE_CLI_MODEL or "abonelik varsayılanı"),
        "bed_mm": [BED_X, BED_Y, BED_Z],
        "max_revisions": MAX_VISUAL_REVISIONS,
    }


class ApiKeyIn(BaseModel):
    api_key: str


@app.post("/api/api-key")
def set_api_key(body: ApiKeyIn):
    """Lets the web UI collect the user's own Claude API key on first run, instead of
    requiring a manual backend/.env edit — so anyone who downloads the project can use it."""
    key = body.api_key.strip()
    if not key:
        raise HTTPException(400, "API anahtarı boş olamaz.")
    try:
        verify_api_key(key)
    except LLMError as e:
        raise HTTPException(400, str(e))
    config.set_api_key(key)
    invalidate_status_cache()
    return {"ok": True}


@app.post("/api/generate")
async def generate(
    prompt: str = Form("", max_length=4000),
    session_id: str | None = Form(None),
    images: list[UploadFile] = File(default=[]),
):
    prompt = prompt.strip()
    images = [f for f in images if f.filename]
    if not prompt and not images:
        raise HTTPException(400, "Mesaj yazın veya en az bir ürün görseli ekleyin.")
    if len(images) > MAX_REFERENCE_IMAGES:
        raise HTTPException(400, f"En fazla {MAX_REFERENCE_IMAGES} görsel yükleyebilirsiniz.")

    session = store.get_or_create_session(session_id)
    job = store.create_job(session, prompt)

    if images:
        ref_dir = job.dir / "reference"
        ref_dir.mkdir(exist_ok=True)
        saved: list[Path] = []
        for i, up in enumerate(images):
            ext = ALLOWED_IMAGE_TYPES.get((up.content_type or "").lower())
            if not ext:
                raise HTTPException(400, f"Desteklenmeyen görsel türü: {up.content_type or up.filename}. PNG, JPEG veya WEBP kullanın.")
            data = await up.read()
            if len(data) > MAX_IMAGE_MB * 1024 * 1024:
                raise HTTPException(400, f"'{up.filename}' {MAX_IMAGE_MB} MB sınırını aşıyor.")
            dest = ref_dir / f"ref_{i}{ext}"
            dest.write_bytes(data)
            saved.append(dest)
        job.reference_images = saved

    executor.submit(run_job, job, session)
    return {"job_id": job.id, "session_id": session.id, "is_revision": session.plan is not None}


@app.post("/api/sessions/new")
def new_session():
    return {"session_id": store.get_or_create_session(None).id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = store.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "İş bulunamadı")
    return {"id": job.id, "status": job.status, "events": job.events, "result": job.result}


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request, after: int = -1):
    job = store.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "İş bulunamadı")

    async def stream():
        last = after
        idle = 0
        while True:
            if await request.is_disconnected():
                return
            new = job.events_after(last)
            for ev in new:
                last = ev["seq"]
                yield f"id: {ev['seq']}\nevent: message\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
                if ev["type"] == "done":
                    return
            idle = 0 if new else idle + 1
            if idle and idle % 50 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.2)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/jobs/{job_id}/download")
def download(job_id: str):
    job = store.jobs.get(job_id)
    if not job or not job.result:
        raise HTTPException(404, "Bu iş için hazır STL yok")
    name = re.sub(r"[^a-zA-Z0-9_-]+", "_", job.result.get("object_name") or "model").strip("_") or "model"
    return FileResponse(job.dir / "final.stl", media_type="model/stl", filename=f"{name}.stl")


app.mount("/files", StaticFiles(directory=DATA_DIR), name="files")

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000)
