import { useEffect, useRef, useState } from "react";
import { useApi, post, put, api, fmt, type Rec } from "../api";
import { ActionButton, Async, Badge, Card, Notice, Pager } from "../ui";

// 複製到剪貼簿：優先用 Clipboard API；在不支援的環境退回選取後 execCommand。
async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch { /* 退回舊作法 */ }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  const ok = document.execCommand("copy");
  document.body.removeChild(ta);
  if (!ok) throw new Error("瀏覽器不允許複製，請手動選取文字複製");
}

function DraftCard({ d, reload, caps }: { d: Rec; reload: () => void; caps: Rec }) {
  const [text, setText] = useState<string>(d.body);
  const [out, setOut] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [note, setNote] = useState("");
  useEffect(() => { setText(d.body); }, [d.body, d.revision]);
  const dirty = text !== d.body;
  const sent = d.status === "sent";
  const mo: Rec | null = d.manual_outcome;
  const posted = mo?.outcome === "posted";
  const locked = sent || posted;
  const publicDemo = !!caps.public_demo;
  const canRecord = !publicDemo;                 // 公開展示站不開放寫入
  const showSimulate = caps.synthetic !== false; // 真實使用模式不顯示「模擬送出」，避免和「已貼到平台」混淆
  return (
    <Card title={<>草稿 <Badge kind={d.status === "approved" ? "ok" : d.status === "rejected" ? "bad" : ""}>{d.status}</Badge>
      {d.approval_valid ? <Badge kind="ok">核准有效</Badge> : <Badge>未核准／已失效</Badge>}
      {d.requires_human && <Badge kind="warn">需人工核准</Badge>}
      {mo && <Badge kind={posted ? "ok" : ""}>{posted ? "已貼到平台" : "已略過"}</Badge>}
      <span className="small muted"> v{d.revision}・品牌 v{d.brand_version}・來源 {d.source}</span></>}>
      {d.brand_outdated && <Notice data-testid="brand-outdated">{d.notice}</Notice>}
      <div className="small muted">
        回覆對象{d.post_author ? ` @${d.post_author} ` : " "}的貼文{d.post_synthetic ? "（合成）" : ""}：
        {d.post_url && <> <a href={d.post_url} target="_blank" rel="noopener noreferrer" data-testid={`draft-post-link-${d.id}`}>開啟原貼文 ↗</a></>}
      </div>
      <div className="post small" style={{ marginBottom: 8 }}>{d.post_text}</div>
      <textarea data-testid={`draft-body-${d.id}`} value={text} onChange={(e) => setText(e.target.value)} disabled={locked} />
      <div className="row">
        <ActionButton testid={`draft-copy-${d.id}`} onClick={async () => { await copyText(text); setCopied(true); setTimeout(() => setCopied(false), 2500); }}>
          {copied ? "已複製 ✓" : "複製草稿"}</ActionButton>
        <ActionButton testid={`draft-save-${d.id}`} disabled={!dirty || locked} onClick={async () => { await put(`/api/drafts/${d.id}`, { body: text }); reload(); }}>儲存修改（核准會失效）</ActionButton>
        <ActionButton kind="primary" testid={`draft-approve-${d.id}`} disabled={locked || dirty || d.status === "rejected"} onClick={async () => { await post(`/api/drafts/${d.id}/approve`); reload(); }}>核准</ActionButton>
        <ActionButton kind="danger" disabled={locked} onClick={async () => { await post(`/api/drafts/${d.id}/reject`); reload(); }}>拒絕</ActionButton>
        <ActionButton disabled={locked} onClick={async () => { await post(`/api/drafts/${d.id}/regenerate`); reload(); }}>依目前品牌重新生成</ActionButton>
        {showSimulate && (
          <ActionButton kind="primary" testid={`draft-send-${d.id}`} disabled={!d.approval_valid || sent || dirty}
            onClick={async () => {
              const r = await post<Rec>(`/api/drafts/${d.id}/simulate-send`, {}, { "Idempotency-Key": `ui-${d.id}-${d.revision}` });
              setOut(`${r.attempt.status}${r.replayed ? "（重複請求，未再投遞）" : ""}${r.attempt.error ? "：" + r.attempt.error : ""}`); reload();
            }}>模擬送出</ActionButton>
        )}
        {out && <span data-testid={`draft-out-${d.id}`} className="small">{out}</span>}
      </div>
      {canRecord && (
        <div className="row" data-testid={`draft-handling-${d.id}`}>
          {mo ? (
            <>
              <span className="small">你記錄為：<b>{posted ? "已貼到平台" : "已略過"}</b>{mo.note ? `（${mo.note}）` : ""}・{fmt(mo.created_at)}</span>
              <ActionButton testid={`draft-undo-${d.id}`} onClick={async () => { await api(`/api/drafts/${d.id}/manual-outcome`, { method: "DELETE" }); reload(); }}>復原記錄</ActionButton>
            </>
          ) : (
            <>
              <input data-testid={`draft-note-${d.id}`} placeholder="備註（選填，例如略過原因）" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
              <ActionButton kind="primary" testid={`draft-posted-${d.id}`} disabled={!d.approval_valid || dirty}
                onClick={async () => { await post(`/api/drafts/${d.id}/manual-outcome`, { outcome: "posted", note }); setNote(""); reload(); }}>我已貼到平台</ActionButton>
              <ActionButton testid={`draft-skip-${d.id}`} disabled={dirty}
                onClick={async () => { await post(`/api/drafts/${d.id}/manual-outcome`, { outcome: "skipped", note }); setNote(""); reload(); }}>略過</ActionButton>
              {!d.approval_valid && <span className="small muted">先「核准」才能記錄為已貼到平台</span>}
            </>
          )}
        </div>
      )}
      {d.delivery && <div className="small muted" data-testid={`draft-delivery-${d.id}`}>投遞：{d.delivery.status}（僅本機模擬，無已讀資料）</div>}
      <div className="small muted">建立：{fmt(d.created_at)}・by {d.created_by}</div>
    </Card>
  );
}

