import { useState } from "react";
import { useApi, post, put, fmt, type Rec } from "../api";
import { ActionButton, Async, Badge, Card, Notice } from "../ui";

const OUTCOMES = ["none", "success", "rate_limit", "permission_revoked", "terminal_failure", "unknown"];

function Rule({ rule, reload }: { rule: Rec; reload: () => void }) {
  const [prev, setPrev] = useState<Rec | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [f, setF] = useState({ keywords: rule.keywords.join(", "), reply_template: rule.reply_template, dm_template: rule.dm_template, send_dm: rule.send_dm, links: rule.links.join("\n") });
  return (
    <Card title={<>{rule.name} <Badge>workflow v{rule.version}</Badge>{rule.enabled ? <Badge kind="ok">啟用</Badge> : <Badge>停用</Badge>}</>}>
      <div className="small muted">綁定貼文 {rule.post_id}（Demo 自有貼文）</div>
      <div className="row">
        <label>關鍵字（contains、不分大小寫、任一）<input data-testid="rule-keywords" value={f.keywords} onChange={(e) => setF({ ...f, keywords: e.target.value })} /></label>
        <label>連結（最多 3，每行一個 http/https）<textarea style={{ minHeight: 40 }} value={f.links} onChange={(e) => setF({ ...f, links: e.target.value })} /></label>
      </div>
      <label>公開回覆模板<textarea value={f.reply_template} onChange={(e) => setF({ ...f, reply_template: e.target.value })} /></label>
      <div className="row"><label><span>同時私訊</span><input type="checkbox" checked={f.send_dm} onChange={(e) => setF({ ...f, send_dm: e.target.checked })} /></label>
        <label>私訊模板<input value={f.dm_template} onChange={(e) => setF({ ...f, dm_template: e.target.value })} /></label></div>
      <div className="row">
        <ActionButton onClick={async () => {
          await put(`/api/automations/${rule.id}`, { name: rule.name, post_id: rule.post_id, enabled: rule.enabled, keywords: f.keywords.split(/[,，]/).map((x: string) => x.trim()).filter(Boolean),
            reply_template: f.reply_template, dm_template: f.dm_template, send_dm: f.send_dm, links: f.links.split("\n").map((x: string) => x.trim()).filter(Boolean) });
          reload();
        }}>儲存（workflow 版本 +1）</ActionButton>
        <ActionButton testid="rule-preview" onClick={async () => setPrev(await post<Rec>(`/api/automations/${rule.id}/preview`))}>預覽（不送出）</ActionButton>
        <ActionButton testid="rule-process" kind="primary" onClick={async () => { const r = await post<Rec>(`/api/automations/${rule.id}/process-existing`); setMsg(`已為 ${r.matched_comments} 則既有留言排入工作（已處理過的 comment+channel 會被去重）`); }}>既有留言一次處理</ActionButton>
      </div>
      {msg && <Notice><span data-testid="process-msg">{msg}</span></Notice>}
      {prev && (<div data-testid="preview">
        <Notice>{prev.note}：共 {prev.total_comments} 則留言，命中 {prev.matching} 則。</Notice>
        <div className="small">公開回覆預覽：<span className="evidence">{prev.public_reply_preview}</span>{prev.dm_preview && <><br />私訊預覽：<span className="evidence">{prev.dm_preview}</span></>}</div>
        <table><thead><tr><th>留言者</th><th>內容</th><th>命中</th><th>已處理（公開／私訊）</th></tr></thead>
          <tbody>{prev.matches.slice(0, 10).map((m: Rec) => <tr key={m.comment_id}><td>{m.author}</td><td>{m.text}</td><td>{m.matched_keyword}</td><td>{String(m.already_handled.public_reply)} / {String(m.already_handled.dm)}</td></tr>)}</tbody></table>
      </div>)}
    </Card>
  );
}

