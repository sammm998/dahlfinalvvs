import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { t as tr, trf, locale } from "../i18n";

/* KAM – årlig prisförhandling. Ersätter arbetsboken med Justeringsvy och Varukorgsanalys: underlaget läses in en
 * gång, räkningen per artikel görs på servern (samma formler som i Excel), och justeringsvyn räknas om direkt här
 * i webbläsaren – netnet NY för en grupp är en rät linje i rabatten: A × (1 − rabatt) + F × (1 + nettojustering). */

type Sums = { qty?: number; in_nu?: number; in_ny?: number; nn_nu?: number; nn_ny?: number; lin_a?: number; lin_f?: number; n?: number };
type Group = {
  kg: string; name: string; omr: string; kat: string; omr_name: string; kat_name: string; leverantor: string; n_articles: number;
  moved: number; month: boolean; rab_nu: number; rab_level: string | null; new_group: boolean; rab_ny: number; rab_old: number | null;
  netto_pct: number; b: Record<string, Sums>;
};
type Calc = { nn_nu: number; nn_ny: number; in_nu: number; in_ny: number; brv_nu: number | null; brv_ny: number | null; brv_diff: number | null; prisdiff: number | null; inprisdiff: number | null };

const BASKETS = ["kund", "riks", "korg3"] as const;
const SERIES = { a: "var(--kam-series-1)", b: "var(--kam-series-2)" };

function calc(g: Group, b: string, rab?: number, netto?: number): Calc {
  const s = g.b[b] || {};
  const x = rab ?? g.rab_ny;
  const p = netto ?? g.netto_pct ?? 0;
  const nn_nu = s.nn_nu || 0, in_nu = s.in_nu || 0, in_ny = s.in_ny || 0;
  const nn_ny = (s.lin_a || 0) * (1 - x / 100) + (s.lin_f || 0) * (1 + p);
  const brv_nu = nn_nu ? (nn_nu - in_nu) / nn_nu : null;
  const brv_ny = nn_ny ? (nn_ny - in_ny) / nn_ny : null;
  return { nn_nu, nn_ny, in_nu, in_ny, brv_nu, brv_ny, brv_diff: brv_nu == null || brv_ny == null ? null : brv_ny - brv_nu,
    prisdiff: nn_nu ? nn_ny / nn_nu - 1 : null, inprisdiff: in_nu ? in_ny / in_nu - 1 : null };
}
function sum(cs: Calc[]): Calc {
  const t = cs.reduce((a, c) => ({ nn_nu: a.nn_nu + c.nn_nu, nn_ny: a.nn_ny + c.nn_ny, in_nu: a.in_nu + c.in_nu, in_ny: a.in_ny + c.in_ny }), { nn_nu: 0, nn_ny: 0, in_nu: 0, in_ny: 0 });
  const brv_nu = t.nn_nu ? (t.nn_nu - t.in_nu) / t.nn_nu : null, brv_ny = t.nn_ny ? (t.nn_ny - t.in_ny) / t.nn_ny : null;
  return { ...t, brv_nu, brv_ny, brv_diff: brv_nu == null || brv_ny == null ? null : brv_ny - brv_nu,
    prisdiff: t.nn_nu ? t.nn_ny / t.nn_nu - 1 : null, inprisdiff: t.in_nu ? t.in_ny / t.in_nu - 1 : null };
}

const kr = (v?: number | null) => v == null ? "–" : Math.round(v).toLocaleString(locale());
const mkr = (v?: number | null) => v == null ? "–" : (v / 1e6).toLocaleString(locale(), { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const pct = (v?: number | null, d = 1) => v == null ? "–" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(d)} %`;
const pp = (v?: number | null) => v == null ? "–" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(2)}`;
const plain = (v?: number | null, d = 1) => v == null ? "–" : `${(v * 100).toFixed(d)} %`;
const STATUS: Record<string, string> = { utkast: "Utkast", attest: "Väntar på attest", godkand: "Attesterad", avslagen: "Avslagen", registrerad: "Registrerad" };
const FLAG: Record<string, string> = {
  UNDER_KOSTPRIS: "Under kostpris", MARGINALTAPP: "Marginaltapp", HOJER_MER_AN_INPRIS: "Höjer mer än inpriset",
  TAPPAR_FORSALJNING: "Tappar försäljning", DYRARE_AN_SEGMENT: "Dyrare än segmentet", NY_GRUPP: "Ny grupp",
  KALKGR_FLYTT: "Kalkylgruppsflytt", AVVIKER_FG_AR: "Avviker från förra året", MANADSPRIS: "Månadspris",
};
const SEV: Record<string, string> = { high: "error", mid: "warn", low: "", info: "" };
function save(b: Blob, name: string) { const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = name; a.click(); }

const VIZ_CSS = `
.kam-viz { --kam-series-1: #257de0; --kam-series-2: #f47230; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .kam-viz { --kam-series-1: #338ced; --kam-series-2: #e76624; } }
:root[data-theme="dark"] .kam-viz { --kam-series-1: #338ced; --kam-series-2: #e76624; }
.kam-bar { height: 8px; border-radius: 0 4px 4px 0; display: block; }
.kam-bar.neg { border-radius: 4px 0 0 4px; margin-left: auto; }
.kam-kpi { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 10px; }
.kam-kpi > div { padding: 10px 12px; border: 1px solid var(--line, #ddd); border-radius: 10px; }
.kam-kpi b { display: block; font-size: 20px; font-variant-numeric: tabular-nums; }
.kam-sticky th { position: sticky; top: 0; z-index: 1; background: var(--bg, #fff); }
.kam-input { width: 84px !important; min-width: 84px; padding: 4px 8px !important; text-align: right; }
@media print { nav, aside, .no-print, .app-side { display: none !important; } .kam-present { box-shadow: none !important; border: 0 !important; } }
`;

/* Horisontella staplar med nollinje i mitten: en eller två serier per rad, med legend och verktygstips. */
function BarChart({ rows, series, fmt }: { rows: { key: string; label: string; values: (number | null)[] }[]; series: { name: string; color: string }[]; fmt: (v: number | null) => string }) {
  const max = Math.max(0.0001, ...rows.flatMap((r) => r.values.map((v) => Math.abs(v || 0))));
  return (
    <div className="kam-viz small">
      {series.length > 1 && <div className="row" style={{ gap: 14, marginBottom: 6 }}>{series.map((s) => (
        <span key={s.name} className="row" style={{ gap: 6, alignItems: "center" }}><span style={{ width: 12, height: 8, borderRadius: 2, background: s.color, display: "inline-block" }} />{s.name}</span>))}</div>}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(120px, 220px) 1fr 1fr 70px", columnGap: 6, rowGap: 6, alignItems: "center" }}>
        {rows.map((r) => (
          <Fragment key={r.key}>
            <span title={r.label} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}><b>{r.key}</b> {r.label}</span>
            <span style={{ borderRight: "1px solid var(--line, #ccc)", display: "flex", flexDirection: "column", gap: 2 }}>
              {r.values.map((v, i) => <span key={i} title={`${series[i].name}: ${fmt(v)}`} className="kam-bar neg" style={{ width: v != null && v < 0 ? `${(Math.abs(v) / max) * 100}%` : 0, background: series[i].color, marginTop: 2 }} />)}
            </span>
            <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              {r.values.map((v, i) => <span key={i} title={`${series[i].name}: ${fmt(v)}`} className="kam-bar" style={{ width: v != null && v > 0 ? `${(v / max) * 100}%` : 0, background: series[i].color, marginTop: 2 }} />)}
            </span>
            <span className="num" style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{fmt(r.values[0])}</span>
          </Fragment>))}
      </div>
    </div>
  );
}

