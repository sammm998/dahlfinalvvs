import { useCallback, useEffect, useRef, useState } from "react";
import { t as tr } from "../i18n";
import { Link, useParams } from "react-router-dom";
import Exercise from "./Exercise";
import { ac } from "./api";
import "./academy.css";

/* Sluttentan och quizet.
 *
 * Tentans hela poäng är att den går att lita på, och det kräver tre saker av gränssnittet:
 *
 *   * **Svaren sparas när de ges**, ett i taget, mot servern. Ingen "spara"-knapp att glömma, och en
 *     omladdning eller en tappad uppkoppling kostar ett svar i stället för ett prov.
 *   * **Ingenting rättas här.** Sidan vet inte vad som är rätt. Den skickar vad du gjorde och visar vad
 *     servern svarade.
 *   * **Ingen koreografi.** Inga scener, ingen parallax, ingen rörelse i ögonvrån. Ett prov ska gå att
 *     skriva.
 */

function Frame({ children, title }: { children: React.ReactNode; title: string }) {
  return (
    <div className="acx acx-exam">
      <header className="acx-top">
        <Link className="acx-brand" to="/academy">Dahl <span>Academy</span></Link>
        <nav className="acx-crumb"><span>{title}</span></nav>
      </header>
      {children}
    </div>
  );
}

/* ---------------------------------------------------------------- sluttentan */

export function ExamPage() {
  const { slug } = useParams();
  const [att, setAtt] = useState<any>(null);
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState<Record<string, "sparar" | "sparat" | "fel">>({});
  const [result, setResult] = useState<any>(null);
  const [at, setAt] = useState(0);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    ac.examStart(slug!).then((a) => {
      setAtt(a);
      if (a.status === "inlamnad") setResult(a.resultat);
    }).catch((e) => setErr(String(e.message || e)));
  }, [slug]);

  const save = useCallback(async (ref: string, given: unknown) => {
    setSaving((s) => ({ ...s, [ref]: "sparar" }));
    try {
      await ac.examSave(att.id, ref, given);
      setSaving((s) => ({ ...s, [ref]: "sparat" }));
      setAtt((a: any) => ({ ...a, svar: { ...a.svar, [ref]: given } }));
    } catch {
      setSaving((s) => ({ ...s, [ref]: "fel" }));
    }
  }, [att]);

  if (err) return <Frame title="Sluttenta"><p className="acx-err">{err}</p>
    <p><Link className="fc-btn sm" to="/academy">Tillbaka</Link></p></Frame>;
  if (!att) return <Frame title="Sluttenta"><p className="acx-load">{tr("Förbereder tentan…")}</p></Frame>;

  if (result) return <ExamResult att={att} result={result} />;

  const items = att.uppgifter;
  const item = items[at];
  const answered = Object.keys(att.svar || {}).length;

  return (
    <Frame title={att.titel}>
      <div className="acx-exam-bar">
        <div>
          <p className="fc-label">Sluttenta</p>
          <h1>{att.titel}</h1>
        </div>
        <div className="acx-exam-prog">
          <span className="fc-label">{answered} av {items.length} besvarade</span>
          <div className="acx-bar"><i style={{ width: `${(answered / items.length) * 100}%` }} /></div>
          <span className="fc-label">{tr("Svaren sparas automatiskt")}</span>
        </div>
      </div>

      <nav className="acx-exam-nav" aria-label="Uppgifter">
        {items.map((u: any, i: number) => (
          <button key={u.slug} className={`acx-pip${i === at ? " on" : ""}${att.svar?.[u.slug] !== undefined ? " done" : ""}`}
            onClick={() => setAt(i)} aria-current={i === at} aria-label={`Uppgift ${i + 1}${att.svar?.[u.slug] !== undefined ? ", besvarad" : ""}`}>
            {i + 1}
          </button>
        ))}
      </nav>

      <section className="acx-exam-item">
        <p className="fc-label">Uppgift {at + 1} av {items.length} · {areaName(item.area)}
          {saving[item.slug] === "sparar" && " · sparar…"}
          {saving[item.slug] === "sparat" && " · sparat"}
          {saving[item.slug] === "fel" && " · kunde inte spara"}
        </p>
        {item.typ === "fraga"
          ? <QuestionView q={item} value={att.svar?.[item.slug]} onChange={(v) => save(item.slug, v)} />
          : <Exercise ex={item} exam onExam={(g) => save(item.slug, g)} />}
      </section>

      <footer className="acx-exam-foot">
        <button className="fc-btn sm" onClick={() => setAt((i) => Math.max(0, i - 1))} disabled={at === 0}>{tr("← Föregående")}</button>
        <button className="fc-btn sm" onClick={() => setAt((i) => Math.min(items.length - 1, i + 1))}
          disabled={at === items.length - 1}>{tr("Nästa →")}</button>
        <button className="fc-btn solid" disabled={sending}
          onClick={async () => {
            if (!window.confirm(`Lämna in tentan? ${items.length - answered} uppgifter är obesvarade och räknas som fel.`)) return;
            setSending(true);
            try { setResult(await ac.examSubmit(att.id)); } finally { setSending(false); }
          }}>
          {sending ? "Lämnar in…" : "Lämna in"}
        </button>
      </footer>
    </Frame>
  );
}

