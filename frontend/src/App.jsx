import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as api from "./api.js";

const TYPE_NAME = { text: "ข้อความ", title: "หัวข้อ", table: "ตาราง", figure: "รูป" };
// ข้อมูลประกอบที่ API ของโมเดลส่งมากับคำตอบ (ช่องที่ไม่อยู่ในรายการนี้แสดงด้วยชื่อเดิม)
const META_NAME = {
  input_tokens: "Token ขาเข้า",
  output_tokens: "Token ขาออก",
  thinking_tokens: "Token ที่ใช้คิด",
  total_tokens: "Token รวม",
  finish_reason: "เหตุผลที่หยุดตอบ",
  model_version: "รุ่นที่ตอบ",
  response_id: "รหัสคำตอบ",
  image_size: "ขนาดภาพที่โมเดลได้รับ",
  parser_version: "รุ่นของโปรแกรมแปลงเอกสาร",
  duration_ms: "เวลาที่โมเดลใช้ (ms)",
  parse_mode: "โหมดการอ่าน",
};

// จัดบรรทัด JSON ให้อ่านง่าย: ส่วนที่ไม่มี object ซ้อนอยู่ข้างใน (เช่น รายการตัวเลขพิกัด) อยู่บรรทัดเดียว
const isFlat = (v) =>
  v === null || typeof v !== "object" || (Array.isArray(v) && v.every(isFlat));
function formatJson(v, pad = "") {
  const entries = Array.isArray(v) ? v.map((x) => [null, x]) : Object.entries(v ?? {});
  if (isFlat(v) || entries.every(([, x]) => isFlat(x))) return JSON.stringify(v);
  const [open, close] = Array.isArray(v) ? "[]" : "{}";
  const lines = entries.map(
    ([k, x]) => `${pad}  ${k === null ? "" : `${JSON.stringify(k)}: `}${formatJson(x, `${pad}  `)}`
  );
  return `${open}\n${lines.join(",\n")}\n${pad}${close}`;
}
const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2];
const BASE_WIDTH = 820; // ความกว้างของหน้าเอกสารที่ซูม 100% (px)
const isActive = (run) => run && (run.status === "queued" || run.status === "running");
// bbox สัดส่วน 0-1 -> พิกัดพิกเซลบนภาพหน้าเอกสาร
const toPixels = ([x0, y0, x1, y1], { w, h }) =>
  [x0 * w, y0 * h, x1 * w, y1 * h].map(Math.round);

