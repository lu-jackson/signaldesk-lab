import { useApi, fmt, type Rec } from "../api";
import { Async, Card, Notice } from "../ui";

export default function Dashboard() {
  const { data, error, loading, reload } = useApi<Rec>("/api/dashboard");
  return (
    <>
      <h2>儀表板</h2>
      <Async loading={loading} error={error} onRetry={reload}>
        {data && (<>
          <Notice>{data.period_note}。更新時間：{fmt(data.updated_at)}
            <button onClick={reload}>重新整理</button></Notice>
          {!data.worker.alive && <Notice>背景 worker 尚未執行：Run Now 與投遞工作會停在 queued。請用 <code>scripts/dev</code> 啟動，或另開終端機執行 <code>python -m app.worker</code>。</Notice>}
          <div className="grid" data-testid="metrics">
            {Object.entries(data.metrics).map(([k, m]: [string, any]) => (
              <a key={k} className="metric" href={`#${m.link}`} data-testid={`metric-${k}`}>
                <div className="d">{m.label}</div>
                <div className="v">{m.value}</div>
                <div className="d">分母：{m.of}（全部）</div>
              </a>
            ))}
          </div>
          <Card title="最近執行">
            {data.recent_runs.length === 0 ? <div className="state">尚無執行紀錄。到「專案與搜尋」按 Run Now。</div> : (
              <table><thead><tr><th>專案</th><th>狀態</th><th>候選</th><th>已分類</th><th>草稿</th><th>開始</th></tr></thead>
                <tbody>{data.recent_runs.map((r: Rec) => (
                  <tr key={r.id}><td>{r.project_name}</td><td>{r.status}</td><td>{r.candidates}</td><td>{r.classified}</td><td>{r.drafts}</td><td>{fmt(r.started_at)}</td></tr>
                ))}</tbody></table>
            )}
          </Card>
          <Card title="工作佇列">
            {Object.entries(data.jobs).map(([k, v]) => <span key={k} className="badge">{k}: {String(v)}</span>)}
            <div className="small muted">Worker：{data.worker.alive ? `執行中（pid ${data.worker.pid}）` : "未執行"}</div>
          </Card>
          <Card title="示例用量（虛擬 units，無現金價值）">
            可用 {data.usage.available} ／ 起始 {data.usage.granted}；進行中保留 {data.usage.in_flight}；已使用 {data.usage.settled}
          </Card>
        </>)}
      </Async>
    </>
  );
}
