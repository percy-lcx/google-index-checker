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

export async function deleteCheck(id) {
  return request(`/api/checks/${id}`, { method: "DELETE" });
}

export async function deleteChecksBulk(ids) {
  return request("/api/checks/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  });
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

// --- Properties ---

export async function getProperties() {
  return request("/api/properties");
}

export async function createProperty(property) {
  return request("/api/properties", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(property),
  });
}

export async function updateProperty(id, property) {
  return request(`/api/properties/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(property),
  });
}

export async function deleteProperty(id) {
  return request(`/api/properties/${id}`, { method: "DELETE" });
}

export async function previewProperties(urls) {
  return request("/api/properties/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ urls }),
  });
}

// --- Watchlist ---

export async function getWatchlist() {
  return request("/api/watchlist");
}

export async function saveWatchlist(urls) {
  return request("/api/watchlist", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ urls }),
  });
}

// --- Schedule ---

export async function getSchedule() {
  return request("/api/schedule");
}

export async function saveSchedule(settings) {
  return request("/api/schedule", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}
