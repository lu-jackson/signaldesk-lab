// 與後端溝通的唯一入口：統一錯誤格式、loading / error / reload 狀態。
import { useCallback, useEffect, useState } from "react";

export type Rec = Record<string, any>; // 後端 JSON 以 OpenAPI 為準；這裡只對關鍵欄位寫型別
export interface Page<T> { items: T[]; total: number; page: number; page_size: number }

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

export async function api<T = Rec>(path: string, init: { method?: string; body?: unknown; headers?: Record<string, string> } = {}): Promise<T> {
  const res = await fetch(path, {
    method: init.method ?? "GET",
    headers: { ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}), ...init.headers },
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const e = data?.error;
    throw new ApiError(res.status, e?.code ?? "http_error", e?.message ?? `HTTP ${res.status}`);
  }
  return data as T;
}

export const post = <T = Rec>(path: string, body?: unknown, headers?: Record<string, string>) => api<T>(path, { method: "POST", body: body ?? {}, headers });
export const put = <T = Rec>(path: string, body: unknown) => api<T>(path, { method: "PUT", body });
export const patch = <T = Rec>(path: string, body: unknown) => api<T>(path, { method: "PATCH", body });

export function useApi<T = Rec>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (path === null) return;
    let alive = true;
    setLoading(true);
    api<T>(path)
      .then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((e) => { if (alive) setError(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [path, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  // 重新整理時保留舊資料（不把畫面換成「載入中」而丟掉元件狀態）；只有第一次載入才算 loading
  return { data, error, loading: loading && data === null, reload };
}

// 時區顯示：資料庫一律 UTC；畫面可切換。
export function getTz(): string { try { return localStorage.getItem("tz") || "UTC"; } catch { return "UTC"; } }
export function fmt(t?: string | null): string {
  if (!t) return "—";
  const d = new Date(t);
  if (isNaN(d.getTime())) return t;
  const tz = getTz();
  return d.toLocaleString("zh-TW", { timeZone: tz, hour12: false }) + (tz === "UTC" ? " UTC" : "");
}
