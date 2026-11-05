import { useSectionProgress } from "./lp-motion";

import { t as tr, num } from "../i18n";
/** The stages the scene walks through as the reader scrolls, in the order the engine does them. */
const BEATS = [
  ["Läser vektorn", "Varje streck, dess penna, färg och lager tas direkt ur PDF:en."],
  ["Bygger tillbaka texten", "Bokstäver som ritats som streck sätts ihop till ord igen."],
  ["Följer ledarlinjerna", "Från etikettens understrykning till den geometri linjen faktiskt rör."],
  ["Äger rören", "Identiteten bärs längs nätet till den gräns ritningen själv sätter."],
  ["Mäter i skalstockens skala", "Och redovisar varje meter med sitt belägg."],
];

const RUNS: { d: string; c: string; m: number }[] = [
  { d: "M120 300 H360 V186 H620", c: "#00b5e2", m: 24.8 },
  { d: "M120 372 H468 V300", c: "#60a5fa", m: 18.2 },
  { d: "M620 186 H812 V402 H520", c: "#f0abfc", m: 31.4 },
  { d: "M240 300 V444 H520", c: "#fbbf24", m: 12.1 },
];

/** Text rows the sheet carries. The four with `u` are pipe labels: their underline is where a leader starts. */
const WORDS: { x: number; y: number; t: string; u?: number }[] = [
  { x: 96, y: 128, t: "VVS PLAN 2" },
  { x: 140, y: 270, t: "KV1-X31-16", u: 60 },
  { x: 392, y: 156, t: "S1-P2-110", u: 56 },
  { x: 646, y: 156, t: "VV1-X31-16", u: 60 },
  { x: 256, y: 414, t: "S3-R8-75", u: 50 },
  { x: 546, y: 292, t: "BETECKNINGAR" },
  { x: 546, y: 314, t: "KV  TAPPKALLVATTEN" },
  { x: 546, y: 336, t: "VV  TAPPVARMVATTEN" },
  { x: 546, y: 358, t: "S   SPILLVATTEN" },
  { x: 546, y: 392, t: "SKALA 1:50" },
];

/** A short window of the scroll, eased, so each beat has its own stretch of the page. */
const win = (p: number, a: number, b: number) => Math.min(1, Math.max(0, (p - a) / (b - a)));

