// Production build: same origin as the page (the API serves the built frontend), unless
// VITE_API_BASE_URL is set. Dev server: the local API on port 8000.
const DEFAULT_BASE = import.meta.env.DEV ? "http://localhost:8000" : "";
export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    throw new ApiError(0, `Cannot reach the API at ${API_BASE}. Is the backend running?`);
  }
  let body = null;
  try {
    body = await res.json();
  } catch {
    /* empty or non-JSON body */
  }
  if (!res.ok) {
    let detail = body && body.detail;
    if (Array.isArray(detail)) detail = detail.map((d) => d.msg).join("; ");
    if (res.status === 429) {
      throw new ApiError(429, detail || "Too many checks from your address. Wait a minute and try again.");
    }
    throw new ApiError(res.status, detail || `Request failed (HTTP ${res.status}).`);
  }
  return body;
}

export const api = {
  health: () => request("/health"),
  banks: () => request("/banks"),
  startCheck: (url) => request("/check", { method: "POST", body: JSON.stringify({ url }) }),
  job: (id) => request(`/jobs/${encodeURIComponent(id)}`),
  cancelJob: (id) => request(`/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  findings: (params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v));
    return request(`/findings${q.toString() ? `?${q}` : ""}`);
  },
  decide: (payload) => request("/decisions", { method: "POST", body: JSON.stringify(payload) }),
  decisions: () => request("/decisions"),
  metrics: () => request("/metrics"),
};

// Every date in the UI is shown in Uzbekistan time, whatever the viewer's browser timezone;
// stored and exported values stay in UTC.
const TZ = "Asia/Tashkent";
const DATE_TIME = new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ, day: "numeric", month: "short", year: "numeric",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});
const DATE_ONLY = new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ, day: "numeric", month: "short", year: "numeric",
});

function parse(iso) {
  if (!iso || iso === "no data") return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

// "11 Oct 2026, 10:42 (Tashkent time)"
export function formatTime(iso) {
  const d = parse(iso);
  if (!d) return iso || "no data";
  return `${DATE_TIME.format(d)} (Tashkent time)`;
}

// "11 Oct 2026" (the date in Tashkent)
export function formatDate(iso) {
  const d = parse(iso);
  return d ? DATE_ONLY.format(d) : iso || "no data";
}
