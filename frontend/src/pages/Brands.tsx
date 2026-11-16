import { useState } from "react";
import { useApi, post, put, type Rec } from "../api";
import { ActionButton, Async, Card, Notice } from "../ui";

const EMPTY = { name: "", data: { intro: "", products: [], audience: "", service_area: "", tone: "", faq: [], facts: [], forbidden: [], cta: "" } as Rec };
const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);

function BrandForm({ brand, onSaved }: { brand: Rec | null; onSaved: () => void }) {
  const init = brand ?? EMPTY;
  const [name, setName] = useState<string>(init.name);
  const [d, setD] = useState<Rec>({ ...init.data, faqText: (init.data.faq ?? []).map((f: Rec) => `${f.q}｜${f.a}`).join("\n") });
  const set = (k: string, v: any) => setD({ ...d, [k]: v });
  const save = async () => {
    const data = { intro: d.intro, audience: d.audience, service_area: d.service_area, tone: d.tone, cta: d.cta,
      products: Array.isArray(d.products) ? d.products : lines(d.products), facts: Array.isArray(d.facts) ? d.facts : lines(d.facts),
      forbidden: Array.isArray(d.forbidden) ? d.forbidden : lines(d.forbidden),
      faq: lines(d.faqText).map((l) => { const [q, ...a] = l.split("｜"); return { q, a: a.join("｜") }; }) };
    if (brand) await put(`/api/brands/${brand.id}`, { name, data }); else await post("/api/brands", { name, data });
    onSaved();
  };
  const L = (v: any) => (Array.isArray(v) ? v.join("\n") : v);
  return (
    <div>
      <div className="row"><label>品牌名稱<input data-testid="brand-name" value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label>語氣<input value={d.tone} onChange={(e) => set("tone", e.target.value)} /></label>
        <label>受眾<input value={d.audience} onChange={(e) => set("audience", e.target.value)} /></label>
        <label>服務範圍<input value={d.service_area} onChange={(e) => set("service_area", e.target.value)} /></label></div>
      <label>介紹<textarea value={d.intro} onChange={(e) => set("intro", e.target.value)} /></label>
      <div className="row">
        <label>產品（每行一項）<textarea value={L(d.products)} onChange={(e) => set("products", e.target.value)} /></label>
        <label>可確認事實（草稿只能引用這些）<textarea data-testid="brand-facts" value={L(d.facts)} onChange={(e) => set("facts", e.target.value)} /></label>
        <label>不可承諾事項<textarea value={L(d.forbidden)} onChange={(e) => set("forbidden", e.target.value)} /></label>
        <label>FAQ（每行：問｜答）<textarea value={d.faqText} onChange={(e) => set("faqText", e.target.value)} /></label>
      </div>
      <label>CTA<input data-testid="brand-cta" style={{ width: "100%" }} value={d.cta} onChange={(e) => set("cta", e.target.value)} /></label>
      <div className="row"><ActionButton kind="primary" testid="brand-save" onClick={save}>{brand ? "儲存（產生新版本）" : "建立品牌"}</ActionButton></div>
    </div>
  );
}

export default function Brands() {
  const brands = useApi<Rec>("/api/brands");
  const accounts = useApi<Rec>("/api/accounts");
  const [editing, setEditing] = useState<string | null>(null);
  const [handle, setHandle] = useState("demo_");
  const [platform, setPlatform] = useState("threads");
  const [dn, setDn] = useState("");
  const [brandId, setBrandId] = useState("");
  return (
    <>
      <h2>品牌與帳號</h2>
      <Notice>所有品牌與帳號皆為虛構；帳號 handle 必須以 <code>demo_</code> 開頭。</Notice>
      <Async loading={brands.loading} error={brands.error} onRetry={brands.reload} empty={brands.data?.items.length === 0 && "尚無品牌"}>
        {brands.data?.items.map((b: Rec) => (
          <Card key={b.id} title={<>{b.name} <span className="badge" data-testid={`brand-version-${b.id}`}>v{b.current_version}</span></>}
            actions={<button onClick={() => setEditing(editing === b.id ? null : b.id)}>{editing === b.id ? "收合" : "編輯"}</button>}>
            {editing === b.id ? <BrandForm brand={b} onSaved={() => { brands.reload(); setEditing(null); }} /> : (
              <div className="small">{b.data.intro}<br />事實 {b.data.facts.length} 條｜FAQ {b.data.faq.length} 條｜CTA：{b.data.cta}</div>)}
          </Card>
        ))}
      </Async>
      <Card title="新增品牌"><BrandForm brand={null} onSaved={brands.reload} /></Card>
      <Card title="Demo 社群帳號">
        <Async loading={accounts.loading} error={accounts.error} onRetry={accounts.reload}>
          <table><thead><tr><th>平台</th><th>Handle</th><th>名稱</th><th>連接品牌</th></tr></thead>
            <tbody>{accounts.data?.items.map((a: Rec) => (
              <tr key={a.id}><td>{a.platform}</td><td>{a.handle}</td><td>{a.display_name}</td>
                <td>{brands.data?.items.find((b: Rec) => b.id === a.brand_id)?.name ?? "—"}</td></tr>))}</tbody></table>
        </Async>
        <div className="row">
          <label>平台<select value={platform} onChange={(e) => setPlatform(e.target.value)}>{["threads", "x", "instagram", "facebook"].map((p) => <option key={p}>{p}</option>)}</select></label>
          <label>Handle<input value={handle} onChange={(e) => setHandle(e.target.value)} /></label>
          <label>顯示名稱<input value={dn} onChange={(e) => setDn(e.target.value)} /></label>
          <label>品牌<select value={brandId} onChange={(e) => setBrandId(e.target.value)}><option value="">（無）</option>{brands.data?.items.map((b: Rec) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
          <ActionButton onClick={async () => { await post("/api/accounts", { platform, handle, display_name: dn, brand_id: brandId || null }); accounts.reload(); }}>新增帳號</ActionButton>
        </div>
      </Card>
    </>
  );
}
