#!/bin/sh
# เปิดบริการ PaddleOCR-VL บน Mac (Apple Silicon) สำหรับแอปเดโม
# รันนอก Docker เพราะ Docker บน Mac ใช้ GPU ไม่ได้   ใช้:  ./paddleocr-service/start.sh
# ครั้งแรกจะติดตั้งแพ็กเกจและดาวน์โหลดโมเดล ใช้เวลาหลายนาที   หยุด: กด Ctrl+C
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install paddlepaddle==3.2.1 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
  .venv/bin/pip install -U "paddleocr[doc-parser]" "mlx-vlm>=0.3.11"
fi

# เปิดรับเฉพาะจากเครื่องนี้ (container ของหลังบ้านเข้าถึงได้ผ่าน host.docker.internal)
.venv/bin/mlx_vlm.server --host 127.0.0.1 --port 8111 &
MLX_PID=$!
trap 'kill $MLX_PID 2>/dev/null' EXIT INT TERM

.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8118
