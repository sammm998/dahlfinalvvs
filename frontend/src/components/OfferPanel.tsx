import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { t as tr, trf, locale } from "../i18n";

/* Offerten: den färdiga matchningen blir en materialoffert eller en kalkyloffert.
 *
 * Kunden väljs med kundnummer och dess rabattmatris läses in; priset per rad är bruttopriset minus kundens rabatt
 * för artikelns rabattgrupp, eller kundens nettopris. Bonusen hämtas med en knapp. Inköp och marginal visas bara i
 * det interna läget och kommer aldrig med på kundens offert. Rader utan artikel, pris eller antal flaggas. */

const kr = (v: number | null | undefined) => v == null ? "–" : v.toLocaleString(locale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const DATA_KINDS: [string, string, string][] = [
  ["kunder", "Kunder", "Kundnr, Namn, Bonus %, Bonusavtal"],
  ["rabatter", "Rabattmatris", "Kundnr, Rabattgrupp, Rabatt %"],
  ["nettopriser", "Kundunika nettopriser", "Kundnr, RSK, Nettopris"],
  ["inkopspriser", "Inköpspriser", "RSK, Inköpspris"],
  ["korsreferens", "Korsreferenslista rör", "Material, Dimension, Fabrikat, Serie, RSK, Benämning, Pris saknas"],
];

export default function OfferPanel({ project }: { project: any }) {
  const [offers, setOffers] = useState<any[]>([]);
  const [open, setOpen] = useState<any>(null);
  const [kind, setKind] = useState("materialoffert");
  const [custNo, setCustNo] = useState("");
  const [hits, setHits] = useState<any[]>([]);
  const [house, setHouse] = useState(false);
  const [rate, setRate] = useState("650");
  const [internal, setInternal] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [dataStatus, setDataStatus] = useState<any>(null);
  const files = useRef<Record<string, HTMLInputElement | null>>({});

  const load = async () => { setOffers(await api.offers(project.id)); setDataStatus(await api.offerData()); };
  useEffect(() => { load().catch((e) => setErr(e.message)); }, [project.id]);
  useEffect(() => {
    if (custNo.trim().length < 2) { setHits([]); return; }
    const t = setTimeout(() => api.customers(custNo).then((r: any) => setHits(r.customers)).catch(() => setHits([])), 250);
    return () => clearTimeout(t);
  }, [custNo]);

  const run = async (f: () => Promise<any>) => {
    setBusy(true); setErr("");
    try { const r = await f(); if (r && r.rows) setOpen(r); await load(); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const create = () => run(() => api.createOffer(project.id, { kind, customer_no: custNo.trim(), use_house_brand: house,
                                                                hourly_rate: Number(rate) || 0 }));
  const download = async (fmt: string, intern = false) => {
    const b: Blob = await (api as any).fetchBlob(`/api/offers/${open.id}/export.${fmt}${intern ? "?internal=true" : ""}`);
    const a = document.createElement("a"); a.href = URL.createObjectURL(b);
    a.download = `${open.kind}-${open.number}${intern ? "-internt" : ""}.${fmt}`; a.click();
  };
  const upload = (k: string) => run(async () => { await api.offerDataUpload(k, files.current[k]!.files![0]); return null; });
  const T = open?.totals;
  const kalk = open?.kind === "kalkyloffert";

  return (
    <section className="card" style={{ marginTop: 18 }}>
      <h2 style={{ margin: 0 }}>{tr("Offert")}</h2>
      <p className="muted small" style={{ maxWidth: 720 }}>
        {tr("Materialoffert: allt material i underlaget (beskrivning, ritning, materiallista, BOM, IFC). Kalkyloffert: materialet och montörstimmarna ur normtidsboken och ritningskalkylen. Kunden väljs med kundnummer; rabattmatrisen läses in och priset räknas per rad. Inköp och marginal visas bara internt.")}
      </p>
      <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label className="small">{tr("Sort")}<br />
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="materialoffert">{tr("Materialoffert")}</option>
            <option value="kalkyloffert">{tr("Kalkyloffert (entreprenad)")}</option>
          </select></label>
        <label className="small" style={{ position: "relative" }}>{tr("Kundnummer")}<br />
          <input value={custNo} onChange={(e) => setCustNo(e.target.value)} placeholder={tr("kundnr eller namn")} />
          {hits.length > 0 && (
            <div className="card" style={{ position: "absolute", zIndex: 5, padding: 6, minWidth: 260 }}>
              {hits.map((h) => <div key={h.kundnr} style={{ cursor: "pointer", padding: 3 }} onClick={() => { setCustNo(h.kundnr); setHits([]); }}>
                <b>{h.kundnr}</b> {h.namn}</div>)}
            </div>)}
        </label>
        {kalk || kind === "kalkyloffert" ? <label className="small">{tr("Timpris (kr)")}<br />
          <input style={{ width: 90 }} value={rate} onChange={(e) => setRate(e.target.value)} /></label> : null}
        <label className="check small"><input type="checkbox" checked={house} onChange={(e) => setHouse(e.target.checked)} />{tr("Föreslå eget varumärke där förskrivning saknas")}</label>
        <button disabled={busy} onClick={create}>{busy ? tr("Räknar…") : tr("Skapa offert")}</button>
      </div>
      {err && <p className="error">{err}</p>}

      {offers.length > 0 && (
        <div className="chips" style={{ marginTop: 10 }}>
          {offers.map((o) => (
            <button key={o.id} className={`chip${open?.id === o.id ? " on" : ""}`} onClick={() => run(() => api.offer(o.id))}>
              {o.number} · {tr(o.kind)} · {o.customer_name || tr("ingen kund")} <i>{kr(o.totals?.total)}</i>
            </button>))}
        </div>)}

      {open && (
        <div style={{ marginTop: 14 }}>
          <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <b>{tr(open.kind)} {open.number}</b>
            <span className="badge">{open.customer_no ? `${open.customer_no} ${open.customer_name}` : tr("ingen kund vald")}</span>
            <span className="badge">{trf("{0} rader", T.rader)}</span>
            {T.flaggade > 0 && <span className="badge warn">{trf("{0} flaggade", T.flaggade)}</span>}
            <span style={{ flex: 1 }} />
            <button className="secondary small" disabled={!open.customer_no || busy} onClick={() => run(() => api.offerBonus(open.id))}>{tr("Hämta bonus")}</button>
            <label className="check small"><input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} />{tr("Visa internt (inköp och marginal)")}</label>
            <button className="secondary small" onClick={() => download("pdf")}>{tr("Kundens offert (PDF)")}</button>
            <button className="secondary small" onClick={() => download("xlsx")}>{tr("Kundens offert (Excel)")}</button>
            <button className="secondary small" onClick={() => download("xlsx", true)}>{tr("Internt underlag (Excel)")}</button>
          </div>
          <div className="tablewrap" style={{ marginTop: 8 }}>
            <table className="qty">
              <thead><tr>
                <th>{tr("Pos")}</th><th>{tr("Benämning")}</th><th>{tr("RSK")}</th><th>{tr("Artikel")}</th><th className="num">{tr("Antal")}</th>
                <th className="num">{tr("Brutto")}</th><th className="num">{tr("Rabatt")}</th><th className="num">{tr("À-pris")}</th><th className="num">{tr("Summa")}</th>
                {kalk && <th className="num">{tr("Timmar")}</th>}
                {internal && <><th className="num">{tr("Inköp")}</th><th className="num">{tr("Marginal")}</th></>}
                <th>{tr("Flaggor")}</th>
              </tr></thead>
              <tbody>
                {open.rows.map((r: any) => (
                  <tr key={r.id}>
                    <td>{r.pos}</td>
                    <td>{r.text}{r.foreskrift && <div className="muted small">{r.foreskrift}</div>}</td>
                    <td className="lf-mono">{r.rsk || "–"}</td>
                    <td className="small">{r.artikel || "–"}{r.val && <div className="muted">{tr(r.val)}</div>}</td>
                    <td className="num"><input style={{ width: 64, textAlign: "right" }} defaultValue={r.antal ?? ""}
                      onBlur={(e) => { const v = e.target.value.replace(",", "."); if (v !== String(r.antal ?? "")) run(() => api.patchOffer(open.id, { rows: [{ id: r.id, antal: Number(v) }] })); }} /> {r.enhet}</td>
                    <td className="num">{kr(r.brutto)}</td>
                    <td className="num">{r.rabatt_pct != null ? `${r.rabatt_pct} %` : "–"}</td>
                    <td className="num" title={r.pris_enligt}>{kr(r.netto)}</td>
                    <td className="num">{kr(r.summa)}</td>
                    {kalk && <td className="num" title={r.tim_kalla}>{r.timmar ?? "–"}</td>}
                    {internal && <><td className="num">{kr(r.inkop_summa)}</td>
                      <td className="num">{r.marginal_pct != null ? `${r.marginal_pct} %` : "–"}</td></>}
                    <td className="small">{(r.flaggor || []).map((f: string) => <span key={f} className="badge small warn" style={{ marginRight: 3 }}>{tr(f)}</span>)}</td>
                  </tr>))}
              </tbody>
            </table>
          </div>
          <p style={{ marginTop: 8 }}>
            <b>{tr("Material")}:</b> {kr(T.material)} kr
            {kalk && <> · <b>{tr("Arbete")}:</b> {kr(T.arbete)} kr ({T.timmar} h)</>}
            {" · "}<b>{tr("Totalt exkl. moms")}:</b> {kr(T.total)} kr
            {T.bonus_kr ? <> · {trf("Bonus {0} %: {1} kr", T.bonus_pct, kr(T.bonus_kr))}</> : null}
            {internal && T.marginal_kr != null && <span className="muted"> · {trf("Internt: inköp {0} kr, marginal {1} kr ({2} %), inköpspris finns för {3}", kr(T.inkop), kr(T.marginal_kr), T.marginal_pct, T.inkop_tackning)}</span>}
          </p>
        </div>)}

      <details className="settings" style={{ marginTop: 12 }}>
        <summary>{tr("Offertdata (tills M3 är kopplat): kunder, rabattmatris, nettopriser, inköpspriser, korsreferens")}</summary>
        <p className="muted small">{tr("Laddas upp som Excel eller CSV av en administratör. Bruttopris och rabattgrupp kommer ur materialboken.")}</p>
        {DATA_KINDS.map(([k, label, cols]) => (
          <div key={k} className="row small" style={{ gap: 8, alignItems: "center", margin: "4px 0" }}>
            <b style={{ width: 190 }}>{tr(label)}</b>
            <span className="muted" style={{ width: 90 }}>{trf("{0} rader", dataStatus?.[k]?.n ?? 0)}</span>
            <input type="file" accept=".xlsx,.csv" id={`od-${k}`} className="file" ref={(el) => { files.current[k] = el; }} onChange={() => upload(k)} />
            <label className="pick small" htmlFor={`od-${k}`}>{tr("Ladda upp")}</label>
            <span className="muted">{tr("Kolumner")}: {cols}</span>
          </div>))}
      </details>
    </section>
  );
}
