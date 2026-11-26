import { useState } from "react";
import { api } from "../api";
import { t as tr, trf } from "../i18n";

/* Golden Standard: korsning mot Altech med Prixel-import. Exakt typ+höjd+längd, annars närmaste KORTARE; H200 blir
 * Altech Konvektor H200 med väggkonsol (Ant = par per konvektor); V/H ger vänster/höger-RSK; effekt jämförs bara
 * inom samma temperaturprogram. Underlaget är ritningens radiatorer eller kundens lista (Excel). */

const MATCH: Record<string, string> = {
  EXACT_MATCH: "Exakt mått", NEAREST_SHORTER: "Närmaste kortare", H200_EXACT: "Konvektor H200 – exakt",
  H200_NEAREST_SHORTER: "Konvektor H200 – kortare", OVERRIDE: "Godkänd överstyrning", NO_MATCH: "Ingen träff",
};
const CLS: Record<string, string> = { EXACT_MATCH: "ok", H200_EXACT: "ok", NEAREST_SHORTER: "warn", H200_NEAREST_SHORTER: "warn", NO_MATCH: "error" };

function save(b: Blob, name: string) {
  const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = name; a.click();
}

export default function GoldenPanel({ drawingId }: { drawingId?: string }) {
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [project, setProject] = useState("");

  const run = async () => {
    setBusy(true); setErr("");
    try { setRes(drawingId ? await api.radiatorsGolden(drawingId) : await api.radiatorsGoldenList(file!, project || "Projekt")); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const xlsx = async () => {
    setErr("");
    try {
      const b: Blob = drawingId
        ? await (api as any).fetchBlob(`/api/drawings/${drawingId}/radiators/golden?fmt=xlsx`)
        : await api.radiatorsGoldenListXlsx(file!, project || "Projekt");
      save(b, res?.filename || "korsning.xlsx");
    } catch (e: any) { setErr(e.message); }
  };

  const s = res?.summary;
  return (
    <section className="card" style={{ marginTop: 12 }}>
      <h2 style={{ margin: 0 }}>{tr("Altech-korsning enligt Golden Standard med Prixel-import")}</h2>
      <p className="muted small" style={{ maxWidth: 820 }}>{tr("Samma typ, höjd och längd – annars närmaste kortare längd, aldrig längre, annan höjd eller annan typ. H200 blir Altech Konvektor H200 med väggkonsol (Ant = par per konvektor). V ger vänster-RSK, H höger-RSK, vändbar gemensamt RSK. Effekt jämförs bara inom samma temperaturprogram. Excel-filen har de nio bladen och en Prixel-import med enbart fasta värden.")}</p>
      {!drawingId && (
        <div className="row small" style={{ gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
          <label>{tr("Projekt")}<br /><input value={project} onChange={(e) => setProject(e.target.value)} placeholder="Explora" /></label>
          <label>{tr("Kundens radiatorlista (Excel med benämning och antal)")}<br />
            <input type="file" accept=".xlsx,.xlsm" onChange={(e) => { setFile(e.target.files?.[0] || null); setRes(null); }} /></label>
        </div>)}
      <div className="row small" style={{ gap: 8, marginTop: 8, flexWrap: "wrap" }}>
        <button className="small" disabled={busy || (!drawingId && !file)} onClick={run}>{busy ? tr("Korsar…") : tr("Korsa mot Altech")}</button>
        <button className="secondary small" disabled={!res || res.export_blocked} onClick={xlsx}
          title={res?.export_blocked ? tr("En blockerande QA-kontroll stoppar exporten") : ""}>{tr("Excel med Prixel-import")}</button>
      </div>
      {err && <p className="error small">{err}</p>}
      {res?.notice && <p className="warn small" style={{ marginTop: 8 }}>{tr(res.notice)}</p>}
      {s && (<>
        <div className="row small" style={{ gap: 6, marginTop: 8, flexWrap: "wrap" }}>
          <span className="badge">{trf("{0} radiatorer på {1} rader", s.radiators, s.radiator_rows)}</span>
          {Object.entries(s.by_match).map(([k, v]: any) => <span key={k} className={`badge ${CLS[k] || ""}`}>{tr(MATCH[k] || k)}: {v}</span>)}
          {s.excluded_accessories > 0 && <span className="badge">{trf("{0} tillbehörsrader exkluderade", s.excluded_accessories)}</span>}
          <span className="badge">{trf("{0} Prixel-rader", s.prixel_rows)}</span>
          {res.export_blocked && <span className="badge error">{tr("Exporten stoppad")}</span>}
        </div>
        <div className="row small" style={{ gap: 6, marginTop: 6, flexWrap: "wrap" }}>
          {res.qa.map((q: any) => <span key={q.id} className={`badge ${q.status === "PASS" ? "ok" : q.status === "FAIL" ? "error" : ""}`} title={q.comment}>QA {q.id} {tr(q.area)}: {q.status}</span>)}
        </div>
        <div className="tablewrap" style={{ marginTop: 8, overflow: "auto" }}>
          <table className="qty small">
            <thead><tr><th>{tr("Original")}</th><th className="num">{tr("Antal")}</th><th>H/V</th><th>{tr("Matchning")}</th><th>{tr("Altech")}</th>
              <th>RSK</th><th className="num">{tr("Δ längd")}</th><th className="num">{tr("Δ effekt W")}</th><th>{tr("Konsol")}</th><th>{tr("Avvikelser")}</th></tr></thead>
            <tbody>{res.results.filter((x: any) => x.category !== "accessory").map((x: any) => (
              <tr key={x.id}>
                <td className="lf-mono">{x.source_text}</td><td className="num">{x.qty}</td><td>{x.orientation === "VÄNDBAR" ? tr("vändbar") : x.orientation || "–"}</td>
                <td><span className={`badge small ${CLS[x.match_status] || ""}`}>{tr(MATCH[x.match_status] || x.match_status)}</span></td>
                <td>{x.selected ? `${x.selected.model} ${x.selected.height}×${x.selected.length}` : "–"}</td>
                <td className="lf-mono">{x.rsk || "–"}</td>
                <td className="num">{x.length_diff_mm ?? "–"}</td>
                <td className="num">{x.power_diff_w != null ? `${x.power_diff_w > 0 ? "+" : ""}${x.power_diff_w}` : x.technical_comparison_status === "TEMPERATURE_REGIME_MISMATCH" ? tr("ej jämförbar") : "–"}</td>
                <td>{x.bracket ? trf("{0} Ant {1}", x.bracket.rsk, x.bracket.pairs_per_convector) : ""}</td>
                <td className="small">{x.deviations.join(", ")}</td>
              </tr>))}</tbody>
          </table>
        </div>
        {res.deviations.length > 0 && (
          <details style={{ marginTop: 6 }}><summary className="small">{trf("Avvikelser ({0})", res.deviations.length)}</summary>
            <ul className="small">{res.deviations.map((d: any, i: number) => <li key={i}>{d.id} {d.source_text}: {d.code} {tr(d.text)}</li>)}</ul>
          </details>)}
        <p className="muted small">{trf("Regelversion {0} · filnamn {1}", res.rule_version, res.filename)}</p>
      </>)}
    </section>
  );
}