export default function App() {
  const [models, setModels] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [docId, setDocId] = useState("");
  const [modelId, setModelId] = useState("");
  const [run, setRun] = useState(null); // ผลของเอกสาร + โมเดลที่เลือกอยู่
  const [pinnedRunId, setPinnedRunId] = useState(null); // ผลที่เปิดจากประวัติ (null = ใช้ผลล่าสุด)
  const [history, setHistory] = useState([]); // ผลทุกชุดของทุกเอกสาร แบบสรุป
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(null); // { id, from: "list" | "page" }
  const [showAll, setShowAll] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [imageSize, setImageSize] = useState(null); // ขนาดจริงของภาพหน้าเอกสาร { w, h } (px)
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef(null);

  const doc = documents.find((d) => d.id === docId);
  const model = models.find((m) => m.id === modelId);

  // โหลดรายการโมเดลและเอกสารครั้งแรก
  useEffect(() => {
    Promise.all([api.getModels(), api.getDocuments()])
      .then(([ms, ds]) => {
        setModels(ms);
        setDocuments(ds);
        setModelId((ms.find((m) => m.available) || ms[0])?.id || "");
        setDocId(ds[0]?.id || "");
      })
      .catch((e) => setError(e.message));
  }, []);

  // เมื่อเปลี่ยนเอกสารหรือโมเดล: ดึงผลล่าสุดที่เก็บไว้ของคู่นี้
  // ถ้าเปิดมาจากประวัติ: ดึงผลชุดที่เลือกไว้แทน
  useEffect(() => {
    setRun(null);
    setSelected(null);
    if (!docId || !modelId) return;
    let cancelled = false;
    const load = pinnedRunId
      ? api.getRun(pinnedRunId)
      : api.getRuns(docId).then((runs) => {
          const mine = runs.filter((r) => r.model_id === modelId);
          const pick = mine.find(isActive) || mine.find((r) => r.status === "done") || mine[0];
          return pick ? api.getRun(pick.id) : null;
        });
    load
      .then((r) => !cancelled && setRun(r))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [docId, modelId, pinnedRunId]);

  // รายการประวัติ: โหลดใหม่ทุกครั้งที่ผลที่เปิดอยู่เปลี่ยนชุดหรือเปลี่ยนสถานะ (เริ่ม เสร็จ ล้มเหลว)
  const runStatus = run?.status;
  useEffect(() => {
    api.getAllRuns().then(setHistory).catch((e) => setError(e.message));
  }, [run?.id, runStatus]);

  useEffect(() => setPage(1), [docId]);
  useEffect(() => setImageSize(null), [docId, page]);

  // ระหว่างประมวลผล: ถามสถานะทุก 1 วินาที
  const runId = run?.id;
  const polling = isActive(run);
  useEffect(() => {
    if (!polling) return;
    const timer = setInterval(() => {
      api.getRun(runId).then(setRun).catch((e) => setError(e.message));
    }, 1000);
    return () => clearInterval(timer);
  }, [runId, polling]);

  const upload = async (file) => {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const d = await api.uploadDocument(file);
      setDocuments((list) => [d, ...list.filter((x) => x.id !== d.id)]);
      setPinnedRunId(null);
      setDocId(d.id);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const process = async (force) => {
    setError("");
    setSelected(null);
    try {
      const started = await api.startRun(docId, modelId, force);
      setPinnedRunId(null); // ผลใหม่คือผลล่าสุด เลิกดูผลย้อนหลัง
      setRun(started);
    } catch (e) {
      setError(e.message);
    }
  };

  const pageResult = useMemo(
    () => run?.pages?.find((p) => p.page === page) || null,
    [run, page]
  );
  const blocks = pageResult?.blocks || [];
  const hasResult = run?.status === "done";

  // เปิดผลชุดหนึ่งจากประวัติ: เมนูเอกสารและโมเดลเปลี่ยนตาม
  const openRun = useCallback((row) => {
    setDocId(row.document_id);
    setModelId(row.model_id);
    setPinnedRunId(row.id);
  }, []);
  // ผลล่าสุดที่สำเร็จของเอกสาร + โมเดลที่เลือกอยู่ ใช้บอกว่ากำลังดูผลย้อนหลังหรือไม่
  const latestDone = history.find(
    (r) => r.document_id === docId && r.model_id === modelId && r.status === "done"
  );
  const viewingOld = Boolean(run && latestDone && latestDone.id !== run.id && !isActive(run));
  const select = useCallback((id, from) => setSelected({ id, from }), []);

  return (
    <div className="app">
      <header className="toolbar">
        <label className="field">
          <span>เอกสาร</span>
          <select
            value={docId}
            onChange={(e) => { setPinnedRunId(null); setDocId(e.target.value); }}
            disabled={!documents.length}
          >
            {!documents.length && <option value="">ยังไม่มีเอกสาร</option>}
            {documents.map((d) => (
              <option key={d.id} value={d.id}>
                {d.filename} ({d.page_count} หน้า)
              </option>
            ))}
          </select>
        </label>
        <input
          ref={fileInput}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.webp"
          hidden
          onChange={(e) => upload(e.target.files[0])}
        />
        <button onClick={() => fileInput.current.click()} disabled={busy}>
          {busy ? "กำลังอัปโหลด" : "อัปโหลดเอกสาร"}
        </button>

        <label className="field">
          <span>โมเดล</span>
          <select value={modelId} onChange={(e) => { setPinnedRunId(null); setModelId(e.target.value); }}>
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
                {m.available ? "" : ` (${m.reason})`}
              </option>
            ))}
          </select>
        </label>
        <button
          className="primary"
          onClick={() => process(hasResult)}
          disabled={!doc || !model?.available || polling}
          title={model && !model.available ? model.reason : ""}
        >
          {polling ? "กำลังประมวลผล" : hasResult ? "ประมวลผลใหม่" : "ประมวลผล"}
        </button>
      </header>

      {error && (
        <div className="error" role="alert">
          <span>{error}</span>
          <button onClick={() => setError("")}>ปิด</button>
        </div>
      )}

      <main className="workspace">
        <section className="doc-pane">
          {doc ? (
            <>
              <div className="doc-scroll">
                <PageView
                  src={api.pageImageUrl(doc.id, page)}
                  blocks={blocks}
                  selected={selected}
                  showAll={showAll}
                  width={BASE_WIDTH * zoom}
                  onSelect={select}
                  onImageSize={setImageSize}
                />
              </div>
              <div className="doc-controls">
                <button onClick={() => { setPage(page - 1); setSelected(null); }} disabled={page <= 1}>
                  หน้าก่อน
                </button>
                <span>หน้า {page} / {doc.page_count}</span>
                <button
                  onClick={() => { setPage(page + 1); setSelected(null); }}
                  disabled={page >= doc.page_count}
                >
                  หน้าถัดไป
                </button>
                <label className="check">
                  <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
                  แสดงกรอบทั้งหมด
                </label>
                <label className="field inline">
                  <span>ซูม</span>
                  <select value={zoom} onChange={(e) => setZoom(Number(e.target.value))}>
                    {ZOOMS.map((z) => (
                      <option key={z} value={z}>{z * 100}%</option>
                    ))}
                  </select>
                </label>
              </div>
            </>
          ) : (
            <p className="empty">อัปโหลดเอกสาร PDF หรือภาพเพื่อเริ่มต้น</p>
          )}
        </section>

        <aside className="list-pane" aria-label="ข้อความที่อ่านได้">
          <BlockList
            doc={doc}
            model={model}
            models={models}
            history={history}
            onOpenRun={openRun}
            run={run}
            page={page}
            pageResult={pageResult}
            imageSize={imageSize}
            selected={selected}
            onSelect={select}
          />
        </aside>
      </main>

      <StatusBar run={run} model={model} viewingOld={viewingOld} onLatest={() => setPinnedRunId(null)} />
    </div>
  );
}

