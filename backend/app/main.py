"""API ของแอปเดโม Bounding Box POC

ไม่มี endpoint สำหรับแก้ไขหรือลบผลลัพธ์ เพราะตำแหน่งข้อความเป็นข้อมูลอ้างอิงจากต้นทาง
"""
import hashlib
import os
import shutil
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import adapters, pipeline, render, storage

MAX_UPLOAD_BYTES = 30 * 1024 * 1024
DPI = int(os.environ.get("RENDER_DPI", "150"))

app = FastAPI(title="Bounding Box POC")
storage.init()


class RunRequest(BaseModel):
    model_id: str
    force: bool = False   # True = ประมวลผลใหม่ แม้มีผลเดิมอยู่แล้ว (ผลเดิมยังถูกเก็บไว้)


def _document_or_404(doc_id: str) -> dict:
    doc = storage.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "ไม่พบเอกสาร")
    return doc


@app.get("/api/models")
def list_models():
    return adapters.describe()


@app.get("/api/documents")
def list_documents():
    return storage.list_documents()


@app.post("/api/documents")
def upload_document(file: UploadFile = File(...)):
    name = Path(file.filename or "document").name
    ext = Path(name).suffix.lower()
    if ext not in render.ALLOWED_EXT:
        raise HTTPException(400, "รองรับเฉพาะไฟล์ PDF, PNG, JPG และ WEBP")
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "ไฟล์ใหญ่เกิน 30 MB")
    if not content:
        raise HTTPException(400, "ไฟล์ว่างเปล่า")

    sha = hashlib.sha256(content).hexdigest()
    existing = storage.find_document_by_hash(sha)
    if existing:
        return existing   # ไฟล์เดียวกันเคยอัปโหลดแล้ว ใช้เอกสารเดิมและผลที่เก็บไว้

    doc_id = storage.new_id()
    doc_dir = storage.document_dir(doc_id)
    doc_dir.mkdir(parents=True)
    source = doc_dir / f"source{ext}"
    source.write_bytes(content)
    try:
        pages = render.render(source, doc_dir, DPI)
    except Exception as e:
        shutil.rmtree(doc_dir, ignore_errors=True)
        raise HTTPException(400, f"เปิดไฟล์นี้ไม่ได้: {e}")
    return storage.add_document(doc_id, name, sha, pages, DPI if ext == ".pdf" else None)


@app.get("/api/documents/{doc_id}/pages/{page}")
def get_page_image(doc_id: str, page: int):
    doc = _document_or_404(doc_id)
    if not 1 <= page <= doc["page_count"]:
        raise HTTPException(404, "ไม่พบหน้านี้")
    return FileResponse(render.page_path(storage.document_dir(doc_id), page),
                        media_type="image/png",
                        headers={"Cache-Control": "max-age=86400"})


@app.get("/api/documents/{doc_id}/runs")
def list_runs(doc_id: str):
    _document_or_404(doc_id)
    return storage.list_runs(doc_id)


@app.post("/api/documents/{doc_id}/runs")
def start_run(doc_id: str, req: RunRequest, background: BackgroundTasks):
    _document_or_404(doc_id)
    adapter = adapters.REGISTRY.get(req.model_id)
    if not adapter:
        raise HTTPException(404, "ไม่พบโมเดลนี้")

    active = storage.latest_run(doc_id, req.model_id, ("queued", "running"))
    if active:
        return storage.get_run(active)          # กำลังประมวลผลอยู่ ไม่เริ่มซ้ำ
    if not req.force:
        done = storage.latest_run(doc_id, req.model_id)
        if done:
            return storage.get_run(done)        # ใช้ผลที่เก็บไว้

    ok, reason = adapter.availability()
    if not ok:
        raise HTTPException(409, f"โมเดล {adapter.name} ยังใช้ไม่ได้: {reason}")

    run_id = storage.add_run(doc_id, adapter.id, adapter.version())
    background.add_task(pipeline.execute_run, run_id)
    return storage.get_run(run_id)


@app.get("/api/runs")
def list_all_runs():
    return storage.list_all_runs()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = storage.get_run(run_id)
    if not run:
        raise HTTPException(404, "ไม่พบผลการประมวลผล")
    return run
