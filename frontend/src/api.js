// ฟังก์ชันเรียกหลังบ้าน ทุกตัวโยน Error พร้อมข้อความจากเซิร์ฟเวอร์เมื่อไม่สำเร็จ

async function request(path, options) {
  let res;
  try {
    res = await fetch(`/api${path}`, options);
  } catch {
    throw new Error("ติดต่อหลังบ้านไม่ได้ ตรวจว่ารัน uvicorn ที่พอร์ต 8000 แล้ว");
  }
  if (!res.ok) {
    let detail = `เซิร์ฟเวอร์ตอบกลับด้วยรหัส ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* ใช้ข้อความเริ่มต้น */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const getModels = () => request("/models");
export const getDocuments = () => request("/documents");
export const getRuns = (docId) => request(`/documents/${docId}/runs`);
export const getRun = (runId) => request(`/runs/${runId}`);
export const getAllRuns = () => request("/runs");
export const pageImageUrl = (docId, page) => `/api/documents/${docId}/pages/${page}`;

export function uploadDocument(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/documents", { method: "POST", body: form });
}

export function startRun(docId, modelId, force = false) {
  return request(`/documents/${docId}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model_id: modelId, force }),
  });
}