function PageView({ src, blocks, selected, showAll, width, onSelect, onImageSize }) {
  const refs = useRef({});
  useEffect(() => {
    if (selected?.from === "list") {
      refs.current[selected.id]?.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
    }
  }, [selected]);

  // วาดกรอบใหญ่ก่อน กรอบเล็กจึงอยู่ด้านบนและคลิกได้ แม้มีกรอบใหญ่ครอบทั้งหน้า
  const area = (b) => (b.bbox[2] - b.bbox[0]) * (b.bbox[3] - b.bbox[1]);
  const ordered = useMemo(() => [...blocks].sort((a, b) => area(b) - area(a)), [blocks]);

  return (
    <div className="sheet" style={{ width }}>
      <img
        src={src}
        alt="หน้าเอกสารต้นฉบับ"
        onLoad={(e) => onImageSize({ w: e.target.naturalWidth, h: e.target.naturalHeight })}
      />
      {ordered.map((b) => {
        const [x0, y0, x1, y1] = b.bbox;
        const on = selected?.id === b.block_id;
        if (!showAll && !on) return null;
        return (
          <button
            key={b.block_id}
            ref={(el) => (refs.current[b.block_id] = el)}
            className={`box t-${b.type}${on ? " on" : ""}`}
            style={{
              left: `${x0 * 100}%`,
              top: `${y0 * 100}%`,
              width: `${(x1 - x0) * 100}%`,
              height: `${(y1 - y0) * 100}%`,
            }}
            aria-label={`กรอบที่ ${b.reading_order} ${TYPE_NAME[b.type]}`}
            onClick={() => onSelect(b.block_id, "page")}
          />
        );
      })}
    </div>
  );
}

