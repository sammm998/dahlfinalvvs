import { useSectionProgress } from "./lp-motion";
import { t as tr } from "../i18n";
import { usePointerParallax } from "./tilt";

/* One method, not one template.
 *
 * Every office draws pipes differently: dashes of one length, dashes of another, a solid line, two lines with a
 * gap, a chain of dots. None of that is configured anywhere - the reading works out what this sheet's pipes look
 * like from this sheet, by watching where its own labels land. The section shows the styles as what they are:
 * a stack of sheets that fans out, each drawn its own way, all read the same way.
 */

const SHEETS: { name: string; note: string; draw: (k: number) => React.ReactNode }[] = [
  {
    name: "Streckad",
    note: "korta streck, jämn lucka",
    draw: (k) => (
      <g stroke="#00b5e2" strokeWidth="3" strokeLinecap="round" strokeDasharray="13 6"
         pathLength={1} strokeDashoffset={0} opacity={k}>
        <path d="M24 96 H150 V52 H272" fill="none" />
        <path d="M24 140 H196" fill="none" />
      </g>
    ),
  },
  {
    name: "Streck-punkt",
    note: "lång-kort, som en centrumlinje",
    draw: (k) => (
      <g stroke="#60a5fa" strokeWidth="3" strokeLinecap="round" strokeDasharray="20 5 3 5" opacity={k}>
        <path d="M24 88 H120 V140 H272" fill="none" />
        <path d="M120 88 H272" fill="none" />
      </g>
    ),
  },
  {
    name: "Heldragen",
    note: "ingen lucka alls",
    draw: (k) => (
      <g stroke="#f0abfc" strokeWidth="3.2" strokeLinecap="round" opacity={k}>
        <path d="M24 76 H176 V148 H272" fill="none" />
        <path d="M96 76 V148" fill="none" />
      </g>
    ),
  },
  {
    name: "Dubbellinje",
    note: "rörets två väggar, ritade var för sig",
    draw: (k) => (
      <g stroke="#fbbf24" strokeWidth="1.8" opacity={k} fill="none">
        <path d="M24 92 H180 V60 H272" />
        <path d="M24 100 H172 V68 H272" />
        <path d="M24 144 H210" />
        <path d="M24 152 H210" />
      </g>
    ),
  },
];

/** The sheet under the drawn run: a frame, a stacked label and the line it draws to the pipe. */
function Sheet({ s, k }: { s: typeof SHEETS[number]; k: number }) {
  return (
    <svg viewBox="0 0 300 190" aria-hidden="true">
      <rect x="8" y="8" width="284" height="174" rx="5" className="lp-fan-paper" />
      <g className="lp-fan-frame">
        <path d="M8 44 H292 M232 44 V182" />
      </g>
      {s.draw(k)}
      <g fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace" fontSize="8.5" opacity={0.4 + 0.6 * k}>
        <text x="20" y="28" fill="#c9cfd8">{s.name.toUpperCase()}</text>
        <text x="240" y="28" fill="#5b616c">1:50</text>
      </g>
      {/* the label and the line from it: the one thing every style has in common */}
      <g opacity={k}>
        <rect x="196" y="104" width="76" height="15" rx="3" className="lp-fan-lbl" />
        <text x="202" y="115" fontFamily="ui-monospace, SFMono-Regular, monospace" fontSize="8" fill="#e8ecf1">
          KV1-X31-16
        </text>
        <path d="M196 112 L150 96" stroke="#c026d3" strokeWidth="1.2" fill="none" />
        <circle cx="150" cy="96" r="3.4" fill="#0b0d10" stroke="#c026d3" strokeWidth="1.6" />
      </g>
    </svg>
  );
}

export default function StyleFan() {
  const { ref, p } = useSectionProgress<HTMLElement>();
  const pp = usePointerParallax();
  const open = Math.min(1, Math.max(0, (p - 0.05) / 0.45));
  const at = Math.min(SHEETS.length - 1, Math.floor(p * SHEETS.length * 0.999));

  return (
    <section className="lp-fan" ref={ref} id="stilar">
      <div className="lp-fan-pin">
        <div className="lp-sec-head">
          <div className="lp-kicker">Stilar</div>
          <h2 className="lp-h2">{tr("En metodik, inte en mall")}</h2>
          <p>
            Varje kontor ritar rör på sitt sätt. Ingenting av det är inställt någonstans — läsningen kommer fram
            till hur just det här bladets rör ser ut genom att se var bladets egna etiketter landar.
          </p>
        </div>
        <div className="lp-fan-grid">
          <div className="lp-fan-stage" style={{ transform: `rotateX(${10 - 6 * open}deg) rotateY(${pp.x * 5}deg)` }}>
            {SHEETS.map((s, i) => {
              const mid = (SHEETS.length - 1) / 2;
              const d = i - mid;
              const on = i === at;
              const k = Math.min(1, Math.max(0, (p - 0.08 - i * 0.13) / 0.28));
              return (
                <div key={s.name} className={`lp-fan-card${on ? " on" : ""}`}
                  style={{
                    transform: `translateX(${d * 27 * open}%) translateZ(${(on ? 74 : 0) - Math.abs(d) * 30}px) `
                      + `rotateY(${-d * 15 * open}deg) rotateZ(${d * 1.2 * open}deg)`,
                    zIndex: 10 - Math.abs(Math.round(d * 2)),
                  }}>
                  <Sheet s={s} k={k} />
                  <span className="lp-fan-note">{s.note}</span>
                </div>
              );
            })}
          </div>
          <ol className="lp-beats lp-fan-list">
            {SHEETS.map((s, i) => (
              <li key={s.name} className={i === at ? "on" : i < at ? "past" : ""}>
                <span className="no">{String(i + 1).padStart(2, "0")}</span>
                <span><b>{s.name}</b><em>{s.note}</em></span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
