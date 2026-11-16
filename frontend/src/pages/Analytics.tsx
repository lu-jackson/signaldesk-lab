import { useState } from "react";
import { useApi, post, fmt, type Rec } from "../api";
import { ActionButton, Async, Card, Notice } from "../ui";

const RANGES: [string, number][] = [["近 1 天", 1], ["近 3 天", 3], ["近 7 天", 7], ["近 14 天", 14]];
const iso = (d: Date) => d.toISOString().replace(/\.\d+Z$/, "Z");

const n = (v: number | null | undefined) => (v === null || v === undefined ? "—" : String(v));

function Bars({ series, k, label }: { series: Rec[]; k: string; label: string }) {
  const max = Math.max(1, ...series.map((s) => s[k]));
  return (
    <div>
      <div className="small muted">{label}</div>
      <div className="bars" role="img" aria-label={label} data-testid={`bars-${k}`}>
        {series.map((s) => <div key={s.day} className="bar" title={`${s.day}: ${s[k]}`} style={{ height: `${(s[k] / max) * 100}%` }}><span>{s[k]}</span></div>)}
      </div>
      <div className="bars-x small muted" style={{ display: "flex", gap: 6 }}>{series.map((s) => <span key={s.day} style={{ flex: 1, textAlign: "center" }}>{s.day.slice(5)}</span>)}</div>
    </div>
  );
}

export default function Analytics() {
  const [days, setDays] = useState(7);
  // to 取「下一個整分鐘」：半開區間 [from, to) 才包含剛剛發生的點擊
  const end = new Date(); end.setUTCSeconds(0, 0); end.setUTCMinutes(end.getUTCMinutes() + 1);
  const start = new Date(end.getTime() - days * 86400000);
  const q = `from=${iso(start)}&to=${iso(end)}`;
  const s = useApi<Rec>(`/api/analytics/summary?${q}`);
  const eng = useApi<Rec>(`/api/analytics/engagement?${q}`);
  const links = useApi<Rec>("/api/links");
  const [label, setLabel] = useState("");
  const [dest, setDest] = useState("http://127.0.0.1:8000/demo-landing");
  return (
    <>
      <h2>連結與分析</h2>
      <Notice>數字皆來自本機模擬或合成資料。「模擬送出」不是真實送達；沒有已讀與成交資料；unique 只是用隨機 session cookie 的估算。</Notice>
      <div className="row">{RANGES.map(([l, d]) => <button key={d} className={days === d ? "primary" : ""} data-testid={`range-${d}`} onClick={() => setDays(d)}>{l}</button>)}
        <button onClick={() => { s.reload(); eng.reload(); links.reload(); }}>重新整理</button></div>
      <Async loading={s.loading} error={s.error} onRetry={s.reload}>
        {s.data && (<>
          <div className="small muted" data-testid="period">期間（UTC，半開區間 [from, to)）：{fmt(s.data.period.from)} → {fmt(s.data.period.to)}　更新 {fmt(s.data.generated_at)}</div>
          {!s.data.has_data && <Notice>這段期間沒有任何投遞或點擊資料（不是 0%，而是沒有資料）。</Notice>}
          <div className="grid" data-testid="analytics-cards">
            <div className="metric"><div className="d">API accepted（模擬）</div><div className="v" data-testid="card-accepted">{s.data.api_accepted}</div></div>
            <div className="metric"><div className="d">simulated sent</div><div className="v" data-testid="card-sent">{s.data.simulated_sent}</div></div>
            <div className="metric"><div className="d">點擊（不含 bot）</div><div className="v" data-testid="card-clicks">{s.data.clicks}</div><div className="d">bot {s.data.bot_clicks}，其中合成 {s.data.synthetic_clicks}</div></div>
            <div className="metric"><div className="d">estimated unique</div><div className="v" data-testid="card-unique">{s.data.estimated_unique}</div></div>
            <div className="metric"><div className="d">點擊 / 模擬送出</div><div className="v" data-testid="card-rate">{n(s.data.click_per_simulated_send)}</div><div className="d">分母：{s.data.denominators.click_per_simulated_send}</div></div>
          </div>
          <Card title="每日點擊（與上方卡片同一份資料）"><Bars series={s.data.series} k="clicks" label="clicks" /><Bars series={s.data.series} k="estimated_unique" label="estimated unique" /></Card>
          <Card title="裝置（標示：種子資料為合成）">{s.data.devices.length === 0 ? "沒有資料" : s.data.devices.map((d: Rec) => <span key={d.device} className="badge">{d.device}: {d.c}{d.synthetic ? "（含合成）" : ""}</span>)}</Card>
        </>)}
      </Async>
      <Card title="貼文監測（固定 seed 合成 engagement，非即時平台資料）">
        <Async loading={eng.loading} error={eng.error} onRetry={eng.reload} empty={eng.data?.items.length === 0 && "沒有資料"}>
          {eng.data && <Bars series={eng.data.items.map((i: Rec) => ({ day: i.day, impressions: i.impressions }))} k="impressions" label="impressions（合成）" />}
        </Async>
      </Card>
      <Card title="追蹤連結">
        <Async loading={links.loading} error={links.error} onRetry={links.reload}>
          <table><thead><tr><th>名稱</th><th>短連結</th><th>目的地（預先驗證）</th><th>點擊</th><th>unique</th></tr></thead>
            <tbody>{links.data?.items.map((l: Rec) => <tr key={l.id}><td>{l.label}</td><td><a href={l.short_url} target="_blank" rel="noreferrer">{l.short_url}</a></td><td className="small">{l.destination}</td><td>{l.clicks}</td><td>{l.estimated_unique}</td></tr>)}</tbody></table>
        </Async>
        <div className="row">
          <label>名稱<input data-testid="link-label" value={label} onChange={(e) => setLabel(e.target.value)} /></label>
          <label>目的網址<input data-testid="link-dest" style={{ minWidth: 300 }} value={dest} onChange={(e) => setDest(e.target.value)} /></label>
          <ActionButton testid="link-create" onClick={async () => { await post("/api/links", { label, destination: dest }); links.reload(); }}>建立連結</ActionButton>
        </div>
        <div className="small muted">只接受 http/https 且主機在允許清單（預設 127.0.0.1、localhost）；redirect 目標永遠取自這裡儲存的值。</div>
      </Card>
    </>
  );
}
