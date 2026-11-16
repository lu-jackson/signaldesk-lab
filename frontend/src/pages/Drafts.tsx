import { useEffect, useState } from "react";
import { useApi, post, put, fmt, type Rec } from "../api";
import { ActionButton, Async, Badge, Card, Notice, Pager } from "../ui";

function DraftCard({ d, reload }: { d: Rec; reload: () => void }) {
  const [text, setText] = useState<string>(d.body);
  const [out, setOut] = useState<string | null>(null);
  useEffect(() => { setText(d.body); }, [d.body, d.revision]);
  const dirty = text !== d.body;
  const sent = d.status === "sent";
  return (
    <Card title={<>草稿 <Badge kind={d.status === "approved" ? "ok" : d.status === "rejected" ? "bad" : ""}>{d.status}</Badge>
      {d.approval_valid ? <Badge kind="ok">核准有效</Badge> : <Badge>未核准／已失效</Badge>}
      {d.requires_human && <Badge kind="warn">需人工核准</Badge>}
      <span className="small muted"> v{d.revision}・品牌 v{d.brand_version}・來源 {d.source}</span></>}>
      {d.brand_outdated && <Notice data-testid="brand-outdated">{d.notice}</Notice>}
      <div className="small muted">回覆對象 @{d.post_author} 的貼文（合成）：</div>
      <div className="post small" style={{ marginBottom: 8 }}>{d.post_text}</div>
      <textarea data-testid={`draft-body-${d.id}`} value={text} onChange={(e) => setText(e.target.value)} disabled={sent} />
      <div className="row">
        <ActionButton testid={`draft-save-${d.id}`} disabled={!dirty || sent} onClick={async () => { await put(`/api/drafts/${d.id}`, { body: text }); reload(); }}>儲存修改（核准會失效）</ActionButton>
        <ActionButton kind="primary" testid={`draft-approve-${d.id}`} disabled={sent || dirty || d.status === "rejected"} onClick={async () => { await post(`/api/drafts/${d.id}/approve`); reload(); }}>核准</ActionButton>
        <ActionButton kind="danger" disabled={sent} onClick={async () => { await post(`/api/drafts/${d.id}/reject`); reload(); }}>拒絕</ActionButton>
        <ActionButton disabled={sent} onClick={async () => { await post(`/api/drafts/${d.id}/regenerate`); reload(); }}>依目前品牌重新生成</ActionButton>
        <ActionButton kind="primary" testid={`draft-send-${d.id}`} disabled={!d.approval_valid || sent || dirty}
          onClick={async () => {
            const r = await post<Rec>(`/api/drafts/${d.id}/simulate-send`, {}, { "Idempotency-Key": `ui-${d.id}-${d.revision}` });
            setOut(`${r.attempt.status}${r.replayed ? "（重複請求，未再投遞）" : ""}${r.attempt.error ? "：" + r.attempt.error : ""}`); reload();
          }}>模擬送出</ActionButton>
        {out && <span data-testid={`draft-out-${d.id}`} className="small">{out}</span>}
      </div>
      {d.delivery && <div className="small muted" data-testid={`draft-delivery-${d.id}`}>投遞：{d.delivery.status}（僅本機模擬，無已讀資料）</div>}
      <div className="small muted">建立：{fmt(d.created_at)}・by {d.created_by}</div>
    </Card>
  );
}

export default function Drafts() {
  const initial = new URLSearchParams(window.location.hash.split("?")[1] ?? "").get("status") ?? "";
  const [status, setStatus] = useState(initial);
  const [page, setPage] = useState(1);
  const r = useApi<Rec>(`/api/drafts?page=${page}&page_size=10${status ? `&status=${status}` : ""}`);
  return (
    <>
      <h2>草稿審核</h2>
      <Notice>核准綁定草稿內容：修改後舊核准立刻失效；沒有有效核准不能送出；送出只會寫入本機模擬投遞紀錄。</Notice>
      <div className="row"><label>狀態<select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
        <option value="">全部</option>{["draft", "approved", "rejected", "sent"].map((s) => <option key={s}>{s}</option>)}</select></label>
        <button onClick={r.reload}>重新整理</button></div>
      <Async loading={r.loading} error={r.error} onRetry={r.reload} empty={r.data?.total === 0 && "沒有草稿。到「專案與搜尋」執行一次，或請 AI 助手準備草稿。"}>
        {r.data?.items.map((d: Rec) => <DraftCard key={d.id} d={d} reload={r.reload} />)}
        {r.data && <Pager page={page} total={r.data.total} size={10} onPage={setPage} />}
      </Async>
    </>
  );
}
