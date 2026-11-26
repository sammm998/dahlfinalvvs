import { useEffect, useState } from "react";
import { api } from "../api";
import { t as tr, trf, locale } from "../i18n";

/* KAM: prisjustering för KAM-kund. Ersätter Dahlmenyns PrisJusteringKund: kundens artiklar (antal, CP) mot ny
 * prislista och matris, Ändr % och Hbv% per nivå, kundavvikelser och extrarabatt, attest av säljare och
 * säljledare och registrering. Simulerad - statistik, prislista och matris kommer ur uppladdade filer. */

const kr = (v: number | null | undefined) => v == null ? "–" : Math.round(v).toLocaleString(locale());
const pct = (v: number | null | undefined) => v == null ? "–" : `${v > 0 ? "+" : ""}${v.toFixed(1)} %`;
const hbv = (v: number | null | undefined) => v == null ? "–" : `${v.toFixed(1)} %`;
const STATUS: Record<string, string> = { utkast: "Utkast", attest: "Väntar på attest", godkand: "Attesterad", avslagen: "Avslagen", registrerad: "Registrerad" };
const LEVEL: Record<string, string> = { SÄLJARE: "Säljaren räcker", SÄLJLEDARE: "Kräver säljledare", BLOCKERAD: "Stoppad – under kostpris" };

function save(b: Blob, name: string) { const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = name; a.click(); }

