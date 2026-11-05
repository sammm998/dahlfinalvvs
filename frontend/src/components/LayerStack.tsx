import { useSectionProgress } from "./lp-motion";
import { t as tr } from "../i18n";
import { usePointerParallax } from "./tilt";

/* The three layers a reading actually works in, as three planes that come apart.
 *
 * This is not an ornament standing in for an idea - it is the idea. The ink on the sheet is one thing, what that
 * ink forms is another, and the pipe that carries a quantity is a third. A metre is only defensible when you can
 * say which of the three it came out of, so the page pulls them apart and lets each be looked at on its own.
 */

const LAYERS = [
  {
    key: "raw",
    tag: "Lager 1",
    name: "Bläcket",
    body: "Varje streck som PDF:en faktiskt innehåller, med sin penna, sin bredd, sin färg och sitt lager. "
      + "Ingenting är tolkat än — det här är bara vad som står på papperet.",
    unit: "RawPath · Seg",
  },
  {
    key: "prim",
    tag: "Lager 2",
    name: "Formen",
    body: "Strecken som hör ihop blir sträckor, sträckorna blir ett nät med noder, och pennorna som ritar rör "
      + "skiljs från dem som ritar väggar. Fortfarande ingen identitet: bara geometri som hänger ihop.",
    unit: "Prim · PipeGraph · RepresentationFamily",
  },
  {
    key: "phys",
    tag: "Lager 3",
    name: "Röret",
    body: "Beteckningen bladet skriver, ledarlinjen därifrån till geometrin, och nätet geometrin bildar. Först "
      + "här finns ett rör med ett namn, en dimension och en längd — och hela vägen tillbaka till bläcket.",
    unit: "PhysicalPipe",
  },
];

/** Each layer's own sheet, drawn at the level of detail that layer has and no more. */
function Plate({ kind, k }: { kind: string; k: number }) {
  const draw = Math.min(1, Math.max(0, k));
  if (kind === "raw") {
    return (
      <svg viewBox="0 0 320 200" aria-hidden="true">
        <g stroke="#7b838f" strokeWidth="1" fill="none" opacity={0.6}>
          <path d="M20 30 H300 M20 30 V180 M300 30 V180 M20 180 H300 M190 30 V180" />
        </g>
        {/* loose ink: dashes, ticks and stray strokes, nothing joined up */}
        <g stroke="#c2cad6" strokeWidth="2.2" strokeLinecap="round" opacity={0.45 + 0.5 * draw}>
          {Array.from({ length: 26 }, (_, i) => {
            const x = 36 + (i % 13) * 20;
            const y = 70 + Math.floor(i / 13) * 46;
            return <line key={i} x1={x} y1={y} x2={x + 12} y2={y} />;
          })}
          {Array.from({ length: 7 }, (_, i) => (
            <line key={`v${i}`} x1={214 + i * 12} y1={58} x2={214 + i * 12} y2={70} />
          ))}
        </g>
      </svg>
    );
  }
  if (kind === "prim") {
    return (
      <svg viewBox="0 0 320 200" aria-hidden="true">
        <g stroke="#5c636f" strokeWidth="1" fill="none" opacity={0.5}>
          <path d="M20 30 H300 M20 30 V180 M300 30 V180 M20 180 H300" />
        </g>
        {/* the same ink, joined into runs, with the nodes where they meet */}
        <g fill="none" stroke="#b6bec9" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round"
           pathLength={1} strokeDasharray="1" strokeDashoffset={1 - draw}>
          <path d="M40 70 H160 V116 H280" />
          <path d="M40 116 H160" />
          <path d="M100 70 V150 H240" />
        </g>
        <g fill="#0b0d10" stroke="#c9cfd8" strokeWidth="1.6" opacity={draw}>
          {[[160, 70], [160, 116], [100, 70], [100, 116], [100, 150], [240, 150]].map(([x, y]) => (
            <circle key={`${x}-${y}`} cx={x} cy={y} r="4" />
          ))}
        </g>
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 320 200" aria-hidden="true">
      <g stroke="#2b3038" strokeWidth="1" fill="none" opacity={0.35}>
        <path d="M20 30 H300 M20 30 V180 M300 30 V180 M20 180 H300" />
      </g>
      {/* the same shape, now owned: a colour per identity, and a length beside it */}
      <g fill="none" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round"
         pathLength={1} strokeDasharray="1" strokeDashoffset={1 - draw}>
        <path d="M40 70 H160 V116 H280" stroke="#00b5e2" />
        <path d="M40 116 H160" stroke="#60a5fa" />
        <path d="M100 70 V150 H240" stroke="#f0abfc" />
      </g>
      <g fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace" fontSize="9.5" opacity={draw}>
        <text x="44" y="62" fill="#00b5e2">S3-R8-110 · 24,8 m</text>
        <text x="44" y="134" fill="#60a5fa">{tr("KV1-X31-16 · 12,1 m")}</text>
        <text x="112" y="166" fill="#f0abfc">{tr("VV1-X31-16 · 18,2 m")}</text>
      </g>
    </svg>
  );
}

export default function LayerStack() {
  const { ref, p } = useSectionProgress<HTMLElement>();
  const pp = usePointerParallax();
  // the plates lie on each other until the section is entered, then separate and stay apart
  const open = Math.min(1, Math.max(0, (p - 0.06) / 0.5));
  const at = Math.min(LAYERS.length - 1, Math.floor(p * LAYERS.length * 0.999));

  return (
    <section className="lp-layers" ref={ref} id="lager">
      <div className="lp-layers-pin">
        <div className="lp-sec-head">
          <div className="lp-kicker">{tr("Tre lager")}</div>
          <h2 className="lp-h2">{tr("Varje meter vet vilket lager den kom ur")}</h2>
        </div>
        <div className="lp-layers-grid">
          <div className="lp-stack" style={{
            transform: `rotateX(${44 - 14 * open}deg) rotateZ(${-19 + 6 * open}deg) `
              + `rotateY(${pp.x * 3}deg) translateY(${-8 * open}px)`,
          }}>
            {LAYERS.map((l, i) => {
              // apart in depth *and* across, or the plate on top simply hides the two under it and the point -
              // that each layer holds something of its own - is made by a stack you cannot see into
              const lift = open * (i - 1) * 88;
              const k = Math.min(1, Math.max(0, (p - 0.1 - i * 0.16) / 0.3));
              return (
                <div key={l.key} className={`lp-plate${i === at ? " on" : ""}`}
                  style={{ transform: `translate3d(${lift * 0.72}px, ${lift * -0.16}px, ${lift}px)`,
                           zIndex: i + 1 }}>
                  <Plate kind={l.key} k={k} />
                  <span className="lp-plate-tag">{l.unit}</span>
                </div>
              );
            })}
          </div>
          <ol className="lp-beats lp-layers-list">
            {LAYERS.map((l, i) => (
              <li key={l.key} className={i === at ? "on" : i < at ? "past" : ""}>
                <span className="no">{l.tag.replace("Lager ", "0")}</span>
                <span>
                  <b>{l.name}</b>
                  <em>{l.body}</em>
                </span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