export default function KamNegotiationPage() {
  const { id } = useParams();
  const [neg, setNeg] = useState<any>(null);
  const [data, setData] = useState<any>(null);
  const [ins, setIns] = useState<any[] | null>(null);
  const [tab, setTab] = useState<"underlag" | "oversikt" | "justering" | "insikter" | "kund" | "attest">("underlag");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const [role, setRole] = useState("");
  const [rab, setRab] = useState<Record<string, number>>({});
  const [netto, setNetto] = useState<Record<string, number>>({});
  const [comments, setComments] = useState<Record<string, string>>({});
  const pending = useRef<{ rab: Record<string, number | null>; netto: Record<string, number | null>; comments: Record<string, string> }>({ rab: {}, netto: {}, comments: {} });
  const timer = useRef<number | null>(null);

  const loadNeg = useCallback(async () => { try { const n = await api.neg(id!); setNeg(n); return n; } catch (e: any) { setErr(e.message); return null; } }, [id]);
  const loadData = useCallback(async () => {
    try {
      const d = await api.negGroups(id!);
      setData(d); setComments(d.comments || {});
      setRab(Object.fromEntries(d.groups.map((g: Group) => [g.kg, g.rab_ny])));
      setNetto(Object.fromEntries(d.groups.filter((g: Group) => g.netto_pct).map((g: Group) => [g.kg, g.netto_pct])));
    } catch (e: any) { setErr(e.message); }
  }, [id]);
  const loadIns = useCallback(async () => { try { setIns((await api.negInsights(id!)).insights); } catch (e: any) { setErr(e.message); } }, [id]);

  useEffect(() => {
    loadNeg().then((n) => { if (n?.totals) { loadData(); setTab("oversikt"); } });
    api.myRole().then((r: any) => setRole(r?.role || "")).catch(() => setRole(""));
  }, [loadNeg, loadData]);
  // inläsningen pågår: fråga tills den är klar
  useEffect(() => {
    if (neg?.job?.state !== "running") return;
    const t = window.setTimeout(async () => { const n = await loadNeg(); if (n?.job?.state === "done") { loadData(); setIns(null); } }, 1500);
    return () => window.clearTimeout(t);
  }, [neg, loadNeg, loadData]);
  useEffect(() => { if ((tab === "insikter" || tab === "oversikt") && data && ins == null) loadIns(); }, [tab, data, ins, loadIns]);

  const editable = neg && (neg.status === "utkast" || neg.status === "avslagen");
  const groups: Group[] = useMemo(() => (data?.groups || []).map((g: Group) => ({ ...g, rab_ny: rab[g.kg] ?? g.rab_nu, netto_pct: netto[g.kg] ?? 0 })), [data, rab, netto]);

  const flush = useCallback(async () => {
    const body = pending.current; pending.current = { rab: {}, netto: {}, comments: {} };
    if (!Object.keys(body.rab).length && !Object.keys(body.netto).length && !Object.keys(body.comments).length) return;
    try { await api.negAdjust(id!, body); setIns(null); } catch (e: any) { setErr(e.message); }
  }, [id]);
  const queue = (kind: "rab" | "netto" | "comments", kg: string, v: any) => {
    (pending.current[kind] as any)[kg] = v;
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(flush, 600);
  };
  const setGroupRab = (g: Group, v: number | null) => {
    setRab((r) => ({ ...r, [g.kg]: v == null ? g.rab_nu : v }));
    queue("rab", g.kg, v == null || v === g.rab_nu ? null : v);
  };
  const setGroupNetto = (g: Group, v: number | null) => {
    setNetto((r) => { const n = { ...r }; if (v) n[g.kg] = v; else delete n[g.kg]; return n; });
    queue("netto", g.kg, v || null);
  };

  if (!neg) return <main>{err ? <p className="error">{err}</p> : tr("Laddar…")}</main>;
  const T = Object.fromEntries(BASKETS.map((b) => [b, groups.length ? sum(groups.map((g) => calc(g, b))) : null]));

  return (
    <main>
      <style>{VIZ_CSS}</style>
      <p className="small no-print"><Link to="/kam">← {tr("KAM")}</Link></p>
      <h1 style={{ marginBottom: 4 }}>{neg.name} <span className="badge">{tr(STATUS[neg.status] || neg.status)}</span></h1>
      <p className="muted small">{trf("Kund {0} · kundnr {1} · gäller från {2}", neg.customer || "–", neg.kundnr || "–", neg.valid_from || "–")} · <span className="warn">{tr("Simulerad – ingen M3-koppling, underlaget läses ur filer")}</span></p>
      <div className="row no-print" style={{ gap: 6, flexWrap: "wrap", margin: "10px 0" }}>
        {([["underlag", "Underlag"], ["oversikt", "Översikt"], ["justering", "Justeringsvy"], ["insikter", "Insikter och förslag"], ["kund", "Kundpresentation"], ["attest", "Attest och export"]] as const).map(([k, l]) => (
          <button key={k} className={tab === k ? "small" : "ghost small"} disabled={k !== "underlag" && !data?.groups?.length} onClick={() => setTab(k)}>{tr(l)}</button>))}
      </div>
      {err && <p className="error small">{err} <button className="ghost small" onClick={() => setErr("")}>×</button></p>}

      {tab === "underlag" && <Underlag neg={neg} setNeg={setNeg} busy={busy} setBusy={setBusy} setErr={setErr} reload={async () => { await loadNeg(); await loadData(); setIns(null); }} />}
      {tab === "oversikt" && data && <Oversikt groups={groups} T={T} names={data.basket_names} ins={ins} go={(kg) => { setTab("justering"); window.setTimeout(() => window.dispatchEvent(new CustomEvent("kam-search", { detail: kg })), 0); }} />}
      {tab === "justering" && data && <Justering negId={id!} groups={groups} T={T} names={data.basket_names} segments={data.segments} ins={ins} editable={!!editable}
        comments={comments} setComment={(kg: string, v: string) => { setComments((c) => ({ ...c, [kg]: v })); queue("comments", kg, v); }}
        setGroupRab={setGroupRab} setGroupNetto={setGroupNetto} />}
      {tab === "insikter" && data && <Insikter negId={id!} ins={ins} editable={!!editable} groups={groups} reload={async () => { await flush(); await loadData(); await loadIns(); }} setErr={setErr}
        go={(kg: string) => { setTab("justering"); window.setTimeout(() => window.dispatchEvent(new CustomEvent("kam-search", { detail: kg })), 0); }} />}
      {tab === "kund" && data && <Kund neg={neg} groups={groups} T={T} supplier={data.supplier_info} flush={flush} />}
      {tab === "attest" && <Attest neg={neg} role={role} T={T} setNeg={setNeg} flush={flush} setErr={setErr} />}
    </main>
  );
}

