"""งานประมวลผลเบื้องหลัง: ส่งภาพทีละหน้าให้โมเดล แล้วบันทึกผล"""
import json
import time

from . import storage
from .adapters import REGISTRY
from .adapters.base import UnreadableResponse, clean_blocks
from .render import page_path


def execute_run(run_id: str) -> None:
    run = storage.get_run(run_id, with_pages=False)
    adapter = REGISTRY[run["model_id"]]
    doc_dir = storage.document_dir(run["document_id"])
    storage.update_run(run_id, status="running")
    total = 0.0
    try:
        for page in range(1, run["page_count"] + 1):
            t0 = time.time()
            raw, meta = "", {}
            try:
                items, raw, meta = adapter.run_page(page_path(doc_dir, page))
                blocks, warnings = clean_blocks(items, page)
            except UnreadableResponse as e:  # เก็บคำตอบดิบไว้ด้วย จะได้เปิดดูว่าโมเดลตอบอะไรมา
                blocks, warnings, raw, meta = [], [f"อ่านคำตอบของโมเดลไม่ได้: {e}"], e.raw, e.meta
            except (json.JSONDecodeError, AttributeError, TypeError) as e:  # คำตอบไม่ใช่ JSON ตามที่คาด
                blocks, warnings = [], [f"อ่านคำตอบของโมเดลไม่ได้: {e}"]
            seconds = round(time.time() - t0, 2)
            total += seconds
            storage.add_run_page(run_id, page, seconds, warnings, blocks, raw, meta)
            storage.update_run(run_id, pages_done=page, total_seconds=round(total, 2))
        storage.update_run(run_id, status="done")
    except Exception as e:  # เช่น API key ผิด เครือข่ายล่ม ชื่อรุ่นไม่ถูกต้อง
        storage.update_run(run_id, status="failed", error=f"{type(e).__name__}: {e}"[:500])
