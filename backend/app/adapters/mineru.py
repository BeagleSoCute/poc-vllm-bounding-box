"""ตัวเชื่อม MinerU (self-hosted)

โมเดลรันบนเครื่องเองผ่านเซิร์ฟเวอร์ของ MinerU (mineru-service/start.sh) ไฟล์นี้เรียก API ของเซิร์ฟเวอร์นั้น
MinerU คืนพิกัดเป็น [x0, y0, x1, y1] สัดส่วน 0-1 ของหน้า ซึ่งตรงกับรูปแบบมาตรฐานของแอปอยู่แล้ว
"""
import base64
import json
import os
import time
import urllib.request
from pathlib import Path

from .base import Adapter, UnreadableResponse

# ประเภทบล็อกของ MinerU จัดเข้า 4 ประเภทของแอป ประเภทเดิมยังดูได้ในคำตอบดิบ
# ประเภทที่ไม่อยู่ในรายการนี้ (เช่น text, header, footer, list) นับเป็นข้อความ
BLOCK_TYPE = {"title": "title", "table": "table", "image": "figure", "chart": "figure"}
TIMEOUT_SECONDS = 600


def block_text(content) -> str:
    """รวมข้อความจากเนื้อหาของบล็อก ซึ่งเป็นรายการซ้อนของ {"type": ..., "content": ...}"""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return block_text(content.get("content"))
    if isinstance(content, list):
        return "\n".join(t for t in map(block_text, content) if t)
    return ""


def parse_response(raw: str) -> list:
    data = json.loads(raw)
    out = []
    for page in data["pages"]:
        for it in page["blocks"]:
            box = it.get("bbox")
            ok = (isinstance(box, list) and len(box) == 4
                  and all(isinstance(v, (int, float)) for v in box))
            out.append({"type": BLOCK_TYPE.get(it.get("type"), "text"),
                        "text": block_text(it.get("content")), "bbox": box if ok else None})
    return out


class MinerUAdapter(Adapter):
    id = "mineru"
    name = "MinerU"
    kind = "self-hosted"
    raw_note = "bbox คือ [x0, y0, x1, y1] เป็นสัดส่วน 0-1 ของหน้า จุดกำเนิดอยู่มุมซ้ายบน"

    def __init__(self):
        self._url = os.environ.get("MINERU_URL", "http://localhost:8119").rstrip("/")
        self._tier = os.environ.get("MINERU_TIER", "standard")
        self._version = "mineru"   # รู้ชื่อรุ่นจริงเมื่อติดต่อบริการได้

    def _call(self, method: str, path: str, body=None, timeout: int = 60) -> bytes:
        req = urllib.request.Request(
            self._url + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()

    def version(self) -> str:
        return self._version

    def availability(self) -> tuple:
        try:
            tiers = json.loads(self._call("GET", "/v1/tiers", timeout=2))["data"]
            model = next(t["current_model"] for t in tiers if t["id"] == self._tier)
            self._version = f"{model} ({self._tier})"
            return True, ""
        except (OSError, ValueError, KeyError, StopIteration):
            return False, "ยังไม่ได้เปิดบริการ รัน mineru-service/start.sh ก่อน"

    def run_page(self, image_path: Path) -> tuple:
        image = base64.b64encode(image_path.read_bytes()).decode()
        job = json.loads(self._call("POST", "/v1/parse/jobs", {
            "files": [{"source": {"type": "inline", "name": "page.png", "data": image}}],
            "tier": self._tier, "output_formats": ["middle_json"]}))
        deadline = time.time() + TIMEOUT_SECONDS
        while job["status"] in ("queued", "running"):
            if time.time() > deadline:
                raise TimeoutError(f"MinerU ไม่ตอบภายใน {TIMEOUT_SECONDS} วินาที")
            time.sleep(0.5)
            job = json.loads(self._call("GET", f"/v1/parse/jobs/{job['job_id']}"))
        result = job["files"][0]
        if job["status"] != "completed" or not (result.get("output_files") or {}).get("middle_json"):
            raise RuntimeError(f"MinerU ประมวลผลไม่สำเร็จ ({job['status']}): {result.get('error')}")

        file_id = result["output_files"]["middle_json"]["file_id"]
        raw = self._call("GET", f"/v1/files/{file_id}/content").decode("utf-8")
        try:
            self._call("DELETE", f"/v1/files/{file_id}")   # ไม่ทิ้งไฟล์ผลลัพธ์ค้างไว้ที่เซิร์ฟเวอร์
        except OSError:
            pass

        parse = result.get("parse") or {}
        meta = {"model_version": self._version, "parser_version": parse.get("parser_version"),
                "duration_ms": parse.get("duration_ms")}
        try:
            meta["parse_mode"] = json.loads(raw)["extensions"]["mineru"]["parse_mode"]
            meta = {k: v for k, v in meta.items() if v is not None}
            return parse_response(raw), raw, meta
        except (json.JSONDecodeError, AttributeError, TypeError, KeyError) as e:
            raise UnreadableResponse(f"{type(e).__name__}: {e}", raw,
                                     {k: v for k, v in meta.items() if v is not None})
