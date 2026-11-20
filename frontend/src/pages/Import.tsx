import { useState } from "react";
import { useApi, post, type Rec } from "../api";
import { ActionButton, Async, Badge, Card, Notice, riskBadge } from "../ui";

const PLATFORMS = ["threads", "x", "instagram", "facebook"];

// 手動貼上一則「你自己在社群上看到的公開貼文」，走既有的 納入 → 分類 → 草稿。
// 不會自動送出；草稿要到「草稿審核」由你核准，再自己到平台貼上。
export default function Import() {
  const projects = useApi<Rec>("/api/projects");
  const caps = useApi<Rec>("/api/settings");
  const [f, setF] = useState({ project_id: "", platform: "threads", text: "", author_handle: "", source_url: "" });
  const [result, setResult] = useState<Rec | null>(null);
  const items: Rec[] = projects.data?.items ?? [];
  const pid = f.project_id || items[0]?.id || "";
  const s = (k: string, v: string) => setF({ ...f, [k]: v });
  const submit = async () => {
    setResult(null);
    setResult(await post("/api/posts/import", { ...f, project_id: pid })); // 失敗時由按鈕元件顯示錯誤訊息
  };
  const ev = result?.evaluation;
  return (
    <div>
      <h2>匯入貼文</h2>
      <Notice data-testid="import-help">
        把你在社群上看到的一則公開貼文貼在這裡，工具會判斷是不是在求助、風險高不高，並備好回覆草稿。
        <b>草稿不會自動送出</b>：請到「草稿審核」核准後，自己到平台貼上。請不要貼私訊或含個人資料的內容，作者帳號可以留空。
      </Notice>
      {caps.data?.public_demo && <Notice data-testid="import-public-note">公開展示站不開放匯入（只在本機可用），按下去會被擋下。</Notice>}
      <Card title="貼上貼文">
        <div className="row">
          <label>用哪個專案判斷
            <select data-testid="import-project" value={pid} onChange={(e) => s("project_id", e.target.value)}>
              {items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <label>平台
            <select data-testid="import-platform" value={f.platform} onChange={(e) => s("platform", e.target.value)}>
              {PLATFORMS.map((p) => <option key={p}>{p}</option>)}
            </select>
          </label>
          <label>作者帳號（可留空）<input data-testid="import-author" value={f.author_handle} maxLength={40} onChange={(e) => s("author_handle", e.target.value)} /></label>
          <label>來源網址（可留空）<input data-testid="import-url" value={f.source_url} maxLength={500} placeholder="https://" onChange={(e) => s("source_url", e.target.value)} /></label>
        </div>
        <label>貼文內容（最多 1500 字）
          <textarea data-testid="import-text" rows={5} maxLength={1500} value={f.text} onChange={(e) => s("text", e.target.value)} />
        </label>
        <div className="row"><ActionButton kind="primary" testid="import-submit" disabled={!f.text.trim() || !pid} onClick={submit}>分析並備草稿</ActionButton></div>
      </Card>
      {result && ev && (
        <Card title="結果">
          {result.duplicate && <Notice>這則貼文先前已匯入並分析過，下面是原本的結果（不會重複計費）。</Notice>}
          <p data-testid="import-intent">意圖：<Badge>{ev.intent ?? "未分類"}</Badge> 風險：{riskBadge(ev.risk)} 分類者：<span className="muted">{ev.classifier}</span></p>
          <p className="small">{ev.reason}</p>
          <p className="small muted">納入原因：{ev.inclusion_reason}</p>
          {ev.classify_error && <div className="notice">分類失敗：{ev.classify_error}</div>}
          {(ev.flags ?? []).length > 0 && <p>標記：{ev.flags.map((x: string) => <Badge key={x} kind="warn">{x}</Badge>)}</p>}
          {result.draft
            ? (<div data-testid="import-draft"><h4>回覆草稿（尚未送出）</h4><pre className="post">{result.draft.body}</pre>
                <a href="#/drafts">到「草稿審核」處理 →</a></div>)
            : <p data-testid="import-nodraft" className="muted">沒有產生草稿：只有「明確在求助、相關、且沒有安全疑慮」的貼文才會備草稿，或此專案為只觀察模式。</p>}
        </Card>
      )}
      <Async loading={projects.loading} error={projects.error} onRetry={projects.reload}>{null}</Async>
    </div>
  );
}
