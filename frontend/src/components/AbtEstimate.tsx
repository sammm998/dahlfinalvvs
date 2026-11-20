import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { locale, num, t as tr, trf } from "../i18n";

/* ABT 06 fas 3: nyckeltalen och schablonraderna.
 *
 * Nyckeltalen är dina egna: per enhet eller per m², med vad de ger – rör per system, artiklar ur Dahls katalog,
 * timmar. Inget här är ett branschvärde. Biblioteket är tomt tills du lägger in dina, och ett nyckeltal används i
 * ett projekt först när du har bekräftat det. Ändrar du ett bekräftat nyckeltal blir det ett utkast igen.
 *
 * En schablonrad är räknade enheter, lägenheter eller m² gånger ett valt nyckeltal, med riskpåslaget ovanpå. Raden
 * räknas fram varje gång och visar var den kommer ifrån. */

const BASIS: Record<string, string> = { per_enhet: "Per enhet", per_m2: "Per m²" };
const MEASURE: Record<string, string> = { LENGTH: "Längd (m)", COUNT: "Antal (st)", AREA: "Yta (m²)", VOLUME: "Volym (m³)" };
const STATUS: Record<string, string> = { utkast: "Utkast", bekraftad: "Bekräftad" };
const amount = (v: number) => v.toLocaleString(locale(), { maximumFractionDigits: 3 });   // 2,5 and 47 - no trailing zeros

type Output = { system: string; measure: string; value: number | string; unit?: string; article: { a: string; n: string; e: string } | null };
type Form = { id?: string; name: string; basis: string; unit_code: string; room_type: string; building_type: string;
  outputs: Output[]; hours: string; source: string };

const EMPTY: Form = { name: "", basis: "per_enhet", unit_code: "", room_type: "", building_type: "",
  outputs: [{ system: "", measure: "LENGTH", value: "", article: null }], hours: "", source: "" };

