import { useState, type HTMLAttributes, type ReactNode } from "react";

export function Async({ loading, error, onRetry, children, empty }: { loading: boolean; error: string | null; onRetry: () => void; children: ReactNode; empty?: string | false }) {
  if (loading) return <div className="state" data-testid="loading" role="status">載入中…</div>;
  if (error) return <div className="state error" data-testid="error" role="alert">載入失敗：{error} <button onClick={onRetry}>重試</button></div>;
  if (empty) return <div className="state" data-testid="empty">{empty}</div>;
  return <>{children}</>;
}

export function Badge({ kind, children }: { kind?: string; children: ReactNode }) {
  return <span className={`badge ${kind ?? ""}`}>{children}</span>;
}

export function riskBadge(r?: string | null) {
  if (!r) return <Badge>未分類</Badge>;
  return <Badge kind={`risk-${r}`}>{r}</Badge>;
}

/** 有 loading / error 狀態的動作按鈕。 */
export function ActionButton({ onClick, children, kind, testid, disabled }: { onClick: () => Promise<unknown>; children: ReactNode; kind?: string; testid?: string; disabled?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <span className="action">
      <button className={kind} data-testid={testid} disabled={busy || disabled} onClick={async () => {
        setBusy(true); setErr(null);
        try { await onClick(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
      }}>{busy ? "處理中…" : children}</button>
      {err && <span className="inline-error" role="alert">{err}</span>}
    </span>
  );
}

export function Card({ title, children, actions }: { title?: ReactNode; children: ReactNode; actions?: ReactNode }) {
  return <section className="card">{(title || actions) && <header><h3>{title}</h3><div>{actions}</div></header>}{children}</section>;
}

export function Pager({ page, total, size, onPage }: { page: number; total: number; size: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / size));
  return (
    <div className="pager">
      <button disabled={page <= 1} onClick={() => onPage(page - 1)}>上一頁</button>
      <span>第 {page} / {pages} 頁（共 {total} 筆）</span>
      <button disabled={page >= pages} onClick={() => onPage(page + 1)}>下一頁</button>
    </div>
  );
}

export function Notice({ children, ...rest }: { children: ReactNode } & HTMLAttributes<HTMLDivElement>) { return <div className="notice" {...rest}>{children}</div>; }
