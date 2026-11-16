import { useState } from "react";
import { useApi, post, fmt, type Rec } from "../api";
import { ActionButton, Async, Badge, Card, Notice, Pager } from "../ui";

export default function Jobs() {
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const r = useApi<Rec>(`/api/jobs?page=${page}&page_size=20${status ? `&status=${status}` : ""}`);
  const health = useApi<Rec>("/api/health");
  return (
    <>
      <h2>工作與事件</h2>
      <Notice>狀態：queued / running / succeeded / failed / cancelled / unknown。<b>unknown</b> = 外部結果不明，不會被自動重跑，請到「留言與私訊模擬」的投遞紀錄 reconcile。取消不會撤回已完成的副作用。</Notice>
      <div className="small muted">Worker：{health.data?.worker.alive ? `執行中（pid ${health.data.worker.pid}）` : "未執行——queued 工作不會被處理"}</div>
      <div className="row">
        {r.data && Object.entries(r.data.stats).map(([k, v]) => <Badge key={k}>{k}: {String(v)}</Badge>)}
        <label>篩選<select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}><option value="">全部</option>{["queued", "running", "succeeded", "failed", "cancelled", "unknown"].map((s) => <option key={s}>{s}</option>)}</select></label>
        <button onClick={() => { r.reload(); health.reload(); }}>重新整理</button>
      </div>
      <Async loading={r.loading} error={r.error} onRetry={r.reload} empty={r.data?.total === 0 && "沒有工作"}>
        <Card><table data-testid="jobs"><thead><tr><th>類型</th><th>狀態</th><th>嘗試</th><th>下次執行</th><th>錯誤／結果</th><th /></tr></thead>
          <tbody>{r.data?.items.map((j: Rec) => (
            <tr key={j.id}><td>{j.type}{j.side_effect ? <Badge kind="warn">有副作用</Badge> : null}</td>
              <td><Badge kind={j.status === "succeeded" ? "ok" : j.status === "failed" ? "bad" : j.status === "unknown" ? "warn" : ""}>{j.status}</Badge></td>
              <td>{j.attempts}/{j.max_attempts}</td><td>{j.status === "queued" ? fmt(j.run_at) : "—"}</td>
              <td className="small">{j.last_error ?? (j.result ? JSON.stringify(j.result) : "")}</td>
              <td>{["queued", "running"].includes(j.status) && <ActionButton onClick={async () => { await post(`/api/jobs/${j.id}/cancel`); r.reload(); }}>取消</ActionButton>}
                {["failed", "cancelled"].includes(j.status) && !j.side_effect && <ActionButton onClick={async () => { await post(`/api/jobs/${j.id}/retry`); r.reload(); }}>重試</ActionButton>}</td></tr>))}</tbody></table>
          {r.data && <Pager page={page} total={r.data.total} size={20} onPage={setPage} />}</Card>
      </Async>
    </>
  );
}
