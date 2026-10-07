"""ตัวเชื่อม Gemini (Cloud API)

Gemini คืนพิกัดเป็น [ymin, xmin, ymax, xmax] สเกล 0-1000
ไฟล์นี้แปลงเป็นรูปแบบมาตรฐาน [x_min, y_min, x_max, y_max] สเกล 0-1
"""
import json
import os
import re
from pathlib import Path

from .base import Adapter, UnreadableResponse

PROMPT = """You are a document OCR engine. Detect every content block on this page in natural reading order.

Return ONLY a JSON array. Each element must be an object with:
- "box_2d": [ymin, xmin, ymax, xmax], integers normalized to 0-1000 relative to the image
- "label": one of "text", "title", "table", "figure"
- "text": the exact text inside the box, in its original language. Do not translate or correct it.
  For "table", write the table as Markdown. For "figure", use an empty string.

Rules:
- One box per paragraph, heading, table or figure. Boxes must fit tightly around the content.
- Include page headers and footers as their own blocks.
- Do not invent text that is not visible on the page."""

# บังคับรูปแบบคำตอบด้วย schema ถ้าไม่บังคับ บางครั้งโมเดลคืน JSON ที่ขาดตอนกลางรายการ
# ทำให้อ่านไม่ได้ทั้งหน้า
RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "box_2d": {"type": "ARRAY", "items": {"type": "INTEGER"},
                       "minItems": 4, "maxItems": 4},
            "label": {"type": "STRING", "enum": ["text", "title", "table", "figure"]},
            "text": {"type": "STRING"},
        },
        "required": ["box_2d", "label", "text"],
        "propertyOrdering": ["box_2d", "label", "text"],
    },
}


def parse_response(raw: str) -> list:
    text = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    data = json.loads(text)
    items = data if isinstance(data, list) else data.get("blocks", [])
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        box = it.get("box_2d")
        bbox = None
        if (isinstance(box, list) and len(box) == 4
                and all(isinstance(v, (int, float)) for v in box)):
            ymin, xmin, ymax, xmax = [v / 1000 for v in box]
            bbox = [xmin, ymin, xmax, ymax]
        out.append({"type": it.get("label", "text"), "text": it.get("text", ""), "bbox": bbox})
    return out


def response_meta(resp) -> dict:
    """ข้อมูลประกอบที่ Gemini ส่งมากับคำตอบ ช่องที่ไม่มีค่าไม่ถูกเก็บ"""
    usage = resp.usage_metadata
    reason = getattr((resp.candidates or [None])[0], "finish_reason", None)
    meta = {
        "input_tokens": getattr(usage, "prompt_token_count", None),
        "output_tokens": getattr(usage, "candidates_token_count", None),
        "thinking_tokens": getattr(usage, "thoughts_token_count", None),
        "total_tokens": getattr(usage, "total_token_count", None),
        "finish_reason": getattr(reason, "name", reason),
        "model_version": resp.model_version,
        "response_id": resp.response_id,
    }
    return {k: v for k, v in meta.items() if v is not None}


class GeminiAdapter(Adapter):
    id = "gemini"
    name = "Gemini"
    kind = "cloud"
    raw_note = ("box_2d คือ [ymin, xmin, ymax, xmax] สเกล 0-1000 ของหน้า (แกน y มาก่อน)"
                " · เหตุผลที่หยุดตอบ: STOP คือตอบจบปกติ MAX_TOKENS คือคำตอบถูกตัดเพราะยาวเกิน")

    def __init__(self):
        self._client = None

    def version(self) -> str:
        return os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

    def availability(self) -> tuple:
        if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            return True, ""
        return False, "ยังไม่ได้ตั้ง GEMINI_API_KEY"

    def run_page(self, image_path: Path) -> tuple:
        from google import genai
        from google.genai import types
        if self._client is None:
            # Gemini ตอบ 503 (ผู้ใช้หนาแน่น) เป็นช่วงสั้นๆ ได้ จึงลองใหม่เอง 3 ครั้ง (รอ 2, 4, 8 วินาที)
            # ไม่ลองมากกว่านี้เพราะคำขอที่ได้ 503 ก็ดูจะถูกนับในโควตารายวันของ free tier
            # ไม่ลองใหม่เมื่อได้ 429 เพราะโควตารายวันหมดแล้ว ลองอีกก็ไม่ผ่านและเปลืองโควตา
            self._client = genai.Client(http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(
                    attempts=4, initial_delay=2, max_delay=8,
                    http_status_codes=[500, 502, 503, 504])))
        resp = self._client.models.generate_content(
            model=self.version(),
            contents=[
                types.Part.from_bytes(data=image_path.read_bytes(), mime_type="image/png"),
                PROMPT,
            ],
            config=types.GenerateContentConfig(
                temperature=0, response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA),
        )
        raw = resp.text or ""
        meta = response_meta(resp)
        try:
            return parse_response(raw), raw, meta
        except (json.JSONDecodeError, AttributeError, TypeError) as e:
            raise UnreadableResponse(str(e), raw, meta)
