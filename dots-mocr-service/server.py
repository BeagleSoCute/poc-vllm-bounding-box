"""บริการ dots.mocr สำหรับแอปเดโม รันบน Mac โดยตรงด้วย MLX (นอก Docker)

รับภาพหนึ่งหน้า แล้วคืนคำตอบของโมเดลตามที่ได้มา พร้อมขนาดภาพที่โมเดลได้รับ
หลังบ้านของแอป (backend/app/adapters/dots_mocr.py) เป็นผู้แปลงเป็นรูปแบบมาตรฐาน

dots.mocr คืนพิกัดเป็นพิกเซลของภาพที่มันได้รับ ไม่ใช่ของภาพต้นฉบับ
บริการนี้จึงย่อ/ขยายภาพให้ด้านเป็นพหุคูณของ 28 เองก่อนส่ง (วิธีเดียวกับโค้ดต้นทางของ dots.ocr)
เพื่อให้รู้ขนาดที่แน่นอน แล้วแจ้งขนาดนั้นกลับไปคู่กับคำตอบ
"""
import math
import os
import tempfile
import threading
from contextlib import asynccontextmanager
from io import BytesIO

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from mlx_vlm import generate, load
from mlx_vlm.prompt_utils import apply_chat_template
from PIL import Image

# bf16 คือความละเอียดเต็มของโมเดลต้นฉบับ รุ่นย่อ (เช่น dots.mocr-8bit) เล็กและเร็วกว่าแต่อาจแม่นน้อยลง
MODEL = os.environ.get("DOTS_MOCR_MODEL", "mlx-community/dots.mocr-bf16")
MAX_TOKENS = int(os.environ.get("DOTS_MOCR_MAX_TOKENS", "16000"))

# ค่าจากโค้ดต้นทาง: github.com/rednote-hilab/dots.ocr  dots_ocr/utils/consts.py
MIN_PIXELS, MAX_PIXELS, IMAGE_FACTOR = 3136, 11289600, 28

# prompt_layout_all_en จาก dots_ocr/utils/prompts.py ของโค้ดต้นทาง ใช้ตามต้นฉบับทุกตัวอักษร
PROMPT = """Please output the layout information from the PDF image, including each layout element's bbox, its category, and the corresponding text content within the bbox.

1. Bbox format: [x1, y1, x2, y2]

2. Layout Categories: The possible categories are ['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title'].

3. Text Extraction & Formatting Rules:
    - Picture: For the 'Picture' category, the text field should be omitted.
    - Formula: Format its text as LaTeX.
    - Table: Format its text as HTML.
    - All Others (Text, Title, etc.): Format their text as Markdown.

4. Constraints:
    - The output text must be the original text from the image, with no translation.
    - All layout elements must be sorted according to human reading order.

5. Final Output: The entire output must be a single JSON object.
"""

state = {}
lock = threading.Lock()   # โมเดลรับงานทีละหน้า


def smart_resize(height: int, width: int) -> tuple:
    """ขนาดที่โมเดลใช้: ด้านเป็นพหุคูณของ 28 และจำนวนพิกเซลอยู่ในช่วงที่โมเดลรับได้"""
    h = max(IMAGE_FACTOR, round(height / IMAGE_FACTOR) * IMAGE_FACTOR)
    w = max(IMAGE_FACTOR, round(width / IMAGE_FACTOR) * IMAGE_FACTOR)
    if h * w > MAX_PIXELS:
        beta = math.sqrt(height * width / MAX_PIXELS)
        h = max(IMAGE_FACTOR, math.floor(height / beta / IMAGE_FACTOR) * IMAGE_FACTOR)
        w = max(IMAGE_FACTOR, math.floor(width / beta / IMAGE_FACTOR) * IMAGE_FACTOR)
    elif h * w < MIN_PIXELS:
        beta = math.sqrt(MIN_PIXELS / (height * width))
        h = math.ceil(height * beta / IMAGE_FACTOR) * IMAGE_FACTOR
        w = math.ceil(width * beta / IMAGE_FACTOR) * IMAGE_FACTOR
    return h, w


def load_model() -> None:
    state["model"], state["processor"] = load(MODEL)
    state["prompt"] = apply_chat_template(
        state["processor"], state["model"].config, PROMPT, num_images=1)


def parse_image(image_bytes: bytes) -> dict:
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    height, width = smart_resize(image.height, image.width)
    with lock, tempfile.NamedTemporaryFile(suffix=".png") as f:
        image.resize((width, height), Image.LANCZOS).save(f.name)
        result = generate(state["model"], state["processor"], state["prompt"], image=[f.name],
                          max_tokens=MAX_TOKENS, temperature=0.0, verbose=False)
    return {
        "model": MODEL,
        "image_width": width,      # ขนาดภาพที่โมเดลได้รับ พิกัดในคำตอบอ้างอิงขนาดนี้
        "image_height": height,
        "output": result.text,     # คำตอบของโมเดล ไม่ผ่านการแก้ไข
        "prompt_tokens": result.prompt_tokens,
        "generation_tokens": result.generation_tokens,
        "truncated": result.generation_tokens >= MAX_TOKENS,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()
    yield


app = FastAPI(title="dots.mocr service", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL}


@app.post("/parse")
async def parse(request: Request):
    image = await request.body()
    if not image:
        raise HTTPException(400, "ไม่มีข้อมูลภาพ")
    return await run_in_threadpool(parse_image, image)