function ExamResult({ att, result }: { att: any; result: any }) {
  const areas = result.per_omrade || {};
  return (
    <Frame title={att.titel}>
      <section className={`acx-result ${result.passed ? "ok" : "no"}`}>
        <p className="fc-label">Resultat</p>
        <h1 className="fc-display fc-display-lg">
          <span aria-hidden="true">{result.passed ? "✓" : "✕"}</span> {result.passed ? "Godkänd" : "Inte godkänd"}
        </h1>
        <p className="acx-result-n">{Math.round(result.score * 100)} %</p>

        <table className="acx-areas">
          <thead><tr><th>{tr("Område")}</th><th className="num">Vikt</th><th className="num">Resultat</th><th /></tr></thead>
          <tbody>
            {Object.entries(areas).map(([a, v]: [string, any]) => (
              <tr key={a} className={v.godkand ? "ok" : "no"}>
                <td>{areaName(a)}</td>
                <td className="num">{v.vikt} %</td>
                <td className="num">{Math.round(v.andel * 100)} %</td>
                <td><span aria-hidden="true">{v.godkand ? "✓" : "✕"}</span> {v.godkand ? "godkänt" : "under gränsen"}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {result.passed ? (
          <div className="acx-result-cta">
            <p>{tr("Du är Dahl Certified. Certifikatet är utfärdat och går att verifiera med sitt id.")}</p>
            <Link className="fc-btn solid" to={`/certifikat/${result.certifikat}`}>{tr("Öppna certifikatet")} <span aria-hidden="true">→</span></Link>
          </div>
        ) : (
          <div className="acx-result-cta">
            <p>
              Godkänt kräver {att.pass_pct} % totalt och minst {att.section_min_pct} % i varje del.
              {result.svaga?.length ? ` Repetera: ${result.svaga.map(areaName).join(", ")}.` : ""}
            </p>
            <Link className="fc-btn solid" to="/academy">{tr("Tillbaka till utbildningarna")}</Link>
          </div>
        )}
      </section>
    </Frame>
  );
}

/* ---------------------------------------------------------------- frågan */

export function QuestionView(
  { q, value, onChange }: { q: any; value: any; onChange: (v: any) => void },
) {
  const [num, setNum] = useState(value ?? "");
  const timer = useRef(0);
  // fältet fylls om när frågan byts, inte när värdet ändras av det egna skrivandet
  useEffect(() => { setNum(value ?? ""); }, [q.slug]);

  return (
    <div className="acx-q">
      <p className="acx-q-p">{q.prompt}</p>
      {q.kind === "single" && (
        <div className="ex-choice" role="radiogroup" aria-label={q.prompt}>
          {q.options.map((o: string, i: number) => (
            <button key={o} role="radio" aria-checked={value === i}
              className={`ex-opt${value === i ? " on" : ""}`} onClick={() => onChange(i)}>
              <span className="ex-opt-k">{String.fromCharCode(65 + i)}</span>{o}
            </button>
          ))}
        </div>
      )}
      {q.kind === "bool" && (
        <div className="ex-choice" role="radiogroup" aria-label={q.prompt}>
          {[["Sant", true], ["Falskt", false]].map(([t, v]) => (
            <button key={String(t)} role="radio" aria-checked={value === v}
              className={`ex-opt${value === v ? " on" : ""}`} onClick={() => onChange(v)}>
              <span className="ex-opt-k">{v ? "S" : "F"}</span>{t as string}
            </button>
          ))}
        </div>
      )}
      {q.kind === "multi" && (
        <div className="ex-choice" role="group" aria-label={q.prompt}>
          {q.options.map((o: string, i: number) => {
            const on = Array.isArray(value) && value.includes(i);
            return (
              <button key={o} aria-pressed={on} className={`ex-opt${on ? " on" : ""}`}
                onClick={() => onChange(on ? (value as number[]).filter((x) => x !== i) : [...(value || []), i])}>
                <span className="ex-opt-k">{on ? "✓" : String.fromCharCode(65 + i)}</span>{o}
              </button>
            );
          })}
        </div>
      )}
      {q.kind === "numeric" && (
        <label className="ex-num">
          <span>{tr("Ditt svar")}</span>
          <input inputMode="decimal" value={num}
            onChange={(e) => {
              setNum(e.target.value);
              // Autospar när skrivandet står stilla en stund: ett anrop per tangenttryck gör tentan långsam.
              window.clearTimeout(timer.current);
              timer.current = window.setTimeout(() => onChange(e.target.value), 600);
            }}
            onBlur={() => onChange(num)} />
        </label>
      )}
    </div>
  );
}

function areaName(a: string): string {
  return ({ teori: "Teori", ritning: "Ritningsläsning", mangdning: "Mängdning",
            kalkyl: "Kalkyl", kontroll: "Kalkylkontroll" } as Record<string, string>)[a] || a;
}

/* ---------------------------------------------------------------- modulens quiz */

export function QuizPage() {
  const { kurs, modul } = useParams();
  const [q, setQ] = useState<any>(null);
  const [svar, setSvar] = useState<Record<string, any>>({});
  const [out, setOut] = useState<any>(null);
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    setOut(null); setSvar({});
    ac.quiz(kurs!, modul!).then(setQ).catch((e) => setErr(String(e.message || e)));
  }, [kurs, modul]);
  useEffect(load, [load]);

  if (err) return <Frame title="Quiz"><p className="acx-err">{err}</p></Frame>;
  if (!q) return <Frame title="Quiz"><p className="acx-load">{tr("Hämtar frågor…")}</p></Frame>;

  return (
    <Frame title={`Quiz — ${q.modul}`}>
      <section className="acx-quiz">
        <h1 className="fc-display fc-display-md">Quiz — {q.modul}</h1>
        {!out && (
          <>
            {q.fragor.map((f: any, i: number) => (
              <article key={f.slug} className="acx-qcard">
                <p className="fc-label">Fråga {i + 1} av {q.fragor.length}</p>
                <QuestionView q={f} value={svar[f.slug]} onChange={(v) => setSvar((s) => ({ ...s, [f.slug]: v }))} />
              </article>
            ))}
            <button className="fc-btn solid"
              disabled={Object.keys(svar).length < q.fragor.length}
              onClick={async () => {
                const order = Object.fromEntries(q.fragor.map((f: any) => [f.slug, f.order]));
                setOut(await ac.quizSubmit(kurs!, modul!, svar, order));
              }}>
              Rätta quizet
            </button>
          </>
        )}
        {out && (
          <div className={`acx-quiz-res ${out.passed ? "ok" : "no"}`}>
            <p className="fc-label">Resultat</p>
            <h2 className="fc-display fc-display-md">
              <span aria-hidden="true">{out.passed ? "✓" : "✕"}</span> {Math.round(out.score * 100)} %
              {out.xp > 0 && <span className="ex-xp"> +{out.xp} XP</span>}
            </h2>
            <ul className="acx-qres">
              {out.fragor.map((r: any, i: number) => (
                <li key={r.slug} className={r.ratt ? "ok" : "no"}>
                  <b><span aria-hidden="true">{r.ratt ? "✓" : "✕"}</span> Fråga {i + 1}</b>
                  <span>{r.forklaring}</span>
                </li>
              ))}
            </ul>
            <div className="acx-quiz-cta">
              <button className="fc-btn sm" onClick={load}>{tr("Gör ett nytt quiz")}</button>
              <Link className="fc-btn sm" to={`/academy/${kurs}`}>Tillbaka</Link>
            </div>
          </div>
        )}
      </section>
    </Frame>
  );
}
