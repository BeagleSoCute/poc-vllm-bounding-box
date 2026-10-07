#!/bin/sh
# เปิดบริการ dots.mocr บน Mac (Apple Silicon) สำหรับแอปเดโม   ใช้:  ./dots-mocr-service/start.sh
# รันนอก Docker เพราะ Docker บน Mac ใช้ GPU ไม่ได้ เอกสารถูกประมวลผลบนเครื่องนี้
# ครั้งแรกจะติดตั้งแพ็กเกจและดาวน์โหลดโมเดลราว 6 GB   ใช้แรมราว 7 GB ขณะเปิด   หยุด: กด Ctrl+C
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -U "mlx-vlm>=0.3.11" pillow
fi

# เปิดรับเฉพาะจากเครื่องนี้ (container ของหลังบ้านเข้าถึงได้ผ่าน host.docker.internal)
exec .venv/bin/uvicorn server:app --host 127.0.0.1 --port 8120
