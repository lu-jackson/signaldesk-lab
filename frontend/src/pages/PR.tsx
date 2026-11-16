import { useState } from "react";
import { useApi, fmt, type Rec } from "../api";
import { Async, Badge, Card, Notice, Pager, riskBadge } from "../ui";

export default function PR() {
  const [risk, setRisk] = useState("high");
  const [page, setPage] = useState(1);
  const r = useApi<Rec>(`/api/evaluations?risk=${risk}&page=${page}&page_size=15`);
  return (
    <>
      <h2>PR 風險分流</h2>
      <Notice>依分類的風險等級分流，保留原文與理由。這不是「預測危機」，只是規則／模型對單篇貼文的建議；人工判斷為準。</Notice>
      <div className="row">{["high", "medium", "low"].map((x) => (
        <button key={x} className={risk === x ? "primary" : ""} data-testid={`pr-${x}`} onClick={() => { setRisk(x); setPage(1); }}>{x}</button>))}</div>
      <Async loading={r.loading} error={r.error} onRetry={r.reload} empty={r.data?.total === 0 && `目前沒有 ${risk} 風險的已分類貼文`}>
        {r.data?.items.map((e: Rec) => (
          <Card key={e.id} title={<>{riskBadge(e.risk)}<Badge>{e.intent}</Badge>{e.flags.map((f: string) => <Badge key={f} kind="bad">{f}</Badge>)}<span className="small muted"> @{e.author_handle}・{fmt(e.post_created_at)}</span></>}>
            <div className="post">{e.post_text}</div>
            <div className="small" style={{ marginTop: 6 }}>理由（{e.classifier === "demo" ? "規則" : e.classifier}）：{e.reason}</div>
            {e.evidence && <div className="small">證據：<span className="evidence">{e.evidence}</span></div>}
          </Card>))}
        {r.data && <Pager page={page} total={r.data.total} size={15} onPage={setPage} />}
      </Async>
    </>
  );
}