const HANDLING: [string, string][] = [["", "全部"], ["pending", "待處理"], ["posted", "已貼到平台"], ["skipped", "已略過"]];

export default function Drafts() {
  const initial = new URLSearchParams(window.location.hash.split("?")[1] ?? "").get("status") ?? "";
  const [status, setStatus] = useState(initial);
  const [handling, setHandling] = useState("");
  const [page, setPage] = useState(1);
  const caps = useApi<Rec>("/api/settings");
  // 真實使用模式一打開就只看「待處理」，已處理的不會一直擋在前面；Demo／公開站維持「全部」
  const defaulted = useRef(false);
  useEffect(() => {
    if (!defaulted.current && caps.data) {
      defaulted.current = true;
      if (caps.data.synthetic === false && !initial) setHandling("pending");
    }
  }, [caps.data, initial]);
  const q = `/api/drafts?page=${page}&page_size=10${status ? `&status=${status}` : ""}${handling ? `&handling=${handling}` : ""}`;
  const r = useApi<Rec>(caps.data ? q : null);
  return (
    <>
      <h2>草稿審核</h2>
      <Notice>
        流程：<b>核准</b> → <b>複製草稿</b> → 到平台自己貼上 → 回來按<b>「我已貼到平台」</b>（或「略過」）。
        核准綁定草稿內容，修改後舊核准立刻失效；這個工具<b>不會替你送出任何東西</b>，「已貼到平台」只是你的記錄。
      </Notice>
      <div className="row">
        <label>處理狀態<select data-testid="draft-handling-filter" value={handling} onChange={(e) => { setHandling(e.target.value); setPage(1); }}>
          {HANDLING.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        <label>草稿狀態<select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">全部</option>{["draft", "approved", "rejected", "sent"].map((s) => <option key={s}>{s}</option>)}</select></label>
        <button onClick={r.reload}>重新整理</button></div>
      <Async loading={r.loading || caps.loading} error={r.error ?? caps.error} onRetry={r.reload}
        empty={r.data?.total === 0 && (handling === "pending" ? "沒有待處理的草稿 🎉 到「匯入貼文」貼新的貼文，或切換上方篩選看已處理的。" : "沒有草稿。到「匯入貼文」或「專案與搜尋」開始。")}>
        {r.data?.items.map((d: Rec) => <DraftCard key={d.id} d={d} reload={r.reload} caps={caps.data ?? {}} />)}
        {r.data && <Pager page={page} total={r.data.total} size={10} onPage={setPage} />}
      </Async>
    </>
  );
}
