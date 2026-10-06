/** Browser API client: cookie auth + CSRF double-submit + one transparent refresh on token expiry. */
export class ApiError extends Error {
  status: number;
  code: string;
  details?: Record<string, string>;
  requestId?: string;
  constructor(status: number, code: string, message: string, details?: Record<string, string>, requestId?: string) {
    super(message);
    this.status = status; this.code = code; this.details = details; this.requestId = requestId;
  }
  get isNetwork() { return this.status === 0; }
}

export type ApiConfig = {
  baseUrl?: string;
  csrfCookie: string;
  refreshPath: string;
  /** Called when the session can't be recovered (refresh failed). */
  onSessionExpired?: () => void;
  /** Called for restricted-workspace errors (402) so the app can show the paywall. */
  onPaymentRequired?: (e: ApiError) => void;
};

export type Page<T> = { data: T[]; meta: { page: number; per_page: number; total: number; pages: number; [k: string]: unknown } };

function readCookie(name: string) {
  if (typeof document === "undefined") return "";
  return document.cookie.split("; ").find((c) => c.startsWith(name + "="))?.split("=")[1] ?? "";
}

export function createApi(cfg: ApiConfig) {
  let refreshing: Promise<boolean> | null = null;
  const base = cfg.baseUrl ?? "";

  async function refresh(): Promise<boolean> {
    refreshing ??= fetch(`${base}${cfg.refreshPath}`, { method: "POST", credentials: "include", headers: { "X-CSRF-Token": readCookie(cfg.csrfCookie) } })
      .then((r) => r.ok).catch(() => false).finally(() => { setTimeout(() => (refreshing = null), 0); });
    return refreshing;
  }

  async function raw(method: string, path: string, body?: unknown, retry = true): Promise<Response> {
    const isForm = typeof FormData !== "undefined" && body instanceof FormData;
    let res: Response;
    try {
      res = await fetch(`${base}${path}`, {
        method, credentials: "include",
        headers: { ...(isForm || body === undefined ? {} : { "Content-Type": "application/json" }), "X-CSRF-Token": readCookie(cfg.csrfCookie) },
        body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
      });
    } catch {
      throw new ApiError(0, "network_error", "Can't reach the server. Check your connection and try again.");
    }
    if (res.status === 401 && retry && !path.includes("/auth/login") && !path.includes("/auth/refresh")) {
      const err = await res.clone().json().catch(() => null);
      const code = err?.error?.code;
      if (code === "token_expired" || code === "unauthenticated") {
        if (await refresh()) return raw(method, path, body, false);
      }
      if (code !== "invalid_credentials") cfg.onSessionExpired?.();
    }
    return res;
  }

  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await raw(method, path, body);
    if (res.status === 204) return undefined as T;
    const json = await res.json().catch(() => null);
    if (!res.ok) {
      const e = json?.error ?? {};
      const err = new ApiError(res.status, e.code ?? "error", e.message ?? "Something went wrong. Please try again.", e.details, e.request_id);
      if (res.status === 402) cfg.onPaymentRequired?.(err);
      throw err;
    }
    return json as T;
  }

  const qs = (params?: Record<string, unknown>) => {
    if (!params) return "";
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length)) continue;
      u.set(k, Array.isArray(v) ? v.join(",") : String(v));
    }
    const s = u.toString();
    return s ? `?${s}` : "";
  };

  return {
    qs,
    raw,
    /** GET returning the `data` field. */
    get: async <T,>(path: string, params?: Record<string, unknown>) => (await request<{ data: T }>("GET", path + qs(params))).data,
    /** GET returning `{data, meta}` for paginated endpoints. */
    page: <T,>(path: string, params?: Record<string, unknown>) => request<Page<T>>("GET", path + qs(params)),
    post: async <T,>(path: string, body?: unknown) => (await request<{ data: T }>("POST", path, body ?? {})).data,
    put: async <T,>(path: string, body?: unknown) => (await request<{ data: T }>("PUT", path, body ?? {})).data,
    patch: async <T,>(path: string, body?: unknown) => (await request<{ data: T }>("PATCH", path, body ?? {})).data,
    delete: (path: string, body?: unknown) => request<void>("DELETE", path, body),
    upload: async <T,>(path: string, form: FormData) => (await request<{ data: T }>("POST", path, form)).data,
  };
}
export type Api = ReturnType<typeof createApi>;