// ---------------------------------------------------------------- underlag

const NEEDS: { key: string; label: string; ok: (s: any) => boolean; what: string }[] = [
  { key: "nya", label: "Nya priser (prisgrund nu/NY, brutto NY, ny kalkylgrupp)", ok: (s) => s.with_pg > 0 && s.with_brutto_ny > 0, what: "Bladet Nya priser ur arbetsboken, eller en fil med Artnr, Kalkgr NY, Prisgrund nu, Prisgrund NY, Brutto NY" },
  { key: "brutto", label: "Brutto nu och nuvarande kalkylgrupp", ok: (s) => s.with_brutto_nu > 0, what: "Arbetsboken (Varukorgsanalys) eller prisfilen till kund (Dahlpris: Rsknr, Rabgr, GNP)" },
  { key: "rab", label: "Kundens rabattbrev", ok: (s) => s.rabattbrev > 0, what: "Rabattbrevet som .txt ur M3 eller bladet Rabattbrev" },
  { key: "kund", label: "Antal sålda R12 – kundens varukorg", ok: (s) => s.baskets?.kund > 0, what: "Bladet Antal sålda (Artnr, Antal sålda)" },
  { key: "riks", label: "Antal sålda R12 – riksåterförsäljare (jämförelse)", ok: (s) => s.baskets?.riks > 0, what: "Andra korgen i Antal sålda" },
  { key: "bonus", label: "Bonusförutsättningar", ok: (s) => s.bonus_scenarios > 0, what: "Bladet Bonusförutsättningar (scenarier och avvikelsegrupper)" },
  { key: "stod", label: "Stöttningar", ok: (s) => s.support > 0, what: "Bladet Stöttningar" },
  { key: "unika", label: "Kundunika BP och nettopriser", ok: (s) => s.kund_bp + s.kund_netto > 0, what: "Bladet Kundunika BP & Nettopriser" },
  { key: "villkor", label: "Försäljningsvillkor (månads-/kvartalspris)", ok: (s) => s.monthly > 0, what: "Bladet Försäljningsvillkor" },
  { key: "hier", label: "Artikelregister (produktområde, kategori, leverantör)", ok: (s) => s.hierarchy > 0, what: "Artikel Data / Artikelregister" },
  { key: "seg", label: "Segmentkorgar (BRV per segment R12)", ok: (s) => Object.keys(s.segments || {}).length > 0, what: "Korg-filerna (Artikelnr, BRV % Akt R12, Antal total Akt R12)" },
  { key: "lev", label: "Leverantörernas prisförändringar (till kundpresentationen)", ok: (s) => s.supplier_info > 0, what: "Tabell med Leverantör, Prisförändring, Volym, Kommentar" },
];

