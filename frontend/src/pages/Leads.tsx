import { useState } from "react";
import { useApi, patch, post, fmt, type Rec } from "../api";
import { ActionButton, Async, Badge, Card, Notice, Pager } from "../ui";

const STATUSES = ["New", "Qualified", "Ignored", "Converted"];

function Detail({ id, onChanged }: { id: string; onChanged: () => void }) {
  const d = useApi<Rec>(`/api/leads/${id}`);
  const [note, setNote] = useState<string | null>(null);
  return (
    <Async loading={d.loading} error={d.error} onRetry={d.reload}>
      {d.data && (<div data-testid="lead-detail">
        <div className="row">
          <label>狀態<select data-testid="lead-status" value={d.data.status} onChange={async (e) => { await patch(`/api/leads/${id}`, { status: e.target.value }); d.reload(); onChanged(); }}>
            {STATUSES.map((s) => <option key={s}>{s}</option>)}</select></label>
          <label>備註<input value={note ?? d.data.note} onChange={(e) => setNote(e.target.value)} /></label>
          <ActionButton onClick={async () => { await patch(`/api/leads/${id}`, { note: note ?? d.data!.note }); d.reload(); onChanged(); }}>儲存備註</ActionButton>
        </div>
        {d.data.status === "Converted" && <Notice>Converted 是人工分類，不代表訂單或成交。</Notice>}
        <h3>來源（{d.data.sources.length}）</h3>
        <ul>{d.data.sources.map((s: Rec) => <li key={s.id}>{s.reason}<div className="small muted post">{s.post_text}</div></li>)}</ul>
        <h3>歷史</h3>
        <ul className="small">{d.data.activity.map((a: Rec) => <li key={a.id}>{fmt(a.created_at)}｜{a.kind}｜{a.detail}</li>)}</ul>
      </div>)}
    </Async>
  );
}

export default function Leads() {
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  const [h, setH] = useState("demo_");
  const [reason, setReason] = useState("");
  const qs = `page=${page}&page_size=15${status ? `&status=${status}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}`;
  const r = useApi<Rec>(`/api/leads?${qs}`);
  const filt = `${status ? `status=${status}` : ""}${q ? `${status ? "&" : ""}q=${encodeURIComponent(q)}` : ""}`;
  return (
    <>
      <h2>名單</h2>
      <Notice>以「平台＋handle」去重；同一人從多個來源進來只會有一筆，並保留所有來源與歷史。匯出包含所有符合條件的資料（不只這一頁）。</Notice>
      <div className="row">
        <label>狀態<select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}><option value="">全部</option>{STATUSES.map((s) => <option key={s}>{s}</option>)}</select></label>
        <label>handle 包含<input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} /></label>
        <a href={`/api/leads/export.csv?${filt}`} data-testid="export-csv"><button>匯出 CSV</button></a>
        <a href={`/api/leads/export.json?${filt}`} data-testid="export-json"><button>匯出 JSON（含歷史）</button></a>
      </div>
      <Async loading={r.loading} error={r.error} onRetry={r.reload} empty={r.data?.total === 0 && "沒有符合的名單。留言事件被處理後會自動加入。"}>
        <table data-testid="leads"><thead><tr><th>平台</th><th>Handle</th><th>狀態</th><th>來源數</th><th>更新</th><th /></tr></thead>
          <tbody>{r.data?.items.map((l: Rec) => (
            <tr key={l.id}><td>{l.platform}</td><td>{l.handle}</td><td><Badge>{l.status}</Badge></td><td>{l.source_count}</td><td>{fmt(l.updated_at)}</td>
              <td><button onClick={() => setOpen(open === l.id ? null : l.id)}>{open === l.id ? "收合" : "詳情"}</button></td></tr>))}</tbody></table>
        {r.data && <Pager page={page} total={r.data.total} size={15} onPage={setPage} />}
      </Async>
      {open && <Card title="名單詳情"><Detail id={open} onChanged={r.reload} /></Card>}
      <Card title="手動加入／新增來源">
        <div className="row"><label>Handle<input value={h} onChange={(e) => setH(e.target.value)} /></label>
          <label>理由<input value={reason} onChange={(e) => setReason(e.target.value)} /></label>
          <ActionButton onClick={async () => { await post("/api/leads", { platform: "threads", handle: h, reason }); r.reload(); }}>加入</ActionButton></div>
      </Card>
    </>
  );
}
