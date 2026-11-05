import { useEffect, useMemo, useState } from "react";
import { t as tr, locale, num as exakt } from "../i18n";
import { api } from "../api";
import { Accounts, Content, Crm, Experiments, Heatmap, Partners } from "../components/AdminBusiness";
import { Messages } from "../components/AdminMessages";
import { AgentRecipes, Corrections, Learning, LearnedRules, Readings, RulesMoved } from "../components/AdminReading";
import { RulesCatalogue } from "../components/AdminRules";
import { Assumptions } from "../components/AdminSettings";
import { SystemHealth } from "../components/AdminSystem";
import { ApiBudget } from "../components/AdminApiBudget";

/* Att driva tjänsten.
 *
 * Portalen har tre delar som aldrig får blandas ihop. Läsningen: vad som lästs, hur det gick, vad kunder rättat,
 * vad rättelserna lärt, och reglerna och antagandena läsningen går efter. Företaget: konton, planer, partners,
 * provision, innehåll och prov. Systemet: vad som kör och hur det mår.
 *
 * Ingenting på företagssidan får avgöra hur en ritning läses. Den dagen en rabattsats kan flytta en meter går
 * det inte längre att svara på varför en mängd blev som den blev, och hela systemet står och faller på att den
 * frågan går att besvara. Reglerna bor här av motsatt skäl: en flyttad regel gäller varje ritning tjänsten
 * läser härnäst, och den som flyttar den ska stå för det med namn, skäl och bild.
 */

type Section = "overblick" | "lasningar" | "rattelser" | "inlarning" | "recept" | "regler_larda" | "regler" | "antaganden"
  | "konton" | "partners" | "crm" | "meddelanden" | "innehall" | "prov" | "heatmap" | "system" | "ai_kostnad";

const SECTIONS: { id: Section; label: string; group: string; lead: string }[] = [
  { id: "overblick", label: "Överblick", group: "Läsningen", lead: "Hur läsningen mår, och vad som väntar på någon." },
  { id: "lasningar", label: "Läsningar", group: "Läsningen", lead: "Varje blad som lästs: hur långt läsningen kom och hur lång tid det tog." },
  { id: "rattelser", label: "Rättelser", group: "Läsningen", lead: "Vad kunderna rättat, efter slag. En rättelse är ett påstående om att läsningen hade fel." },
  { id: "inlarning", label: "Inlärning", group: "Läsningen", lead: "Vad rättelserna lärt: sex nycklar, aldrig träning, alltid spårbart till en person och ett blad." },
  { id: "recept", label: "Agentens recept", group: "Läsningen", lead: "Lösningar agenten hittat och som personen lät stå. Delas med agenten på alla konton - metoden, aldrig ritningen - och rangordnas efter hur ofta de höll." },
  { id: "regler_larda", label: "Lärda regler", group: "Läsningen", lead: "Agentens lösningar skrivna som regler. De prövas mot kontrollerade ritningar; när en klarat spärren aktiverar du den, och den gäller sedan alla läsningar." },
  { id: "regler", label: "Regler", group: "Läsningen", lead: "Varje gräns läsningen använder, med skäl och figur. En flyttad regel gäller nästa läsning, för alla." },
  { id: "antaganden", label: "Antaganden", group: "Läsningen", lead: "Hur det lästa räknas ihop till en mängd: våningshöjd, stigare, skrafferade ytor." },
  { id: "konton", label: "Konton", group: "Företaget", lead: "Kontona, deras planer och vad de betalar. Ingenting här når läsningen." },
  { id: "partners", label: "Partners", group: "Företaget", lead: "Vilka som hänvisat kunder, vad de tjänat på det, och vad som är utbetalt." },
  { id: "crm", label: "Kundvård", group: "Företaget", lead: "Anteckningar per konto: vad som sagts, lovats och väntar." },
  { id: "meddelanden", label: "Meddelanden", group: "Företaget", lead: "Det som skrivits på kontaktsidan, och tjänstens egna varningar om AI-budgeten: vem, vad, och om någon svarat." },
  { id: "innehall", label: "Innehåll", group: "Företaget", lead: "Texterna på landningssidan och i dokumentationen, redigerbara utan en driftsättning." },
  { id: "prov", label: "A/B-prov", group: "Företaget", lead: "Två varianter av samma sak, och vilken som gick bäst." },
  { id: "heatmap", label: "Heatmap", group: "Företaget", lead: "Var i gränssnittet folk klickar, och var de ger upp." },
  { id: "system", label: "Systemet", group: "Systemet", lead: "Vad som kör och hur det mår: byggning, andra läsaren, kö, lager, databas." },
  { id: "ai_kostnad", label: "AI-kostnad", group: "Systemet", lead: "Den gemensamma AI-budgeten: taket (10 000 kr), prislistan och nollställningen. Alla inloggade ser förbrukningen under Credits och en varning från 80 %; när taket är nått låses AI för alla." },
];

