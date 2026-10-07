"""ตัวเชื่อม PaddleOCR-VL (self-hosted)

โมเดลรันบนเครื่องเองผ่านบริการใน paddleocr-service/ ไฟล์นี้ส่งภาพไปให้บริการนั้น
PaddleOCR คืนพิกัดเป็น [x1, y1, x2, y2] หน่วยพิกเซลของภาพ ไฟล์นี้แปลงเป็นสเกล 0-1
"""
import json
import os
import urllib.request
from pathlib import Path

from .base import Adapter, UnreadableResponse

# ป้ายของ PaddleOCR มีหลายสิบแบบ จัดเข้า 4 ประเภทของแอป ป้ายเดิมยังดูได้ในคำตอบดิบ
# ป้ายที่ไม่อยู่ในรายการนี้ (เช่น text, header, footer, formula) นับเป็นข้อความ
LABEL_TYPE = {
    "doc_title": "title", "paragraph_title": "title",
    "table": "table",
    "image": "figure", "chart": "figure", "seal": "figure",
    "header_image": "figure", "footer_image": "figure",
}


def parse_response(raw: str) -> list:
    data = json.loads(raw)
    width, height = data["width"], data["height"]
    out = []
    for it in data["parsing_res_list"]:
        box = it.get("block_bbox")
        bbox = None
        if (isinstance(box, list) and len(box) == 4
                and all(isinstance(v, (int, float)) for v in box)):
            x0, y0, x1, y1 = box
            bbox = [x0 / width, y0 / height, x1 / width, y1 / height]
        out.append({"type": LABEL_TYPE.get(it.get("block_label"), "text"),
                    "text": it.get("block_content", ""), "bbox": bbox})
    return out


class PaddleOCRVLAdapter(Adapter):
    id = "paddleocr-vl"
    name = "PaddleOCR-VL"
    kind = "self-hosted"
    raw_note = ("block_bbox คือ [x1, y1, x2, y2] หน่วยพิกเซลของภาพหน้าเอกสาร"
                " · score ใน layout_det_res คือความมั่นใจของการหาตำแหน่งบล็อก (0-1)")

    def __init__(self):
        self._url = os.environ.get("PADDLEOCR_VL_URL", "http://localhost:8118").rstrip("/")
        self._version = "paddleocr-vl"   # รู้ชื่อรุ่นจริงเมื่อติดต่อบริการได้

    def version(self) -> str:
        return self._version

    def availability(self) -> tuple:
        try:
            with urllib.request.urlopen(f"{self._url}/health", timeout=2) as resp:
                self._version = json.load(resp)["model"]
            return True, ""
        except (OSError, ValueError, KeyError):
            return False, "ยังไม่ได้เปิดบริการ รัน paddleocr-service/start.sh ก่อน"

    def run_page(self, image_path: Path) -> tuple:
        req = urllib.request.Request(f"{self._url}/parse", data=image_path.read_bytes(),
                                     headers={"Content-Type": "image/png"})
        # หน้าแรกหลังเปิดบริการช้า เพราะต้องโหลดโมเดลเข้าหน่วยความจำ
        with urllib.request.urlopen(req, timeout=600) as resp:
            raw = resp.read().decode("utf-8")
        meta = {"model_version": self._version}
        try:
            data = json.loads(raw)
            meta["image_size"] = f"{data['width']} × {data['height']} px"
            return parse_response(raw), raw, meta
        except (json.JSONDecodeError, AttributeError, TypeError, KeyError) as e:
            raise UnreadableResponse(f"{type(e).__name__}: {e}", raw, meta)
