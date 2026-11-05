import { useEffect, useState } from "react";
import { t as tr } from "../i18n";
import { Link } from "react-router-dom";
import { MODULES, readProgress, syncProgress, type Module } from "../learn";
import { FLAT, lessonHref } from "./Lecture";

/* Akademin som en plats, inte som en flik.
 *
 * Det som gör en utbildningsplattform till en utbildningsplattform är att man alltid vet tre saker: vad kursen
 * innehåller, var man själv är i den, och vad nästa steg är. Katalogen nedan säger alla tre på en gång - och
 * varje kurs och varje föreläsning har en egen adress, så man kan spara en, dela en, och komma tillbaka till
 * precis den man var på.
 *
 * Samma komponenter används publikt och inloggat. Skillnaden är `base` (vilken adress föreläsningarna ligger
 * under) och att stegen bara sparas när någon är inloggad.
 */

export function useProgress(sync: boolean) {
  const [prog, setProg] = useState<Record<string, boolean>>(() => readProgress());
  useEffect(() => { if (sync) syncProgress().then(setProg); }, [sync]);
  return prog;
}

export function courseMinutes(m: Module) {
  return m.lessons.reduce((n, l) => n + l.minutes, 0);
}

/** Ringen som säger hur långt man kommit, i procent av hela akademin. */
export function ProgressRing({ done, of, size = 108 }: { done: number; of: number; size?: number }) {
  const pct = of ? done / of : 0;
  const r = size / 2 - 7;
  const c = 2 * Math.PI * r;
  return (
    <div className="ac-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--ac-track)" strokeWidth="6" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#00b5e2" strokeWidth="6"
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - pct)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`} style={{ transition: "stroke-dashoffset 0.8s cubic-bezier(0.22,1,0.36,1)" }} />
      </svg>
      <span className="ac-ring-n">{done}<i>/{of}</i></span>
    </div>
  );
}

/** Det man ska göra härnäst, som en egen sak högst upp. */
export function ResumeCard({ base, prog }: { base: string; prog: Record<string, boolean> }) {
  const done = FLAT.filter((f) => prog[f.l.id]).length;
  const next = FLAT.find((f) => !prog[f.l.id]) ?? FLAT[0];
  const left = FLAT.filter((f) => !prog[f.l.id]).reduce((a, f) => a + f.l.minutes, 0);
  const all = done === FLAT.length;
  return (
    <div className="ac-resume">
      <div>
        <p className="lp-mono">{all ? "Du är igenom hela akademin" : done === 0 ? "Börja här" : "Fortsätt där du slutade"}</p>
        <h2>{next.l.title}</h2>
        <p className="ac-resume-sub">
          {next.m.title} · föreläsning {next.li + 1} av {next.m.lessons.length} · {next.l.minutes} min
          {!all && left > 0 && ` · ${left} min kvar totalt`}
        </p>
        <Link className="lp-btn primary lg" to={lessonHref(base, next.m.id, next.l.id)}>
          {all ? "Gå igenom igen" : done === 0 ? "Starta första föreläsningen" : "Fortsätt"} <span aria-hidden="true">→</span>
        </Link>
      </div>
      <ProgressRing done={done} of={FLAT.length} />
    </div>
  );
}

/** En kurs som ett kort: nummer, titel, vad den ger, och hur långt man kommit i den. */
export function CourseCard({ m, mi, base, prog }:
  { m: Module; mi: number; base: string; prog: Record<string, boolean> }) {
  const done = m.lessons.filter((l) => prog[l.id]).length;
  const pct = Math.round((done / m.lessons.length) * 100);
  const next = m.lessons.find((l) => !prog[l.id]) ?? m.lessons[0];
  return (
    <article className={`ac-course${done === m.lessons.length ? " full" : ""}`}>
      <Link className="ac-course-hit" to={`${base}/${m.id}`} aria-label={`Öppna kursen ${m.title}`} />
      <div className="ac-course-top">
        <span className="ac-no">{String(mi + 1).padStart(2, "0")}</span>
        <span className="lp-mono">{m.lessons.length} föreläsningar · {courseMinutes(m)} min</span>
      </div>
      <h3>{m.title}</h3>
      <p>{m.blurb}</p>
      <ul className="ac-course-list">
        {m.lessons.slice(0, 3).map((l) => (
          <li key={l.id} className={prog[l.id] ? "done" : ""}><span className="tick" aria-hidden="true" />{l.title}</li>
        ))}
        {m.lessons.length > 3 && <li className="more">+{m.lessons.length - 3} till</li>}
      </ul>
      <div className="ac-course-foot">
        <div className="ac-bar" aria-hidden="true"><i style={{ width: `${pct}%` }} /></div>
        <span className="lp-mono">{done} av {m.lessons.length}</span>
      </div>
      <span className="ac-course-go" aria-hidden="true">
        {done === 0 ? "Börja kursen" : done === m.lessons.length ? "Läs igen" : `Fortsätt: ${next.title}`} →
      </span>
    </article>
  );
}

/** Hela katalogen. */
export function CourseGrid({ base, prog }: { base: string; prog: Record<string, boolean> }) {
  return (
    <div className="ac-grid">
      {MODULES.map((m, mi) => <CourseCard key={m.id} m={m} mi={mi} base={base} prog={prog} />)}
    </div>
  );
}

/** Kurssidan: kursens egna föreläsningar, en lista man går uppifrån och ned. */
export function CourseView({ m, mi, base, prog }:
  { m: Module; mi: number; base: string; prog: Record<string, boolean> }) {
  const done = m.lessons.filter((l) => prog[l.id]).length;
  const next = m.lessons.find((l) => !prog[l.id]) ?? m.lessons[0];
  const prevC = mi > 0 ? MODULES[mi - 1] : null;
  const nextC = mi < MODULES.length - 1 ? MODULES[mi + 1] : null;
  return (
    <div className="ac-coursepage">
      <nav className="ac-crumbs" aria-label={tr("Var du är")}>
        <Link to={base}>Akademin</Link>
        <span aria-hidden="true">/</span>
        <span className="here">{m.title}</span>
      </nav>

      <header className="ac-coursehead">
        <div>
          <p className="lp-mono">Kurs {String(mi + 1).padStart(2, "0")} av {MODULES.length}</p>
          <h1>{m.title}</h1>
          <p className="ac-lede">{m.blurb}</p>
          <Link className="lp-btn primary lg" to={lessonHref(base, m.id, next.id)}>
            {done === 0 ? "Börja kursen" : done === m.lessons.length ? "Läs igen" : "Fortsätt kursen"} <span aria-hidden="true">→</span>
          </Link>
        </div>
        <ProgressRing done={done} of={m.lessons.length} size={96} />
      </header>

      <ol className="ac-lessons">
        {m.lessons.map((l, li) => (
          <li key={l.id} className={prog[l.id] ? "done" : ""}>
            <Link to={lessonHref(base, m.id, l.id)}>
              <span className="tick" aria-hidden="true" />
              <span className="no">{li + 1}</span>
              <span className="nm">
                {l.title}
                {!!l.short?.length && <i>{l.short[0]}</i>}
              </span>
              <span className="mi lp-mono">{l.minutes} min</span>
            </Link>
          </li>
        ))}
      </ol>

      <nav className="ac-coursenav" aria-label={tr("Andra kurser")}>
        {prevC
          ? <Link className="ac-step prev" to={`${base}/${prevC.id}`}>
              <span className="lp-mono">{tr("Föregående kurs")}</span><b>{prevC.title}</b>
            </Link>
          : <span />}
        {nextC
          ? <Link className="ac-step next" to={`${base}/${nextC.id}`}>
              <span className="lp-mono">{tr("Nästa kurs")}</span><b>{nextC.title}</b>
            </Link>
          : <span />}
      </nav>
    </div>
  );
}
