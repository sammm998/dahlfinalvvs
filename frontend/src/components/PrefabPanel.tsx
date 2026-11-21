import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { t as tr, trf, locale } from "../i18n";

/* SmartHangers (Novipro prefab): rören i IFC-modellen blir prefabricerade upphängningar.
 *
 * Ladda upp modellen och ange takhöjd per våning (annars räknas den ur nästa våning minus bjälklaget, och källan
 * står på varje hängare). Granska i planvyn och tabellen: flytta, ändra pendel, kvittera flaggor. Godkänn offert,
 * konstruktion och produktion var för sig; produktionen frisläpps först när reglerna är verifierade. Etiketterna
 * har en QR-kod som öppnar hängaren i montageguiden. En ny modellrevision jämförs med den förra. */

const STATUS_COLOR: Record<string, string> = {
  "föreslagen": "#9aa3ad", "granskad": "#5b8def", "godkänd": "#2f6fdf", "producerad": "#c88a12",
  "packad": "#a86ad8", "levererad": "#0f9aa8", "monterad": "#1f9d55",
};
export const statusColor = (s: string, dev?: string) => dev ? "#d64545" : (STATUS_COLOR[s] || "#9aa3ad");
const STATUSES = ["föreslagen", "granskad", "godkänd", "producerad", "packad", "levererad", "monterad"];
const CALC_FIELDS: [string, string][] = [
  ["antal", "Antal hängare"], ["normtid_trad_h", "Normtid traditionellt (h/st)"], ["normtid_montage_h", "Montagetid SmartHanger (h/st)"],
  ["produktion_h", "Produktionstid (h/st)"], ["montor_kr_h", "Montör kr/h"], ["larling_kr_h", "Lärling kr/h"],
  ["material_trad_kr", "Material traditionellt (kr/st)"], ["material_prefab_kr", "Material prefab (kr/st)"],
  ["uppstart_kr", "Uppstart (kr)"], ["styckpris_kr", "Styckpris extern prefab (kr/st)"], ["frakt_kr", "Frakt (kr)"], ["paslag_pct", "Påslag %"],
];
const kr = (v: number | null | undefined) => v == null ? "–" : Math.round(v).toLocaleString(locale());

function PlanView({ set, storey, sel, onSel }: { set: any; storey: string; sel: string; onSel: (id: string) => void }) {
  const hs = set.hangers.filter((h: any) => h.storey === storey);
  const box = useMemo(() => {
    const xs = hs.map((h: any) => h.position.x), ys = hs.map((h: any) => h.position.y);
    if (!xs.length) return null;
    const pad = 1500;
    return { x0: Math.min(...xs) - pad, y0: Math.min(...ys) - pad, w: Math.max(...xs) - Math.min(...xs) + 2 * pad, h: Math.max(...ys) - Math.min(...ys) + 2 * pad };
  }, [hs]);
  if (!box) return null;
  const pipes = (set.pipes_preview || []).filter((p: any) => p.storey === storey);
  const r = Math.max(box.w, box.h) / 160;
  // y växer uppåt i modellen, nedåt på skärmen
  return (
    <svg viewBox={`${box.x0} ${-box.y0 - box.h} ${box.w} ${box.h}`} style={{ width: "100%", height: 360, background: "var(--panel, #f7f8fa)", borderRadius: 8 }}>
      {pipes.map((p: any) => <line key={p.id} x1={p.start[0]} y1={-p.start[1]} x2={p.end[0]} y2={-p.end[1]} stroke="#7aa7d9" strokeWidth={r / 2} />)}
      {hs.map((h: any) => (
        <g key={h.id} onClick={() => onSel(h.id)} style={{ cursor: "pointer" }}>
          <circle cx={h.position.x} cy={-h.position.y} r={h.id === sel ? r * 1.8 : r} fill={statusColor(h.status, h.deviation)}
            stroke={h.flags?.length ? "#d64545" : "#fff"} strokeWidth={r / 3} />
          {h.id === sel && <text x={h.position.x + r * 2} y={-h.position.y} fontSize={r * 3}>{h.id}</text>}
        </g>))}
    </svg>
  );
}