function ArticlePicker({ value, onChange }: { value: Output["article"]; onChange: (a: Output["article"]) => void }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<any[]>([]);
  const timer = useRef<any>(null);
  useEffect(() => {
    clearTimeout(timer.current);
    if (q.trim().length < 2) { setRows([]); return; }
    timer.current = setTimeout(() => {
      api.materials(new URLSearchParams({ q, limit: "8" }).toString()).then((d: any) => setRows(d.rows ?? [])).catch(() => setRows([]));
    }, 250);
    return () => clearTimeout(timer.current);
  }, [q]);
  if (value) return (
    <span className="small">{value.a} · {value.n} <button type="button" className="secondary small" onClick={() => onChange(null)} aria-label={tr("Ta bort artikeln")}>×</button></span>
  );
  return (
    <div style={{ position: "relative", minWidth: 0 }}>
      <input value={q} placeholder={tr("Sök artikel (valfritt)")} onChange={(e) => setQ(e.target.value)}
        style={{ width: "100%", minWidth: 0, boxSizing: "border-box" }} />
      {rows.length > 0 && (
        <div className="card" style={{ position: "absolute", zIndex: 5, left: 0, right: 0, padding: 4, maxHeight: 220, overflow: "auto" }}>
          {rows.map((r) => (
            <button type="button" key={r.a} className="secondary small" style={{ display: "block", width: "100%", textAlign: "left", marginBottom: 2 }}
              onClick={() => { onChange({ a: r.a, n: r.n, e: r.e }); setQ(""); setRows([]); }}>
              {r.a} · {r.n} ({r.e})
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function AbtKeyFigures({ project }: { project: any }) {
  const [lib, setLib] = useState<any[] | null>(null);
  const [est, setEst] = useState<any>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [err, setErr] = useState("");
  const load = async () => {
    try {
      const [l, s] = await Promise.all([api.keyFigures(), api.projectSchablon(project.id)]);
      setLib(l.key_figures); setEst(s);
    } catch (e: any) { setErr(e.message); }
  };
  useEffect(() => { load(); }, [project.id]);
  const chosen = new Set<string>(est?.key_figures ?? []);
  const act = async (f: () => Promise<any>) => { setErr(""); try { await f(); await load(); } catch (e: any) { setErr(e.message); } };
  const use = (kf: any, on: boolean) => {
    const ids = on ? [...chosen, kf.id] : [...chosen].filter((x) => x !== kf.id);
    setEst({ ...est, key_figures: ids });           // the box follows the hand; the server's answer follows
    return act(() => api.putEstimate(project.id, { key_figures: ids }));
  };
  const save = () => act(async () => {
    if (!form) return;
    const body = { name: form.name, basis: form.basis, unit_code: form.unit_code, room_type: form.room_type,
      building_type: form.building_type, source: form.source, hours: form.hours === "" ? null : Number(form.hours),
      outputs: form.outputs.filter((o) => o.system || o.value !== "" || o.article)
        .map((o) => ({ system: o.system, measure: o.measure, value: Number(o.value || 0), article: o.article })) };
    if (form.id) await api.updateKeyFigure(form.id, body); else await api.createKeyFigure(body);
    setForm(null);
  });
  const editOf = (kf: any): Form => ({ id: kf.id, name: kf.name, basis: kf.basis, unit_code: kf.unit_code, room_type: kf.room_type,
    building_type: kf.building_type, hours: kf.hours == null ? "" : String(kf.hours), source: kf.source,
    outputs: (kf.outputs.length ? kf.outputs : EMPTY.outputs).map((o: any) => ({ ...o })) });
  const setOut = (i: number, patch: Partial<Output>) => form && setForm({ ...form, outputs: form.outputs.map((o, j) => (j === i ? { ...o, ...patch } : o)) });
  const bases = est?.bases;
  const names = [...new Set<string>([...(bases?.units ?? []).flatMap((u: any) => [u.code, u.name].filter(Boolean)),
    ...(bases?.symbols ?? []).map((s: any) => s.name), ...(bases?.apartments ?? []).map((a: any) => a.type)])];
  return (
    <div style={{ marginTop: 12 }}>
      <p className="muted small">{tr("Nyckeltalen är dina egna: per enhet eller per m², med vad de ger – rör per system, artiklar ur Dahls katalog, timmar. Inget här är ett branschvärde. Ett nyckeltal används i projektet först när du har bekräftat det, och ett bekräftat nyckeltal som ändras blir ett utkast igen.")}</p>
      {err && <p className="error" role="alert">{err}</p>}
      <div className="row" style={{ gap: 8, margin: "8px 0" }}>
        <button className="small" onClick={() => setForm({ ...EMPTY, outputs: EMPTY.outputs.map((o) => ({ ...o })) })}>{tr("Nytt nyckeltal")}</button>
      </div>
      {form && (
        <div className="card" style={{ padding: 12, display: "grid", gap: 8, marginBottom: 12 }}>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <label className="small">{tr("Namn")}<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
            <label className="small">{tr("Grund")}
              <select value={form.basis} onChange={(e) => setForm({ ...form, basis: e.target.value })}>
                {Object.entries(BASIS).map(([k, v]) => <option key={k} value={k}>{tr(v)}</option>)}
              </select>
            </label>
            {form.basis === "per_enhet" ? (
              <label className="small">{tr("Enhet (kod, symbolnamn eller lägenhetstyp)")}
                <input list="abt-kf-units" value={form.unit_code} onChange={(e) => setForm({ ...form, unit_code: e.target.value })} />
              </label>
            ) : (
              <label className="small">{tr("Rumstyp (tom för alla rum)")}
                <input list="abt-kf-rooms" value={form.room_type} onChange={(e) => setForm({ ...form, room_type: e.target.value })} />
              </label>
            )}
            <label className="small">{tr("Timmar per enhet eller m²")}<input type="number" min={0} step="any" value={form.hours} onChange={(e) => setForm({ ...form, hours: e.target.value })} /></label>
          </div>
          <datalist id="abt-kf-units">{names.map((n) => <option key={n} value={n} />)}</datalist>
          <datalist id="abt-kf-rooms">{(bases?.room_names ?? []).map((n: string) => <option key={n} value={n} />)}</datalist>
          <div className="tablewrap">
            <table className="qty">
              <thead><tr><th>{tr("System eller beteckning")}</th><th>{tr("Mått")}</th><th className="num">{tr("Värde")}</th><th>{tr("Artikel")}</th><th></th></tr></thead>
              <tbody>{form.outputs.map((o, i) => (
                <tr key={i}>
                  <td><input value={o.system} placeholder="KV" onChange={(e) => setOut(i, { system: e.target.value })} /></td>
                  <td><select value={o.measure} onChange={(e) => setOut(i, { measure: e.target.value })}>
                    {Object.entries(MEASURE).map(([k, v]) => <option key={k} value={k}>{tr(v)}</option>)}</select></td>
                  <td className="num"><input type="number" min={0} step="any" value={o.value} style={{ width: 90 }} onChange={(e) => setOut(i, { value: e.target.value })} /></td>
                  <td style={{ minWidth: 220 }}><ArticlePicker value={o.article} onChange={(a) => setOut(i, { article: a })} /></td>
                  <td><button type="button" className="secondary small" onClick={() => setForm({ ...form, outputs: form.outputs.filter((_, j) => j !== i) })}>{tr("Ta bort")}</button></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button type="button" className="secondary small" onClick={() => setForm({ ...form, outputs: [...form.outputs, { system: "", measure: "LENGTH", value: "", article: null }] })}>{tr("Lägg till rad")}</button>
          </div>
          <label className="small" style={{ display: "grid", gap: 4 }}>{tr("Källa – var värdet kommer ifrån")}
            <input value={form.source} placeholder={tr("t.ex. eget utfall, projekt och år")} style={{ width: "100%", boxSizing: "border-box" }}
              onChange={(e) => setForm({ ...form, source: e.target.value })} />
          </label>
          <div className="row" style={{ gap: 8 }}>
            <button onClick={save} disabled={!form.name.trim()}>{tr("Spara som utkast")}</button>
            <button className="secondary" onClick={() => setForm(null)}>{tr("Avbryt")}</button>
          </div>
        </div>
      )}
      {lib && lib.length === 0 && !form && <p className="muted">{tr("Biblioteket är tomt. Lägg in dina egna nyckeltal – inga värden finns förifyllda.")}</p>}
      {lib && lib.length > 0 && (
        <div className="tablewrap">
          <table className="qty">
            <thead><tr><th>{tr("I projektet")}</th><th>{tr("Namn")}</th><th>{tr("Grund")}</th><th>{tr("Gäller")}</th><th>{tr("Ger")}</th><th>{tr("Status")}</th><th>{tr("Källa")}</th><th></th></tr></thead>
            <tbody>{lib.map((kf) => (
              <tr key={kf.id}>
                <td><input type="checkbox" checked={chosen.has(kf.id)} disabled={kf.status !== "bekraftad" && !chosen.has(kf.id)}
                  title={kf.status !== "bekraftad" ? tr("Bekräfta nyckeltalet först") : ""} aria-label={tr("Använd i projektet")}
                  onChange={(e) => use(kf, e.target.checked)} /></td>
                <td><b>{kf.name}</b></td>
                <td>{tr(BASIS[kf.basis] ?? kf.basis)}</td>
                <td>{kf.basis === "per_m2" ? (kf.room_type || tr("alla rum")) : kf.unit_code}</td>
                <td className="small">{kf.outputs.map((o: any) => `${o.system || "–"} ${amount(o.value)} ${o.unit}`).join(", ")}{kf.hours ? ` · ${amount(kf.hours)} h` : ""}</td>
                <td><span className={`badge ${kf.status === "bekraftad" ? "ok" : "warn"}`}>{tr(STATUS[kf.status] ?? kf.status)}</span></td>
                <td className="muted small">{kf.source}</td>
                <td className="row" style={{ gap: 4 }}>
                  {kf.status === "bekraftad"
                    ? <button className="secondary small" onClick={() => act(() => api.updateKeyFigure(kf.id, { status: "utkast" }))}>{tr("Gör till utkast")}</button>
                    : <button className="small" onClick={() => act(() => api.updateKeyFigure(kf.id, { status: "bekraftad" }))}>{tr("Bekräfta")}</button>}
                  <button className="secondary small" onClick={() => setForm(editOf(kf))}>{tr("Ändra")}</button>
                  <button className="secondary small" onClick={() => window.confirm(trf("Ta bort {0}?", kf.name)) && act(() => api.deleteKeyFigure(kf.id))}>{tr("Ta bort")}</button>
                </td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function AbtSchablon({ project }: { project: any }) {
  const [data, setData] = useState<any>(null);
  const [risk, setRisk] = useState<string | null>(null);
  const [lines, setLines] = useState<Record<string, string>>({});
  const [err, setErr] = useState("");
  const load = () => api.projectSchablon(project.id).then(setData).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, [project.id]);
  const put = async (body: any) => {
    setErr("");
    try { setData(await api.putEstimate(project.id, body)); } catch (e: any) { setErr(e.message); }
  };
  const csv = async () => {
    const b = await api.fetchBlob(`/api/projects/${project.id}/schablon.csv`);
    const a = document.createElement("a"); a.href = URL.createObjectURL(b);
    a.download = `${(project.name || "projekt").replace(/[^\wåäöÅÄÖ-]+/g, "_")}-schablon.csv`; a.click();
  };
  const rows: any[] = data?.rows ?? [];
  return (
    <div style={{ marginTop: 12 }}>
      <p className="muted small">{tr("En schablonrad är räknade enheter, lägenheter eller m² gånger ett valt nyckeltal, med riskpåslaget ovanpå. Raden räknas fram varje gång ur det som räknats och visar var den kommer ifrån. Påslaget gäller projektet; en rad kan få ett eget.")}</p>
      {err && <p className="error" role="alert">{err}</p>}
      {data && <>
        <div className="row" style={{ gap: 8, alignItems: "end", margin: "8px 0" }}>
          <label className="small">{tr("Riskpåslag för projektet, %")}
            <input type="number" step="any" value={risk ?? String(data.risk_pct)} style={{ width: 100 }} onChange={(e) => setRisk(e.target.value)} />
          </label>
          {risk !== null && <button className="small" onClick={() => { put({ risk_pct: Number(risk || 0) }); setRisk(null); }}>{tr("Spara")}</button>}
          <button className="secondary small" onClick={csv} disabled={rows.length === 0}>{tr("Exportera schablonraderna (CSV)")}</button>
        </div>
        {rows.length === 0 && <p className="muted">{tr("Inga schablonrader än. Bekräfta nyckeltal och välj dem för projektet i fliken Nyckeltal.")}</p>}
        {rows.length > 0 && <>
          <div className="kpi">
            <div className="card"><div className="v">{rows.length}</div><div className="l">{tr("Rader")}</div></div>
            <div className="card"><div className="v">{num(data.totals.hours, 1)}</div><div className="l">{tr("Timmar med risk")}</div></div>
            <div className="card"><div className="v">{rows.some((r) => r.cost != null) ? num(data.totals.cost, 0) : "–"}</div><div className="l">{tr("Materialkostnad netto, kr")}</div></div>
          </div>
          <div className="tablewrap" style={{ marginTop: 10 }}>
            <table className="qty">
              <thead><tr><th>{tr("Källtyp")}</th><th>{tr("Nyckeltal")}</th><th>{tr("System")}</th><th>{tr("Underlag")}</th><th className="num">{tr("Mängd")}</th><th className="num">{tr("Risk, %")}</th><th className="num">{tr("Med risk")}</th><th>{tr("Artikel")}</th><th className="num">{tr("Kostnad, kr")}</th></tr></thead>
              <tbody>{rows.map((r) => (
                <tr key={r.key}>
                  <td><span className="badge">{r.source_type}</span></td>
                  <td>{r.key_figure.name}<div className="muted small">{r.key_figure.source}</div></td>
                  <td>{r.system}</td>
                  <td className="small">{`${amount(r.basis_qty)} ${r.basis_unit} × ${amount(r.per)} ${r.unit} = ${amount(r.quantity)} ${r.unit}`}
                    <div className="muted small">{r.basis_from.join(" + ")}</div></td>
                  <td className="num">{num(r.quantity, 2)} {r.unit}</td>
                  <td className="num">
                    <input type="number" step="any" value={lines[r.key] ?? String(r.risk_pct)} style={{ width: 70 }} aria-label={tr("Radens riskpåslag")}
                      onChange={(e) => setLines({ ...lines, [r.key]: e.target.value })} />
                    {lines[r.key] !== undefined && <button className="small" onClick={() => { put({ line_risk: { [r.key]: Number(lines[r.key] || 0) } }); setLines({ ...lines, [r.key]: undefined as any }); }}>{tr("Spara")}</button>}
                    {r.own_risk && lines[r.key] === undefined && <button className="secondary small" title={tr("Använd projektets påslag")} onClick={() => put({ line_risk: { [r.key]: null } })}>↺</button>}
                  </td>
                  <td className="num"><b>{num(r.quantity_with_risk, 2)}</b> {r.unit}</td>
                  <td className="small">{r.article ? `${r.article.a} · ${r.article.n}` : "–"}</td>
                  <td className="num">{r.cost == null ? "–" : num(r.cost, 0)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </>}
      </>}
    </div>
  );
}
