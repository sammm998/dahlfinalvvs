import { useEffect, useMemo, useState } from "react";
import { t as tr } from "../i18n";
import { Link, useNavigate, useParams } from "react-router-dom";
import Exercise from "./Exercise";
import TrainingDrawing from "./TrainingDrawing";
import { ac, type Block, type ExerciseOut, type PlanData } from "./api";
import "./academy.css";

/* Dahl Academy - utbildningsportalen.
 *
 * Tre vyer, som i en riktig lärplattform: översikten (var du är, vad du fortsätter med, katalogen), kurssidan
 * (kursplanen modul för modul, vad du lär dig, tentan) och lektionen (kursplanen i sidan, texten i mitten,
 * vidare till nästa). Ljust och lugnt: en lektion ska gå att läsa i fyrtio minuter.
 */

const LEVEL: Record<string, string> = { grund: "Grundkurs", fortsattning: "Fortsättning", avancerad: "Avancerad" };

/* Varje utbildning får sitt eget omslag: en färg och en symbol ur ämnet, alltid samma för samma kurs. */
const COVERS: [RegExp, string, string][] = [
  [/vent|kanal|luft/i, "#2563eb", "vent"],
  [/jurid|ab 04|abt|avtal/i, "#7c3aed", "law"],
  [/mark|spill|dagvat|avlopp/i, "#0e7490", "drain"],
  [/ritning|läs/i, "#b45309", "plan"],
  [/avancer/i, "#be123c", "calc"],
  [/mängd|mangd/i, "#047857", "measure"],
  [/futurecalc|radiator|vpr/i, "#111827", "app"],
  [/kalkyl/i, "#0f766e", "calc"],
];

function cover(title: string, slug: string): { color: string; icon: string } {
  const hit = COVERS.find(([re]) => re.test(`${title} ${slug}`));
  return hit ? { color: hit[1], icon: hit[2] } : { color: "#334155", icon: "calc" };
}