function Underlag({ neg, setNeg, busy, setBusy, setErr, reload }: any) {
  const [files, setFiles] = useState<File[]>([]);
  const [meta, setMeta] = useState({ name: neg.name, customer: neg.customer, kundnr: neg.kundnr, valid_from: neg.valid_from });
  const s = neg.data_status || {};
  const running = neg.job?.state === "running";
  const upload = async () => {
    setBusy("up"); setErr("");
    try { setNeg(await api.negUpload(neg.id, files)); setFiles([]); } catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  };
  return (
    <div className="row" style={{ gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
      <section className="card" style={{ flex: "1 1 520px", padding: 14 }}>
        <h2 style={{ marginTop: 0 }}>{tr("Läs in underlaget")}</h2>
        <p className="small muted">{tr("Välj alla filer på en gång: den befintliga arbetsboken för prisförhandlingen (.xlsm), artikelregistret, korgfilerna, rabattbrevet (.txt), prisgrunden (.xlsb) och prisfilen. Filerna känns igen på sina kolumner; arbetsboken läses blad för blad och bara indatabladen används.")}</p>
        <input type="file" multiple accept=".xlsx,.xlsm,.xlsb,.txt,.csv" disabled={running || !!busy} onChange={(e) => setFiles(Array.from(e.target.files || []))} />
        {files.length > 0 && <p className="small">{files.map((f) => `${f.name} (${(f.size / 1e6).toFixed(1)} MB)`).join(" · ")}</p>}
        <div className="row" style={{ gap: 8, marginTop: 8 }}>
          <button className="small" disabled={!files.length || running || !!busy} onClick={upload}>{busy === "up" ? tr("Laddar upp…") : tr("Läs in")}</button>
          {neg.files?.length > 0 && <button className="ghost small" disabled={running} onClick={async () => { if (confirm(tr("Töm underlaget? Justeringarna sparas."))) { setNeg(await api.negReset(neg.id)); await reload(); } }}>{tr("Töm underlaget")}</button>}
        </div>
        {neg.job?.state && <p className={`small ${neg.job.state === "error" ? "error" : ""}`} style={{ marginTop: 8 }}>
          {running ? "⏳ " : neg.job.state === "done" ? "✓ " : ""}{neg.job.step}{neg.job.state === "done" && neg.job.groups ? ` – ${trf("{0} artiklar i {1} kalkylgrupper", neg.job.articles, neg.job.groups)}` : ""}
          {neg.job.unknown?.length > 0 && <span className="warn"> · {trf("Kändes inte igen: {0}", neg.job.unknown.join(", "))}</span>}</p>}
        <h3>{tr("Vad underlaget innehåller")}</h3>
        <table className="qty small"><tbody>
          {NEEDS.map((n) => { const ok = n.ok(s); return (
            <tr key={n.key}><td>{ok ? <span className="badge ok small">✓</span> : <span className="badge warn small">!</span>}</td><td>{tr(n.label)}</td><td className="muted">{ok ? "" : tr(n.what)}</td></tr>); })}
        </tbody></table>
        {s.computed_articles > 0 && <p className="small muted">{trf("{0} artiklar räknade, {1} kalkylgrupper. Utan prisunderlag (räknas inte): kund {2}, riks {3}.", s.computed_articles, s.groups, s.missing_in_price_base?.kund ?? 0, s.missing_in_price_base?.riks ?? 0)}</p>}
        {neg.files?.length > 0 && <details><summary className="small">{trf("Inlästa filer ({0})", neg.files.length)}</summary>
          <ul className="small">{neg.files.map((f: any, i: number) => <li key={i}>{f.name}: {f.kinds.join(", ") || tr("kändes inte igen")} <span className="muted">{(f.at || "").slice(0, 16).replace("T", " ")}</span></li>)}</ul></details>}
      </section>
      <section className="card" style={{ flex: "0 1 340px", padding: 14 }}>
        <h2 style={{ marginTop: 0 }}>{tr("Uppgifter")}</h2>
        {(["name", "customer", "kundnr", "valid_from"] as const).map((k) => (
          <label key={k} className="small" style={{ display: "block", marginBottom: 6 }}>{tr({ name: "Namn", customer: "Kund", kundnr: "Kundnummer", valid_from: "Gäller från" }[k])}<br />
            <input value={(meta as any)[k] || ""} onChange={(e) => setMeta({ ...meta, [k]: e.target.value })} style={{ width: "100%" }} /></label>))}
        <button className="secondary small" onClick={async () => { try { setNeg(await api.negUpdate(neg.id, meta)); } catch (e: any) { setErr(e.message); } }}>{tr("Spara")}</button>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------- översikt

function Kpis({ c, title }: { c: Calc | null; title: string }) {
  if (!c) return null;
  return (
    <section style={{ marginBottom: 14 }}>
      <h3 style={{ margin: "0 0 6px" }}>{title}</h3>
      <div className="kam-kpi">
        <div><span className="small muted">{tr("Netnet nu (Mkr)")}</span><b>{mkr(c.nn_nu)}</b></div>
        <div><span className="small muted">{tr("Netnet NY (Mkr)")}</span><b>{mkr(c.nn_ny)}</b></div>
        <div><span className="small muted">{tr("Prisförändring")}</span><b>{pct(c.prisdiff, 2)}</b></div>
        <div><span className="small muted">{tr("Inprisförändring")}</span><b>{pct(c.inprisdiff, 2)}</b></div>
        <div><span className="small muted">{tr("BRV nu → NY")}</span><b>{plain(c.brv_nu)} → {plain(c.brv_ny)}</b></div>
        <div><span className="small muted">{tr("BRV-förändring (%-enheter)")}</span><b>{pp(c.brv_diff)}</b></div>
      </div>
    </section>
  );
}

function areas(groups: Group[]) {
  const m = new Map<string, { omr: string; name: string; k: Calc[]; r: Calc[] }>();
  for (const g of groups) {
    const a = m.get(g.omr) || { omr: g.omr, name: g.omr_name, k: [], r: [] };
    a.k.push(calc(g, "kund")); a.r.push(calc(g, "riks")); if (!a.name && g.omr_name) a.name = g.omr_name;
    m.set(g.omr, a);
  }
  return [...m.values()].map((a) => ({ omr: a.omr, name: a.name, k: sum(a.k), r: sum(a.r) })).filter((a) => a.k.nn_nu > 0 || a.r.nn_nu > 0);
}

function Oversikt({ groups, T, names, ins, go }: { groups: Group[]; T: Record<string, Calc | null>; names: Record<string, string>; ins: any[] | null; go: (kg: string) => void }) {
  const ar = useMemo(() => areas(groups).sort((a, b) => b.k.nn_nu - a.k.nn_nu), [groups]);
  const totK = T.kund?.nn_nu || 0, totR = T.riks?.nn_nu || 0;
  const top = useMemo(() => groups.map((g) => ({ g, c: calc(g, "kund") })).filter((x) => x.c.nn_nu > 0).sort((a, b) => Math.abs(b.c.nn_ny - b.c.nn_nu) - Math.abs(a.c.nn_ny - a.c.nn_nu)).slice(0, 12), [groups]);
  const counts = useMemo(() => { const c: Record<string, number> = {}; (ins || []).forEach((i) => i.flags.forEach((f: any) => { c[f.code] = (c[f.code] || 0) + 1; })); return c; }, [ins]);
  return (
    <div>
      {BASKETS.map((b) => T[b] && T[b]!.nn_nu > 0 && <Kpis key={b} c={T[b]} title={tr(names[b] || b)} />)}
      {ins && <div className="row small" style={{ gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
        {Object.entries(counts).map(([k, v]) => <span key={k} className={`badge ${k === "UNDER_KOSTPRIS" ? "error" : k === "MANADSPRIS" || k === "NY_GRUPP" || k === "KALKGR_FLYTT" ? "" : "warn"}`}>{tr(FLAG[k] || k)}: {v}</span>)}</div>}
      <div className="row" style={{ gap: 16, flexWrap: "wrap", alignItems: "flex-start" }}>
        <section className="card" style={{ flex: "1 1 460px", padding: 14 }}>
          <h3 style={{ marginTop: 0 }}>{tr("Prisförändring mot inprisförändring per produktområde (kundens korg)")}</h3>
          <BarChart rows={ar.slice(0, 18).map((a) => ({ key: a.omr, label: a.name, values: [a.k.prisdiff, a.k.inprisdiff] }))}
            series={[{ name: tr("Prisförändring kund"), color: SERIES.a }, { name: tr("Inprisförändring"), color: SERIES.b }]} fmt={(v) => pct(v, 1)} />
        </section>
        <section className="card" style={{ flex: "1 1 460px", padding: 14 }}>
          <h3 style={{ marginTop: 0 }}>{tr("Andel av inköpen: kunden mot riksåterförsäljarna")}</h3>
          <p className="small muted" style={{ marginTop: 0 }}>{tr("Där kundens andel är mycket lägre än marknadens köper kunden troligen annanstans.")}</p>
          <BarChart rows={ar.slice(0, 18).map((a) => ({ key: a.omr, label: a.name, values: [totK ? a.k.nn_nu / totK : null, totR ? a.r.nn_nu / totR : null] }))}
            series={[{ name: tr("Kunden"), color: SERIES.a }, { name: tr("Riksåterförsäljare"), color: SERIES.b }]} fmt={(v) => plain(v, 1)} />
        </section>
      </div>
      <section className="card" style={{ padding: 14, marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>{tr("Störst förändring i kronor (kundens korg)")}</h3>
        <table className="qty small"><thead><tr><th>{tr("Kalkylgrupp")}</th><th>{tr("Benämning")}</th><th className="num">{tr("Netnet nu")}</th><th className="num">{tr("Förändring kr")}</th><th className="num">{tr("Prisdiff")}</th><th className="num">{tr("BRV nu → NY")}</th></tr></thead>
          <tbody>{top.map(({ g, c }) => <tr key={g.kg}><td><button className="ghost small lf-mono" onClick={() => go(g.kg)}>{g.kg}</button></td><td>{g.name}</td><td className="num">{kr(c.nn_nu)}</td><td className="num">{kr(c.nn_ny - c.nn_nu)}</td><td className="num">{pct(c.prisdiff)}</td><td className="num">{plain(c.brv_nu)} → {plain(c.brv_ny)}</td></tr>)}</tbody></table>
        <details style={{ marginTop: 8 }}><summary className="small">{tr("Tabell per produktområde")}</summary>
          <table className="qty small"><thead><tr><th>{tr("Område")}</th><th className="num">{tr("Netnet nu")}</th><th className="num">{tr("Netnet NY")}</th><th className="num">{tr("Prisdiff")}</th><th className="num">{tr("Inprisdiff")}</th><th className="num">{tr("BRV nu")}</th><th className="num">{tr("BRV NY")}</th><th className="num">{tr("Andel kund")}</th><th className="num">{tr("Andel riks")}</th></tr></thead>
            <tbody>{ar.map((a) => <tr key={a.omr}><td><b>{a.omr}</b> {a.name}</td><td className="num">{kr(a.k.nn_nu)}</td><td className="num">{kr(a.k.nn_ny)}</td><td className="num">{pct(a.k.prisdiff)}</td><td className="num">{pct(a.k.inprisdiff)}</td><td className="num">{plain(a.k.brv_nu)}</td><td className="num">{plain(a.k.brv_ny)}</td><td className="num">{totK ? plain(a.k.nn_nu / totK, 2) : "–"}</td><td className="num">{totR ? plain(a.r.nn_nu / totR, 2) : "–"}</td></tr>)}</tbody></table></details>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------- justeringsvyn

type Level = "kg" | "kat" | "omr";
function Justering({ negId, groups, T, names, segments, ins, editable, comments, setComment, setGroupRab, setGroupNetto }: any) {
  const [q, setQ] = useState("");
  const [omr, setOmr] = useState("");
  const [cmp, setCmp] = useState<"riks" | "korg3">("riks");
  const [onlyVol, setOnlyVol] = useState(true);
  const [filt, setFilt] = useState("");
  const [level, setLevel] = useState<Level>("kg");
  const [sort, setSort] = useState<{ k: string; dir: number }>({ k: "nn_nu", dir: -1 });
  const [limit, setLimit] = useState(150);
  const [open, setOpen] = useState<string>("");
  const [arts, setArts] = useState<any>(null);
  const [bulk, setBulk] = useState("");
  useEffect(() => { const h = (e: any) => { setQ(e.detail); setOmr(""); setFilt(""); setLevel("kg"); }; window.addEventListener("kam-search", h); return () => window.removeEventListener("kam-search", h); }, []);
  const flagged = useMemo(() => new Map<string, any>((ins || []).map((i: any) => [i.kg, i])), [ins]);
  const segName = Object.keys(segments || {})[0];
  const omrs = useMemo(() => [...new Map<string, string>(groups.map((g: Group) => [g.omr, g.omr_name])).entries()].sort(), [groups]);

  const rows = useMemo(() => {
    const ql = q.trim().toLowerCase();
    const gs: Group[] = groups.filter((g: Group) =>
      (!onlyVol || (g.b.kund?.nn_nu || 0) > 0 || (g.b[cmp]?.nn_nu || 0) > 0) && (!omr || g.omr === omr) &&
      (!ql || g.kg.toLowerCase().includes(ql) || g.name.toLowerCase().includes(ql) || (g.leverantor || "").toLowerCase().includes(ql)) &&
      (!filt || (filt === "justerad" ? Math.abs(g.rab_ny - g.rab_nu) > 1e-9 || g.netto_pct : filt === "ny" ? g.new_group : filt === "flytt" ? g.moved > 0 : filt === "manad" ? g.month : filt === "flagg" ? flagged.has(g.kg) : flagged.get(g.kg)?.flags.some((f: any) => f.code === filt))));
    const make = (key: string, label: string, list: Group[]) => ({ key, label, list, k: sum(list.map((g) => calc(g, "kund"))), c: sum(list.map((g) => calc(g, cmp))) });
    let out: any[];
    if (level === "kg") out = gs.map((g) => ({ key: g.kg, label: g.name, list: [g], g, k: calc(g, "kund"), c: calc(g, cmp) }));
    else {
      const m = new Map<string, Group[]>();
      for (const g of gs) { const k = level === "omr" ? g.omr : g.kat; m.set(k, [...(m.get(k) || []), g]); }
      out = [...m.entries()].map(([k, l]) => make(k, level === "omr" ? l[0].omr_name : l[0].kat_name, l));
    }
    const val = (r: any) => ({ kg: r.key, nn_nu: r.k.nn_nu, nn_ny: r.k.nn_ny, prisdiff: r.k.prisdiff ?? -9, inprisdiff: r.k.inprisdiff ?? -9, brv_nu: r.k.brv_nu ?? -9, brv_ny: r.k.brv_ny ?? -9, brv_diff: r.k.brv_diff ?? -9, rab: r.g ? r.g.rab_ny - r.g.rab_nu : 0, cmp: r.c.prisdiff ?? -9 } as any)[sort.k];
    out.sort((a, b) => { const x = val(a), y = val(b); return (typeof x === "string" ? x.localeCompare(y) : x - y) * sort.dir; });
    return out;
  }, [groups, q, omr, onlyVol, filt, level, sort, cmp, flagged]);
  const sel = sum(rows.map((r: any) => r.k));
  const th = (k: string, label: string, num = true) => <th className={num ? "num" : ""} style={{ cursor: "pointer", whiteSpace: "nowrap" }} onClick={() => setSort((s) => ({ k, dir: s.k === k ? -s.dir : -1 }))}>{tr(label)}{sort.k === k ? (sort.dir > 0 ? " ▲" : " ▼") : ""}</th>;
  const drill = async (kg: string) => { if (open === kg) { setOpen(""); return; } setOpen(kg); setArts(null); try { setArts(await api.negArticles(negId, kg)); } catch { setArts({ articles: [] }); } };
  const applyBulk = () => {
    const d = Number(bulk.replace(",", ".")); if (!isFinite(d) || !d) return;
    if (!confirm(trf("Ändra rabatt NY med {0} %-enheter för {1} filtrerade kalkylgrupper?", d, rows.flatMap((r: any) => r.list).length))) return;
    rows.flatMap((r: any) => r.list).forEach((g: Group) => { if (!g.month) setGroupRab(g, Math.max(0, Math.min(99, Math.round((g.rab_ny + d) * 100) / 100))); });
    setBulk("");
  };

  return (
    <div>
      <div className="row small no-print" style={{ gap: 8, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 8 }}>
        <label>{tr("Sök")}<br /><input value={q} onChange={(e) => { setQ(e.target.value); setLimit(150); }} placeholder={tr("kalkylgrupp, benämning, leverantör")} /></label>
        <label>{tr("Produktområde")}<br /><select value={omr} onChange={(e) => setOmr(e.target.value)}><option value="">{tr("Alla")}</option>{omrs.map(([k, n]: any) => <option key={k} value={k}>{k} {n}</option>)}</select></label>
        <label>{tr("Visa")}<br /><select value={filt} onChange={(e) => setFilt(e.target.value)}>
          <option value="">{tr("Alla grupper")}</option><option value="flagg">{tr("Med avvikelse")}</option><option value="justerad">{tr("Justerade")}</option>
          {Object.keys(FLAG).map((k) => <option key={k} value={k}>{tr(FLAG[k])}</option>)}
          <option value="ny">{tr("Nya grupper")}</option><option value="flytt">{tr("Kalkylgruppsflyttar")}</option><option value="manad">{tr("Månadspris")}</option></select></label>
        <label>{tr("Nivå")}<br /><select value={level} onChange={(e) => setLevel(e.target.value as Level)}><option value="kg">{tr("Kalkylgrupp")}</option><option value="kat">{tr("Produktkategori")}</option><option value="omr">{tr("Produktområde")}</option></select></label>
        <label>{tr("Jämför med")}<br /><select value={cmp} onChange={(e) => setCmp(e.target.value as any)}><option value="riks">{tr(names.riks)}</option><option value="korg3">{tr(names.korg3)}</option></select></label>
        <label className="row" style={{ gap: 4, alignItems: "center" }}><input type="checkbox" checked={onlyVol} onChange={(e) => setOnlyVol(e.target.checked)} /> {tr("Bara grupper med försäljning")}</label>
        {editable && <span className="row" style={{ gap: 4 }}><input value={bulk} onChange={(e) => setBulk(e.target.value)} placeholder="±pp" style={{ width: 60 }} />
          <button className="ghost small" disabled={!bulk} onClick={applyBulk} title={tr("Ändrar rabatt NY för alla filtrerade grupper (inte månadspris)")}>{tr("Justera filtrerade")}</button></span>}
      </div>
      <div className="row small" style={{ gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
        <span className="badge">{trf("{0} rader", rows.length)}</span>
        <span className="badge">{trf("Urval: netnet {0} → {1} Mkr", mkr(sel.nn_nu), mkr(sel.nn_ny))}</span>
        <span className="badge">{trf("Prisdiff {0} · inpris {1}", pct(sel.prisdiff, 2), pct(sel.inprisdiff, 2))}</span>
        <span className="badge">{trf("BRV {0} → {1}", plain(sel.brv_nu, 2), plain(sel.brv_ny, 2))}</span>
        <span className="badge">{trf("Hela kundkorgen: prisdiff {0}, BRV {1} → {2}", pct(T.kund?.prisdiff, 2), plain(T.kund?.brv_nu, 2), plain(T.kund?.brv_ny, 2))}</span>
      </div>
      <div className="tablewrap kam-sticky" style={{ overflow: "auto", maxHeight: "68vh" }}>
        <table className="qty small">
          <thead><tr>
            {th("kg", level === "kg" ? "Kalkylgrupp" : level === "kat" ? "Kategori" : "Område", false)}<th>{tr("Benämning")}</th>
            {level === "kg" && <><th className="num">{tr("Rabatt nu")}</th><th className="num">{tr("Rabatt NY")}</th>{th("rab", "Diff")}</>}
            {th("nn_nu", "Netnet nu")}{th("nn_ny", "Netnet NY")}{th("prisdiff", "Prisdiff")}{th("inprisdiff", "Inpris")}{th("brv_nu", "BRV nu")}{th("brv_ny", "BRV NY")}{th("brv_diff", "BRV diff")}
            {th("cmp", "Prisdiff jmf")}<th className="num">{tr("BRV NY jmf")}</th>{segName && level === "kg" && <th className="num" title={segName}>{tr("BRV segment")}</th>}<th>{tr("Info")}</th>
          </tr></thead>
          <tbody>{rows.slice(0, limit).map((r: any) => {
            const g: Group | undefined = r.g; const f = flagged.get(r.key);
            const adj = g && (Math.abs(g.rab_ny - g.rab_nu) > 1e-9 || g.netto_pct);
            return (<Fragment key={r.key}>
              <tr style={adj ? { background: "var(--hl, rgba(37,125,224,.07))" } : undefined}>
                <td className="lf-mono">{level === "kg" ? <button className="ghost small" onClick={() => drill(r.key)} title={tr("Visa artiklarna")}>{open === r.key ? "▾" : "▸"} {r.key}</button> : <b>{r.key}</b>}</td>
                <td style={{ maxWidth: 240 }}>{r.label}{g?.leverantor ? <div className="muted" style={{ fontSize: 11 }}>{g.leverantor}</div> : null}</td>
                {g && <>
                  <td className="num">{g.rab_nu}{g.rab_old != null && g.rab_old !== g.rab_nu ? <div className="muted" style={{ fontSize: 11 }}>{trf("fg år {0}", g.rab_old)}</div> : null}</td>
                  <td className="num">{editable && !g.month && (g.b.kund?.lin_a || 0) + (g.b[cmp]?.lin_a || 0) > 0
                    ? <input className="kam-input" type="number" step="0.5" min={0} max={99} value={g.rab_ny} onChange={(e) => setGroupRab(g, e.target.value === "" ? null : Number(e.target.value))} />
                    : g.rab_ny}
                    {(g.b.kund?.lin_f || 0) > 0 && <div style={{ fontSize: 11 }}>{tr("netto")} {editable
                      ? <input className="kam-input" type="number" step="0.5" value={g.netto_pct ? Math.round(g.netto_pct * 1000) / 10 : ""} placeholder="±%" onChange={(e) => setGroupNetto(g, e.target.value === "" ? null : Number(e.target.value) / 100)} />
                      : pct(g.netto_pct)}</div>}</td>
                  <td className="num">{pp((g.rab_ny - g.rab_nu) / 100)}</td></>}
                <td className="num">{kr(r.k.nn_nu)}</td><td className="num">{kr(r.k.nn_ny)}</td>
                <td className="num">{pct(r.k.prisdiff)}</td><td className="num">{pct(r.k.inprisdiff)}</td>
                <td className="num">{plain(r.k.brv_nu)}</td><td className={`num ${r.k.brv_ny != null && r.k.brv_ny < 0 ? "error" : ""}`}>{plain(r.k.brv_ny)}</td><td className="num">{pp(r.k.brv_diff)}</td>
                <td className="num">{pct(r.c.prisdiff)}</td><td className="num">{plain(r.c.brv_ny)}</td>
                {segName && level === "kg" && <td className="num">{plain(segments[segName]?.[r.key]?.brv)}</td>}
                <td style={{ maxWidth: 220 }}>
                  {g?.month && <span className="badge small">{tr("Månadspris")}</span>}{g?.new_group && <span className="badge small">{tr("Ny grupp")}</span>}{g && g.moved > 0 && <span className="badge small">{trf("{0} flyttade", g.moved)}</span>}
                  {f?.flags.filter((x: any) => !["MANADSPRIS", "NY_GRUPP", "KALKGR_FLYTT"].includes(x.code)).map((x: any) => <span key={x.code} className={`badge small ${SEV[x.sev]}`} title={x.text}>{tr(FLAG[x.code] || x.code)}</span>)}
                  {f?.suggestion && editable && g && <button className="ghost small" title={f.suggestion.why} onClick={() => f.suggestion.type === "netto" ? setGroupNetto(g, f.suggestion.pct) : setGroupRab(g, f.suggestion.rab)}>{f.suggestion.type === "netto" ? trf("Förslag netto {0}", pct(f.suggestion.pct)) : trf("Förslag {0} %", f.suggestion.rab)}</button>}
                </td>
              </tr>
              {open === r.key && g && <tr><td colSpan={17} style={{ background: "var(--panel, rgba(0,0,0,.02))" }}>
                <label className="small" style={{ display: "block", marginBottom: 6 }}>{tr("Kommentar")}<br />
                  <input style={{ width: "100%" }} disabled={!editable} value={comments[g.kg] || ""} onChange={(e) => setComment(g.kg, e.target.value)} placeholder={tr("t.ex. överenskommet på kategorimötet")} /></label>
                {!arts ? <span className="muted small">{tr("Laddar artiklar…")}</span> : (
                  <table className="qty small"><thead><tr><th>{tr("Artikel")}</th><th>{tr("Benämning")}</th><th className="num">{tr("Antal R12")}</th><th className="num">{tr("Brutto nu → NY")}</th><th className="num">{tr("Netnet nu → NY")}</th><th className="num">{tr("Prisdiff")}</th><th className="num">{tr("BRV nu → NY")}</th><th>{tr("Info")}</th></tr></thead>
                    <tbody>{arts.articles.slice(0, 60).map((a: any) => <tr key={a.artnr}><td className="lf-mono">{a.artnr}</td><td>{a.namn}</td><td className="num">{kr(a.qty?.kund)}</td>
                      <td className="num">{kr(a.brutto_nu)} → {kr(a.brutto_ny)}</td><td className="num">{a.nn_nu.toFixed(2)} → {a.nn_ny.toFixed(2)}</td><td className="num">{pct(a.prisdiff)}</td>
                      <td className={`num ${a.brv_ny != null && a.brv_ny < 0 ? "error" : ""}`}>{plain(a.brv_nu)} → {plain(a.brv_ny)}</td>
                      <td>{a.netto_unikt && <span className="badge small">{tr("kundunikt netto")}</span>}{a.moved && <span className="badge small">{trf("från {0}", a.kg_nu)}</span>}</td></tr>)}</tbody></table>)}
                {arts?.articles.length > 60 && <p className="muted small">{trf("Visar 60 av {0} artiklar (störst volym först).", arts.articles.length)}</p>}
              </td></tr>}
            </Fragment>);
          })}</tbody>
        </table>
      </div>
      {rows.length > limit && <button className="ghost small" onClick={() => setLimit(limit + 300)}>{trf("Visa fler ({0} kvar)", rows.length - limit)}</button>}
    </div>
  );
}

// ---------------------------------------------------------------- insikter

function Insikter({ negId, ins, editable, groups, reload, setErr, go }: any) {
  const [code, setCode] = useState("");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  if (!ins) return <p className="muted">{tr("Analyserar…")}</p>;
  const gm = new Map<string, Group>(groups.map((g: Group) => [g.kg, g]));
  const list = ins.filter((i: any) => !code || i.flags.some((f: any) => f.code === code));
  const withSugg = list.filter((i: any) => i.suggestion);
  const apply = async (kgs: string[]) => {
    setBusy(true);
    try { await api.negApply(negId, kgs); await reload(); setSel(new Set()); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <div>
      <p className="small muted" style={{ maxWidth: 900 }}>{tr("Varje kalkylgrupp jämförs med inpriset, med kundens tidigare marginal, med riksåterförsäljarnas inköp och med segmentkorgarna. Förslagen räknas fram exakt (rabatten som ger målet), avrundas till halva procent och begränsas till ±5 %-enheter. Inget förs in förrän du väljer det.")}</p>
      <div className="row small" style={{ gap: 8, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 8 }}>
        <label>{tr("Typ")}<br /><select value={code} onChange={(e) => setCode(e.target.value)}><option value="">{tr("Alla")}</option>{Object.keys(FLAG).map((k) => <option key={k} value={k}>{tr(FLAG[k])}</option>)}</select></label>
        {editable && <>
          <button className="small" disabled={busy || !sel.size} onClick={() => apply([...sel])}>{trf("För in valda förslag ({0})", sel.size)}</button>
          <button className="secondary small" disabled={busy || !withSugg.length} onClick={() => { if (confirm(trf("För in alla {0} förslag i urvalet?", withSugg.length))) apply(withSugg.map((i: any) => i.kg)); }}>{trf("För in alla i urvalet ({0})", withSugg.length)}</button></>}
      </div>
      <div className="tablewrap" style={{ overflow: "auto", maxHeight: "70vh" }}>
        <table className="qty small"><thead><tr><th></th><th>{tr("Kalkylgrupp")}</th><th>{tr("Benämning")}</th><th className="num">{tr("Volym kund")}</th><th>{tr("Avvikelser")}</th><th className="num">{tr("Rabatt nu / NY")}</th><th>{tr("Förslag")}</th><th className="num">{tr("Effekt")}</th></tr></thead>
          <tbody>{list.slice(0, 400).map((i: any) => { const g = gm.get(i.kg); const s = i.suggestion; return (
            <tr key={i.kg}>
              <td>{s && editable && <input type="checkbox" checked={sel.has(i.kg)} onChange={(e) => { const n = new Set(sel); if (e.target.checked) n.add(i.kg); else n.delete(i.kg); setSel(n); }} />}</td>
              <td><button className="ghost small lf-mono" onClick={() => go(i.kg)}>{i.kg}</button></td><td>{i.name}</td><td className="num">{kr(i.volume)}</td>
              <td style={{ maxWidth: 420 }}>{i.flags.map((f: any) => <div key={f.code}><span className={`badge small ${SEV[f.sev]}`}>{tr(FLAG[f.code] || f.code)}</span> <span className="muted">{f.text}</span></div>)}</td>
              <td className="num">{g ? `${g.rab_nu} / ${g.rab_ny}` : ""}</td>
              <td>{s ? <><b>{s.type === "netto" ? trf("Nettopriser {0}", pct(s.pct)) : trf("Rabatt {0} %", s.rab)}</b><div className="muted">{s.why}</div></> : <span className="muted">{tr("Bedöm manuellt")}</span>}</td>
              <td className="num">{s ? <>{trf("prisdiff {0}", pct(s.prisdiff))}<br />{trf("BRV {0}", plain(s.brv_ny))}</> : ""}</td>
            </tr>); })}</tbody></table>
      </div>
      {list.length > 400 && <p className="muted small">{trf("Visar 400 av {0}. Filtrera på typ för att se resten.", list.length)}</p>}
    </div>
  );
}

// ---------------------------------------------------------------- kundpresentation

function Kund({ neg, groups, T, supplier, flush }: any) {
  const ar = useMemo(() => areas(groups).filter((a) => a.k.nn_nu > 0).sort((a, b) => b.k.nn_nu - a.k.nn_nu), [groups]);
  const changed = groups.filter((g: Group) => Math.abs(g.rab_ny - g.rab_nu) > 1e-9 && (g.b.kund?.nn_nu || 0) > 0);
  const k = T.kund as Calc, r = T.riks as Calc | null;
  const dl = async (path: string, name: string) => { await flush(); save(await (api as any).fetchBlob(path), name); };
  return (
    <div>
      <div className="row no-print" style={{ gap: 6, marginBottom: 10, flexWrap: "wrap" }}>
        <button className="small" onClick={() => window.print()}>{tr("Skriv ut / spara som PDF")}</button>
        <button className="secondary small" onClick={() => dl(`/api/kam/negotiations/${neg.id}/export.xlsx?kind=kund`, "prisjustering_kund.xlsx")}>{tr("Excel till kunden")}</button>
        <button className="secondary small" onClick={() => dl(`/api/kam/negotiations/${neg.id}/rabattbrev.txt`, "rabattbrev.txt")}>{tr("Nytt rabattbrev (.txt)")}</button>
        <span className="small muted">{tr("Kundvyn visar aldrig inpris, stöttning eller marginal.")}</span>
      </div>
      <section className="card kam-present" style={{ padding: 24, maxWidth: 980 }}>
        <p className="muted small" style={{ margin: 0 }}>{tr("Prisjustering")} {neg.valid_from ? `· ${trf("gäller från {0}", neg.valid_from)}` : ""}</p>
        <h2 style={{ margin: "4px 0 14px" }}>{neg.customer || neg.name}</h2>
        <div className="kam-kpi" style={{ marginBottom: 18 }}>
          <div><span className="small muted">{tr("Er inköpsvolym R12, nuvarande priser")}</span><b>{mkr(k.nn_nu)} {tr("Mkr")}</b></div>
          <div><span className="small muted">{tr("Samma volym med nya priser")}</span><b>{mkr(k.nn_ny)} {tr("Mkr")}</b></div>
          <div><span className="small muted">{tr("Prisförändring på er varukorg")}</span><b>{pct(k.prisdiff, 1)}</b></div>
          {r && r.nn_nu > 0 && <div><span className="small muted">{tr("Marknadens prisförändring (riksåterförsäljare)")}</span><b>{pct(r.prisdiff, 1)}</b></div>}
        </div>
        <h3>{tr("Prisförändring per produktområde")}</h3>
        <BarChart rows={ar.slice(0, 20).map((a) => ({ key: a.omr, label: a.name, values: [a.k.prisdiff] }))} series={[{ name: tr("Prisförändring"), color: SERIES.a }]} fmt={(v) => pct(v, 1)} />
        <table className="qty small" style={{ marginTop: 10 }}><thead><tr><th>{tr("Område")}</th><th className="num">{tr("Volym nu (kr)")}</th><th className="num">{tr("Volym ny (kr)")}</th><th className="num">{tr("Förändring")}</th></tr></thead>
          <tbody>{ar.map((a) => <tr key={a.omr}><td><b>{a.omr}</b> {a.name}</td><td className="num">{kr(a.k.nn_nu)}</td><td className="num">{kr(a.k.nn_ny)}</td><td className="num">{pct(a.k.prisdiff)}</td></tr>)}</tbody></table>
        {supplier?.length > 0 && <>
          <h3>{tr("Leverantörernas prisförändringar")}</h3>
          <table className="qty small"><thead><tr><th>{tr("Leverantör")}</th><th className="num">{tr("Förändring")}</th><th>{tr("Volym")}</th><th>{tr("Bakgrund")}</th></tr></thead>
            <tbody>{supplier.map((s: any, i: number) => <tr key={i}><td>{s.leverantor}</td><td className="num">{pct(s.change)}</td><td>{s.volym}</td><td style={{ maxWidth: 520 }}>{s.kommentar}</td></tr>)}</tbody></table></>}
        {changed.length > 0 && <>
          <h3>{tr("Ändrade rabatter")}</h3>
          <table className="qty small"><thead><tr><th>{tr("Kalkylgrupp")}</th><th>{tr("Benämning")}</th><th className="num">{tr("Rabatt nu")}</th><th className="num">{tr("Ny rabatt")}</th></tr></thead>
            <tbody>{changed.map((g: Group) => <tr key={g.kg}><td className="lf-mono">{g.kg}</td><td>{g.name}</td><td className="num">{g.rab_nu} %</td><td className="num"><b>{g.rab_ny} %</b></td></tr>)}</tbody></table></>}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------- attest

function Attest({ neg, role, T, setNeg, flush, setErr }: any) {
  const act = async (a: "submit" | "approve" | "reject" | "register") => {
    await flush();
    const comment = a === "reject" ? (prompt(tr("Varför avslås förhandlingen?")) || "") : "";
    if (a === "register" && !confirm(tr("Registrera kundens nya rabatter? De ersätter kundens rabatter i offertdatan."))) return;
    try { setNeg(await api.negAction(neg.id, a, comment)); } catch (e: any) { setErr(e.message); }
  };
  const editable = neg.status === "utkast" || neg.status === "avslagen";
  return (
    <section className="card" style={{ padding: 14, maxWidth: 900 }}>
      <h2 style={{ marginTop: 0 }}>{tr("Attest och export")}</h2>
      {T.kund && <p className="small">{trf("Kundens korg: prisdiff {0}, BRV {1} → {2}, {3} justerade grupper.", pct(T.kund.prisdiff, 2), plain(T.kund.brv_nu, 2), plain(T.kund.brv_ny, 2), neg.n_adjusted)}</p>}
      <div className="row small" style={{ gap: 6, flexWrap: "wrap" }}>
        {editable && <button className="small" onClick={() => act("submit")}>{tr("Skicka för attest")}</button>}
        {role === "admin" && neg.status === "attest" && <><button className="small" onClick={() => act("approve")}>{tr("Attestera (säljledare)")}</button><button className="secondary small" onClick={() => act("reject")}>{tr("Avslå")}</button></>}
        {role === "admin" && neg.status === "godkand" && <button className="small" onClick={() => act("register")}>{tr("Registrera (simulerat M3)")}</button>}
        <button className="secondary small" onClick={async () => { await flush(); save(await (api as any).fetchBlob(`/api/kam/negotiations/${neg.id}/export.xlsx?kind=intern`), "prisjustering_intern.xlsx"); }}>{tr("Excel: justeringsvy och insikter (internt)")}</button>
        <button className="secondary small" onClick={async () => { await flush(); save(await (api as any).fetchBlob(`/api/kam/negotiations/${neg.id}/rabattbrev.txt?only_changed=true`), "rabattbrev_andringar.txt"); }}>{tr("Ändrade rabatter (.txt)")}</button>
      </div>
      <p className="small muted">{trf("Attest säljare: {0} · säljledare: {1}", neg.attest_saljare || "–", neg.attest_saljledare || "–")}</p>
      <h3>{tr("Historik")}</h3>
      <ul className="small">{(neg.history || []).slice().reverse().map((h: any, i: number) => <li key={i}>{h.at.slice(0, 16).replace("T", " ")} {h.by}: {h.what}</li>)}</ul>
    </section>
  );
}
