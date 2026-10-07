"""บริการ PaddleOCR-VL สำหรับแอปเดโม รันบน Mac โดยตรง (นอก Docker)

รับภาพหนึ่งหน้า แล้วคืนผลของ pipeline ตามที่ PaddleOCR ให้มา
หลังบ้านของแอป (backend/app/adapters/paddleocr_vl.py) เป็นผู้แปลงเป็นรูปแบบมาตรฐาน

pipeline มี 2 ขั้น: หาตำแหน่งบล็อกด้วย PP-DocLayoutV3 (รันบน CPU ในโปรเซสนี้)
แล้วอ่านข้อความในแต่ละบล็อกด้วย PaddleOCR-VL (รันบน GPU ของ Mac ผ่าน mlx_vlm.server)
"""
import os
import tempfile
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from paddleocr import PaddleOCRVL

PIPELINE_VERSION = os.environ.get("PADDLEOCR_VL_VERSION", "v1.6")
MODEL_NAME = f"PaddleOCR-VL-{PIPELINE_VERSION.lstrip('v')}"
MLX_URL = os.environ.get("MLX_VLM_URL", "http://127.0.0.1:8111/")

state = {}
lock = threading.Lock()   # pipeline รับงานทีละหน้า


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["pipeline"] = PaddleOCRVL(
        pipeline_version=PIPELINE_VERSION,
        vl_rec_backend="mlx-vlm-server",
        vl_rec_server_url=MLX_URL,
        vl_rec_api_model_name=f"PaddlePaddle/{MODEL_NAME}",
    )
    yield


app = FastAPI(title="PaddleOCR-VL service", lifespan=lifespan)


def _parse(image: bytes) -> dict:
    with lock, tempfile.NamedTemporaryFile(suffix=".png") as f:
        f.write(image)
        f.flush()
        # merge_layout_blocks=False: อ่านข้อความแยกทีละบล็อก ข้อความจึงตรงกับกรอบของตัวเอง
        # (ค่าเริ่มต้นจะรวมข้อความของบล็อกที่อยู่ติดกันไปไว้ที่บล็อกแรก)
        result = next(iter(state["pipeline"].predict(f.name, merge_layout_blocks=False)))
    data = result.json["res"]
    data.pop("input_path", None)                      # ที่อยู่ไฟล์ชั่วคราว ไม่มีความหมายนอกเครื่องนี้
    data.get("layout_det_res", {}).pop("input_path", None)
    return data


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME}


@app.post("/parse")
async def parse(request: Request):
    image = await request.body()
    if not image:
        raise HTTPException(400, "ไม่มีข้อมูลภาพ")
    return await run_in_threadpool(_parse, image)
