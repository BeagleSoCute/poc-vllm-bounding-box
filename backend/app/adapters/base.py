"""โครงของตัวเชื่อมโมเดล (adapter)

adapter แต่ละตัวต้องคืนบล็อกในรูปแบบมาตรฐานเดียวกัน:
    {"type": "text|title|table|figure", "text": "...", "bbox": [x_min, y_min, x_max, y_max]}
โดย bbox เป็นสัดส่วน 0-1 ของหน้า จุดกำเนิดอยู่มุมซ้ายบน
"""
from pathlib import Path

BLOCK_TYPES = {"text", "title", "table", "figure"}


class Adapter:
    id = ""            # รหัสที่ใช้ใน API
    name = ""          # ชื่อที่แสดงในเมนู
    kind = ""          # cloud | self-hosted
    raw_note = ""      # คำอธิบายรูปแบบพิกัดในคำตอบดิบ แสดงในหน้าจอคู่กับคำตอบดิบ

    def version(self) -> str:
        """ชื่อรุ่นของโมเดล บันทึกไว้กับผลลัพธ์ทุกชุด"""
        return self.id

    def availability(self) -> tuple:
        """คืน (พร้อมใช้หรือไม่, เหตุผลถ้าไม่พร้อม)"""
        return True, ""

    def run_page(self, image_path: Path) -> tuple:
        """คืน (รายการบล็อก, คำตอบดิบของโมเดลเป็นข้อความ, ข้อมูลประกอบ)

        ข้อมูลประกอบเป็น dict ของสิ่งที่ API ส่งมาพร้อมคำตอบ เช่น จำนวน token
        ถ้าโมเดลไม่มีให้ คืน {} ได้
        """
        raise NotImplementedError


class UnreadableResponse(Exception):
    """คำตอบของโมเดลแปลงเป็นบล็อกไม่ได้ เก็บคำตอบดิบไว้ให้เปิดดูในหน้าจอได้"""

    def __init__(self, reason: str, raw: str, meta: dict):
        super().__init__(reason)
        self.raw, self.meta = raw, meta


class NotConnected(Adapter):
    """โมเดลที่อยู่ใน shortlist แต่ยังไม่ได้เขียนตัวเชื่อม แสดงในเมนูแบบเลือกไม่ได้"""
    kind = "self-hosted"

    def __init__(self, id: str, name: str):
        self.id, self.name = id, name

    def availability(self) -> tuple:
        return False, "ยังไม่ได้เชื่อมต่อ"


def clean_blocks(items: list, page: int) -> tuple:
    """ตรวจและจัดรูปบล็อกจาก adapter: ตัดพิกัดที่หลุดขอบ ทิ้งกรอบที่ใช้ไม่ได้ ใส่รหัสและลำดับ"""
    blocks, warnings = [], []
    for n, it in enumerate(items, start=1):
        box = it.get("bbox") if isinstance(it, dict) else None
        if not (isinstance(box, (list, tuple)) and len(box) == 4
                and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in box)):
            warnings.append(f"บล็อกที่ {n}: ไม่มีพิกัดหรือรูปแบบผิด จึงข้าม")
            continue
        if any(v < 0 or v > 1 for v in box):
            warnings.append(f"บล็อกที่ {n}: พิกัดหลุดขอบหน้า จึงตัดให้อยู่ในหน้า")
        xa, ya, xb, yb = [min(1.0, max(0.0, float(v))) for v in box]
        x0, x1 = sorted((xa, xb))
        y0, y1 = sorted((ya, yb))
        if x1 - x0 <= 0 or y1 - y0 <= 0:
            warnings.append(f"บล็อกที่ {n}: กรอบไม่มีพื้นที่ จึงข้าม")
            continue
        label = str(it.get("type", "text")).lower()
        order = len(blocks) + 1
        blocks.append({
            "block_id": f"p{page}_b{order:03d}",
            "type": label if label in BLOCK_TYPES else "text",
            "text": str(it.get("text") or ""),
            "bbox": [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)],
            "reading_order": order,
        })
    return blocks, warnings
