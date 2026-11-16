import { useApi, patch, fmt, type Rec } from "../api";
import { Async, Badge, Card, Notice } from "../ui";

export default function Settings() {
  const s = useApi<Rec>("/api/settings");
  const u = useApi<Rec>("/api/usage");
  const set = async (b: Rec) => { await patch("/api/settings", b); s.reload(); };
  const c = s.data;
  return (
    <>
      <h2>設定與用量</h2>
      <Async loading={s.loading} error={s.error} onRetry={s.reload}>
        {c && (<>
          <Card title="三個獨立開關（不會一個 LIVE 全開）">
            <div className="row">
              <label>資料來源 SOCIAL_SOURCE<select data-testid="set-social" value={c.social_source} onChange={(e) => set({ social_source: e.target.value }).catch((er) => alert(er.message))}>
                <option value="demo">demo（合成資料）</option><option value="threads_readonly">threads_readonly（唯讀）</option></select></label>
              <label>AI AI_PROVIDER<select data-testid="set-ai" value={c.ai_provider} onChange={(e) => set({ ai_provider: e.target.value }).catch((er) => alert(er.message))}>
                <option value="demo">demo（規則／模板）</option><option value="anthropic">anthropic（Live）</option></select></label>
              <label>投遞 DELIVERY_MODE<input disabled value={c.delivery_mode} /></label>
            </div>
            <div className="small">
              Anthropic：{c.anthropic_configured ? <Badge kind="ok">已配置（model: {c.anthropic_model}）</Badge> : <Badge kind="warn">未配置（需 .env 的 ANTHROPIC_API_KEY 與 ANTHROPIC_MODEL）</Badge>}
              Threads 唯讀：{c.threads_configured ? <Badge kind="ok">token 已配置（未實測）</Badge> : <Badge kind="warn">未配置／未實測</Badge>}
            </div>
            <Notice>選了 Live 但沒配置時，分類與助手會顯示錯誤，不會自動改回 Demo。API key 只存在後端環境變數，前端只看得到「已配置」。投遞永遠只是本機模擬。</Notice>
          </Card>
        </>)}
      </Async>
      <Card title="示例用量帳本（虛擬 units，無現金價值）">
        <Async loading={u.loading} error={u.error} onRetry={u.reload}>
          {u.data && (<>
            <div data-testid="balance">可用 {u.data.balance.available}｜起始 {u.data.balance.granted}｜已使用 {u.data.balance.settled}｜進行中保留 {u.data.balance.in_flight}｜已釋放 {u.data.balance.released}</div>
            <div className="small muted">示例費率：{Object.entries(u.data.rates).map(([k, v]) => `${k}=${v}`).join("、")}。{u.data.balance.unit_note}</div>
            <table><thead><tr><th>時間</th><th>operation</th><th>類型</th><th>units</th><th>分類</th></tr></thead>
              <tbody>{u.data.entries.slice(0, 30).map((e: Rec) => <tr key={e.id}><td>{fmt(e.created_at)}</td><td className="small">{e.operation_id}</td><td>{e.entry_type}</td><td>{e.units}</td><td>{e.category}</td></tr>)}</tbody></table>
          </>)}
        </Async>
      </Card>
    </>
  );
}
