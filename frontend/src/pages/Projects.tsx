import { useState } from "react";
import { useApi, post, put, fmt, type Rec } from "../api";
import { ActionButton, Async, Badge, Card, Notice, Pager, riskBadge } from "../ui";

const csv = (s: string) => s.split(/[,，\n]/).map((x) => x.trim()).filter(Boolean);

function ProjectForm({ project, brands, accounts, onSaved }: { project: Rec | null; brands: Rec[]; accounts: Rec[]; onSaved: () => void }) {
  const p = project;
  const [f, setF] = useState<Rec>({
    name: p?.name ?? "", brand_id: p?.brand_id ?? brands[0]?.id ?? "", account_id: p?.account_id ?? accounts[0]?.id ?? "", purpose: p?.purpose ?? "",
    keywords: (p?.keywords ?? []).join(", "), must_terms: (p?.must_terms ?? []).join(", "), exclude_terms: (p?.exclude_terms ?? []).join(", "),
    window_days: p?.window_days ?? 7, mode: p?.mode ?? "manual_review", daily_limit: p?.daily_limit ?? 5,
    schedule_enabled: p?.schedule_enabled ?? false, interval_seconds: p?.interval_seconds ?? 3600, enabled: p?.enabled ?? true,
  });
  const s = (k: string, v: any) => setF({ ...f, [k]: v });
  const save = async () => {
    const body = { ...f, keywords: csv(f.keywords), must_terms: csv(f.must_terms), exclude_terms: csv(f.exclude_terms), window_days: Number(f.window_days), daily_limit: Number(f.daily_limit), interval_seconds: Number(f.interval_seconds) };
    if (p) await put(`/api/projects/${p.id}`, body); else await post("/api/projects", body);
    onSaved();
  };
  return (
    <div>
      <div className="row">
        <label>專案名稱<input data-testid="proj-name" value={f.name} onChange={(e) => s("name", e.target.value)} /></label>
        <label>品牌<select data-testid="proj-brand" value={f.brand_id} onChange={(e) => s("brand_id", e.target.value)}>{brands.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
        <label>帳號<select data-testid="proj-account" value={f.account_id} onChange={(e) => s("account_id", e.target.value)}>{accounts.map((a) => <option key={a.id} value={a.id}>{a.platform}/{a.handle}</option>)}</select></label>
        <label>模式<select value={f.mode} onChange={(e) => s("mode", e.target.value)}><option value="manual_review">Manual Review</option><option value="observe_only">Observe Only</option><option value="auto_simulate">Auto Simulate</option></select></label>
      </div>
      <div className="row">
        <label>關鍵字（任一，逗號分隔）<input data-testid="proj-keywords" value={f.keywords} onChange={(e) => s("keywords", e.target.value)} /></label>
        <label>必要條件（全部）<input value={f.must_terms} onChange={(e) => s("must_terms", e.target.value)} /></label>
        <label>排除條件（任一）<input data-testid="proj-exclude" value={f.exclude_terms} onChange={(e) => s("exclude_terms", e.target.value)} /></label>
        <label>時間範圍（天）<input type="number" value={f.window_days} onChange={(e) => s("window_days", e.target.value)} /></label>
        <label>每日模擬上限<input type="number" value={f.daily_limit} onChange={(e) => s("daily_limit", e.target.value)} /></label>
      </div>
      <div className="row">
        <label>目的<input value={f.purpose} onChange={(e) => s("purpose", e.target.value)} /></label>
        <label><span>排程</span><input type="checkbox" checked={f.schedule_enabled} onChange={(e) => s("schedule_enabled", e.target.checked)} /></label>
        <label>間隔（秒）<input type="number" value={f.interval_seconds} onChange={(e) => s("interval_seconds", e.target.value)} /></label>
        <label><span>啟用</span><input type="checkbox" checked={f.enabled} onChange={(e) => s("enabled", e.target.checked)} /></label>
        <ActionButton kind="primary" testid="proj-save" onClick={save}>{p ? "儲存專案" : "建立專案"}</ActionButton>
      </div>
    </div>
  );
}

function Results({ runId }: { runId: string }) {
  const [page, setPage] = useState(1);
  const [onlyIncluded, setOnly] = useState(false);
  const r = useApi<Rec>(`/api/runs/${runId}/results?page=${page}&page_size=15${onlyIncluded ? "&included=true" : ""}`);
  return (
    <Async loading={r.loading} error={r.error} onRetry={r.reload} empty={r.data?.total === 0 && "沒有符合的貼文（範圍內沒有命中關鍵字）"}>
      <div className="row"><label><span>只看納入</span><input type="checkbox" checked={onlyIncluded} onChange={(e) => { setOnly(e.target.checked); setPage(1); }} /></label></div>
      <table data-testid="results"><thead><tr><th>原文（合成）</th><th>搜尋結果</th><th>意圖</th><th>風險</th><th>分類理由與證據</th><th>草稿</th></tr></thead>
        <tbody>{r.data?.items.map((e: Rec) => (
          <tr key={e.id} data-testid="result-row" data-included={e.included}>
            <td className="post">{e.post_text}<div className="small muted">@{e.author_handle}・{fmt(e.post_created_at)}</div></td>
            <td><Badge kind={e.included ? "ok" : "warn"}>{e.included ? "納入" : "排除"}</Badge><div className="small">{e.inclusion_reason}</div></td>
            <td>{e.intent ? <Badge>{e.intent}</Badge> : <span className="muted">未分類</span>}{e.relevant === 0 && <Badge kind="warn">不相關</Badge>}</td>
            <td>{e.included ? riskBadge(e.risk) : "—"}</td>
            <td className="small">{e.reason}{e.evidence && <div>證據：<span className="evidence">{e.evidence}</span></div>}{e.classify_error && <div className="inline-error">{e.classify_error}</div>}
              {e.flags?.length > 0 && e.flags.map((x: string) => <Badge key={x} kind="bad">{x}</Badge>)}</td>
            <td>{e.draft ? <a href="#/drafts">{e.draft.status}</a> : e.included && e.intent === "seeking" ? <span className="muted small">無（風險或模式）</span> : "—"}</td>
          </tr>))}</tbody></table>
      {r.data && <Pager page={page} total={r.data.total} size={15} onPage={setPage} />}
    </Async>
  );
}

export default function Projects() {
  const projects = useApi<Rec>("/api/projects");
  const brands = useApi<Rec>("/api/brands");
  const accounts = useApi<Rec>("/api/accounts");
  const [sel, setSel] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const runs = useApi<Rec>(sel ? `/api/projects/${sel}/runs?page_size=10` : null);
  const ready = brands.data && accounts.data && projects.data;
  const runNow = async (id: string, sync: boolean) => {
    const res = await post<Rec>(`/api/projects/${id}/run-now${sync ? "?sync=true" : ""}`, {}, { "Idempotency-Key": crypto.randomUUID() });
    if (res.run) { setRunId(res.run.id); setMsg(`完成：候選 ${res.run.candidates}、已分類 ${res.run.classified}、草稿 ${res.run.drafts}（狀態 ${res.run.status}${res.run.error ? "：" + res.run.error : ""}）`); }
    else setMsg(`已排入工作 ${res.job.id}（狀態 ${res.job.status}）。由背景 worker 執行，完成後在「最近執行」可看到。`);
    setSel(id); runs.reload(); projects.reload();
  };
  return (
    <>
      <h2>專案與搜尋</h2>
      <Notice>搜尋只是用關鍵字與時間查本機合成資料（不是向量語意搜尋）；「意圖」要靠後面的分類步驟判斷，兩者是分開的。</Notice>
      <Async loading={projects.loading || brands.loading || accounts.loading} error={projects.error || brands.error || accounts.error} onRetry={() => { projects.reload(); brands.reload(); accounts.reload(); }}>
        {ready && projects.data!.items.map((p: Rec) => (
          <Card key={p.id} title={<>{p.name} <Badge>{p.mode}</Badge>{!p.enabled && <Badge kind="warn">已停用</Badge>}</>}
            actions={<>
              <ActionButton kind="primary" testid={`run-sync-${p.id}`} onClick={() => runNow(p.id, true)}>立即執行並看結果</ActionButton>
              <ActionButton testid={`run-queue-${p.id}`} onClick={() => runNow(p.id, false)}>Run Now（排入工作）</ActionButton>
              <button onClick={() => { setSel(p.id); setRunId(null); }}>執行紀錄</button>
              <button onClick={() => setEditing(editing === p.id ? null : p.id)}>{editing === p.id ? "收合" : "編輯"}</button></>}>
            <div className="small">關鍵字：{p.keywords.join("、")}｜排除：{p.exclude_terms.join("、") || "—"}｜近 {p.window_days} 天｜每日模擬上限 {p.daily_limit}｜排程：{p.schedule_enabled ? `每 ${p.interval_seconds} 秒，下次 ${fmt(p.next_run_at)}` : "關閉"}</div>
            {editing === p.id && <ProjectForm project={p} brands={brands.data!.items} accounts={accounts.data!.items} onSaved={() => { projects.reload(); setEditing(null); }} />}
          </Card>
        ))}
        {ready && <Card title="新增專案"><ProjectForm project={null} brands={brands.data!.items} accounts={accounts.data!.items} onSaved={projects.reload} /></Card>}
      </Async>
      {msg && <Notice><span data-testid="run-msg">{msg}</span></Notice>}
      {sel && (
        <Card title="最近執行紀錄" actions={<button onClick={runs.reload}>重新整理</button>}>
          <Async loading={runs.loading} error={runs.error} onRetry={runs.reload} empty={runs.data?.total === 0 && "尚無執行"}>
            <table><thead><tr><th>開始</th><th>觸發</th><th>狀態</th><th>候選</th><th>分類</th><th>草稿</th><th>品牌版本</th><th /></tr></thead>
              <tbody>{runs.data?.items.map((r: Rec) => (
                <tr key={r.id}><td>{fmt(r.started_at)}</td><td>{r.trigger}</td><td>{r.status}{r.error && <div className="inline-error">{r.error}</div>}</td><td>{r.candidates}</td><td>{r.classified}</td><td>{r.drafts}</td><td>v{r.brand_version}</td>
                  <td><button onClick={() => setRunId(r.id)}>看結果</button></td></tr>))}</tbody></table>
          </Async>
        </Card>
      )}
      {runId && <Card title={`執行結果 ${runId}`}><Results runId={runId} /></Card>}
    </>
  );
}
