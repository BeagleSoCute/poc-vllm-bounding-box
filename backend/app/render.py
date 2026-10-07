"""แปลงเอกสารเป็นภาพรายหน้า (PNG) โมเดลทุกตัวใช้ภาพชุดเดียวกันนี้"""
from pathlib import Path

from PIL import Image, ImageOps

PDF_EXT = {".pdf"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_EXT = PDF_EXT | IMAGE_EXT


def page_path(doc_dir: Path, page: int) -> Path:
    return doc_dir / f"p{page:03d}.png"


def render(source: Path, doc_dir: Path, dpi: int) -> int:
    """คืนจำนวนหน้า"""
    if source.suffix.lower() in PDF_EXT:
        import fitz  # PyMuPDF
        doc = fitz.open(source)
        try:
            for i, page in enumerate(doc, start=1):
                page.get_pixmap(dpi=dpi).save(page_path(doc_dir, i))
            return doc.page_count
        finally:
            doc.close()
    img = ImageOps.exif_transpose(Image.open(source))  # หมุนภาพถ่ายจากมือถือให้ถูกทิศ
    img.convert("RGB").save(page_path(doc_dir, 1))
    return 1