function BlockList({
  doc, model, models, history, onOpenRun, run, page, pageResult, imageSize, selected, onSelect,
}) {
  const refs = useRef({});
  const [view, setView] = useState("blocks"); // "blocks" | "raw" | "history"
  useEffect(() => {
    if (selected?.from === "page") {
      setView("blocks"); // คลิกกรอบบนหน้าเอกสาร ให้กลับมาที่รายการเพื่อเห็นบล็อกที่เลือก
    }
  }, [selected]);
  useEffect(() => {
    if (selected?.from === "page" && view === "blocks") {
      refs.current[selected.id]?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [selected, view]);

  const tabs = (
    <div className="tabs" role="tablist">
      <button role="tab" aria-selected={view === "blocks"} onClick={() => setView("blocks")}>
        ข้อความและตำแหน่ง
      </button>
      <button role="tab" aria-selected={view === "raw"} onClick={() => setView("raw")}>
        คำตอบดิบของโมเดล
      </button>
      <button role="tab" aria-selected={view === "history"} onClick={() => setView("history")}>
        ประวัติ ({history.length})
      </button>
    </div>
  );

  // แท็บประวัติเปิดได้เสมอ แม้ยังไม่ได้เลือกเอกสารหรือยังไม่มีผล
  if (view === "history") {
    return (
      <>
        {tabs}
        <HistoryView rows={history} models={models} doc={doc} currentRunId={run?.id} onOpen={onOpenRun} />
      </>
    );
  }

  let waiting = null; // ข้อความแทนเนื้อหา เมื่อยังไม่มีผลของหน้านี้ให้แสดง
  if (!doc) {
    waiting = <p className="empty">ข้อความที่โมเดลอ่านได้จะแสดงที่นี่</p>;
  } else if (!run) {
    waiting = (
      <p className="empty">
        {model?.available
          ? `ยังไม่มีผลของ ${model.name} สำหรับเอกสารนี้ กด "ประมวลผล" เพื่อเริ่ม`
          : `ยังไม่มีผลของ ${model?.name || "โมเดลนี้"} และโมเดลยังใช้ไม่ได้: ${model?.reason || ""}`}
      </p>
    );
  } else if (run.status === "failed" && !pageResult) {
    waiting = <p className="empty failed">ประมวลผลไม่สำเร็จ: {run.error}</p>;
  } else if (!pageResult) {
    waiting = (
      <div className="empty">
        <p>กำลังประมวลผล หน้า {Math.min(run.pages_done + 1, run.page_count)} จาก {run.page_count}</p>
        <progress value={run.pages_done} max={run.page_count} />
      </div>
    );
  }
  if (waiting) {
    return (
      <>
        {tabs}
        {waiting}
      </>
    );
  }

  if (view === "raw") {
    return (
      <>
        {tabs}
        <RawView raw={pageResult.raw} meta={pageResult.meta} page={page} note={model?.raw_note} />
      </>
    );
  }

  return (
    <>
      {tabs}
      <h2>ข้อความที่อ่านได้ในหน้า {page} ({pageResult.blocks.length} บล็อก)</h2>
      <p className="legend">
        bbox = [x_min, y_min, x_max, y_max] เป็นสัดส่วน 0-1 ของหน้า จุดกำเนิดอยู่มุมซ้ายบน
        {imageSize && ` · px = พิกัดเดียวกันบนภาพหน้าเอกสาร ${imageSize.w} × ${imageSize.h} px`}
      </p>
      {pageResult.warnings.length > 0 && (
        <ul className="warnings">
          {pageResult.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}
      {pageResult.blocks.length === 0 && <p className="empty">โมเดลไม่ได้คืนกรอบสำหรับหน้านี้</p>}
      {pageResult.blocks.map((b) => (
        <button
          key={b.block_id}
          ref={(el) => (refs.current[b.block_id] = el)}
          className={`item t-${b.type}${selected?.id === b.block_id ? " on" : ""}`}
          onClick={() => onSelect(b.block_id, "list")}
        >
          <span className="tag">
            {b.reading_order}. {TYPE_NAME[b.type]}
            <code>{b.block_id}</code>
          </span>
          {b.text || "(ไม่มีข้อความ)"}
          <code className="coords">
            bbox [{b.bbox.join(", ")}]
            {imageSize && `\npx   [${toPixels(b.bbox, imageSize).join(", ")}]`}
          </code>
        </button>
      ))}
    </>
  );
}

// ประวัติผลการประมวลผลทุกชุด คลิกแถวเพื่อเปิดผลชุดนั้นโดยไม่ต้องอัปโหลดหรือประมวลผลใหม่
function HistoryView({ rows, models, doc, currentRunId, onOpen }) {
  const [scope, setScope] = useState("doc"); // "doc" = เฉพาะเอกสารที่เปิดอยู่ | "all"
  const [modelFilter, setModelFilter] = useState("");
  const [hideFailed, setHideFailed] = useState(true);

  const modelName = (id) => models.find((m) => m.id === id)?.name || id;
  // ผลล่าสุดที่สำเร็จของแต่ละคู่เอกสาร + โมเดล (rows เรียงจากใหม่ไปเก่าอยู่แล้ว)
  const latestIds = useMemo(() => {
    const seen = new Set();
    const ids = new Set();
    for (const r of rows) {
      const key = `${r.document_id}|${r.model_id}`;
      if (r.status === "done" && !seen.has(key)) {
        seen.add(key);
        ids.add(r.id);
      }
    }
    return ids;
  }, [rows]);

  const inScope = rows.filter(
    (r) => (scope === "all" || !doc || r.document_id === doc.id) && (!modelFilter || r.model_id === modelFilter)
  );
  const shown = inScope.filter((r) => !hideFailed || r.status !== "failed" || r.id === currentRunId);
  const hidden = inScope.length - shown.length;

  return (
    <>
      <div className="filters">
        <button aria-pressed={scope === "doc"} onClick={() => setScope("doc")} disabled={!doc}>
          เอกสารนี้
        </button>
        <button aria-pressed={scope === "all"} onClick={() => setScope("all")}>
          ทุกเอกสาร
        </button>
        <select value={modelFilter} onChange={(e) => setModelFilter(e.target.value)} aria-label="กรองตามโมเดล">
          <option value="">ทุกโมเดล</option>
          {models.map((m) => (
            <option key={m.id} value={m.id}>{m.name}</option>
          ))}
        </select>
        <label className="check">
          <input type="checkbox" checked={hideFailed} onChange={(e) => setHideFailed(e.target.checked)} />
          ซ่อนที่ไม่สำเร็จ{hidden > 0 && ` (${hidden})`}
        </label>
      </div>
      {shown.length === 0 && <p className="empty">ยังไม่มีผลการประมวลผลตามตัวกรองนี้</p>}
      {shown.map((r) => (
        <button
          key={r.id}
          className={`hist${r.id === currentRunId ? " on" : ""}${r.status === "failed" ? " failed" : ""}`}
          onClick={() => onOpen(r)}
        >
          <span className="hist-head">
            <strong>{modelName(r.model_id)}</strong>
            {r.id === currentRunId && <span className="badge viewing">กำลังดู</span>}
            {latestIds.has(r.id) && <span className="badge">ล่าสุด</span>}
            {isActive(r) && <span className="badge">กำลังประมวลผล</span>}
            {r.status === "failed" && <span className="badge danger">ไม่สำเร็จ</span>}
            {r.warning_count > 0 && <span className="badge warn">คำเตือน {r.warning_count}</span>}
          </span>
          <span className="hist-sub">
            {r.filename} · {r.model_version} ·{" "}
            {new Date(r.created_at).toLocaleString("th-TH", {
              day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
            })}
          </span>
          {r.status === "failed" ? (
            <span className="hist-sub">{r.error}</span>
          ) : (
            <code>
              {r.block_count} กรอบ · {r.total_seconds} วิ
              {r.total_tokens > 0 && ` · ${r.total_tokens.toLocaleString()} token`}
              {r.page_count > 1 && ` · ${r.pages_done}/${r.page_count} หน้า`}
            </code>
          )}
        </button>
      ))}
    </>
  );
}

// คำตอบของโมเดลก่อนที่แอปจะแปลงเป็นรูปแบบมาตรฐาน
function RawView({ raw, meta, page, note }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => setCopied(false), [raw]);

  // จัดบรรทัดใหม่ให้หนึ่งรายการอยู่หนึ่งบรรทัด ถ้าไม่ใช่ JSON ก็แสดงตามที่ได้มา
  const shown = useMemo(() => {
    try {
      return formatJson(JSON.parse(raw));
    } catch {
      return raw;
    }
  }, [raw]);

  const metaRows = Object.entries(meta || {});
  const metaView = (
    <>
      <h2>ข้อมูลประกอบจาก API หน้า {page}</h2>
      {metaRows.length ? (
        <dl className="meta">
          {metaRows.map(([k, v]) => (
            <div key={k}>
              <dt>{META_NAME[k] || k}</dt>
              <dd>{typeof v === "number" ? v.toLocaleString() : String(v)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="legend">ไม่มีข้อมูลประกอบ ผลชุดนี้ประมวลผลก่อนที่แอปจะเริ่มเก็บ</p>
      )}
    </>
  );

  if (!raw) {
    return (
      <>
        {metaView}
        <p className="empty">ไม่มีคำตอบดิบของหน้านี้เก็บไว้</p>
      </>
    );
  }
  return (
    <>
      {metaView}
      <h2>
        คำตอบดิบของโมเดล หน้า {page}
        <button className="copy" onClick={() => navigator.clipboard.writeText(raw).then(() => setCopied(true))}>
          {copied ? "คัดลอกแล้ว" : "คัดลอก"}
        </button>
      </h2>
      <p className="legend">
        คำตอบตามที่โมเดลส่งกลับมา ก่อนแอปแปลงเป็นรูปแบบมาตรฐาน จัดบรรทัดใหม่ให้อ่านง่ายเท่านั้น
        {note && ` · ${note}`}
      </p>
      <pre className="raw">{shown}</pre>
    </>
  );
}

function StatusBar({ run, model, viewingOld, onLatest }) {
  if (!run) {
    return <footer className="status">{model ? model.name : ""} ยังไม่มีผลลัพธ์</footer>;
  }
  const pages = run.pages || [];
  const boxes = pages.reduce((n, p) => n + p.blocks.length, 0);
  const warnings = pages.reduce((n, p) => n + p.warnings.length, 0);
  const tokens = pages.reduce((n, p) => n + (p.meta?.total_tokens || 0), 0);
  const state = {
    queued: "รอคิว",
    running: `กำลังประมวลผล ${run.pages_done}/${run.page_count} หน้า`,
    done: "เสร็จแล้ว",
    failed: "ไม่สำเร็จ",
  }[run.status];
  return (
    <footer className="status">
      <span>{model?.name || run.model_id} ({run.model_version})</span>
      <span>{state}</span>
      <span>{boxes} กรอบ</span>
      <span>{run.total_seconds} วินาที</span>
      {tokens > 0 && <span>{tokens.toLocaleString()} token</span>}
      <span>คำเตือน {warnings}</span>
      <span>ประมวลผลเมื่อ {new Date(run.created_at).toLocaleString("th-TH")}</span>
      {viewingOld ? (
        <span className="readonly old">
          กำลังดูผลย้อนหลัง
          <button onClick={onLatest}>กลับไปผลล่าสุด</button>
        </span>
      ) : (
        <span className="readonly">ตำแหน่งดูได้อย่างเดียว</span>
      )}
    </footer>
  );
}