function Icon({ name, size = 28 }: { name: string; size?: number }) {
  const p = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.6,
              strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  switch (name) {
    case "vent": return <svg {...p}><path d="M3 8h13a3 3 0 1 0-3-3" /><path d="M3 12h17a3 3 0 1 1-3 3" /><path d="M3 16h8" /></svg>;
    case "law": return <svg {...p}><path d="M12 3v18M5 7h14" /><path d="M5 7l-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0z" /></svg>;
    case "drain": return <svg {...p}><path d="M4 4v6a4 4 0 0 0 4 4h12" /><path d="M16 10l4 4-4 4" /></svg>;
    case "plan": return <svg {...p}><rect x="3" y="4" width="18" height="16" rx="1.5" /><path d="M3 10h8v10M11 14h10" /></svg>;
    case "measure": return <svg {...p}><path d="M3 17L17 3l4 4L7 21z" /><path d="M7 13l2 2M10 10l2 2M13 7l2 2" /></svg>;
    case "app": return <svg {...p}><path d="M2 14.5h6V7h7v7.5h7" /><circle cx="8" cy="14.5" r="2" /></svg>;
    case "play": return <svg {...p}><circle cx="12" cy="12" r="9" /><path d="M10 8.5l5 3.5-5 3.5z" /></svg>;
    case "check": return <svg {...p}><circle cx="12" cy="12" r="9" /><path d="M8 12.5l2.5 2.5L16 9.5" /></svg>;
    case "lock": return <svg {...p}><rect x="5" y="11" width="14" height="9" rx="1.5" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>;
    case "quiz": return <svg {...p}><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5v.5M12 17h.01" /></svg>;
    case "award": return <svg {...p}><circle cx="12" cy="9" r="6" /><path d="M8.5 14L7 22l5-3 5 3-1.5-8" /></svg>;
    case "clock": return <svg {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>;
    case "book": return <svg {...p}><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z" /><path d="M4 19V5" /></svg>;
    case "bolt": return <svg {...p}><path d="M13 2L4 14h7l-1 8 9-12h-7z" /></svg>;
    case "target": return <svg {...p}><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1" /></svg>;
    default: return <svg {...p}><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 7h8M8 11h8M8 15h5" /></svg>;
  }
}

function Shell({ children, crumb }: { children: React.ReactNode; crumb?: React.ReactNode }) {
  return (
    <div className="acx acp">
      <header className="acx-top acp-top">
        <Link className="acx-brand" to="/academy">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="M2 13.5h5.2V6h5.6v7.5H18" stroke="currentColor" strokeWidth="1.7" strokeLinecap="square" />
            <circle cx="7.2" cy="13.5" r="1.7" fill="currentColor" />
          </svg>
          Dahl <span>Academy</span>
        </Link>
        <nav className="acp-nav">
          <Link to="/academy">{tr("Översikt")}</Link>
          <Link to="/academy#katalog">{tr("Utbildningar")}</Link>
          <Link to="/academy#certifikat">{tr("Certifikat")}</Link>
        </nav>
        <nav className="acx-crumb">{crumb}</nav>
        <Link className="fc-btn sm" to="/projekt">{tr("Till verktyget")}</Link>
      </header>
      {children}
    </div>
  );
}

function Progress({ v, label }: { v: number; label?: string }) {
  return (
    <div className="acp-prog" role="progressbar" aria-valuenow={Math.round(v * 100)} aria-valuemin={0} aria-valuemax={100}>
      <div className="acp-prog-bar"><i style={{ width: `${Math.round(v * 100)}%` }} /></div>
      {label && <span>{label}</span>}
    </div>
  );
}

function Cover({ title, slug, level, small = false }: { title: string; slug: string; level?: string; small?: boolean }) {
  const c = cover(title, slug);
  return (
    <div className={`acp-cover${small ? " small" : ""}`} style={{ "--cv": c.color } as React.CSSProperties}>
      <span className="acp-cover-icon"><Icon name={c.icon} size={small ? 22 : 34} /></span>
      {level && <span className="acp-chip on-cover">{LEVEL[level] ?? level}</span>}
    </div>
  );
}

/* ---------------------------------------------------------------- översikten */

export function AcademyHome() {
  const [me, setMe] = useState<any>(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [lvl, setLvl] = useState("");
  useEffect(() => { ac.me().then(setMe).catch((e) => setErr(String(e.message || e))); }, []);

  const courses = useMemo(() => (me?.kurser ?? []).filter((k: any) =>
    (!lvl || k.level === lvl) && (!q || `${k.title} ${k.blurb}`.toLowerCase().includes(q.toLowerCase()))), [me, q, lvl]);

  if (err) return <Shell><p className="acx-err">{err}</p></Shell>;
  if (!me) return <Shell><p className="acx-load">{tr("Hämtar ditt läge…")}</p></Shell>;

  const niva = me.niva;
  const going = (me.kurser as any[]).filter((k) => k.state === "pagaende");
  const lessonsDone = (me.kurser as any[]).reduce((n, k) => n + k.klara, 0);
  const lessonsAll = (me.kurser as any[]).reduce((n, k) => n + k.av, 0);
  const cont = me.fortsatt;
  const contCourse = cont && (me.kurser as any[]).find((k) => k.slug === cont.kurs);

  return (
    <Shell>
      <section className="acp-hero">
        <div className="acp-hero-main">
          <p className="acp-eyebrow">{tr("Dahl Academy")}</p>
          <h1>{cont ? tr("Välkommen tillbaka") : tr("Lär dig mängda och kalkylera VVS")}</h1>
          <p className="acp-lead">
            {me.kurser.length} {tr("utbildningar i VVS-kalkyl, mängdning, ventilation, mark och entreprenadjuridik.")}
            {" "}{tr("Lektioner, övningar på riktiga ritningar och certifikat du kan visa upp.")}
          </p>
          {cont && contCourse ? (
            <Link className="acp-continue" to={`/academy/lektion/${cont.lektion}`}>
              <Cover title={contCourse.title} slug={contCourse.slug} small />
              <div>
                <span className="acp-eyebrow">{tr("Fortsätt där du slutade")}</span>
                <b>{cont.titel}</b>
                <span className="acp-muted">{cont.kurs_titel}</span>
                <Progress v={contCourse.andel} label={`${contCourse.klara}/${contCourse.av} ${tr("lektioner")}`} />
              </div>
              <span className="fc-btn solid">{tr("Fortsätt")} <span aria-hidden="true">→</span></span>
            </Link>
          ) : (
            <a className="fc-btn solid" href="#katalog">{tr("Utforska utbildningarna")} <span aria-hidden="true">→</span></a>
          )}
        </div>
        <aside className="acp-level">
          <div className="acp-level-top">
            <span className="acp-badge"><Icon name="award" size={22} /></span>
            <div>
              <span className="acp-eyebrow">{tr("Din nivå")}</span>
              <b>{niva.namn}</b>
            </div>
          </div>
          <p className="acp-xp"><b>{me.xp}</b> XP</p>
          {niva.nasta && (
            <>
              <Progress v={Math.min(1, (me.xp - niva.fran) / Math.max(1, niva.nasta_vid - niva.fran))} />
              <span className="acp-muted">{niva.kvar} XP {tr("till")} {niva.nasta}</span>
            </>
          )}
        </aside>
      </section>

      <section className="acp-stats">
        <div><Icon name="book" size={22} /><b>{lessonsDone}<small>/{lessonsAll}</small></b><span>{tr("Lektioner klara")}</span></div>
        <div><Icon name="target" size={22} /><b>{me.ovningar.godkanda}<small>/{me.ovningar.gjorda}</small></b><span>{tr("Övningar godkända")}</span></div>
        <div><Icon name="bolt" size={22} /><b>{Math.round(me.ovningar.snitt * 100)} %</b><span>{tr("Snittresultat")}</span></div>
        <div><Icon name="award" size={22} /><b>{me.certifikat.length}</b><span>{tr("Certifikat")}</span></div>
      </section>

      {going.length > 0 && (
        <section className="acp-sec">
          <div className="acp-sec-h"><h2>{tr("Mina pågående utbildningar")}</h2></div>
          <div className="acp-grid">
            {going.map((k) => <CourseCard key={k.slug} k={k} />)}
          </div>
        </section>
      )}

      <section className="acp-sec" id="katalog">
        <div className="acp-sec-h">
          <h2>{tr("Alla utbildningar")}</h2>
          <div className="acp-filters">
            {["", "grund", "fortsattning", "avancerad"].map((l) => (
              <button key={l || "alla"} className={`acp-chip${lvl === l ? " on" : ""}`} onClick={() => setLvl(l)}>
                {l ? LEVEL[l] : tr("Alla")}
              </button>
            ))}
            <input className="acp-search" placeholder={tr("Sök utbildning…")} value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <div className="acp-grid">
          {courses.map((k: any) => <CourseCard key={k.slug} k={k} />)}
          {!courses.length && <p className="acp-muted">{tr("Ingen utbildning matchar sökningen.")}</p>}
        </div>
      </section>

      <section className="acp-sec acp-two" id="certifikat">
        <div>
          <div className="acp-sec-h"><h2>{tr("Dina certifikat")}</h2></div>
          {me.certifikat.length ? (
            <div className="acp-certs">
              {me.certifikat.map((c: any) => (
                <Link key={c.code} className="acp-cert" to={`/certifikat/${c.code}`}>
                  <span className="acp-badge"><Icon name="award" size={22} /></span>
                  <div>
                    <span className="acp-eyebrow">{tr("Dahl Certified")}</span>
                    <b>{c.title}</b>
                    <span className="acp-muted">{c.code} · {c.score} % · {c.issued.slice(0, 10)}</span>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="acp-empty">
              <Icon name="award" size={30} />
              <p>{tr("Klara en utbildnings sluttenta för att få ett verifierbart certifikat.")}</p>
            </div>
          )}
        </div>
        <div>
          <div className="acp-sec-h"><h2>{tr("Senaste aktivitet")}</h2></div>
          {me.aktivitet.length ? (
            <ul className="acp-feed">
              {me.aktivitet.map((a: any, i: number) => (
                <li key={i}><span className="acp-dotxp">+{a.points}</span><span>{a.why}</span>
                  <span className="acp-muted">{a.when.slice(0, 10)}</span></li>
              ))}
            </ul>
          ) : <div className="acp-empty"><Icon name="bolt" size={30} /><p>{tr("Din aktivitet visas här när du börjat.")}</p></div>}
        </div>
      </section>
    </Shell>
  );
}

function CourseCard({ k }: { k: any }) {
  const cta = k.state === "klar" ? tr("Repetera") : k.state === "pagaende" ? tr("Fortsätt") : tr("Starta kursen");
  return (
    <Link className="acp-card" to={`/academy/${k.slug}`}>
      <Cover title={k.title} slug={k.slug} level={k.level} />
      <div className="acp-card-body">
        <h3>{k.title}</h3>
        <p>{k.blurb}</p>
        <div className="acp-meta">
          <span><Icon name="clock" size={15} /> {k.hours} h</span>
          <span><Icon name="book" size={15} /> {k.av} {tr("lektioner")}</span>
          {k.state === "klar" && <span className="acp-pill done">{tr("Klar")}</span>}
          {k.state === "pagaende" && <span className="acp-pill">{tr("Pågående")}</span>}
        </div>
        <Progress v={k.andel} label={`${Math.round(k.andel * 100)} %`} />
        <span className="acp-cta">{cta} <span aria-hidden="true">→</span></span>
      </div>
    </Link>
  );
}

/* ---------------------------------------------------------------- kurssidan */

export function AcademyCourse() {
  const { kurs } = useParams();
  const [c, setC] = useState<any>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});
  useEffect(() => { ac.course(kurs!).then(setC).catch((e) => setErr(String(e.message || e))); }, [kurs]);

  if (err) return <Shell><p className="acx-err">{err}</p></Shell>;
  if (!c) return <Shell><p className="acx-load">{tr("Hämtar utbildningen…")}</p></Shell>;

  const lessons = (c.moduler as any[]).flatMap((m) => m.open ? m.lektioner : []);
  const all = (c.moduler as any[]).reduce((n, m) => n + m.lektioner.length, 0);
  const done = (c.moduler as any[]).reduce((n, m) => n + m.lektioner.filter((l: any) => l.state === "klar").length, 0);
  const next = lessons.find((l: any) => l.state !== "klar") ?? lessons[0];
  const minutes = (c.moduler as any[]).reduce((n, m) => n + m.lektioner.reduce((t: number, l: any) => t + (l.minutes || 0), 0), 0);
  const isOpen = (slug: string, i: number) => open[slug] ?? (i === 0 || (c.moduler[i].open && c.moduler[i].lektioner.some((l: any) => l.state !== "klar")));
  const cv = cover(c.title, c.slug);

  return (
    <Shell crumb={<><Link to="/academy">Academy</Link><span aria-hidden="true">/</span><span>{c.title}</span></>}>
      <section className="acp-banner" style={{ "--cv": cv.color } as React.CSSProperties}>
        <div className="acp-banner-in">
          <div>
            <div className="acp-banner-chips">
              <span className="acp-chip on-cover">{LEVEL[c.level] ?? c.level}</span>
              <span className="acp-chip on-cover">{c.hours} {tr("timmar")}</span>
              <span className="acp-chip on-cover">{c.moduler.length} {tr("moduler")} · {all} {tr("lektioner")}</span>
            </div>
            <h1>{c.title}</h1>
            <p>{c.blurb}</p>
            <div className="acp-banner-cta">
              {next && (
                <Link className="fc-btn solid acp-white" to={`/academy/lektion/${next.id}`}>
                  {done ? tr("Fortsätt kursen") : tr("Starta kursen")} <span aria-hidden="true">→</span>
                </Link>
              )}
              <div className="acp-banner-prog"><Progress v={all ? done / all : 0} label={`${done} ${tr("av")} ${all} ${tr("lektioner klara")}`} /></div>
            </div>
          </div>
          <span className="acp-banner-icon"><Icon name={cv.icon} size={96} /></span>
        </div>
      </section>

      <div className="acp-layout">
        <section className="acp-syllabus">
          <h2>{tr("Kursplan")}</h2>
          {(c.moduler as any[]).map((m, i) => {
            const mDone = m.lektioner.filter((l: any) => l.state === "klar").length;
            const expanded = m.open && isOpen(m.slug, i);
            return (
              <div key={m.slug} className={`acp-mod${m.open ? "" : " locked"}`}>
                <button className="acp-mod-h" onClick={() => m.open && setOpen((o) => ({ ...o, [m.slug]: !expanded }))}
                  aria-expanded={expanded}>
                  <span className="acp-mod-n">{String(i + 1).padStart(2, "0")}</span>
                  <span className="acp-mod-t">
                    <b>{m.title}</b>
                    <span className="acp-muted">
                      {m.lektioner.length} {tr("lektioner")}{m.ovningar ? ` · ${m.ovningar} ${tr("övningar")}` : ""}
                      {m.quiz ? ` · ${tr("quiz")}` : ""} · {m.xp} XP
                      {!m.open && ` · ${tr("kräver")} ${m.requires}`}
                    </span>
                  </span>
                  <span className="acp-mod-s">
                    {m.open ? <>{mDone}/{m.lektioner.length}</> : <Icon name="lock" size={18} />}
                    {m.open && <span className={`acp-caret${expanded ? " up" : ""}`} aria-hidden="true">▾</span>}
                  </span>
                </button>
                {expanded && (
                  <ul className="acp-lessons">
                    {m.lektioner.map((l: any) => (
                      <li key={l.id}>
                        <Link to={`/academy/lektion/${l.id}`} className={l.state}>
                          <span className="acp-l-ic"><Icon name={l.state === "klar" ? "check" : "play"} size={20} /></span>
                          <span className="acp-l-t">{l.title}</span>
                          <span className="acp-muted">{l.minutes} min</span>
                        </Link>
                      </li>
                    ))}
                    {!!m.quiz && (
                      <li><Link to={`/academy/${c.slug}/${m.slug}/quiz`} className="quiz">
                        <span className="acp-l-ic"><Icon name="quiz" size={20} /></span>
                        <span className="acp-l-t">{tr("Quiz")} — {m.quiz} {tr("frågor i banken")}</span>
                        <span className="acp-muted">{tr("upp till 50 XP")}</span>
                      </Link></li>
                    )}
                  </ul>
                )}
              </div>
            );
          })}
        </section>

        <aside className="acp-side">
          <div className="acp-box">
            <h3>{tr("Kursen innehåller")}</h3>
            <ul className="acp-facts">
              <li><Icon name="clock" size={18} /> {Math.round(minutes / 6) / 10 || c.hours} {tr("timmar lektioner")}</li>
              <li><Icon name="book" size={18} /> {all} {tr("lektioner i")} {c.moduler.length} {tr("moduler")}</li>
              <li><Icon name="target" size={18} /> {(c.moduler as any[]).reduce((n, m) => n + (m.ovningar || 0), 0)} {tr("övningar på riktiga ritningar")}</li>
              {c.tenta && <li><Icon name="award" size={18} /> {tr("Sluttenta och verifierbart certifikat")}</li>}
            </ul>
          </div>
          <div className="acp-box">
            <h3>{tr("Det här lär du dig")}</h3>
            <ul className="acp-learn">
              {(c.moduler as any[]).map((m) => <li key={m.slug}><Icon name="check" size={18} /> {m.title}</li>)}
            </ul>
          </div>
          {c.tenta && (
            <div className="acp-box acp-exam">
              <span className="acp-badge"><Icon name="award" size={22} /></span>
              <h3>{c.tenta.title}</h3>
              <p className="acp-muted">
                {tr("Fem delar: teori, ritningsläsning, mängdning, kalkyl och kalkylkontroll. Godkänt kräver")}
                {" "}{c.tenta.pass_pct} % {tr("totalt och minst 60 % i varje del.")}
              </p>
              <Link className="fc-btn solid" to={`/academy/tenta/${c.tenta.slug}`}>{tr("Skriv sluttentan")} <span aria-hidden="true">→</span></Link>
            </div>
          )}
        </aside>
      </div>
    </Shell>
  );
}

/* ---------------------------------------------------------------- lektionen */

export function AcademyLesson() {
  const { id } = useParams();
  const nav = useNavigate();
  const [l, setL] = useState<any>(null);
  const [course, setCourse] = useState<any>(null);
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);
  const [xp, setXp] = useState(0);
  const [outline, setOutline] = useState(false);

  useEffect(() => {
    setL(null); setDone(false); setXp(0); setOutline(false);
    ac.lesson(id!).then((d) => {
      setL(d); setDone(d.state === "klar");
      ac.course(d.kurs.slug).then(setCourse).catch(() => setCourse(null));
    }).catch((e) => setErr(String(e.message || e)));
    window.scrollTo(0, 0);
  }, [id]);

  if (err) return <Shell><p className="acx-err">{err}</p></Shell>;
  if (!l) return <Shell><p className="acx-load">{tr("Hämtar lektionen…")}</p></Shell>;

  const markDone = async () => {
    const r = await ac.lessonDone(l.id);
    setDone(true);
    setXp(r.xp);
    if (course) setCourse({ ...course, moduler: course.moduler.map((m: any) => ({ ...m,
      lektioner: m.lektioner.map((x: any) => x.id === l.id ? { ...x, state: "klar" } : x) })) });
  };

  const flat = course ? (course.moduler as any[]).flatMap((m) => m.lektioner) : [];
  const pos = flat.findIndex((x: any) => x.id === l.id);
  const doneN = flat.filter((x: any) => x.state === "klar").length;

  return (
    <Shell crumb={
      <>
        <Link to="/academy">Academy</Link>
        <span aria-hidden="true">/</span>
        <Link to={`/academy/${l.kurs.slug}`}>{l.kurs.title}</Link>
      </>
    }>
      <div className="acp-lessonwrap">
        <aside className={`acp-outline${outline ? " open" : ""}`}>
          <div className="acp-outline-h">
            <Link to={`/academy/${l.kurs.slug}`}><b>{l.kurs.title}</b></Link>
            {flat.length > 0 && <Progress v={doneN / flat.length} label={`${doneN}/${flat.length}`} />}
          </div>
          {course ? (course.moduler as any[]).map((m, i) => (
            <div key={m.slug} className="acp-outline-mod">
              <span className="acp-eyebrow">{String(i + 1).padStart(2, "0")} · {m.title}</span>
              {m.open ? (
                <ul>
                  {m.lektioner.map((x: any) => (
                    <li key={x.id}>
                      <Link to={`/academy/lektion/${x.id}`} className={`${x.state}${x.id === l.id ? " here" : ""}`}>
                        <Icon name={x.state === "klar" ? "check" : "play"} size={16} />
                        <span>{x.title}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : <p className="acp-muted acp-locked"><Icon name="lock" size={14} /> {tr("Låst")}</p>}
            </div>
          )) : <p className="acp-muted">{tr("Hämtar kursplanen…")}</p>}
        </aside>

        <article className="acx-lesson acp-lesson">
          <button className="fc-btn sm acp-outline-toggle" onClick={() => setOutline((v) => !v)}>
            {outline ? tr("Dölj kursplanen") : tr("Visa kursplanen")}
          </button>
          <header>
            <p className="acp-eyebrow">
              {l.modul.title}{pos >= 0 && ` · ${tr("lektion")} ${pos + 1} ${tr("av")} ${flat.length}`}
            </p>
            <h1>{l.title}</h1>
            <div className="acp-meta">
              <span><Icon name="clock" size={15} /> {l.minutes} min</span>
              <span><Icon name="bolt" size={15} /> {l.xp} XP</span>
              {!!l.ovningar.length && <span><Icon name="target" size={15} /> {l.ovningar.length} {tr("övningar")}</span>}
              {done && <span className="acp-pill done">{tr("Klar")}</span>}
            </div>
          </header>

          <div className="acx-blocks">
            {(l.blocks as Block[]).map((b, i) => <BlockView key={i} b={b} />)}
          </div>

          {!!l.ovningar.length && (
            <section className="acx-ex">
              <h2>{tr("Öva")}</h2>
              {l.ovningar.map((e: ExerciseOut) => (
                <Exercise key={e.slug} ex={e} onDone={(r) => setXp((x) => x + r.xp)} />
              ))}
            </section>
          )}

          <footer className="acx-lfoot acp-lfoot">
            <div>
              {done ? (
                <p className="acx-done"><span aria-hidden="true">✓</span> {tr("Lektionen är klar")}{xp > 0 && ` · +${xp} XP`}</p>
              ) : (
                <button className="fc-btn solid" onClick={markDone}>{tr("Markera som läst")}</button>
              )}
            </div>
            <div className="acx-lnav">
              {l.forra && <button className="fc-btn sm" onClick={() => nav(`/academy/lektion/${l.forra}`)}>{tr("← Föregående")}</button>}
              {l.nasta
                ? <button className="fc-btn solid sm" onClick={() => nav(`/academy/lektion/${l.nasta}`)}>{tr("Nästa lektion →")}</button>
                : <Link className="fc-btn sm" to={`/academy/${l.kurs.slug}`}>{tr("Tillbaka till utbildningen")}</Link>}
            </div>
          </footer>
        </article>
      </div>
    </Shell>
  );
}

function BlockView({ b }: { b: Block }) {
  switch (b.k) {
    case "h": return <h2 className="acx-h">{b.t}</h2>;
    case "p": return <p>{b.t}</p>;
    case "ul": return <ul className="acx-ul">{b.t.map((x) => <li key={x}>{x}</li>)}</ul>;
    case "terms":
      return (
        <dl className="acx-terms">
          {b.t.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
        </dl>
      );
    case "note": return <aside className="acx-note"><span className="fc-label">{tr("Att veta")}</span><p>{b.t}</p></aside>;
    case "warn": return <aside className="acx-warn"><span className="fc-label">{tr("Varning")}</span><p>{b.t}</p></aside>;
    case "formula":
      return (
        <figure className="acx-formula">
          <code>{b.t}</code>
          <figcaption>{b.why}</figcaption>
        </figure>
      );
    case "drawing": return <PlanBlock slug={b.plan} caption={b.caption} />;
    default: return null;
  }
}

/** En ritning i löptext. Bladen hämtas ur övningarnas data, så samma blad används på båda ställena. */
function PlanBlock({ slug, caption }: { slug: string; caption: string }) {
  const [plan, setPlan] = useState<PlanData | null>(null);
  useEffect(() => {
    let alive = true;
    ac.plan(slug)
      .then((p) => { if (alive && p) setPlan(p); })
      .catch(() => { /* ritningen är illustration; utan den står texten kvar */ });
    return () => { alive = false; };
  }, [slug]);
  if (!plan) return <figure className="acx-plan acx-plan-none"><figcaption>{caption}</figcaption></figure>;
  return (
    <figure className="acx-plan">
      <TrainingDrawing plan={plan} mode="las" height={360} />
      <figcaption>{caption}</figcaption>
    </figure>
  );
}
