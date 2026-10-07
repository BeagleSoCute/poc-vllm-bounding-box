#!/bin/sh
# เปิดบริการ MinerU บน Mac สำหรับแอปเดโม   ใช้:  ./mineru-service/start.sh
# รันนอก Docker เพราะ Docker บน Mac ใช้ GPU ไม่ได้ เอกสารถูกประมวลผลบนเครื่องนี้ ไม่ส่งไปบริการคลาวด์ของ MinerU
# ครั้งแรกจะติดตั้งแพ็กเกจและดาวน์โหลดโมเดล ใช้เวลาหลายนาที   หยุด: กด Ctrl+C
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -U "mineru>=4.0,<5"
fi

# tier standard = หาตำแหน่งบล็อกด้วยโมเดลเล็ก แล้วอ่านข้อความด้วย VLM ของ MinerU
# เปิดรับเฉพาะจากเครื่องนี้ (container ของหลังบ้านเข้าถึงได้ผ่าน host.docker.internal)
# max-inline-bytes: หลังบ้านส่งภาพหน้าเอกสารมาในคำขอโดยตรง ค่าเริ่มต้น 1 MB ไม่พอสำหรับหน้า PDF
exec .venv/bin/mineru-kit api-server --host 127.0.0.1 --port 8119 \
  --tier standard --preload-models --max-inline-bytes 67108864
