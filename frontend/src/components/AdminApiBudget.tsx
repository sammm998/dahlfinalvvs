import { useEffect, useState } from "react";
import { t as tr, locale } from "../i18n";
import { api } from "../api";

/* Taket på vad tjänsten får lägga på språkmodeller (backend/app/api_budget.py): förbrukat sedan den senaste
 * nollställningen, vad som är kvar, taket och prislistan. När taket är nått låses AI för hela tjänsten och det står
 * att alla krediter för AI är förbrukade; läsning utan AI går som vanligt. */
const kr = (v: number | null | undefined) =>
  v == null ? "–" : `${v.toLocaleString(locale(), { maximumFractionDigits: 2 })} kr`;

export function ApiBudget() {
  const [b, setB] = useState<any>(null);
  const [err, setErr] = useState("");
  const [limit, setLimit] = useState("");
  const [rate, setRate] = useState("");
  const [prices, setPrices] = useState<Record<string, any>>({});
  const [saving, setSaving] = useState(false);
  const load = (r: any) => {
    setB(r); setLimit(String(r.limit_kr)); setRate(String(r.usd_sek)); setPrices(r.prices || {});
  };
  useEffect(() => { api.adm("api-budget").then(load).catch((e) => setErr(e.message)); }, []);
  if (err) return <p className="error">{err}</p>;
  if (!b) return <p className="muted">{tr("Laddar…")}</p>;

  const save = () => {
    setSaving(true); setErr("");
    const clean: Record<string, any> = {};
    for (const [name, p] of Object.entries(prices)) {
      clean[name] = { ...p, in: p.in === "" ? null : Number(p.in), out: p.out === "" ? null : Number(p.out),
        cached: p.cached === "" || p.cached == null ? null : Number(p.cached) };
    }
    api.admPut("api-budget", { limit_kr: Number(limit), usd_sek: Number(rate), prices: clean })
      .then(load).catch((e) => setErr(e.message)).finally(() => setSaving(false));
  };
  const reset = () => {
    if (!window.confirm(tr("Nollställa räkningen? Det som förbrukats står kvar i reskontran, men taket räknas från noll igen."))) return;
    api.admPost("api-budget/reset", {}).then(load).catch((e) => setErr(e.message));
  };
  const setPrice = (name: string, k: string, v: string) =>
    setPrices((ps) => ({ ...ps, [name]: { ...(ps[name] || {}), [k]: v } }));

  return (
    <>
      <div className="adm-stats">
        <div className={`adm-stat${b.exhausted ? " bad" : ""}`}>
          <div className="k">{tr("Förbrukat")}</div><div className="v">{kr(b.spent_kr)}</div>
          <div className="s">{b.reset_at ? `${tr("sedan")} ${String(b.reset_at).slice(0, 16).replace("T", " ")}` : tr("sedan start")}</div>
        </div>
        <div className="adm-stat"><div className="k">{tr("Kvar")}</div><div className="v">{kr(b.remaining_kr)}</div>
          <div className="s">{b.exhausted ? tr("Alla krediter för AI är förbrukade.") : tr("AI är öppen")}</div></div>
        <div className="adm-stat"><div className="k">{tr("Taket")}</div><div className="v">{kr(b.limit_kr)}</div>
          <div className="s">{tr("1 USD")} = {b.usd_sek} kr</div></div>
      </div>

      <section className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>{tr("Tak och växelkurs")}</h3>
        <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
          <label>{tr("Tak (kr)")} <input type="number" min={0} step={100} value={limit} onChange={(e) => setLimit(e.target.value)} /></label>
          <label>{tr("Kronor per USD")} <input type="number" min={0} step={0.01} value={rate} onChange={(e) => setRate(e.target.value)} /></label>
        </div>
        <h3>{tr("Prislista, USD per miljon tokens")}</h3>
        <p className="muted small">{tr("En modell utan pris får inte anropas: en kostnad som inte går att räkna kan inte hållas under taket.")}</p>
        <table className="tbl">
          <thead><tr><th>{tr("Modell")}</th><th>{tr("In")}</th><th>{tr("Cachat")}</th><th>{tr("Ut")}</th><th>{tr("Källa")}</th></tr></thead>
          <tbody>
            {Object.entries(prices).map(([name, p]: [string, any]) => (
              <tr key={name}>
                <td><code>{name}</code></td>
                {["in", "cached", "out"].map((k) => (
                  <td key={k}><input type="number" min={0} step={0.01} style={{ width: 90 }} value={p[k] ?? ""}
                    onChange={(e) => setPrice(name, k, e.target.value)} /></td>
                ))}
                <td className="muted small">{p.source} {p.date ? `(${p.date})` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="row" style={{ gap: 8, marginTop: 12 }}>
          <button className="btn" onClick={save} disabled={saving}>{saving ? tr("Sparar…") : tr("Spara")}</button>
          <button className="secondary" onClick={reset}>{tr("Nollställ räkningen")}</button>
        </div>
      </section>

      <section className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>{tr("Vad som kostat")}</h3>
        {b.by_source.length === 0 ? <p className="muted">{tr("Inga anrop ännu.")}</p> : (
          <table className="tbl">
            <thead><tr><th>{tr("Del")}</th><th>{tr("Modell")}</th><th>{tr("Anrop")}</th><th>{tr("Kostnad")}</th></tr></thead>
            <tbody>
              {b.by_source.map((r: any) => (
                <tr key={`${r.source}-${r.model}`}><td>{r.source}</td><td><code>{r.model}</code></td>
                  <td>{r.requests}</td><td>{kr(r.kr)}</td></tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="muted small" style={{ marginBottom: 0 }}>
          {tr("Röstassistentens samtal går direkt mellan webbläsaren och OpenAI och syns inte här; taket avgör bara om ett samtal får starta.")}
        </p>
      </section>
    </>
  );
}
