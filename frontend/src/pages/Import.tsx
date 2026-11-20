import { useState } from "react";
import { useApi, post, type Rec } from "../api";
import { ActionButton, Async, Badge, Card, Notice, riskBadge } from "../ui";

const PLATFORMS = ["threads", "x", "instagram", "facebook"];

const SAMPLE = "內容,平台,作者,網址\n想找微積分筆記，期末快到了求推薦,threads,,https://example.com/post1\n";

// CSV 批次匯入：第 1 列為標題列（至少要有「內容」欄；平台、作者、網址可有可無），每次最多 50 列。
function CsvImport({ projectId, onProject, items }: { projectId: string; onProject: (id: string) => void; items: Rec[] }) {
  const [csv, setCsv] = useState("");
  const [platform, setPlatform] = useState("threads");
  const [res, setRes] = useState<Rec | null>(null);
  const loadFile = async (file: File | undefined) => {
    if (!file) return;
    if (file.size > 250_000) { alert("檔案超過 250 KB，請分批匯入"); return; }
    setCsv(await file.text());
  };
  const submit = async () => { setRes(null); setRes(await post("/api/posts/import-csv", { project_id: projectId, csv_text: csv, platform })); };
  const template = "data:text/csv;charset=utf-8," + encodeURIComponent("\ufeff" + SAMPLE);
  return (
    <Card title="批次匯入（CSV，每次最多 50 列）">
      <p className="small muted">
        第 1 列要是標題列，至少有「內容」欄（也可寫 text、貼文）；「平台」「作者」「網址」可有可無。用 Excel 或 Google 試算表存成 CSV（UTF-8）即可。
        <a href={template} download="signaldesk-import-template.csv"> 下載範本</a>
      </p>
      <div className="row">
        <label>用哪個專案判斷
          <select data-testid="csv-project" value={projectId} onChange={(e) => onProject(e.target.value)}>{items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
        </label>
        <label>沒填平台時使用
          <select data-testid="csv-platform" value={platform} onChange={(e) => setPlatform(e.target.value)}>{PLATFORMS.map((p) => <option key={p}>{p}</option>)}</select>
        </label>
        <label>選擇 CSV 檔<input data-testid="csv-file" type="file" accept=".csv,text/csv" onChange={(e) => loadFile(e.target.files?.[0])} /></label>
      </div>
      <label>或直接貼上 CSV 文字
        <textarea data-testid="csv-text" rows={6} value={csv} onChange={(e) => setCsv(e.target.value)} placeholder={SAMPLE} />
      </label>
      <div className="row"><ActionButton kind="primary" testid="csv-submit" disabled={!csv.trim() || !projectId} onClick={submit}>批次分析並備草稿</ActionButton></div>
      {res && (
        <div data-testid="csv-result">
          <p>處理 {res.rows_processed} 列：新增 <b>{res.imported}</b>、重複 {res.duplicates}、產生草稿 <b>{res.drafts}</b>、有問題 <b>{res.errors.length}</b>。
            <span className="muted"> 草稿都還沒送出，請到「草稿審核」處理。</span></p>
          {res.errors.length > 0 && (
            <div className="notice" data-testid="csv-errors"><b>以下列沒有匯入：</b>
              <ul>{res.errors.map((e: Rec, i: number) => <li key={i}>第 {e.row} 列：{e.reason}</li>)}</ul></div>
          )}
          {res.results.length > 0 && (
            <table data-testid="csv-table"><thead><tr><th>列</th><th>內容</th><th>意圖</th><th>風險</th><th>草稿</th></tr></thead>
              <tbody>{res.results.map((r: Rec) => (
                <tr key={r.row}><td>{r.row}</td><td className="post">{r.text}{r.duplicate && <Badge>重複</Badge>}</td><td><Badge>{r.intent ?? "—"}</Badge></td>
                  <td>{riskBadge(r.risk)}{(r.flags ?? []).map((x: string) => <Badge key={x} kind="warn">{x}</Badge>)}</td><td>{r.draft_id ? "有" : "—"}</td></tr>
              ))}</tbody></table>
          )}
          {res.drafts > 0 && <p><a href="#/drafts">到「草稿審核」處理 →</a></p>}
        </div>
      )}
    </Card>
  );
}

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
      <CsvImport projectId={pid} onProject={(id) => s("project_id", id)} items={items} />
      <Async loading={projects.loading} error={projects.error} onRetry={projects.reload}>{null}</Async>
    </div>
  );
}