export default function PrefabPanel({ project }: { project: any }) {
  const [sets, setSets] = useState<any[]>([]);
  const [open, setOpen] = useState<any>(null);
  const [heights, setHeights] = useState<Record<string, string>>({});
  const [storey, setStorey] = useState("");
  const [sel, setSel] = useState("");
  const [onlyFlagged, setOnlyFlagged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [calc, setCalc] = useState<any>(null);
  const [calcIn, setCalcIn] = useState<Record<string, string>>({});
  const [rules, setRules] = useState<any>(null);
  const [rulesText, setRulesText] = useState("");
  const nav = useNavigate();
  const [drawings, setDrawings] = useState<any[]>([]);
  const [dwg, setDwg] = useState("");
  const [dwgSheets, setDwgSheets] = useState<Record<string, boolean>>({});
  const [ceil, setCeil] = useState("2700");
  const [drop, setDrop] = useState("300");
  const file = useRef<HTMLInputElement>(null);
  const revFile = useRef<HTMLInputElement>(null);

  const load = async () => setSets(await api.hangerSets(project.id));
  useEffect(() => { api.hangerDrawings(project.id).then((d: any[]) => {
    setDrawings(d);
    if (d.length) { setDwg(d[0].drawing_id); setDwgSheets(Object.fromEntries(d[0].sheets.map((x: any) => [x.name, x.usable && x.confirmed > 0]))); }
  }).catch(() => {}); }, [project.id]);
  const pickDwg = (id: string) => { setDwg(id); const d = drawings.find((x) => x.drawing_id === id); setDwgSheets(Object.fromEntries((d?.sheets || []).map((x: any) => [x.name, x.usable && x.confirmed > 0]))); };
  const fromDrawing = () => run(() => api.hangersFromDrawing(project.id, { drawing_id: dwg, ceiling_mm: Number(ceil) || null, drop_mm: Number(drop) || 300,
                                                                            sheets: Object.entries(dwgSheets).filter(([, v]) => v).map(([k]) => k) }));
  const curDwg = drawings.find((x) => x.drawing_id === dwg);
  useEffect(() => { load().catch((e) => setErr(e.message)); api.prefabRules().then((r: any) => { setRules(r); setRulesText(JSON.stringify(r, null, 2)); }).catch(() => {}); }, [project.id]);

  const show = (s: any) => {
    setOpen({ ...s, pipes_preview: s.pipes_preview || [] });
    if (s.storeys?.length && !s.storeys.find((x: any) => x.name === storey)) setStorey(s.hangers?.[0]?.storey || s.storeys[0].name);
    const h: Record<string, string> = {};
    Object.entries(s.settings?.manual_heights || {}).forEach(([k, v]) => { h[k] = String(v); });
    setHeights(h);
  };
  const run = async (f: () => Promise<any>) => {
    setBusy(true); setErr("");
    try { const r = await f(); if (r && r.hangers) show(r); await load(); return r; }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const create = () => { const f = file.current?.files?.[0]; if (f) run(() => api.createHangerSet(project.id, f, heights)); };
  const revise = () => { const f = revFile.current?.files?.[0]; if (f && open) run(() => api.reviseHangerSet(open.id, f)); };
  const patch = (hid: string, body: any) => run(async () => { await api.patchHanger(open.id, hid, body); return api.hangerSet(open.id); });
  const download = async (fmt: string, ids = "") => {
    const b: Blob = await (api as any).fetchBlob(`/api/hanger-sets/${open.id}/export.${fmt}${ids ? `?ids=${encodeURIComponent(ids)}` : ""}`);
    const a = document.createElement("a"); a.href = URL.createObjectURL(b);
    a.download = `smarthangers-rev${open.revision}${fmt === "pdf" ? "-etiketter" : ""}.${fmt}`; a.click();
  };
  const loadCalc = async (body?: any) => { const r = await api.hangerCalc(open.id, body); setCalc(r); };

  const storeys: any[] = open?.storeys || [];
  const rows = (open?.hangers || []).filter((h: any) => (!storey || h.storey === storey) && (!onlyFlagged || h.flags?.length));
  const cur = open?.hangers?.find((h: any) => h.id === sel);
  const ap = open?.approvals || {};

  return (
    <section className="card" style={{ marginTop: 18 }}>
      <h2 style={{ margin: 0 }}>{tr("SmartHangers – prefabricerade rörupphängningar")}</h2>
      <p className="muted small" style={{ maxWidth: 760 }}>
        {tr("Ladda upp VS-modellen (IFC). Rören läses med läge, dimension, material och system; parallella rör samlas i stråk och får takjärn, ensamma rör en pendel. Klamringsavstånd, placering, last och mått kommer ur en regeluppsättning som en tekniskt ansvarig verifierar. Varje hängare får ID, höjd med källa, materiallista och QR-etikett. Första versionen är ett beslutsstöd: allt granskas av en människa innan produktion.")}
      </p>
      {rules && !rules.verified && <p className="badge warn" style={{ display: "inline-block" }}>{trf("Regler v{0}: EXEMPELVÄRDEN – ej verifierade. Produktion kan inte frisläppas.", rules.version)}</p>}

      <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "flex-end", marginTop: 8 }}>
        <input type="file" accept=".ifc,.zip,.ifczip" id="prefab-ifc" className="file" ref={file} onChange={create} />
        <label className="pick" htmlFor="prefab-ifc">{busy ? tr("Läser modellen…") : tr("Ny uppsättning från IFC")}</label>
        {sets.map((s) => (
          <button key={s.id} className={`chip${open?.id === s.id ? " on" : ""}`} onClick={() => run(() => api.hangerSet(s.id))}>
            {s.name} · rev {s.revision} · {trf("{0} hängare", s.n)}{s.flagged ? ` · ${trf("{0} flaggade", s.flagged)}` : ""}
          </button>))}
      </div>
      {drawings.length > 0 && (
        <details className="settings" style={{ marginTop: 10 }}>
          <summary>{tr("Ingen IFC? Hängare ur de analyserade VS-ritningarna (PDF)")}</summary>
          <p className="muted small">{tr("Bekräftade rör på ritningen används med system, material (ur teckenförklaringen) och dimension. En planritning har ingen höjd: ange takhöjd och avstånd från tak till rörets underkant. Varje hängare märks som antagen höjd och flaggas för mätning på plats. Välj bara de blad som visar samma rör en gång (planen eller detaljen, inte båda).")}</p>
          <div className="row small" style={{ gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
            <label>{tr("Ritning")}<br /><select value={dwg} onChange={(e) => pickDwg(e.target.value)}>
              {drawings.map((d) => <option key={d.drawing_id} value={d.drawing_id}>{d.filename}</option>)}</select></label>
            <label>{tr("Takhöjd mm")}<br /><input style={{ width: 80 }} value={ceil} onChange={(e) => setCeil(e.target.value)} /></label>
            <label>{tr("Tak till rörets underkant mm")}<br /><input style={{ width: 80 }} value={drop} onChange={(e) => setDrop(e.target.value)} /></label>
            <button className="small" disabled={busy || !dwg} onClick={fromDrawing}>{tr("Skapa hängare ur ritningen")}</button>
          </div>
          <div className="small" style={{ marginTop: 6, columns: 3 }}>
            {(curDwg?.sheets || []).map((x: any) => (
              <label key={x.name} className="check" style={{ display: "block", opacity: x.usable ? 1 : 0.5 }}>
                <input type="checkbox" disabled={!x.usable || !x.confirmed} checked={!!dwgSheets[x.name]} onChange={(e) => setDwgSheets({ ...dwgSheets, [x.name]: e.target.checked })} />
                {x.name} {x.scale || ""} · {trf("{0} rör", x.confirmed)}{!x.usable ? ` · ${tr("ingen säker skala")}` : ""}
              </label>))}
          </div>
        </details>)}
      {err && <p className="error">{err}</p>}

      {open && (
        <div style={{ marginTop: 14 }}>
          <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <b>{open.name} · {tr("revision")} {open.revision}</b>
            <span className="badge">{trf("{0} hängare", open.n)}</span>
            {open.flagged > 0 && <span className="badge warn">{trf("{0} flaggade", open.flagged)}</span>}
            {Object.entries(open.status_counts || {}).map(([k, v]) => <span key={k} className="badge" style={{ borderLeft: `4px solid ${statusColor(k)}` }}>{tr(k)} {String(v)}</span>)}
            <span style={{ flex: 1 }} />
            <button className="secondary small" onClick={() => download("xlsx")}>{tr("Material, kapplan, packlista (Excel)")}</button>
            <button className="secondary small" onClick={() => download("pdf")}>{tr("Etiketter med QR (PDF)")}</button>
            <button className="secondary small" onClick={() => download("ifc")}>{tr("Hängarna som IFC")}</button>
            <button className="secondary small" disabled={!open.hangers?.length} onClick={() => nav(`/montage/${open.id}/${open.hangers[0].id}?läge=produktion`)}>{tr("Produktionsvy")}</button>
            <button className="secondary small" disabled={!open.hangers?.length} onClick={() => nav(`/montage/${open.id}/${open.hangers[0].id}`)}>{tr("Montageguide")}</button>
          </div>

          <div className="row small" style={{ gap: 8, flexWrap: "wrap", marginTop: 10, alignItems: "center" }}>
            <b>{tr("Godkännanden")}:</b>
            {(["offert", "konstruktion", "produktion"] as const).map((k) => (
              ap[k] ? <span key={k} className="badge ok">{tr(k)} ✓ {ap[k].by} {String(ap[k].at).slice(0, 10)}</span>
                : <button key={k} className="secondary small" disabled={busy} onClick={() => run(() => api.approveHangerSet(open.id, k))}>{trf("Godkänn {0}", tr(k))}</button>))}
          </div>

          <details className="settings" style={{ marginTop: 10 }}>
            <summary>{trf("Referenslinjer – vägg och grid ({0})", (open.settings?.references || []).length)}</summary>
            <p className="muted small">{tr("Montören mäter från en vägg eller gridlinje. Ange linjens läge i modellens koordinater (mm): x = en linje i y-led, y = en linje i x-led. Varje hängare får avståndet till närmaste linje.")}</p>
            {(open.settings?.references || []).map((l: any, i: number) => (
              <div key={i} className="small">{l.name} · {l.axis} = {l.value}{l.storey ? ` · ${l.storey}` : ""}{" "}
                <button className="secondary small" onClick={() => run(() => api.hangerReferences(open.id, open.settings.references.filter((_: any, j: number) => j !== i)))}>{tr("Ta bort")}</button></div>))}
            <form className="row small" style={{ gap: 6, marginTop: 6 }} onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget);
              run(() => api.hangerReferences(open.id, [...(open.settings?.references || []), { name: f.get("name"), axis: f.get("axis"), value: Number(f.get("value")), storey: f.get("storey") || undefined }])); }}>
              <input name="name" placeholder={tr("Namn, t.ex. Grid 3")} style={{ width: 130 }} required />
              <select name="axis"><option value="x">x</option><option value="y">y</option></select>
              <input name="value" placeholder={tr("läge mm")} style={{ width: 90 }} required />
              <select name="storey"><option value="">{tr("alla våningar")}</option>{storeys.map((s: any) => <option key={s.name} value={s.name}>{s.name}</option>)}</select>
              <button className="small">{tr("Lägg till")}</button>
            </form>
          </details>

          <details className="settings" style={{ marginTop: 10 }}>
            <summary>{tr("Takhöjder per våning")}</summary>
            <p className="muted small">{tr("Tom ruta: höjden räknas ur nästa våning minus bjälklaget. Absolut höjd i mm i modellens koordinater.")}</p>
            {storeys.map((s: any) => (
              <label key={s.name} className="small" style={{ marginRight: 12 }}>{s.name} <span className="muted">({tr("golv")} {s.elevation ?? "?"}; {tr(open.ceilings?.[s.name]?.source || "saknas")} {open.ceilings?.[s.name]?.z ?? ""})</span><br />
                <input style={{ width: 90 }} value={heights[s.name] || ""} onChange={(e) => setHeights({ ...heights, [s.name]: e.target.value })} /></label>))}
            <div><button className="small" disabled={busy} onClick={() => run(() => api.regenerateHangerSet(open.id, heights))}>{tr("Räkna om")}</button></div>
          </details>

          <div className="row" style={{ gap: 8, marginTop: 10, alignItems: "center", flexWrap: "wrap" }}>
            <select value={storey} onChange={(e) => setStorey(e.target.value)}>
              <option value="">{tr("alla våningar")}</option>
              {storeys.filter((s: any) => open.hangers.some((h: any) => h.storey === s.name)).map((s: any) => <option key={s.name} value={s.name}>{s.name}</option>)}
            </select>
            <label className="check small"><input type="checkbox" checked={onlyFlagged} onChange={(e) => setOnlyFlagged(e.target.checked)} />{tr("bara flaggade")}</label>
          </div>
          {storey && <PlanView set={open} storey={storey} sel={sel} onSel={setSel} />}

          {cur && (
            <div className="card" style={{ marginTop: 8, padding: 10 }}>
              <b>{cur.id}</b> · {tr(cur.kind)} · {cur.storey} · {cur.reference?.text}
              <div className="small muted">{tr("Höjdkälla")}: {tr(cur.height_source)} · {tr("placerad för")}: {tr(cur.placed_because)} · {tr("last")} {cur.load_kn} kN</div>
              <div className="row small" style={{ gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                <label>X <input style={{ width: 80 }} defaultValue={cur.position.x} onBlur={(e) => Number(e.target.value) !== cur.position.x && patch(cur.id, { position: { x: Number(e.target.value) } })} /></label>
                <label>Y <input style={{ width: 80 }} defaultValue={cur.position.y} onBlur={(e) => Number(e.target.value) !== cur.position.y && patch(cur.id, { position: { y: Number(e.target.value) } })} /></label>
                <label>{tr("Pendel mm")} <input style={{ width: 70 }} defaultValue={cur.rods?.[0]?.length_mm ?? ""} onBlur={(e) => e.target.value && Number(e.target.value) !== cur.rods?.[0]?.length_mm && patch(cur.id, { rod_length_mm: Number(e.target.value) })} /></label>
                {cur.takjarn && <label>{tr("Takjärn mm")} <input style={{ width: 70 }} defaultValue={cur.takjarn.length_mm} onBlur={(e) => Number(e.target.value) !== cur.takjarn.length_mm && patch(cur.id, { takjarn_length_mm: Number(e.target.value) })} /></label>}
                <select value={cur.status} onChange={(e) => patch(cur.id, { status: e.target.value })}>{STATUSES.map((s) => <option key={s} value={s}>{tr(s)}</option>)}</select>
                {cur.flags?.length > 0 && <button className="secondary small" onClick={() => patch(cur.id, { clear_flags: true, status: "granskad", comment: tr("flaggor granskade") })}>{tr("Granskad – kvittera flaggor")}</button>}
                <button className="secondary small" onClick={() => { if (confirm(tr("Ta bort hängaren?"))) run(async () => { await api.deleteHanger(open.id, cur.id); setSel(""); return api.hangerSet(open.id); }); }}>{tr("Ta bort")}</button>
              </div>
              {cur.flags?.map((f: string) => <div key={f} className="badge small warn" style={{ marginTop: 4, marginRight: 4 }}>{tr(f)}</div>)}
            </div>)}

          <div className="tablewrap" style={{ marginTop: 8, maxHeight: 420, overflow: "auto" }}>
            <table className="qty">
              <thead><tr><th>ID</th><th>{tr("Våning")}</th><th>{tr("Typ")}</th><th>{tr("Rör")}</th><th className="num">{tr("Pendel mm")}</th>
                <th className="num">{tr("Takjärn mm")}</th><th>{tr("Höjdkälla")}</th><th>{tr("Kolli")}</th><th>{tr("Status")}</th><th>{tr("Flaggor")}</th></tr></thead>
              <tbody>
                {rows.slice(0, 600).map((h: any) => (
                  <tr key={h.id} onClick={() => { setSel(h.id); if (!storey) setStorey(h.storey); }} style={{ cursor: "pointer", background: h.id === sel ? "var(--hl, #eef4ff)" : undefined }}>
                    <td className="lf-mono">{h.id}</td><td>{h.storey}</td><td>{tr(h.kind)}</td>
                    <td className="small">{h.pipes.map((p: any) => `${p.system || ""} ${p.material} ${p.dn || p.od}`).join(", ")}</td>
                    <td className="num">{h.rods?.[0]?.length_mm ?? "–"} {h.rods?.[0]?.size}</td>
                    <td className="num">{h.takjarn?.length_mm ?? "–"}</td>
                    <td className="small">{tr(h.height_source)}</td>
                    <td>{h.pack ? `${h.pack.kolli}/${h.pack.seq}` : "–"}</td>
                    <td><span className="badge small" style={{ borderLeft: `4px solid ${statusColor(h.status, h.deviation)}` }}>{tr(h.status)}{h.deviation ? ` · ${tr(h.deviation)}` : ""}</span></td>
                    <td className="small">{h.flags?.length ? <span className="badge small warn">{h.flags.length}</span> : ""}</td>
                  </tr>))}
              </tbody>
            </table>
          </div>
          {open.skipped?.length > 0 && <details className="small" style={{ marginTop: 6 }}><summary>{trf("{0} rör utan takhängare (stigare, korta eller utan geometri)", open.skipped.length)}</summary>
            {open.skipped.slice(0, 100).map((s: any, i: number) => <div key={i} className="muted">{s.name || s.pipe || s.id}: {tr(s.why)}</div>)}</details>}

          <details className="settings" style={{ marginTop: 12 }}>
            <summary>{tr("Ny modellrevision")}</summary>
            <p className="muted small">{tr("Rören jämförs med förra revisionen: nya, borttagna, flyttade och ändrade. Hängare vars rör inte ändrats behåller status. Berörda hängare som redan är producerade, packade, levererade eller monterade är kritiska.")}</p>
            <input type="file" accept=".ifc,.zip,.ifczip" id="prefab-rev" className="file" ref={revFile} onChange={revise} />
            <label className="pick small" htmlFor="prefab-rev">{tr("Ladda upp ny revision")}</label>
            {open.diff && (
              <div className="small" style={{ marginTop: 6 }}>
                <b>{trf("Revision {0} → {1}", open.diff.from_revision, open.diff.to_revision)}:</b>{" "}
                {trf("{0} nya, {1} borttagna, {2} flyttade, {3} ändrade rör; {4} berörda hängare", open.diff.added.length, open.diff.removed.length, open.diff.moved.length, open.diff.changed.length, open.diff.affected.length)}
                {open.diff.critical > 0 && <span className="badge warn" style={{ marginLeft: 6 }}>{trf("{0} kritiska", open.diff.critical)}</span>}
                {open.diff.affected.filter((a: any) => a.critical).map((a: any) => <div key={a.hanger} className="error">{a.hanger}: {tr(a.status)}</div>)}
              </div>)}
          </details>

          <details className="settings" style={{ marginTop: 8 }} onToggle={(e) => (e.target as HTMLDetailsElement).open && !calc && loadCalc()}>
            <summary>{tr("Lönsamhetskalkyl")}</summary>
            {calc && (<>
              <p className="badge warn" style={{ display: "inline-block" }}>{tr(calc.assumptions.label)}</p>
              <div className="row small" style={{ gap: 8, flexWrap: "wrap" }}>
                {CALC_FIELDS.map(([k, label]) => <label key={k}>{tr(label)}<br />
                  <input style={{ width: 90 }} value={calcIn[k] ?? String(calc.assumptions[k])} onChange={(e) => setCalcIn({ ...calcIn, [k]: e.target.value })} /></label>)}
              </div>
              <button className="small" style={{ marginTop: 6 }} onClick={() => loadCalc(Object.fromEntries(Object.entries(calcIn).map(([k, v]) => [k, Number(String(v).replace(",", "."))])))}>{tr("Räkna")}</button>
              <table className="qty" style={{ marginTop: 8, maxWidth: 560 }}><tbody>
                <tr><td>{tr("Traditionell kostnad")}</td><td className="num">{kr(calc.traditionell_kr)} kr</td></tr>
                <tr><td>{tr("Med SmartHangers")}</td><td className="num">{kr(calc.smarthangers_kr)} kr</td></tr>
                <tr><td><b>{tr("Besparing")}</b></td><td className="num"><b>{kr(calc.besparing_kr)} kr ({calc.besparing_pct} %)</b></td></tr>
                <tr><td>{tr("Frigjorda montörstimmar")}</td><td className="num">{calc.frigjorda_montorstimmar} h</td></tr>
                <tr><td>{tr("Kvarvarande lärlingstid")}</td><td className="num">{calc.larlingstimmar} h</td></tr>
                <tr><td>{tr("Fastprisandel")}</td><td className="num">{calc.fastprisandel_pct} %</td></tr>
                <tr><td>{tr("Lönsamhetsgräns")}</td><td className="num">{calc.lonsamhetsgrans_antal ? trf("{0} hängare", calc.lonsamhetsgrans_antal) : tr("ingen – besparingen per hängare är inte positiv")}</td></tr>
              </tbody></table>
              <div className="small muted" style={{ marginTop: 6 }}>{tr("Känslighet")}: {calc.kanslighet.map((s: any) => `${tr(s.variabel)} ${s.andring_pct > 0 ? "+" : ""}${s.andring_pct} %: ${kr(s.besparing_kr)} kr`).join(" · ")}</div>
            </>)}
          </details>
          <button className="secondary small" style={{ marginTop: 10 }} onClick={() => { if (confirm(tr("Ta bort hela uppsättningen?"))) run(async () => { await api.deleteHangerSet(open.id); setOpen(null); return null; }); }}>{tr("Ta bort uppsättningen")}</button>
        </div>)}

      <details className="settings" style={{ marginTop: 12 }}>
        <summary>{trf("Regeluppsättning v{0} ({1})", rules?.version ?? "–", rules?.verified ? tr("verifierad") : tr("ej verifierad"))}</summary>
        <p className="muted small">{tr("Klamringsavstånd, placering, last, hängargeometri, infästning, miljö och tolerans. Värdena ska komma från tillverkaren (t.ex. Bevego/Novipro) och verifieras av en tekniskt ansvarig. En ändring blir en ny version som är overifierad. Bara administratören kan spara och verifiera.")}</p>
        <textarea style={{ width: "100%", height: 260, fontFamily: "monospace", fontSize: 12 }} value={rulesText} onChange={(e) => setRulesText(e.target.value)} />
        <div className="row" style={{ gap: 8 }}>
          <button className="small" disabled={busy} onClick={() => run(async () => { const r = await api.putPrefabRules(JSON.parse(rulesText)); setRules(r); setRulesText(JSON.stringify(r, null, 2)); return null; })}>{tr("Spara som ny version")}</button>
          <button className="secondary small" disabled={busy} onClick={() => run(async () => { const r = await api.verifyPrefabRules(); setRules(r); setRulesText(JSON.stringify(r, null, 2)); return null; })}>{tr("Verifiera reglerna")}</button>
        </div>
      </details>
    </section>
  );
}