const pct = (v: number | null | undefined) =>
  v == null ? "–" : `${exakt(v * 100, 1)} %`;
const num = (v: number | null | undefined, d = 0) =>
  v == null ? "–" : v.toLocaleString(locale(), { maximumFractionDigits: d });

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className={`adm-stat${tone ? ` ${tone}` : ""}`}>
      <div className="k">{label}</div>
      <div className="v">{value}</div>
      {sub && <div className="s">{sub}</div>}
    </div>
  );
}

/* Kurvan som säger om läsningen blir bättre, inte om marknadsföringen gör det.
 *
 * Två serier i samma bild med avsikt: staplarna är hur mycket som lästs, linjen är hur långt läsningen kom.
 * De rör sig oberoende av varandra, och det är just när de gör det man vill veta om det - en månad med dubbelt
 * så många läsningar och sjunkande täckning är en månad då något gick sönder. */
function Trend({ rows }: { rows: any[] }) {
  const W = 720, H = 190, P = 30;
  if (!rows.length) return <p className="muted">{tr("Inga läsningar i perioden.")}</p>;
  const maxR = Math.max(1, ...rows.map((r) => r.readings));
  const x = (i: number) => P + (i * (W - 2 * P)) / Math.max(1, rows.length - 1);
  const bw = Math.max(2, (W - 2 * P) / rows.length - 2);
  const withCov = rows.map((r, i) => [i, r.coverage] as const).filter(([, c]) => c != null);
  const line = withCov.map(([i, c], k) => `${k ? "L" : "M"}${x(i).toFixed(1)},${(H - P - (c as number) * (H - 2 * P)).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="adm-trend" role="img" aria-label={tr("Läsningar och täckning per dygn")}>
      {[0, 0.5, 1].map((f) => (
        <g key={f}>
          <line x1={P} x2={W - P} y1={H - P - f * (H - 2 * P)} y2={H - P - f * (H - 2 * P)} className="grid" />
          <text x={4} y={H - P - f * (H - 2 * P) + 4} className="ax">{Math.round(f * 100)}%</text>
        </g>
      ))}
      {rows.map((r, i) => (
        <g key={r.day}>
          <rect x={x(i) - bw / 2} width={bw} y={H - P - (r.readings / maxR) * (H - 2 * P) * 0.85}
            height={(r.readings / maxR) * (H - 2 * P) * 0.85} className="bar" />
          {r.failed > 0 && (
            <rect x={x(i) - bw / 2} width={bw} y={H - P - (r.failed / maxR) * (H - 2 * P) * 0.85}
              height={(r.failed / maxR) * (H - 2 * P) * 0.85} className="bar bad" />
          )}
        </g>
      ))}
      {line && <path d={line} className="cov" />}
      {withCov.map(([i, c]) => <circle key={i} cx={x(i)} cy={H - P - (c as number) * (H - 2 * P)} r="2.5" className="covdot" />)}
      <text x={P} y={H - 8} className="ax">{rows[0].day}</text>
      <text x={W - P} y={H - 8} textAnchor="end" className="ax">{rows[rows.length - 1].day}</text>
    </svg>
  );
}

/* Det som väntar på någon. Varje rad leder dit man gör något åt den; tom lista är ett svar. */
function Attention({ items, go }: { items: any[]; go: (s: Section) => void }) {
  return (
    <section className="card adm-attn">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <h3 style={{ margin: 0 }}>{tr("Att ta hand om")}</h3>
        <span className="muted small">{items.length ? `${items.length} ${items.length === 1 ? "sak" : "saker"}` : "inget väntar"}</span>
      </div>
      {items.length ? (
        <ul>
          {items.map((it) => (
            <li key={it.kind} className={it.tone}>
              <span className="dot" />
              <span className="txt">{it.text}</span>
              <button className="ghost small" onClick={() => go(it.go as Section)}>{tr("Gå dit →")}</button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted" style={{ margin: "8px 0 0" }}>{tr("Inga misslyckade läsningar, ingen kö, inga öppna utbetalningar. Bra dag.")}</p>
      )}
    </section>
  );
}

function Overview({ attention, go }: { attention: any[]; go: (s: Section) => void }) {
  const [o, setO] = useState<any>(null);
  const [timeline, setTimeline] = useState<any>(null);
  const [days, setDays] = useState(30);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.adm(`overview?days=${days}`).then(setO).catch((e) => setErr(e.message));
    api.adm(`timeline?days=${Math.max(days, 30)}`).then(setTimeline).catch(() => { /* kurvan är inte livsviktig */ });
  }, [days]);
  if (err) return <p className="error">{err}</p>;
  if (!o) return <p className="muted">{tr("Laddar…")}</p>;
  const r = o.readings, a = o.accounts;
  return (
    <>
      <div className="adm-toolbar">
        <div className="seg">
          {[7, 30, 90].map((d) => <button key={d} className={days === d ? "on" : ""} onClick={() => setDays(d)}>{d} dygn</button>)}
        </div>
      </div>
      <div className="adm-stats">
        <Stat label={tr("Läsningar")} value={num(r.total)} sub={`${num(r.done)} klara · ${num(r.failed)} misslyckade`}
          tone={r.failed > r.done * 0.1 ? "bad" : ""} />
        <Stat label={tr("Täckning i snitt")} value={pct(r.mean_coverage)}
          sub="andel rörnamn på bladet som fick meter" tone={(r.mean_coverage ?? 1) < 0.6 ? "bad" : "good"} />
        <Stat label={tr("Onämnt rör")} value={pct(r.mean_unowned_share)} sub="ritat rör som ingen beteckning nådde" />
        <Stat label={tr("Median­tid")} value={r.median_seconds ? `${num(r.median_seconds, 1)} s` : "–"} sub="per blad" />
        <Stat label="Konton" value={num(a.total)} sub={`${num(o.users.active)} har läst i perioden`} />
        <Stat label={tr("Månadsintäkt")} value={`${num(a.mrr_kr, 0)} kr`} sub="aktiva konton" tone="good" />
        <Stat label={tr("Rättelser")} value={num(o.corrections.total)} sub={`av ${num(o.corrections.people)} personer`} />
        <Stat label="Ritningar" value={num(o.drawings)} sub={`${num(o.projects)} projekt`} />
      </div>

      <div className="adm-two" style={{ marginTop: 16 }}>
        <Attention items={attention} go={go} />
        <section className="card">
          <h3 style={{ marginTop: 0 }}>{tr("Rättelser efter slag")}</h3>
          <table className="qty"><tbody>
            {Object.entries(o.corrections.by_kind).map(([k, v]: any) => (
              <tr key={k}><td>{k}</td><td className="num">{num(v)}</td></tr>
            ))}
            {!Object.keys(o.corrections.by_kind).length && <tr><td className="empty">{tr("Ingen har rättat något ännu.")}</td></tr>}
          </tbody></table>
        </section>
      </div>

      <section className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>{tr("Läsningar och täckning per dygn")}</h3>
        <p className="muted">
          Staplarna är hur mycket som lästs, den röda delen är det som misslyckades, linjen är hur långt
          läsningen kom. Att staplarna växer säger något om marknadsföringen. Att linjen sjunker säger att
          något gått sönder, och det är den enda av de två som är brådskande.
        </p>
        {timeline && <Trend rows={timeline.rows} />}
      </section>

      <section className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>Planer</h3>
        <table className="qty"><tbody>
          {Object.entries(a.by_plan).map(([k, v]: any) => (
            <tr key={k}><td>{k}</td><td className="num">{num(v)}</td></tr>
          ))}
          {!Object.keys(a.by_plan).length && <tr><td className="empty">{tr("Inga konton upplagda ännu.")}</td></tr>}
        </tbody></table>
      </section>
    </>
  );
}

function RulesSection() {
  const [view, setView] = useState<"katalog" | "kunder">("katalog");
  return (
    <>
      <div className="adm-toolbar">
        <div className="seg">
          <button className={view === "katalog" ? "on" : ""} onClick={() => setView("katalog")}>Katalogen</button>
          <button className={view === "kunder" ? "on" : ""} onClick={() => setView("kunder")}>{tr("Vad kunderna flyttat")}</button>
        </div>
      </div>
      {view === "katalog" ? <RulesCatalogue /> : <RulesMoved />}
    </>
  );
}

export default function AdminPage() {
  const [sec, setSec] = useState<Section>(() => {
    try { return (localStorage.getItem("vvs.admtab") as Section) || "overblick"; } catch { return "overblick"; }
  });
  const [role, setRole] = useState<string | null>(null);
  const [attn, setAttn] = useState<{ items: any[]; badges: Record<string, number> }>({ items: [], badges: {} });
  const groups = useMemo(() => {
    const g: Record<string, typeof SECTIONS> = {};
    SECTIONS.forEach((t) => { (g[t.group] ||= []).push(t); });
    return Object.entries(g);
  }, []);

  useEffect(() => { api.myRole().then((r) => setRole(r.role)).catch(() => setRole("member")); }, []);
  useEffect(() => {
    if (role !== "admin") return;
    api.adm("attention").then(setAttn).catch(() => { /* listan är en hjälp, inte ett krav */ });
  }, [role, sec]);
  const pick = (t: Section) => { setSec(t); try { localStorage.setItem("vvs.admtab", t); } catch { /* privat läge */ } };
  const current = SECTIONS.find((s) => s.id === sec) ?? SECTIONS[0];

  if (role === null) return <main><p className="muted">{tr("Laddar…")}</p></main>;
  if (role !== "admin") {
    return (
      <main>
        <p className="crumb">Administration</p>
        <h1>{tr("Det här är administratörens sidor")}</h1>
        <p className="lead">
          Ditt konto är {role === "partner" ? "en partner" : "en medlem"}. Partners når sin egen provision under
          Partners; resten kräver administratörsbehörighet.
        </p>
        {role === "partner" && <div style={{ marginTop: 18 }}><Partners /></div>}
      </main>
    );
  }

  const öppna = attn.items?.length ?? 0;

  return (
    <div className="admin adm-shell">
      <div className="adm-sky" aria-hidden="true" />
      <aside className="adm-nav">
        <div className="adm-brand">
          <span className="org">Administration</span>
          <span className="muted small">{öppna ? `${öppna} att se på` : "inget väntar"}</span>
        </div>
        {groups.map(([g, items]) => (
          <div key={g} className="grp">
            <span className="lbl">{g}</span>
            {items.map((t) => {
              const n = attn.badges?.[t.id] ?? 0;
              return (
                <button key={t.id} className={sec === t.id ? "on" : ""} onClick={() => pick(t.id)}>
                  <span>{t.label}</span>
                  {n > 0 && <span className="pill">{n}</span>}
                </button>
              );
            })}
          </div>
        ))}
        <p className="muted small adm-note">{tr("Ingenting på företagssidan når läsningen. Reglerna gäller varje ny läsning.")}</p>
      </aside>

      <div className="adm-main">
        <header className="adm-sec">
          <span className="eyebrow">{current.group}</span>
          <h1>{current.label}</h1>
          <p className="lead">{current.lead}</p>
        </header>
        <div className="adm-body" key={sec}>
          {sec === "overblick" && <Overview attention={attn.items} go={pick} />}
          {sec === "lasningar" && <Readings />}
          {sec === "rattelser" && <Corrections />}
          {sec === "inlarning" && <Learning />}
          {sec === "recept" && <AgentRecipes />}
          {sec === "regler_larda" && <LearnedRules />}
          {sec === "regler" && <RulesSection />}
          {sec === "antaganden" && <Assumptions />}
          {sec === "konton" && <Accounts />}
          {sec === "meddelanden" && <Messages />}
          {sec === "partners" && <Partners />}
          {sec === "crm" && <Crm />}
          {sec === "innehall" && <Content />}
          {sec === "prov" && <Experiments />}
          {sec === "heatmap" && <Heatmap />}
          {sec === "system" && <SystemHealth />}
          {sec === "ai_kostnad" && <ApiBudget />}
        </div>
      </div>
    </div>
  );
}
