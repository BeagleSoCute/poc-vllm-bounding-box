# Bounding Box POC - Demo App

แอปเดโมสำหรับ POC: อ่านเอกสารด้วย vLM แล้วแสดงว่าข้อความแต่ละส่วนมาจากตำแหน่งใดของหน้าเอกสาร
ผู้ใช้เลือกโมเดลได้ และดูกรอบได้อย่างเดียว (แก้ไขไม่ได้)

## สิ่งที่ต้องมี
- Python 3.10 ขึ้นไป
- Node.js 18 ขึ้นไป
- API key ของ Gemini (ขอได้ที่ Google AI Studio)

## วิธีรันด้วย Docker (คำสั่งเดียว ได้ทั้งหน้าบ้านและหลังบ้าน)
ต้องมี Docker Desktop เปิดอยู่ ไม่ต้องติดตั้ง Python หรือ Node.js

```
cp .env.example .env      # แล้วใส่ GEMINI_API_KEY ในไฟล์ .env
docker compose up --build
```
เปิดเบราว์เซอร์ที่ http://localhost:5173 (หลังบ้านอยู่ที่ http://localhost:8000)

- หยุด: `docker compose down`
- หน้าบ้านเป็น hot reload แก้ไฟล์ใน `frontend/` แล้วหน้าเว็บเปลี่ยนตามทันที
- แก้โค้ดหลังบ้าน ต้องรัน `docker compose up --build` ใหม่
- แก้ `frontend/package.json` ต้องรัน `docker compose up --build -V` (ติดตั้งแพ็กเกจใหม่)
- ข้อมูลเก็บที่ `backend/data` ที่เดียวกับการรันแบบไม่ใช้ Docker

## PaddleOCR-VL, MinerU และ dots.mocr (รันบนเครื่อง ไม่มีค่าใช้จ่าย)
โมเดลสามตัวนี้รันบน Mac (Apple Silicon) โดยตรง ไม่ได้อยู่ใน Docker เพราะ Docker บน Mac ใช้ GPU ไม่ได้
เอกสารถูกประมวลผลบนเครื่อง ไม่ส่งออกไปที่อื่น เปิด terminal แยกหน้าต่างละตัว แล้วรันตัวที่ต้องการใช้:

```
./paddleocr-service/start.sh
./mineru-service/start.sh
./dots-mocr-service/start.sh
```
- ครั้งแรกจะติดตั้งแพ็กเกจและดาวน์โหลดโมเดล ใช้เวลาหลายนาที (ต้องมี Python 3.9-3.13)
- เปิดค้างไว้ระหว่างใช้งาน หยุดด้วย Ctrl+C
- ถ้าเปิดแอปอยู่ก่อนแล้ว ให้โหลดหน้าเว็บใหม่ เมนูโมเดลจึงจะเลือกโมเดลนั้นได้
- หน้าแรกหลังเปิดบริการช้ากว่าปกติ เพราะต้องโหลดโมเดลเข้าหน่วยความจำ

## วิธีรันแบบไม่ใช้ Docker (เปิด 2 หน้าต่าง terminal)

### 1) หลังบ้าน
```
cd backend
pip install -r requirements.txt
```
ตั้ง API key:
- macOS / Linux:  `export GEMINI_API_KEY=คีย์ของคุณ`
- Windows (PowerShell):  `$env:GEMINI_API_KEY="คีย์ของคุณ"`

แล้วรัน:
```
uvicorn app.main:app --reload --port 8000
```

### 2) หน้าบ้าน
```
cd frontend
npm install
npm run dev
```
เปิดเบราว์เซอร์ที่ http://localhost:5173

## ตัวแปรที่ตั้งได้
| ตัวแปร | ค่าเริ่มต้น | ความหมาย |
|---|---|---|
| GEMINI_API_KEY | - | API key ของ Gemini |
| GEMINI_MODEL | gemini-3.8-flash | ชื่อรุ่นของ Gemini |
| RENDER_DPI | 150 | ความละเอียดตอนแปลง PDF เป็นภาพ |
| DATA_DIR | backend/data | ที่เก็บฐานข้อมูลและไฟล์ |
| PADDLEOCR_VL_URL | http://localhost:8118 | ที่อยู่ของบริการ PaddleOCR-VL (ใน Docker ตั้งให้แล้ว) |
| MINERU_URL | http://localhost:8119 | ที่อยู่ของบริการ MinerU (ใน Docker ตั้งให้แล้ว) |
| MINERU_TIER | standard | ระดับการประมวลผลของ MinerU |
| DOTS_MOCR_URL | http://localhost:8120 | ที่อยู่ของบริการ dots.mocr (ใน Docker ตั้งให้แล้ว) |
| DOTS_MOCR_MODEL | mlx-community/dots.mocr-bf16 | รุ่นของ dots.mocr ตั้งตอนรัน start.sh (เช่น dots.mocr-8bit เล็กและเร็วกว่า) |

## โครงสร้าง
```
backend/app/
  main.py            API ทั้งหมด
  storage.py         ฐานข้อมูล SQLite (ผลลัพธ์แก้ไขและลบไม่ได้)
  render.py          แปลงเอกสารเป็นภาพรายหน้า
  pipeline.py        งานประมวลผลเบื้องหลัง
  adapters/          ตัวเชื่อมโมเดล หนึ่งไฟล์ต่อหนึ่งโมเดล
paddleocr-service/
  server.py          บริการ PaddleOCR-VL ที่รันบนเครื่อง
  start.sh           ติดตั้งและเปิดบริการ
mineru-service/
  start.sh           ติดตั้งและเปิดเซิร์ฟเวอร์ของ MinerU
dots-mocr-service/
  server.py          บริการ dots.mocr ที่รันบนเครื่อง
  start.sh           ติดตั้งและเปิดบริการ
frontend/src/
  App.jsx            หน้าจอหลัก
  api.js             เรียกหลังบ้าน
```

## การเพิ่มโมเดลใหม่
1. สร้างไฟล์ใน `backend/app/adapters/` ที่สืบทอดจาก `Adapter` (ดู `gemini.py` เป็นตัวอย่าง)
2. ให้ `run_page()` คืน 3 อย่าง: รายการบล็อกที่มี `type`, `text` และ `bbox` ในรูป `[x_min, y_min, x_max, y_max]` สเกล 0-1,
   คำตอบดิบของโมเดลเป็นข้อความ และข้อมูลประกอบจาก API เป็น dict เช่น จำนวน token (ไม่มีให้คืน `{}`)
3. ลงทะเบียนใน `adapters/__init__.py`

## การจัดเก็บ (AC ข้อ 5)
- ไม่มี API สำหรับแก้ไขหรือลบกรอบ
- ตาราง `run_pages` มี trigger ในฐานข้อมูลที่ปฏิเสธคำสั่ง UPDATE และ DELETE
- การประมวลผลซ้ำสร้างผลชุดใหม่ ไม่เขียนทับของเดิม
- เอกสารแต่ละไฟล์เก็บค่า SHA-256 ของไฟล์ต้นฉบับ