export default function LandingScene() {
  const { ref, p } = useSectionProgress<HTMLElement>();
  const beat = Math.min(BEATS.length - 1, Math.floor(p * BEATS.length * 0.999));

  const text = win(p, 0.02, 0.20);
  const words = win(p, 0.14, 0.36);
  const leaders = win(p, 0.32, 0.54);
  const pipes = win(p, 0.48, 0.78);
  const measure = win(p, 0.58, 0.92);

  return (
    <section className="lp-scene" ref={ref} id="hur">
      <div className="lp-scene-pin">
        <div className="lp-scene-grid">
          {/* The sheet lies on a table and rises to face the reader as the reading proceeds - the same motion
              the reading itself makes, taking the pipes off the paper. The tilt is driven by the scroll, so it
              is the reader's own hand that lifts it. */}
          <div className="lp-scene-art" style={{
            transform: `rotateX(${(1 - p) * 13}deg) translateZ(${p * 18}px) scale(${0.97 + 0.03 * p})`,
          }}>
            <svg viewBox="0 0 940 520" role="img" aria-label={tr("Ritningen läses steg för steg medan sidan skrollas")}>
              {/* the sheet */}
              <g stroke="#232830" strokeWidth="1.6" fill="none" opacity={0.75 + 0.25 * text}>
                <path d="M60 90 H880 V470 H60 Z M60 250 H520 M520 90 V470 M700 250 H880 M700 340 H880" />
              </g>
              {/* text rows put back together, letter by letter, the way the glyphs are reassembled */}
              <g fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace" fontSize="12.5" letterSpacing="0.5">
                {WORDS.map((w, i) => {
                  const a = (i / WORDS.length) * 0.7;
                  const k = win(words, a, a + 0.3);
                  const shown = w.t.slice(0, Math.round(w.t.length * k));
                  return (
                    <g key={w.t} opacity={0.35 + 0.65 * k}>
                      <text x={w.x} y={w.y} fill={w.u ? "#e8ecf1" : "#8b93a1"}>{shown}</text>
                      {w.u ? (
                        <line x1={w.x} y1={w.y + 5} x2={w.x + w.u * k} y2={w.y + 5}
                          stroke="#e8ecf1" strokeWidth="1.1" opacity={0.7} />
                      ) : null}
                    </g>
                  );
                })}
              </g>
              {/* leaders reaching from the labels to the runs */}
              <g stroke="#c026d3" strokeWidth="1.3" fill="none" opacity={0.7}>
                {[["M200 275 L246 299"], ["M448 161 L468 300"], ["M706 161 L812 187"], ["M306 419 L330 444"]].map((d, i) => {
                  const k = win(leaders, i * 0.12, i * 0.12 + 0.5);
                  return <path key={i} d={d[0]} pathLength={1} strokeDasharray="1" strokeDashoffset={1 - k} />;
                })}
              </g>
              {/* the runs, drawing themselves - and lifting off the sheet as they are owned */}
              <g fill="none" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round"
                 style={{ transform: `translate(${-4 * pipes}px, ${-7 * pipes}px)`, transition: "transform 0.2s linear" }}>
                {RUNS.map((r, i) => {
                  const k = win(pipes, i * 0.1, i * 0.1 + 0.62);
                  return (
                    <g key={i}>
                      {/* what a lifted line casts on the paper below it */}
                      <path d={r.d} stroke="#05070a" strokeOpacity={0.34 * k} strokeWidth="5"
                        pathLength={1} strokeDasharray="1" strokeDashoffset={1 - k}
                        transform={`translate(${5 * pipes} ${8 * pipes})`} />
                      <path d={r.d} stroke={r.c} pathLength={1} strokeDasharray="1"
                        strokeDashoffset={1 - k} opacity={0.5 + 0.5 * k} />
                    </g>
                  );
                })}
              </g>
              {/* the one the sheet never names */}
              <path d="M700 434 H860" stroke="#4b5160" strokeWidth="3" strokeDasharray="9 6"
                opacity={0.25 + 0.55 * pipes} fill="none" />
              <text x="700" y="422" fill="#5b616c" fontSize="13" opacity={0.3 + 0.7 * pipes}
                fontFamily="ui-monospace, SFMono-Regular, monospace">{tr("onämnd — redovisas, mäts inte")}</text>
            </svg>
          </div>

          <div className="lp-scene-side">
            <ol className="lp-beats">
              {BEATS.map(([h, s], i) => (
                <li key={h} className={i === beat ? "on" : i < beat ? "past" : ""}>
                  <span className="no">{String(i + 1).padStart(2, "0")}</span>
                  <span>
                    <b>{h}</b>
                    <em>{s}</em>
                  </span>
                </li>
              ))}
            </ol>
            <div className="lp-tally">
              {RUNS.map((r, i) => {
                const k = win(measure, i * 0.12, i * 0.12 + 0.55);
                return (
                  <div key={i} className="lp-tally-row">
                    <span className="sw" style={{ background: r.c, opacity: 0.25 + 0.75 * k }} />
                    <span className="dq">{["KV1-X31-16", "S1-P2-110", "VV1-X31-16", "S3-R8-75"][i]}</span>
                    <span className="mq">{num(r.m * k, 1)} m</span>
                  </div>
                );
              })}
              <div className="lp-tally-row sum">
                <span className="dq">Summa</span>
                <span className="mq">{num(RUNS.reduce((s, r) => s + r.m, 0) * measure, 1)} m</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
