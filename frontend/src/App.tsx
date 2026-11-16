import { useEffect, useState, type ComponentType } from "react";
import { useApi, getTz } from "./api";
import Dashboard from "./pages/Dashboard";
import Brands from "./pages/Brands";
import Projects from "./pages/Projects";
import Drafts from "./pages/Drafts";
import Automations from "./pages/Automations";
import Leads from "./pages/Leads";
import PR from "./pages/PR";
import Analytics from "./pages/Analytics";
import Jobs from "./pages/Jobs";
import Assistant from "./pages/Assistant";
import Settings from "./pages/Settings";

const ROUTES: [string, string, ComponentType][] = [
  ["dashboard", "儀表板", Dashboard],
  ["brands", "品牌與帳號", Brands],
  ["projects", "專案與搜尋", Projects],
  ["drafts", "草稿審核", Drafts],
  ["automations", "留言與私訊模擬", Automations],
  ["leads", "名單", Leads],
  ["pr", "PR 風險", PR],
  ["analytics", "連結與分析", Analytics],
  ["jobs", "工作與事件", Jobs],
  ["assistant", "AI 助手", Assistant],
  ["settings", "設定與用量", Settings],
];

function readRoute(): string {
  return window.location.hash.replace(/^#\/?/, "").split("?")[0] || "dashboard";
}

export default function App() {
  const [route, setRoute] = useState(readRoute);
  useEffect(() => {
    const f = () => setRoute(readRoute());
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  const [dark, setDark] = useState(() => { try { return localStorage.getItem("theme") === "dark"; } catch { return false; } });
  const [tz, setTz] = useState(getTz());
  const caps = useApi<any>("/api/settings");
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    try { localStorage.setItem("theme", dark ? "dark" : "light"); } catch { /* ignore */ }
  }, [dark]);
  const Page = (ROUTES.find((r) => r[0] === route) ?? ROUTES[0])[2];
  const c = caps.data;
  return (
    <div className="shell">
      <nav aria-label="主選單">
        <div className="brandmark">SignalDesk <small>Lab</small></div>
        {ROUTES.map(([k, label]) => (
          <a key={k} href={`#/${k}`} className={route === k ? "active" : ""} data-testid={`nav-${k}`}>{label}</a>
        ))}
        <div className="spacer" />
        <label className="tzsel">時區
          <select value={tz} onChange={(e) => { try { localStorage.setItem("tz", e.target.value); } catch { /* ignore */ } setTz(e.target.value); }}>
            <option value="UTC">UTC</option><option value="Europe/London">Europe/London</option><option value="Asia/Taipei">Asia/Taipei</option>
          </select>
        </label>
        <button onClick={() => setDark(!dark)}>{dark ? "淺色" : "深色"}模式</button>
      </nav>
      <main key={tz}>
        <div className="modebar" data-testid="modebar">
          {c ? (<>
            <span>AI：<b>{c.labels.ai}</b></span><span>資料來源：<b>{c.labels.social}</b></span><span>投遞：<b>{c.labels.delivery}</b></span>
          </>) : <span>讀取模式中…</span>}
        </div>
        {c?.public_demo && <div className="notice" data-testid="public-banner">公開展示站：資料為合成、投遞皆為模擬；寫入操作僅限沙盒且有限流，資料會定期重置。完整功能請在本機執行（見 GitHub README）。</div>}
        <Page />
      </main>
    </div>
  );
}
