import { useEffect, useRef, useState } from "react";
import { t as tr, locale } from "../i18n";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";

/* Kalkylen: från mängd till pris, och anbudet. En egen sida, för det är ett eget arbete.
 *
 * Två steg som hålls isär så att varje krona går att spåra till en rad på ritningen. Material: varje
 * beteckning matchas mot Dahls katalog och får ett FÖRSLAG med alternativ bredvid - den som räknar väljer.
 * Arbete: timmarna kommer ur Normtid VVS, med tillägg och avvikelseanalys utskrivna. Där boken inte har någon
 * tid står det, och timmen skrivs för hand.
 *
 * Talen räknas om på servern varje gång ur läsningen med rättelserna ovanpå. Det som sparas är valen och
 * antagandena. Anbudet skrivs ur den sparade kalkylen, och förhandsgranskningen visar det dokument som
 * skickas - sidorna som bilder - inte en efterlikning av det.
 */

const kr = (v: number | null | undefined) =>
  v == null ? "–" : `${v.toLocaleString(locale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 })} kr`;
const num = (v: number | null | undefined, d = 2) =>
  v == null ? "–" : v.toLocaleString(locale(), { maximumFractionDigits: d });

export default function CalcPage() {
  const { id } = useParams();
  const jobId = id!;
  const [job, setJob] = useState<any>(null);
  const [under, setUnder] = useState<any>(null);
  const [A, setA] = useState<any>(null);
  const [ov, setOv] = useState<Record<string, { artikel?: string; timmar?: number }>>({});
  const [calc, setCalc] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [err, setErr] = useState("");
  const [pages, setPages] = useState<string[] | null>(null);
  const [loadingPages, setLoadingPages] = useState(false);
  const urls = useRef<string[]>([]);
  const anbudRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    api.job(jobId).then(setJob).catch((e) => setErr(e.message));
    api.calcUnderlag(jobId).then((u) => {
      setUnder(u);
      api.calc(jobId).then((c) => {
        if (c.status === "SAVED") { setA(c.assumptions); setCalc(c); setSaved(c.saved_at); }
        else setA(u.defaults);
      }).catch(() => setA(u.defaults));
    }).catch((e) => setErr(e.message));
    return () => { urls.current.forEach((u) => URL.revokeObjectURL(u)); };
  }, [jobId]);

  const run = async (save = false) => {
    if (!A) return;
    setBusy(true); setErr("");
    try {
      const r = save ? await api.calcSave(jobId, { assumptions: A, overrides: ov })
                     : await api.calcPreview(jobId, { assumptions: A, overrides: ov });
      setCalc(r);
      setDirty(!save);
      if (save) { setSaved(r.saved_at); setPages(null); }
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  const openPdf = async () => {
    setErr("");
    try {
      const blob = await api.fetchBlob(api.anbudPdfUrl(jobId));
      const u = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = u;
      a.download = `Anbud ${drawingName || jobId.slice(0, 8)}.pdf`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(u), 10000);
    } catch (e: any) { setErr(e.message); }
  };

  /* Anbudet visas innan det lämnas. Sidorna är det dokument som skickas, renderade av servern, inte en
     efterlikning byggd av samma tal en gång till - så det som står på skärmen är det som står i filen. */
  const preview = async () => {
    setLoadingPages(true); setErr("");
    try {
      const info = await api.anbudInfo(jobId);
      urls.current.forEach((u) => URL.revokeObjectURL(u));
      const out: string[] = [];
      for (let n = 1; n <= info.pages; n++) {
        const b = await api.fetchBlob(api.anbudPageUrl(jobId, n));
        out.push(URL.createObjectURL(b));
      }
      urls.current = out;
      setPages(out);
      return out;
    } catch (e: any) { setErr(e.message); return null; } finally { setLoadingPages(false); }
  };

  const showAnbud = async () => {
    anbudRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    if (!pages && !loadingPages) await preview();
  };

  const set = (k: string, v: any) => { setA({ ...A, [k]: v }); setDirty(true); };
  const setRow = (name: string, patch: { artikel?: string; timmar?: number }) => {
    setOv({ ...ov, [name]: { ...ov[name], ...patch } }); setDirty(true);
  };

  if (!A) {
    return (
      <main>
        <p className="crumb"><Link to="/projekt">Projekt</Link> {tr("· Kalkyl")}</p>
        <h1>Kalkyl</h1>
        <p className="lead">{err || "Laddar underlaget…"}</p>
      </main>
    );
  }
  const T = calc?.totals;
  const sup: string[] = A.supplements ?? [];
  const groups: Record<string, any[]> = {};
  (under?.normtid?.supplements ?? []).forEach((s: any) => { (groups[s.group] ??= []).push(s); });
  const regelverk: any[] = under?.regelverk ?? [];
  const drawingName = (job?.drawing_filename || job?.filename || "").replace(/\.pdf$/i, "");

  return (
    <main className="calcpage">
      <p className="crumb">
        {job?.drawing_id && <><Link to={`/drawings/${job.drawing_id}`}>Ritning</Link> · </>}
        <Link to={`/jobs/${jobId}`}>Analys</Link> · Kalkyl
      </p>
      <div className="head">
        <div>
          <h1>Kalkyl</h1>
          <p className="lead">
            {drawingName ? `${drawingName} · ` : ""}Material ur Dahls katalog, timmar ur Normtid VVS, allt utskrivet
            rad för rad. Talen räknas ur läsningen med dina rättelser ovanpå. {under?.normtid?.warning}
          </p>
        </div>
        <div className="row calc-actions">
          <button onClick={() => run(false)} disabled={busy}>{busy ? "Räknar…" : calc ? "Räkna om" : "Kalkylera"}</button>
          {calc && <button className="secondary" onClick={() => run(true)} disabled={busy}>{tr("Spara kalkyl")}</button>}
          {saved && !dirty && <button className="secondary" onClick={showAnbud}>{tr("Visa anbudet")}</button>}
        </div>
      </div>
      <div className="rule" style={{ marginBottom: 22 }} />
      {err && <p className="error">{err}</p>}

      {calc && T && (
        <div className="adm-stats calc-stats">
          <div className="adm-stat"><div className="k">Material</div><div className="v">{kr(T.material_kr)}</div><div className="s">{T.rader} poster</div></div>
          <div className="adm-stat"><div className="k">Arbete</div><div className="v">{kr(T.arbete_kr)}</div><div className="s">{num(T.timmar, 1)} timmar · {kr(A.timpris)}/h</div></div>
          <div className="adm-stat"><div className="k">{tr("Anbudssumma exkl. moms")}</div><div className="v">{kr(T.netto_kr)}</div><div className="s">påslag {kr(T.paslag_material_kr + T.paslag_arbete_kr)}</div></div>
          <div className="adm-stat good"><div className="k">{tr("Att betala inkl. moms")}</div><div className="v">{kr(T.brutto_kr)}</div><div className="s">moms {kr(T.moms_kr)}</div></div>
          {(T.utan_artikel > 0 || T.utan_normtid > 0) && (
            <div className="adm-stat bad"><div className="k">{tr("Att välja")}</div><div className="v">{T.utan_artikel + T.utan_normtid}</div>
              <div className="s">{T.utan_artikel} utan artikel · {T.utan_normtid} utan normtid</div></div>
          )}
        </div>
      )}

      <div className="calc-grid">
        <aside className="card calc-side">
          <h3>Antaganden</h3>
          <div className="calc-fields">
            <label className="adm-field"><span>{tr("Timpris kr/h")}</span><input type="number" value={A.timpris} onChange={(e) => set("timpris", Number(e.target.value))} /></label>
            <label className="adm-field"><span>{tr("Spill %")}</span><input type="number" value={A.spill_pct} onChange={(e) => set("spill_pct", Number(e.target.value))} /></label>
            <label className="adm-field"><span>{tr("Påslag material %")}</span><input type="number" value={A.paslag_material_pct} onChange={(e) => set("paslag_material_pct", Number(e.target.value))} /></label>
            <label className="adm-field"><span>{tr("Påslag arbete %")}</span><input type="number" value={A.paslag_arbete_pct} onChange={(e) => set("paslag_arbete_pct", Number(e.target.value))} /></label>
            <label className="adm-field"><span>{tr("Moms %")}</span><input type="number" value={A.moms_pct} onChange={(e) => set("moms_pct", Number(e.target.value))} /></label>
            <label className="adm-field"><span>{tr("Våningshöjd m")}</span><input type="number" step="0.1" value={A.floor_height_m} onChange={(e) => set("floor_height_m", Number(e.target.value))} /></label>
          </div>

          <h3 style={{ marginTop: 18 }}>Tillägg (Normtid VVS)</h3>
          {Object.entries(groups).map(([g, items]) => (
            <div key={g} className="calc-group">
              <span className="muted small">{g}</span>
              {items.map((s: any) => (
                <label key={s.id} className="small check">
                  <input type="checkbox" checked={sup.includes(s.id)}
                    onChange={(e) => set("supplements", e.target.checked ? [...sup, s.id] : sup.filter((x) => x !== s.id))} />
                  {" "}{s.label} +{Math.round(s.pct * 100)} %
                </label>
              ))}
            </div>
          ))}
          <details style={{ marginTop: 10 }}>
            <summary className="muted small">Avvikelseanalys</summary>
            {(under?.normtid?.factors ?? []).map((f: any) => (
              <div key={f.id} className="row" style={{ marginTop: 6, gap: 8 }}>
                <span className="muted small" style={{ flex: 1 }} title={`${f.less} / ${f.normal} / ${f.more}`}>{f.label}</span>
                <select value={(A.factors ?? {})[f.id] ?? 0} onChange={(e) => set("factors", { ...(A.factors ?? {}), [f.id]: Number(e.target.value) })}>
                  {f.scale.map((v: number) => <option key={v} value={v}>{v > 0 ? `+${v}` : v} %</option>)}
                </select>
              </div>
            ))}
          </details>

          <h3 style={{ marginTop: 18 }}>Anbudet</h3>
          <div className="calc-fields one">
            <label className="adm-field"><span>{tr("Vårt företag")}</span><input value={A.company ?? ""} onChange={(e) => set("company", e.target.value)} /></label>
            <label className="adm-field"><span>{tr("Beställare")}</span><input value={A.customer ?? ""} onChange={(e) => set("customer", e.target.value)} /></label>
            <label className="adm-field"><span>Referens</span><input value={A.reference ?? ""} onChange={(e) => set("reference", e.target.value)} /></label>
            <label className="adm-field"><span>Avtalsvillkor</span>
              <select value={A.regelverk ?? ""} onChange={(e) => set("regelverk", e.target.value)}>
                <option value="">{tr("Inget standardavtal")}</option>
                {regelverk.map((r: any) => <option key={r.id} value={r.id}>{r.label}</option>)}
              </select>
            </label>
            <label className="adm-field"><span>Betalning</span><input value={A.betalning ?? ""} onChange={(e) => set("betalning", e.target.value)} /></label>
            <label className="adm-field"><span>{tr("Giltigt i dagar")}</span><input type="number" value={A.valid_days} onChange={(e) => set("valid_days", Number(e.target.value))} /></label>
            <label className="adm-field"><span>Inledning</span>
              <textarea rows={3} value={A.intro ?? ""} onChange={(e) => set("intro", e.target.value)} placeholder={tr("Lämnas tom för standardtexten")} /></label>
          </div>
          {A.regelverk && regelverk.find((r: any) => r.id === A.regelverk) && (
            <ul className="calc-clauses">
              {regelverk.find((r: any) => r.id === A.regelverk).clauses.map((c: string) => <li key={c}>{c}</li>)}
            </ul>
          )}
        </aside>

        <section className="calc-main">
          {!calc && (
            <div className="card calc-empty">
              <h3>{tr("Inget räknat ännu")}</h3>
              <p className="muted">Tryck <b>Kalkylera</b> {tr("så matchas varje beteckning mot Dahls katalog och får sin normtid. Du väljer sedan artikel och rättar timmar rad för rad.")}</p>
            </div>
          )}
          {calc && (
            <div className="card">
              <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
                <h3 style={{ margin: 0 }}>Poster</h3>
                <span className="muted small">{dirty ? "ändrat · räkna om eller spara" : saved ? `sparad ${new Date(saved).toLocaleString(locale())}` : "ej sparad"}</span>
              </div>
              <div className="tablewrap" style={{ marginTop: 10 }}>
                <table className="qty calc-table">
                  <thead><tr><th>Beteckning</th><th>Artikel (nettopris/m)</th><th className="num">{tr("Kalkylmängd")}</th>
                    <th className="num">Material</th><th>Normtid</th><th className="num">Timmar</th>
                    <th className="num">Arbete</th><th className="num">Summa</th></tr></thead>
                  <tbody>
                    {calc.rows.map((r: any) => (
                      <tr key={r.designation} className={!r.artikel || r.timmar == null ? "pa-weak" : ""}>
                        <td className="lf-mono"><b>{r.designation}</b><div className="muted small">DN{r.dn ?? "?"} · {r.material_ord.join(" ") || r.material_kod || "okänt material"}</div></td>
                        <td>
                          <select value={ov[r.designation]?.artikel ?? r.artikel?.a ?? ""}
                            onChange={(e) => setRow(r.designation, { artikel: e.target.value || undefined })}>
                            <option value="">{r.alternativ.length ? "– välj artikel –" : "ingen träff i boken"}</option>
                            {r.alternativ.map((a: any) => <option key={a.a} value={a.a}>{a.n} · {kr(a.netto)}</option>)}
                            {r.artikel && !r.alternativ.some((a: any) => a.a === r.artikel.a) && <option value={r.artikel.a}>{r.artikel.n} · {kr(r.artikel.netto)}</option>}
                          </select>
                        </td>
                        <td className="num">{num(r.kalkyl_m)} m<div className="muted small">{num(r.horisontellt_m)} + {r.stigare} st</div></td>
                        <td className="num">{kr(r.material_kr)}</td>
                        <td className="muted small">{r.normtid_kalla}{r.steg?.grundtid_per_m ? ` · ${r.steg.grundtid_per_m} h/m` : ""}</td>
                        <td className="num">
                          <input type="number" step="0.1" style={{ width: 78, textAlign: "right" }}
                            value={ov[r.designation]?.timmar ?? r.timmar ?? ""}
                            placeholder={r.timmar == null ? "ange" : ""}
                            onChange={(e) => setRow(r.designation, { timmar: e.target.value === "" ? undefined : Number(e.target.value) })} />
                        </td>
                        <td className="num">{kr(r.arbete_kr)}</td>
                        <td className="num"><b>{kr(r.summa_kr)}</b></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {calc.caveats?.length > 0 && (
                <div className="pa-unread" style={{ marginTop: 12 }}>
                  <b>{tr("Förbehåll som följer med anbudet")}</b>
                  <ul style={{ margin: "6px 0 0 16px" }}>{calc.caveats.map((c: string) => <li key={c} className="small">{c}</li>)}</ul>
                </div>
              )}
              <p className="muted small" style={{ marginBottom: 0 }}>{tr("Ändrade artiklar eller timmar räknas in när du trycker Räkna om eller Spara kalkyl.")}</p>
            </div>
          )}

          {saved && (
            <div className="card calc-anbud" ref={anbudRef}>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 10 }}>
                <div>
                  <h3 style={{ margin: 0 }}>Anbudet</h3>
                  <p className="muted small" style={{ margin: "4px 0 0" }}>
                    Skrivs ur den sparade kalkylen. {dirty
                      ? "Du har osparade ändringar - spara först så följer de med."
                      : "Läs igenom sidorna här. Det som står på skärmen är det som ligger i filen."}
                  </p>
                </div>
                <div className="row">
                  <button className="secondary small" onClick={() => { void preview(); }} disabled={loadingPages || dirty}>
                    {loadingPages ? "Hämtar…" : pages ? "Uppdatera" : "Visa anbudet"}
                  </button>
                </div>
              </div>
              {loadingPages && !pages && <p className="muted small" style={{ marginBottom: 0 }}>{tr("Sätter anbudet…")}</p>}
              {pages && (
                <>
                  <div className="anbud-pages">
                    {pages.map((u, i) => <img key={u} src={u} alt={`Anbud, sida ${i + 1}`} className="anbud-page" />)}
                  </div>
                  {/* nedladdningen står under sidorna: filen hämtas av den som har läst den */}
                  <div className="row" style={{ justifyContent: "flex-end", marginTop: 12 }}>
                    <button className="small" onClick={openPdf} disabled={dirty}>{tr("Ladda ner som PDF")}</button>
                  </div>
                </>
              )}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
