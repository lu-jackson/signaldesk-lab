import { useState } from "react";
import { useApi, post, type Rec } from "../api";
import { ActionButton, Async, Badge, Card, Notice } from "../ui";

const EXAMPLE = "搜尋最近七天需要多益備考協助的 Demo 貼文，排除補習班廣告，替前三篇準備回覆，但不要送出。";

function Trace({ id }: { id: string }) {
  const t = useApi<Rec>(`/api/agent/sessions/${id}`);
  return (
    <Async loading={t.loading} error={t.error} onRetry={t.reload}>
      {t.data && (<div data-testid="trace">
        <Notice>{t.data.session.label}｜狀態 {t.data.session.status}｜模型回合 {t.data.session.model_turns}/{t.data.session.limits.max_model_turns}｜工具呼叫 {t.data.session.tool_calls}/{t.data.session.limits.max_tool_calls}
          {t.data.session.error && <span className="inline-error"> {t.data.session.error}</span>}</Notice>
        <h3>對話</h3>
        {t.data.messages.map((m: Rec, i: number) => m.content.map((b: Rec, j: number) => (
          <div key={`${i}-${j}`} className="trace" data-kind={b.type}>
            <b>{m.role}／{b.type}</b>{" "}{b.type === "text" ? b.text : b.type === "tool_use" ? `${b.name}(${JSON.stringify(b.input)}) id=${b.id}` : `→ ${b.tool_use_id}${b.is_error ? " [error]" : ""}: ${String(b.content).slice(0, 300)}`}
          </div>)))}
        <h3>工具呼叫 trace（脫敏參數、輸出摘要）</h3>
        <table><thead><tr><th>工具</th><th>參數</th><th>狀態</th><th>輸出摘要</th></tr></thead>
          <tbody>{t.data.tool_calls.map((c: Rec) => <tr key={c.id} data-testid="tool-call"><td>{c.name}</td><td className="small">{JSON.stringify(c.args)}</td><td><Badge kind={c.status === "ok" ? "ok" : "bad"}>{c.status}</Badge></td><td className="small">{c.summary}</td></tr>)}</tbody></table>
        {t.data.proposals.length > 0 && <Proposals items={t.data.proposals} onDone={t.reload} />}
      </div>)}
    </Async>
  );
}

function Proposals({ items, onDone }: { items: Rec[]; onDone: () => void }) {
  return (
    <Card title="行動提案（需要你確認才會生效；模型無法替你確認）">
      {items.map((p) => (
        <div key={p.id} className="row" data-testid="proposal"><Badge kind={p.status === "confirmed" ? "ok" : p.status === "pending" ? "warn" : ""}>{p.status}</Badge>
          <span className="small">{p.kind}：{p.payload.platform}/{p.payload.handle} → {p.payload.status ?? "(不改狀態)"}（{p.payload.reason}）</span>
          {p.status === "pending" && <><ActionButton kind="primary" testid="proposal-confirm" onClick={async () => { await post(`/api/agent/proposals/${p.id}/confirm`); onDone(); }}>確認</ActionButton>
            <ActionButton onClick={async () => { await post(`/api/agent/proposals/${p.id}/reject`); onDone(); }}>拒絕</ActionButton></>}</div>))}
    </Card>
  );
}

export default function Assistant() {
  const sessions = useApi<Rec>("/api/agent/sessions");
  const tools = useApi<Rec>("/api/agent/tools");
  const [sid, setSid] = useState<string | null>(null);
  const [text, setText] = useState(EXAMPLE);
  const [ver, setVer] = useState(0);
  const send = async () => {
    let id = sid;
    if (!id) { id = (await post<Rec>("/api/agent/sessions", { title: text.slice(0, 20) })).id; setSid(id); }
    try { await post(`/api/agent/sessions/${id}/messages`, { content: text }, { "Idempotency-Key": crypto.randomUUID() }); }
    finally { setVer(ver + 1); sessions.reload(); }
  };
  return (
    <>
      <h2>AI 助手</h2>
      <Notice>Demo 模式是 <b>scripted planner（模擬規劃）</b>，只支援固定範圍句型，<b>不是 LLM</b>。Live 模式需在後端 .env 配置 Anthropic 並於「設定」啟用；未配置時會直接顯示錯誤，不會偷偷降級。助手沒有送出工具；寫入只能是提案。</Notice>
      <Card title="下指令">
        <textarea data-testid="agent-input" value={text} onChange={(e) => setText(e.target.value)} />
        <div className="row">
          <ActionButton kind="primary" testid="agent-send" onClick={send}>送出給助手</ActionButton>
          <button onClick={() => { setSid(null); setVer(ver + 1); }}>新會話</button>
          <span className="small muted">可試：「查看名單」「把 demo_vip01 標記為 Qualified」「查最近執行狀態」</span>
        </div>
      </Card>
      {sid && <Card title="本次會話 trace" key={`${sid}-${ver}`}><Trace id={sid} /></Card>}
      <Card title="歷史會話">
        <Async loading={sessions.loading} error={sessions.error} onRetry={sessions.reload} empty={sessions.data?.items.length === 0 && "尚無會話"}>
          {sessions.data?.items.map((s: Rec) => <div key={s.id} className="row"><button onClick={() => { setSid(s.id); setVer(ver + 1); }}>{s.title}</button><Badge>{s.status}</Badge><span className="small muted">{s.label}</span></div>)}
        </Async>
      </Card>
      <Card title="工具白名單">
        {tools.data?.items.map((t: Rec) => <div key={t.name} className="small"><b>{t.name}</b>：{t.description}</div>)}
      </Card>
    </>
  );
}
