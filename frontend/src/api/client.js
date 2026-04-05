const API_BASE = "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export async function createCheck(urls) {
  return request("/api/checks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ urls }),
  });
}

export async function uploadCheck(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/checks/upload`, { method: "POST", body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

export async function listChecks() {
  return request("/api/checks");
}

export async function getCheck(id) {
  return request(`/api/checks/${id}`);
}

export async function getQuota() {
  return request("/api/quota");
}

export async function getUrlHistory(urlId) {
  return request(`/api/urls/${urlId}/history`);
}

export async function lookupUrl(url) {
  return request(`/api/urls/lookup?url=${encodeURIComponent(url)}`);
}

export function getExportUrl(checkId) {
  return `${API_BASE}/api/checks/${checkId}/export`;
}

export function subscribeProgress(checkId, onMessage) {
  const es = new EventSource(`${API_BASE}/api/checks/${checkId}/progress`);
  es.addEventListener("progress", (e) => {
    onMessage(JSON.parse(e.data));
  });
  es.onerror = () => es.close();
  return es;
}
