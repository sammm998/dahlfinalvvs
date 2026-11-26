import { Fragment, useEffect, useState } from "react";
import { api } from "../api";
import { t as tr, trf, locale } from "../i18n";
import GoldenPanel from "./GoldenPanel";

/* Radiatorerna på ritningen: varje etikett (TPv4 22-218 med 650W-57l/h-Kv0,25) räknad per hus, och korsad mot
 * Altech – exakt där Altech har storleken, annars närmaste modell som ger den projekterade effekten, med
 * skillnaden i effekt, längd och höjd och vad som ska kontrolleras. Priserna ur Dahls prisfil. */

const kr = (v: number | null | undefined) => v == null ? "–" : Math.round(v).toLocaleString(locale());
const unit = (p: any) => p ? (p.netto ?? p.brutto) : null;
const STATUS_CLASS: Record<string, string> = { exakt: "ok", "närmaste": "warn", "räcker inte": "error", saknas: "error" };

export default function RadiatorPanel({ drawingId, onZoom }: { drawingId: string; onZoom?: (bbox: number[]) => void }) {
  const [temps, setTemps] = useState("55/45/20");
  const [prefer, setPrefer] = useState(() => { try { return localStorage.getItem("vvs.rad.prefer") || "length"; } catch { return "length"; } });
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<string>("");

  const load = async (t = temps, p = prefer) => {
    setBusy(true); setErr("");
    try { setRes(await api.radiators(drawingId, t, p)); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  useEffect(() => { load(); }, [drawingId]);
  const xlsx = async () => {
    const b: Blob = await (api as any).fetchBlob(`/api/drawings/${drawingId}/radiators.xlsx?temps=${encodeURIComponent(temps)}&prefer=${prefer}`);
    const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = "radiatorer.xlsx"; a.click();
  };

  const s = res?.summary;
  return (<>
    <section className="card" style={{ marginTop: 12 }}>
      <h2 style={{ margin: 0 }}>{tr("Radiatorer och Altech-korsning")}</h2>
      <p className="muted small" style={{ maxWidth: 800 }}>{tr("Varje radiatoretikett på ritningen (t.ex. TPv4 22-218 med 650W-57l/h-Kv0,25) räknas per hus och korsas mot Altech. Finns samma typ, höjd och längd hos Altech och ger den den projekterade effekten är det en exakt motsvarighet; annars väljs närmaste modell som ger effekten – samma typ före kraftigare, och sedan efter valet nedan antingen samma längd (radiatorn blir högre) eller samma höjd (den blir längre), kortare före längre. Skillnaden i effekt, längd och höjd visas, liksom alternativen.")}</p>
      <div className="row small" style={{ gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
        <label>{tr("Temperaturer fram/retur/rum °C")}<br />
          <select value={temps} onChange={(e) => { setTemps(e.target.value); load(e.target.value, prefer); }}>
            {["55/45/20", "60/45/20", "50/40/20", "45/35/20", "70/40/20", "75/65/20"].map((t) => <option key={t} value={t}>{t}</option>)}
          </select></label>
        <label>{tr("Vid lucka i Altechs sortiment")}<br />
          <select value={prefer} onChange={(e) => { const v = e.target.value; setPrefer(v); try { localStorage.setItem("vvs.rad.prefer", v); } catch { /* privat fönster */ } load(temps, v); }}>
            <option value="length">{tr("Samma längd – högre radiator")}</option>
            <option value="height">{tr("Samma höjd – längre radiator")}</option>
          </select></label>
        <button className="secondary small" disabled={!s?.total} onClick={xlsx}>{tr("Excel: sammanställning, detaljlista, korsning")}</button>
        {busy && <span className="muted">{tr("Läser ritningen…")}</span>}
      </div>
      {err && <p className="error small">{err}</p>}
      {res && !s?.total && (
        <p className="muted small" style={{ marginTop: 8 }}>{res.no_text_pages?.length
          ? tr("Ritningen har ingen läsbar text (skannad bild) – radiatoretiketterna kan inte läsas. Ladda upp den ursprungliga PDF:en från CAD.")
          : tr("Inga radiatoretiketter hittades som text på ritningen (t.ex. TPv4 22-218, CV22-512, C22-300-1200). Syns beteckningarna ändå på ritningen är texten utritad som linjer vid PDF-utskriften och kan inte läsas – ladda upp en PDF utskriven med text, eller kundens radiatorlista som Excel under Kom igång.")}</p>)}
      {s?.total > 0 && (<>
        <div className="row small" style={{ gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          <span className="badge">{trf("{0} radiatorer", s.total)}</span>
          <span className="badge">{trf("{0} W projekterat", kr(s.w_total))}</span>
          {s.zones.filter(Boolean).map((z: string) => <span key={z} className="badge">{z}: {s.per_zone[z]}</span>)}
          {res.totals?.price_list
            ? <><span className="badge">{trf("Altech {0} kr", kr(res.totals.altech))}</span>
              {res.totals.prescribed_designations_with_price > 0
                ? <span className="badge" title={tr("Jämförelsen görs bara på de beteckningar där prisfilen har den föreskrivna modellen.")}>
                    {trf("Där föreskriven modell har pris ({0} av {1} beteckningar): föreskrivet {2} kr, Altech {3} kr", res.totals.prescribed_designations_with_price, res.totals.designations, kr(res.totals.prescribed), kr(res.totals.altech_same_designations))}</span>
                : <span className="badge">{tr("Föreskrivna modeller saknas i prisfilen – ingen prisjämförelse")}</span>}</>
            : <span className="badge warn">{tr("Ingen prisfil uppladdad – priser saknas")}</span>}
        </div>
        <div className="tablewrap" style={{ marginTop: 8, overflow: "auto" }}>
          <table className="qty small">
            <thead><tr><th>{tr("Beteckning")}</th><th>{tr("H×L mm")}</th>{s.zones.map((z: string) => <th key={z} className="num">{z || tr("Antal")}</th>)}
              <th className="num">{tr("Totalt")}</th><th className="num">{tr("Proj. W")}</th></tr></thead>
            <tbody>{s.rows.map((r: any) => (
              <tr key={r.designation}><td className="lf-mono">{r.designation}</td><td>{r.h}×{r.l}</td>
                {s.zones.map((z: string) => <td key={z} className="num">{r.per_zone[z] || ""}</td>)}
                <td className="num"><b>{r.total}</b></td><td className="num">{kr(r.w_total)}{r.without_effect ? ` (${trf("{0} utan effekt", r.without_effect)})` : ""}</td></tr>))}
            </tbody>
          </table>
        </div>
        <h3 style={{ marginBottom: 4 }}>{trf("Korsning mot Altech vid {0} °C", res.temps)}</h3>
        <div className="tablewrap" style={{ overflow: "auto" }}>
          <table className="qty small">
            <thead><tr><th>{tr("Föreskriven")}</th><th className="num">{tr("Antal")}</th><th className="num">{tr("Proj. W max")}</th>
              <th>{tr("Korsning")}</th><th>{tr("Altech")}</th><th>RSK</th><th className="num">{tr("Altech W")}</th>
              <th className="num">{tr("Mot proj.")}</th><th className="num">{tr("Mot föreskriven")}</th><th className="num">{tr("Δ längd")}</th>
              <th className="num">{tr("Δ höjd")}</th><th className="num">{tr("Pris st")}</th><th></th></tr></thead>
            <tbody>{res.cross.map((x: any) => {
              const a = x.altech || {};
              return (<Fragment key={x.designation}>
                <tr>
                  <td className="lf-mono">{x.designation}</td><td className="num">{x.count}</td><td className="num">{x.w_max ?? "–"}</td>
                  <td><span className={`badge small ${STATUS_CLASS[x.status] || ""}`}>{tr(x.status)}</span></td>
                  <td>{a.name}</td><td className="lf-mono">{(a.rsk || []).join(", ")}</td><td className="num">{a.w ?? "–"}</td>
                  <td className="num">{a.dw_need != null ? `${a.dw_need > 0 ? "+" : ""}${a.dw_need} (${a.dw_need_pct} %)` : "–"}</td>
                  <td className="num">{a.dw_prescribed != null ? `${a.dw_prescribed > 0 ? "+" : ""}${a.dw_prescribed}` : "–"}</td>
                  <td className="num">{a.dl_mm ? `${a.dl_mm > 0 ? "+" : ""}${a.dl_mm}` : "0"}</td>
                  <td className="num">{a.dh_mm ? `${a.dh_mm > 0 ? "+" : ""}${a.dh_mm}` : "0"}</td>
                  <td className="num">{kr(unit(a.price))}{x.prescribed_price ? <span className="muted"> ({tr("föreskr.")} {kr(unit(x.prescribed_price))})</span> : null}</td>
                  <td><button className="secondary small" onClick={() => setOpen(open === x.designation ? "" : x.designation)}>{open === x.designation ? tr("Dölj") : tr("Detaljer")}</button></td>
                </tr>
                {open === x.designation && (
                  <tr><td colSpan={13}>
                    <div className="small">{(a.notes || []).map((n: string) => <div key={n}>• {tr(n)}</div>)}</div>
                    {x.radiators_under?.length > 0 && <div className="error small">{trf("Altech ger för lite för radiator nr {0}", x.radiators_under.join(", "))}</div>}
                    <div className="small muted">{trf("Effekt: {0}", a.w_source)}{x.prescribed_source ? ` · ${tr("föreskriven")}: ${x.prescribed_source}` : ""}</div>
                    {x.alternatives?.length > 0 && <table className="qty small" style={{ marginTop: 4 }}><tbody>
                      {x.alternatives.map((al: any) => (
                        <tr key={al.name}><td>{tr(al.why)}</td><td>{al.name}</td><td className="lf-mono">{al.rsk.join(", ")}</td><td className="num">{al.w} W</td>
                          <td className="num">{al.dw_need != null ? `${al.dw_need > 0 ? "+" : ""}${al.dw_need}` : ""}</td>
                          <td className="num">{al.dl_mm ? `${al.dl_mm > 0 ? "+" : ""}${al.dl_mm} mm` : ""}</td>
                          <td className="num">{al.dh_mm ? `${al.dh_mm > 0 ? "+" : ""}${al.dh_mm} mm` : ""}</td>
                          <td className="num">{kr(unit(al.price))}</td><td className="small">{al.notes.map((n: string) => tr(n)).join("; ")}</td></tr>))}
                    </tbody></table>}
                    {onZoom && <div className="small" style={{ marginTop: 4 }}>{tr("Visa på ritningen")}: {res.radiators.filter((r: any) => r.designation === x.designation).slice(0, 40).map((r: any) => (
                      <button key={r.nr} className="chip" onClick={() => onZoom(r.bbox)}>{r.nr}{r.zone ? ` ${r.zone}` : ""}{r.w ? ` ${r.w} W` : ""}</button>))}</div>}
                  </td></tr>)}
              </Fragment>);
            })}</tbody>
          </table>
        </div>
        <p className="muted small">{tr("Källa Altech")}: {res.source}</p>
      </>)}
    </section>
    {s?.total > 0 && <GoldenPanel drawingId={drawingId} />}
  </>);
}