export default function KamPage() {
  const [status, setStatus] = useState<any>(null);
  const [cases, setCases] = useState<any[]>([]);
  const [cur, setCur] = useState<any>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const [role, setRole] = useState("");
  const [nc, setNc] = useState({ kundnr: "", old_period: "", new_period: "", rabattsystem: "DAHL12" });
  const [prop, setProp] = useState<any>(null);
  const [newGroup, setNewGroup] = useState({ kg: "", pct: "" });
  const [level, setLevel] = useState<"per_omr" | "per_pgr" | "per_kg">("per_omr");

  const act = async (label: string, f: () => Promise<any>) => {
    setBusy(label); setErr("");
    try { return await f(); } catch (e: any) { setErr(e.message); return null; } finally { setBusy(""); }
  };
  const loadList = async () => { const r = await act("list", () => api.kamCases()); if (r) setCases(r.cases); };
  const show = (c: any) => { setCur(c); setProp(c ? { ...c.proposal, comment: c.comment } : null); };
  useEffect(() => {
    act("status", async () => setStatus(await api.kamStatus()));
    loadList();
    api.myRole().then((r: any) => setRole(r?.role || "")).catch(() => setRole(""));
  }, []);

  const open = async (id: string) => { const c = await act("open", () => api.kamCase(id)); if (c) show(c); };
  const create = async () => {
    const c = await act("create", () => api.kamCreate(nc));
    if (c) { show(c); loadList(); }
  };
  const after = (c: any) => { if (c) { show(c); loadList(); } };
  const saveProposal = async (p = prop) => after(await act("prop", () => api.kamProposal(cur.id, p)));
  const editable = cur && (cur.status === "utkast" || cur.status === "avslagen");
  const sim = cur?.simulation;
  const t = sim?.totals;

  return (
    <main>
      <h1>{tr("KAM – prisjustering för KAM-kund")}</h1>
      <p className="lead" style={{ maxWidth: 900 }}>{tr("Kundens artiklar med antal och kostpris räknas mot ny prislista och matris: Ändr % och bruttovinst (Hbv%) per produktområde, produktgrupp och kalkylgrupp. Ändra kundavvikelser och extrarabatt, skicka för attest och registrera.")}</p>
      <p className="warn small" style={{ maxWidth: 900 }}>{tr("Simulerad: ingen skarp koppling till M3. Statistiken kommer ur en uppladdad fil eller kundens offerter, prislistan och matrisen ur prisfilen, och registreringen skriver kundens rabatter i tjänstens offertdata.")}</p>
      {status && <div className="row small" style={{ gap: 6, flexWrap: "wrap" }}>
        <span className={`badge ${status.prislista ? "ok" : "warn"}`}>{trf("Prislista: {0} artiklar", status.prislista)}</span>
        <span className={`badge ${status.matris ? "ok" : "warn"}`}>{trf("Matris: {0} kalkylgrupper", status.matris)}</span>
        <span className="badge">{trf("Kunder: {0}", status.kunder)}</span>
        <span className="badge">{trf("Kundrabatter: {0}", status.kundrabatter)}</span>
        <span className="badge">{trf("Inköpspriser: {0}", status.inkopspriser)}</span>
        {!status.prislista && <span className="small muted">{tr("Ladda upp Dahls prisfil under Offert → Offertdata (administratör).")}</span>}
      </div>}
      {err && <p className="error small">{err}</p>}

      <div className="row" style={{ gap: 16, alignItems: "flex-start", flexWrap: "wrap", marginTop: 12 }}>
        <section className="card" style={{ flex: "0 0 300px", padding: 14 }}>
          <h2 style={{ marginTop: 0 }}>{tr("Nytt ärende")}</h2>
          <label className="small">{tr("Kundnummer")}<br /><input value={nc.kundnr} onChange={(e) => setNc({ ...nc, kundnr: e.target.value })} placeholder="830102" /></label>
          <div className="row small" style={{ gap: 6 }}>
            <label>{tr("Gammalt prisdatum (ÅÅMM)")}<br /><input value={nc.old_period} onChange={(e) => setNc({ ...nc, old_period: e.target.value })} size={6} placeholder="2601" /></label>
            <label>{tr("Nytt prisdatum (ÅÅMM)")}<br /><input value={nc.new_period} onChange={(e) => setNc({ ...nc, new_period: e.target.value })} size={6} placeholder="2701" /></label>
          </div>
          <label className="small">{tr("Rabattsystem")}<br />
            <select value={nc.rabattsystem} onChange={(e) => setNc({ ...nc, rabattsystem: e.target.value })}>
              <option value="DAHL12">DAHL12 → KAM12</option><option value="VVSC12">VVSC12 → VVSKAM</option>
            </select></label>
          <div style={{ marginTop: 8 }}><button className="small" disabled={!nc.kundnr || !!busy} onClick={create}>{tr("Skapa ärende")}</button></div>
          <h2>{tr("Ärenden")}</h2>
          {cases.length === 0 && <p className="muted small">{tr("Inga ärenden ännu.")}</p>}
          {cases.map((c) => (
            <button key={c.id} className={`ghost small ${cur?.id === c.id ? "on" : ""}`} style={{ display: "block", width: "100%", textAlign: "left", marginBottom: 4 }} onClick={() => open(c.id)}>
              <b>{c.kundnr}</b> {c.kundnamn} <span className="badge small">{tr(STATUS[c.status] || c.status)}</span><br />
              <span className="muted">{trf("{0} artiklar · {1}", c.n_articles, (c.updated_at || "").slice(0, 10))}</span>
            </button>))}
        </section>

        {cur && (
          <section className="card" style={{ flex: "1 1 640px", padding: 14, minWidth: 0 }}>
            <h2 style={{ marginTop: 0 }}>{cur.kundnr} {cur.kundnamn} <span className="badge">{tr(STATUS[cur.status] || cur.status)}</span></h2>
            <p className="small muted">{trf("Rabattsystem {0} · prisdatum {1} → {2} · statistik: {3}", cur.rabattsystem, cur.old_period || "–", cur.new_period || "–", cur.statistics_source || tr("ingen ännu"))}</p>
            {editable && <div className="row small" style={{ gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
              <label>{tr("Kundens statistik (Dahlmenyns offertfil eller tabell med Artnr och Antal)")}<br />
                <input type="file" accept=".xlsx,.xlsm,.csv" onChange={async (e) => { const f = e.target.files?.[0]; if (f) after(await act("stat", () => api.kamStatistics(cur.id, f))); }} /></label>
              <button className="secondary small" disabled={!!busy} onClick={async () => after(await act("off", () => api.kamStatisticsFromOffers(cur.id)))}>{tr("Hämta ur kundens offerter")}</button>
            </div>}

            {prop && <div style={{ marginTop: 10 }}>
              <h3 style={{ marginBottom: 4 }}>{tr("Förslag till ändring")}</h3>
              <div className="row small" style={{ gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
                <label>{tr("Nytt pris ur")}<br />
                  <select disabled={!editable} value={prop.price_source || "prisfil"} onChange={(e) => setProp({ ...prop, price_source: e.target.value })}>
                    <option value="prisfil">{tr("Uppladdad prisfil")}</option>
                    <option value="index">{tr("Simulerad prisändring i %")}</option>
                  </select></label>
                <label>{tr("Prisändring %")}<br /><input disabled={!editable} type="number" step="0.1" size={5} value={prop.list_change_pct ?? ""} onChange={(e) => setProp({ ...prop, list_change_pct: e.target.value === "" ? null : Number(e.target.value) })} /></label>
                <label>{tr("Extrarabatt %")}<br /><input disabled={!editable} type="number" step="0.1" size={5} value={prop.extra ?? ""} onChange={(e) => setProp({ ...prop, extra: e.target.value === "" ? null : Number(e.target.value) })} /></label>
                <label>{tr("Marginalgolv Hbv%")}<br /><input disabled={!editable} type="number" step="0.5" size={5} value={prop.margin_floor ?? 10} onChange={(e) => setProp({ ...prop, margin_floor: Number(e.target.value) })} /></label>
              </div>
              <div className="small" style={{ marginTop: 8 }}>
                <b>{tr("Kundavvikelser per kalkylgrupp")}</b> <span className="muted">{tr("(2, 4 eller 6 tecken – 6 går före 4 som går före 2; tomt värde tar bort avvikelsen)")}</span>
                <div className="row" style={{ gap: 6, flexWrap: "wrap", marginTop: 4 }}>
                  {Object.entries({ ...(cur.terms?.rabatter || {}), ...(prop.avvikelser || {}) }).map(([k]) => (
                    <label key={k} className="chip">{k}{cur.terms?.rabatter?.[k] != null ? ` (${tr("nu")} ${cur.terms.rabatter[k]} %)` : ""}{" "}
                      <input disabled={!editable} type="number" step="0.1" style={{ width: 90, minWidth: 90 }}
                        value={k in (prop.avvikelser || {}) ? (prop.avvikelser[k] ?? "") : (cur.terms?.rabatter?.[k] ?? "")}
                        onChange={(e) => setProp({ ...prop, avvikelser: { ...prop.avvikelser, [k]: e.target.value === "" ? null : Number(e.target.value) } })} /></label>))}
                  {editable && <span className="row" style={{ gap: 4 }}>
                    <input placeholder={tr("Kalkylgrupp")} value={newGroup.kg} onChange={(e) => setNewGroup({ ...newGroup, kg: e.target.value.toUpperCase() })} style={{ width: 120, minWidth: 120 }} />
                    <input placeholder="%" type="number" value={newGroup.pct} onChange={(e) => setNewGroup({ ...newGroup, pct: e.target.value })} style={{ width: 80, minWidth: 80 }} />
                    <button className="ghost small" disabled={!newGroup.kg || newGroup.pct === ""} onClick={() => { setProp({ ...prop, avvikelser: { ...prop.avvikelser, [newGroup.kg]: Number(newGroup.pct) } }); setNewGroup({ kg: "", pct: "" }); }}>{tr("Lägg till")}</button>
                  </span>}
                </div>
              </div>
              <label className="small" style={{ display: "block", marginTop: 6 }}>{tr("Kommentar")}<br />
                <textarea disabled={!editable} rows={2} style={{ width: "100%" }} value={prop.comment || ""} onChange={(e) => setProp({ ...prop, comment: e.target.value })} /></label>
              {editable && <button className="small" disabled={!!busy} onClick={() => saveProposal()}>{busy === "prop" ? tr("Räknar…") : tr("Räkna om")}</button>}
            </div>}

            {t && <>
              <div className="row small" style={{ gap: 6, flexWrap: "wrap", marginTop: 12 }}>
                <span className="badge">{trf("{0} artiklar", t.rows)}</span>
                <span className="badge">{trf("Gammalt {0} kr", kr(t.old))}</span>
                <span className="badge">{trf("Nytt {0} kr", kr(t.new))}</span>
                <span className={`badge ${t.change_pct > 0 ? "ok" : t.change_pct < 0 ? "warn" : ""}`}>{trf("Ändr {0}", pct(t.change_pct))}</span>
                <span className="badge">{trf("Hbv% avtal {0} → nytt {1}", hbv(t.hbv_avtal), hbv(t.hbv_nytt))}</span>
                <span className={`badge ${sim.approval_level === "SÄLJARE" ? "ok" : sim.approval_level === "SÄLJLEDARE" ? "warn" : "error"}`}>{tr(LEVEL[sim.approval_level] || sim.approval_level)}</span>
                {t.rows_without_cp > 0 && <span className="badge warn">{trf("{0} utan kostpris", t.rows_without_cp)}</span>}
                {t.rows_simulated_price > 0 && <span className="badge">{trf("{0} med simulerat listpris", t.rows_simulated_price)}</span>}
              </div>
              <div className="row small" style={{ gap: 6, marginTop: 8 }}>
                {(["per_omr", "per_pgr", "per_kg"] as const).map((l) => <button key={l} className={`ghost small ${level === l ? "on" : ""}`} onClick={() => setLevel(l)}>
                  {tr(l === "per_omr" ? "Produktområde" : l === "per_pgr" ? "Produktgrupp" : "Kalkylgrupp")}</button>)}
              </div>
              <div className="tablewrap" style={{ overflow: "auto", maxHeight: 420, marginTop: 4 }}>
                <table className="qty small">
                  <thead><tr><th>{tr("Grupp")}</th><th>{tr("Benämning")}</th><th className="num">{tr("Rader")}</th><th className="num">{tr("Gammalt")}</th>
                    <th className="num">{tr("Nytt")}</th><th className="num">{tr("Ändr")}</th><th className="num">{tr("Hbv% avtal")}</th>
                    <th className="num">{tr("Hbv% nytt")}</th><th className="num">{tr("Hbv% matris")}</th><th></th></tr></thead>
                  <tbody>{sim[level].map((g: any) => (
                    <tr key={g.key}><td className="lf-mono">{g.key}</td><td>{g.name}</td><td className="num">{g.rows}</td><td className="num">{kr(g.old)}</td>
                      <td className="num">{kr(g.new)}</td><td className="num">{pct(g.change_pct)}</td><td className="num">{hbv(g.hbv_avtal)}</td>
                      <td className="num">{hbv(g.hbv_nytt)}</td><td className="num">{hbv(g.hbv_matris)}</td>
                      <td>{g.flags.map((f: string) => <span key={f} className={`badge small ${f === "UNDER_KOSTPRIS" ? "error" : "warn"}`}>{tr(f === "UNDER_KOSTPRIS" ? "under kostpris" : "under golvet")}</span>)}</td></tr>))}
                  </tbody>
                </table>
              </div>
              {sim.changes.avvikelser.length > 0 && <p className="small"><b>{tr("Ändrade kundavvikelser")}:</b> {sim.changes.avvikelser.map((r: any) => `${r.kg} ${r.tid_rab ?? "–"} → ${r.ny_rab ?? "–"} %`).join(" · ")}</p>}
              <div className="row small" style={{ gap: 6, flexWrap: "wrap", marginTop: 8 }}>
                {(["analys", "registrering", "kund"] as const).map((k) => (
                  <button key={k} className="secondary small" onClick={async () => { const b = await act("x", () => (api as any).fetchBlob(`/api/kam/cases/${cur.id}/export.xlsx?kind=${k}`)); if (b) save(b, `KAM_${cur.kundnr}_${k}.xlsx`); }}>
                    {tr(k === "analys" ? "Excel: analys (internt)" : k === "registrering" ? "Excel: registreringsunderlag" : "Excel: kundutskrift")}</button>))}
              </div>
            </>}

            <div className="row small" style={{ gap: 6, flexWrap: "wrap", marginTop: 12 }}>
              {editable && <button className="small" disabled={!sim || sim.approval_level === "BLOCKERAD" || !!busy} onClick={async () => after(await act("s", () => api.kamAction(cur.id, "submit")))}>{tr("Skicka för attest")}</button>}
              {role === "admin" && cur.status === "attest" && <>
                <button className="small" onClick={async () => after(await act("a", () => api.kamAction(cur.id, "approve")))}>{tr("Attestera (säljledare)")}</button>
                <button className="secondary small" onClick={async () => after(await act("r", () => api.kamAction(cur.id, "reject", prompt(tr("Varför avslås förslaget?")) || "")))}>{tr("Avslå")}</button></>}
              {role === "admin" && cur.status === "godkand" && <button className="small" onClick={async () => { if (confirm(tr("Registrera kundens nya rabatter? De ersätter kundens nuvarande rabatter i offertdatan."))) after(await act("g", () => api.kamAction(cur.id, "register"))); }}>{tr("Registrera (simulerat M3)")}</button>}
              {editable && <button className="ghost small" onClick={async () => { if (confirm(tr("Ta bort ärendet?"))) { await act("d", () => api.kamDelete(cur.id)); show(null); loadList(); } }}>{tr("Ta bort")}</button>}
            </div>
            <p className="small muted">{trf("Attest säljare: {0} · säljledare: {1}", cur.attest_saljare || "–", cur.attest_saljledare || "–")}</p>
            <details><summary className="small">{tr("Historik")}</summary>
              <ul className="small">{(cur.history || []).map((h: any, i: number) => <li key={i}>{h.at.slice(0, 16).replace("T", " ")} {h.by}: {h.what}</li>)}</ul></details>
          </section>)}
      </div>
    </main>
  );
}
