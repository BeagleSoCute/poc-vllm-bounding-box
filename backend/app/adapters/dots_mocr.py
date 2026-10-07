"""ตัวเชื่อม dots.mocr (self-hosted)

โมเดลรันบนเครื่องเองผ่านบริการใน dots-mocr-service/ ไฟล์นี้ส่งภาพไปให้บริการนั้น
dots.mocr คืนพิกัดเป็น [x1, y1, x2, y2] หน่วยพิกเซลของภาพที่โมเดลได้รับ (บริการปรับขนาดภาพก่อนส่ง
และแจ้งขนาดนั้นกลับมา) ไฟล์นี้แปลงเป็นสเกล 0-1 ด้วยขนาดดังกล่าว
"""
import json
import os
import urllib.request
from pathlib import Path

from .base import Adapter, UnreadableResponse

# หมวดของ dots.mocr จัดเข้า 4 ประเภทของแอป หมวดเดิมยังดูได้ในคำตอบดิบ
# หมวดที่ไม่อยู่ในรายการนี้ (เช่น Text, List-item, Page-header, Formula) นับเป็นข้อความ
CATEGORY_TYPE = {"Title": "title", "Section-header": "title", "Table": "table", "Picture": "figure"}


def parse_response(output: str, width: int, height: int) -> list:
    data = json.loads(output)
    out = []
    for it in data:
        box = it.get("bbox")
        bbox = None
        if (isinstance(box, list) and len(box) == 4
                and all(isinstance(v, (int, float)) for v in box)):
            x0, y0, x1, y1 = box
            bbox = [x0 / width, y0 / height, x1 / width, y1 / height]
        out.append({"type": CATEGORY_TYPE.get(it.get("category"), "text"),
                    "text": it.get("text") or "", "bbox": bbox})
    return out


class DotsMocrAdapter(Adapter):
    id = "dots-mocr"
    name = "dots.mocr"
    kind = "self-hosted"
    raw_note = ("bbox คือ [x1, y1, x2, y2] หน่วยพิกเซลของภาพที่โมเดลได้รับ"
                " ซึ่งถูกปรับขนาดก่อนส่ง (ดูขนาดในข้อมูลประกอบ) ไม่ใช่ของภาพต้นฉบับ")

    def __init__(self):
        self._url = os.environ.get("DOTS_MOCR_URL", "http://localhost:8120").rstrip("/")
        self._version = "dots-mocr"   # รู้ชื่อรุ่นจริงเมื่อติดต่อบริการได้

    def version(self) -> str:
        return self._version

    def availability(self) -> tuple:
        try:
            with urllib.request.urlopen(f"{self._url}/health", timeout=2) as resp:
                self._version = json.load(resp)["model"]
            return True, ""
        except (OSError, ValueError, KeyError):
            return False, "ยังไม่ได้เปิดบริการ รัน dots-mocr-service/start.sh ก่อน"

    def run_page(self, image_path: Path) -> tuple:
        req = urllib.request.Request(f"{self._url}/parse", data=image_path.read_bytes(),
                                     headers={"Content-Type": "image/png"})
        # โมเดลเขียนคำตอบทีละ token หน้าที่มีข้อความมากใช้เวลาหลายนาที
        with urllib.request.urlopen(req, timeout=1800) as resp:
            result = json.load(resp)
        raw = result["output"]   # คำตอบของโมเดลตามที่ได้มา
        width, height = result["image_width"], result["image_height"]
        meta = {
            "model_version": result["model"],
            "image_size": f"{width} × {height} px",
            "input_tokens": result["prompt_tokens"],
            "output_tokens": result["generation_tokens"],
            "total_tokens": result["prompt_tokens"] + result["generation_tokens"],
            "finish_reason": "MAX_TOKENS" if result["truncated"] else "STOP",
        }
        try:
            return parse_response(raw, width, height), raw, meta
        except (json.JSONDecodeError, AttributeError, TypeError) as e:
            raise UnreadableResponse(f"{type(e).__name__}: {e}", raw, meta)