export default function Automations() {
  const rules = useApi<Rec>("/api/automations");
  const events = useApi<Rec>("/api/events?page_size=8");
  const deliveries = useApi<Rec>("/api/deliveries?limit=30");
  const settings = useApi<Rec>("/api/settings");
  const [eid, setEid] = useState(`evt-${Math.random().toString(36).slice(2, 8)}`);
  const [text, setText] = useState("請給我清單");
  const [last, setLast] = useState<Rec | null>(null);
  const refresh = () => { events.reload(); deliveries.reload(); };
  return (
    <>
      <h2>留言轉私訊模擬</h2>
      <Notice>所有「公開回覆」與「私訊」只寫入本機模擬紀錄，不會送到任何真實平台。收到事件、投遞結果、已讀是三件分開的事；模擬平台不回報已讀，所以不會顯示已讀。</Notice>
      <Async loading={rules.loading} error={rules.error} onRetry={rules.reload} empty={rules.data?.items.length === 0 && "尚無規則"}>
        {rules.data?.items.map((r: Rec) => <Rule key={r.id + r.version} rule={r} reload={rules.reload} />)}
      </Async>
      <Card title="新事件觸發（webhook simulator）" actions={<button onClick={refresh}>重新整理</button>}>
        <div className="small muted">先以 event_id 去重落地，再排工作。同一 event_id 再送一次，會得到相同的「已接受」結果但不會重複投遞。</div>
        <div className="row">
          <label>event_id<input data-testid="evt-id" value={eid} onChange={(e) => setEid(e.target.value)} /></label>
          <label>留言內容（貼到 own_rent_1）<input data-testid="evt-text" value={text} onChange={(e) => setText(e.target.value)} /></label>
          <ActionButton kind="primary" testid="evt-send" onClick={async () => { setLast(await post<Rec>("/api/simulator/events", { event_id: eid, post_id: "own_rent_1", author_handle: "demo_tester", text })); refresh(); }}>注入事件</ActionButton>
        </div>
        {last && <Notice><span data-testid="evt-result">accepted={String(last.accepted)}・duplicate={String(last.duplicate)}・事件狀態 {last.event_status}</span></Notice>}
        <h3>失敗注入（下一次投遞的模擬結果）</h3>
        <div className="row">
          {(["public_reply", "dm"] as const).map((ch) => (
            <label key={ch}>{ch === "public_reply" ? "公開回覆" : "私訊"}
              <select data-testid={`inject-${ch}`} value={settings.data?.injection?.[`inject_${ch}`] ?? "none"}
                onChange={async (e) => { await post("/api/simulator/inject", { channel: ch, outcome: e.target.value }); settings.reload(); }}>
                {OUTCOMES.map((o) => <option key={o}>{o}</option>)}</select></label>))}
        </div>
      </Card>
      <Card title="最近事件">
        <Async loading={events.loading} error={events.error} onRetry={events.reload} empty={events.data?.total === 0 && "尚無事件"}>
          <table><thead><tr><th>event_id</th><th>類型</th><th>狀態</th><th>收到</th></tr></thead>
            <tbody>{events.data?.items.map((e: Rec) => <tr key={e.id}><td>{e.event_id}</td><td>{e.type}</td><td>{e.status}</td><td>{fmt(e.received_at)}</td></tr>)}</tbody></table>
        </Async>
      </Card>
      <Card title="投遞紀錄（模擬）">
        <Async loading={deliveries.loading} error={deliveries.error} onRetry={deliveries.reload} empty={deliveries.data?.items.length === 0 && "尚無投遞。注入事件後需要 worker 執行。"}>
          <table data-testid="deliveries"><thead><tr><th>類型</th><th>收件人</th><th>狀態</th><th>嘗試</th><th>已讀</th><th>錯誤</th><th>規則版本</th><th /></tr></thead>
            <tbody>{deliveries.data?.items.map((a: Rec) => (
              <tr key={a.id} data-status={a.status}><td>{a.kind}</td><td>{a.recipient}</td><td><Badge kind={a.status === "simulated_sent" ? "ok" : a.status === "unknown" ? "warn" : a.status.startsWith("failed") ? "bad" : ""}>{a.status}</Badge></td>
                <td>{a.attempts}</td><td className="muted">{a.read_status === "not_reported" ? "平台未回報" : a.read_status}</td><td className="small">{a.error}</td><td>{a.rule_version ? `v${a.rule_version}` : "—"}</td>
                <td>{a.status === "unknown" && <>
                  <ActionButton onClick={async () => { await post(`/api/deliveries/${a.id}/reconcile?resolution=sent`); refresh(); }}>確認已送出</ActionButton>
                  <ActionButton onClick={async () => { await post(`/api/deliveries/${a.id}/reconcile?resolution=not_sent`); refresh(); }}>確認未送出</ActionButton></>}</td></tr>))}</tbody></table>
        </Async>
      </Card>
    </>
  );
}
