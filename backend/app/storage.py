"""ฐานข้อมูล SQLite ของแอปเดโม

ตาราง run_pages เก็บข้อความและตำแหน่ง (bbox) ที่ได้จากโมเดล
มี trigger ปฏิเสธ UPDATE และ DELETE เพื่อให้ข้อมูลอ้างอิงจากต้นทางแก้ไขไม่ได้
"""
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DB_PATH = DATA_DIR / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    page_count INTEGER NOT NULL,
    dpi INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    status TEXT NOT NULL,            -- queued | running | done | failed
    pages_done INTEGER NOT NULL DEFAULT 0,
    total_seconds REAL NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_pages (
    run_id TEXT NOT NULL REFERENCES runs(id),
    page INTEGER NOT NULL,
    seconds REAL NOT NULL,
    warnings TEXT NOT NULL,          -- JSON array
    blocks TEXT NOT NULL,            -- JSON array ในรูปแบบมาตรฐาน
    raw TEXT NOT NULL,               -- คำตอบดิบของโมเดล
    meta TEXT NOT NULL DEFAULT '{}', -- JSON object ข้อมูลประกอบจาก API เช่น จำนวน token
    PRIMARY KEY (run_id, page)
);
CREATE TRIGGER IF NOT EXISTS run_pages_no_update BEFORE UPDATE ON run_pages
BEGIN SELECT RAISE(ABORT, 'run_pages is immutable'); END;
CREATE TRIGGER IF NOT EXISTS run_pages_no_delete BEFORE DELETE ON run_pages
BEGIN SELECT RAISE(ABORT, 'run_pages is immutable'); END;
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript(SCHEMA)
        # ฐานข้อมูลที่สร้างก่อนมีคอลัมน์ meta: เพิ่มคอลัมน์ ผลเดิมได้ค่า {} และไม่ถูกแก้ไข
        if "meta" not in [r["name"] for r in c.execute("PRAGMA table_info(run_pages)")]:
            c.execute("ALTER TABLE run_pages ADD COLUMN meta TEXT NOT NULL DEFAULT '{}'")
        # งานที่ค้างจากการปิดเซิร์ฟเวอร์กลางคัน
        c.execute(
            "UPDATE runs SET status='failed', error='เซิร์ฟเวอร์ถูกปิดระหว่างประมวลผล' "
            "WHERE status IN ('queued','running')")


# ---------- documents ----------
def document_dir(doc_id: str) -> Path:
    return DATA_DIR / "documents" / doc_id


def find_document_by_hash(sha256: str):
    with connect() as c:
        row = c.execute("SELECT * FROM documents WHERE sha256=?", (sha256,)).fetchone()
        return dict(row) if row else None


def add_document(doc_id, filename, sha256, page_count, dpi) -> dict:
    with connect() as c:
        c.execute("INSERT INTO documents VALUES (?,?,?,?,?,?)",
                  (doc_id, filename, sha256, page_count, dpi, now()))
    return get_document(doc_id)


def get_document(doc_id: str):
    with connect() as c:
        row = c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        return dict(row) if row else None


def list_documents() -> list:
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM documents ORDER BY created_at DESC")]


# ---------- runs ----------
def add_run(document_id, model_id, model_version) -> str:
    run_id = new_id()
    with connect() as c:
        c.execute(
            "INSERT INTO runs (id, document_id, model_id, model_version, status, created_at) "
            "VALUES (?,?,?,?, 'queued', ?)",
            (run_id, document_id, model_id, model_version, now()))
    return run_id


def update_run(run_id: str, **fields) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    with connect() as c:
        c.execute(f"UPDATE runs SET {cols} WHERE id=?", (*fields.values(), run_id))


def add_run_page(run_id, page, seconds, warnings, blocks, raw, meta) -> None:
    with connect() as c:
        c.execute("INSERT INTO run_pages VALUES (?,?,?,?,?,?,?)",
                  (run_id, page, seconds,
                   json.dumps(warnings, ensure_ascii=False),
                   json.dumps(blocks, ensure_ascii=False), raw,
                   json.dumps(meta, ensure_ascii=False)))


def get_run(run_id: str, with_pages: bool = True):
    with connect() as c:
        row = c.execute(
            "SELECT r.*, d.page_count FROM runs r JOIN documents d ON d.id=r.document_id "
            "WHERE r.id=?", (run_id,)).fetchone()
        if not row:
            return None
        run = dict(row)
        if with_pages:
            run["pages"] = [
                {"page": p["page"], "seconds": p["seconds"],
                 "warnings": json.loads(p["warnings"]), "blocks": json.loads(p["blocks"]),
                 "raw": p["raw"], "meta": json.loads(p["meta"])}
                for p in c.execute(
                    "SELECT * FROM run_pages WHERE run_id=? ORDER BY page", (run_id,))]
        return run


def list_runs(document_id: str) -> list:
    """ผลทุกชุดของเอกสาร เรียงจากใหม่ไปเก่า (ไม่รวมเนื้อหารายหน้า)"""
    with connect() as c:
        return [dict(r) for r in c.execute(
            "SELECT r.*, d.page_count FROM runs r JOIN documents d ON d.id=r.document_id "
            "WHERE r.document_id=? ORDER BY r.created_at DESC, r.rowid DESC", (document_id,))]


def list_all_runs() -> list:
    """ผลทุกชุดของทุกเอกสาร เรียงจากใหม่ไปเก่า พร้อมชื่อไฟล์และตัวเลขสรุป (ไม่รวมเนื้อหารายหน้า)"""
    with connect() as c:
        return [dict(r) for r in c.execute(
            "SELECT r.*, d.filename, d.page_count, "
            "COALESCE(SUM(json_array_length(p.blocks)), 0) AS block_count, "
            "COALESCE(SUM(json_array_length(p.warnings)), 0) AS warning_count, "
            "COALESCE(SUM(json_extract(p.meta, '$.total_tokens')), 0) AS total_tokens "
            "FROM runs r JOIN documents d ON d.id=r.document_id "
            "LEFT JOIN run_pages p ON p.run_id=r.id "
            "GROUP BY r.id ORDER BY r.created_at DESC, r.rowid DESC")]


def latest_run(document_id: str, model_id: str, statuses=("done",)):
    marks = ",".join("?" * len(statuses))
    with connect() as c:
        row = c.execute(
            f"SELECT id FROM runs WHERE document_id=? AND model_id=? AND status IN ({marks}) "
            "ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (document_id, model_id, *statuses)).fetchone()
        return row["id"] if row else None
