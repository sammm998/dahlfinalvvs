import { useEffect } from "react";
import { t as tr } from "../i18n";
import { Link } from "react-router-dom";
import "../landing.css";
import LandingScene from "../components/LandingScene";
import SiteHeader from "../components/SiteHeader";
import FeatureArt from "../components/FeatureArt";
import { FEATURES } from "../features";
import LayerStack from "../components/LayerStack";
import EvidenceSection from "../components/EvidenceSection";
import StyleFan from "../components/StyleFan";
import AgentShowcase from "../components/AgentShowcase";
import AcademySection from "../components/AcademySection";
import { useCountUp, useInView, useScrollProgress } from "../components/lp-motion";
import { useParallax, useSmoothScroll } from "../components/lp-smooth";
import RevealLines from "../components/Reveal";
import ChapterBar from "../components/ChapterBar";
import { tiltStyle, usePointerParallax, useTilt } from "../components/tilt";

/* The drawing in the hero is the product's own subject: a dash-dot waste run with a branch, two labels on
   leaders, and the marks the engine puts back on the paper. It draws itself in once, then the labels land. */
function Drawing() {
  return (
    <svg viewBox="0 0 1040 380" role="img" aria-label={tr("Planritning där rören markerats och mätts")}>
      <defs>
        <linearGradient id="lpFade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#6ee7a5" stopOpacity="0.95" />
          <stop offset="1" stopColor="#6ee7a5" stopOpacity="0.55" />
        </linearGradient>
        <clipPath id="lpWipe" clipPathUnits="userSpaceOnUse">
          <rect className="lp-wipe" x="0" y="0" width="1040" height="380" />
        </clipPath>
      </defs>

      {/* the building, drawn faintly: this is what the engine must not measure */}
      <g stroke="#3a4049" strokeWidth="1.5" fill="none">
        <path d="M70 60 H620 V320 H70 Z" />
        <path d="M320 60 V320 M70 200 H320 M470 200 H620" />
        <path d="M660 60 H970 V190 H660 Z M660 230 H970 V320 H660 Z" />
      </g>
      <g stroke="#262b33" strokeWidth="1.1" fill="none">
        {[110, 150, 250, 290].map((y) => (
          <path key={y} d={`M86 ${y} H304`} />
        ))}
      </g>

      {/* the pipes, in the drawing's own dash-dot */}
      <g fill="none" strokeWidth="3.6" strokeLinecap="butt" clipPath="url(#lpWipe)">
        <path d="M120 260 H430 V140 H590 V96 H900" stroke="url(#lpFade)" strokeDasharray="20 7 3.5 7" />
        <path d="M430 260 H760 V236" stroke="#60a5fa" strokeOpacity="0.85" strokeDasharray="20 7 3.5 7" />
      </g>

      {/* connection circles where the runs stop */}
      <g className="lp-pop" fill="#07080a" stroke="#6ee7a5" strokeWidth="2.2">
        <circle cx="120" cy="260" r="5.5" />
        <circle cx="900" cy="96" r="5.5" />
      </g>
      <g className="lp-pop" fill="#07080a" stroke="#60a5fa" strokeWidth="2.2">
        <circle cx="760" cy="236" r="5.5" />
      </g>

      {/* labels on their leaders, the way the sheet writes them */}
      <g className="lp-pop" style={{ animationDelay: "1.65s" }}>
        <path d="M470 96 L560 100" stroke="#6ee7a5" strokeOpacity="0.5" strokeWidth="1.2" fill="none" />
        <path d="M372 74 H470" stroke="#6ee7a5" strokeOpacity="0.5" strokeWidth="1.2" fill="none" />
        <text x="372" y="66" fill="#f4f5f7" fontSize="16" fontFamily="ui-monospace, SFMono-Regular, monospace">
          S1-P5-110
        </text>
        <text x="372" y="92" fill="#8b929e" fontSize="14" fontFamily="ui-monospace, SFMono-Regular, monospace">
          24,8 m
        </text>
      </g>
      <g className="lp-pop" style={{ animationDelay: "1.85s" }}>
        <path d="M520 196 L600 258" stroke="#60a5fa" strokeOpacity="0.5" strokeWidth="1.2" fill="none" />
        <path d="M418 196 H520" stroke="#60a5fa" strokeOpacity="0.5" strokeWidth="1.2" fill="none" />
        <text x="418" y="188" fill="#f4f5f7" fontSize="16" fontFamily="ui-monospace, SFMono-Regular, monospace">
          KV1-X7-32
        </text>
        <text x="418" y="214" fill="#8b929e" fontSize="14" fontFamily="ui-monospace, SFMono-Regular, monospace">
          11,4 m
        </text>
      </g>

      {/* one run the drawing does not name: shown, never counted */}
      <g className="lp-pop" style={{ animationDelay: "2.05s" }}>
        <path d="M690 290 H950" stroke="#565d6a" strokeWidth="3.2" strokeDasharray="18 6 3 6" fill="none" />
        <text x="690" y="280" fill="#6a7280" fontSize="13.5" fontFamily="ui-monospace, SFMono-Regular, monospace">
          onämnd — redovisas, mäts inte
        </text>
      </g>
    </svg>
  );
}

function LineSample({ color, dash }: { color: string; dash: string }) {
  return (
    <svg width="104" height="12" viewBox="0 0 104 12" aria-hidden="true">
      <path d="M2 6 H102" stroke={color} strokeWidth="2.6" strokeDasharray={dash} strokeLinecap="round" fill="none" />
    </svg>
  );
}

const LINES: { code: string; name: string; line: string; color: string; dash: string }[] = [
  { code: "KV / VV / VVC", name: "Tappkall-, tappvarm- och cirkulationsvatten", line: "Heldragen, över golv", color: "#6ee7a5", dash: "" },
  { code: "S", name: "Spillvatten — självfall, ofta gjutjärn i stam och PP liggande", line: "Streckad i eller under golv", color: "#f0abfc", dash: "14 6" },
  { code: "D / DR", name: "Dagvatten och dränering", line: "Streckad, grövre dimensioner", color: "#fcd34d", dash: "14 6" },
  { code: "VS / VP", name: "Värme sekundär och primär, fram- och returledning", line: "Punktstreckad under tak", color: "#60a5fa", dash: "16 5 3 5" },
  { code: "KB / KM", name: "Köldbärare och kylsystem", line: "Punktstreckad, egen penna", color: "#67e8f9", dash: "16 5 3 5" },
  { code: "SP / G / TA", name: "Sprinkler, gas och tryckluft", line: "Egen linjetyp per system", color: "#fb923c", dash: "20 5 3 5 3 5" },
];

function Figure({ to, suffix, decimals, label }: { to: number; suffix?: string; decimals?: number; label: string }) {
  const { ref, seen } = useInView<HTMLDivElement>();
  const n = useCountUp(to, seen);
  return (
    <div ref={ref} className={`lp-fig${seen ? " in" : ""}`}>
      <div className="n">{n.toFixed(decimals ?? 0).replace(".", ",")}{suffix ?? ""}</div>
      <div className="l">{label}</div>
    </div>
  );
}

function Figures() {
  return (
    <section className="lp-wrap">
      <div className="lp-figures">
        <Figure to={15.46} decimals={2} suffix=" m" label={tr("samlad avvikelse mot facit över fyra referensritningar")} />
        <Figure to={377} label={tr("sidor i stilbiblioteket, körda sida för sida vid varje ändring")} />
        <Figure to={180} label={tr("tester som måste hålla innan en siffra får ändras")} />
        <Figure to={0} label={tr("gissningar — identitet endast via riktiga ledarlinjer, aldrig närmaste rör")} />
      </div>
    </section>
  );
}

/* The hero, as depth rather than as a stack of images.
 *
 * Three planes at three distances: the film furthest back, the drawing on the paper, and the identities the
 * reading lifts off it nearest the reader. They part as the pointer moves and settle as the page is scrolled
 * away, which is the same motion the product makes - the pipes come off the sheet.
 */
function Stage() {
  const pp = usePointerParallax();
  const s = useScrollProgress();
  const near = Math.max(0, 1 - s * 5.5);                     // the deck flattens as the hero leaves
  const d = (z: number) => ({
    transform: `translate3d(${pp.x * z * near}px, ${pp.y * z * 0.55 * near}px, 0) `
      + `rotateY(${pp.x * -2.4 * near}deg) rotateX(${pp.y * 1.8 * near}deg)`,
  });
  return (
    <div className="lp-stage-art lp-deck" aria-hidden="true">
      <div className="lp-plane far" style={d(9)}>
        <video className="lp-video" src="/hero.mp4" autoPlay muted loop playsInline preload="auto" />
      </div>
      <div className="lp-plane mid" style={d(20)}>
        <div className="lp-stage-draw"><Drawing /></div>
      </div>
      {/* what the reading takes off the paper, floating in front of it */}
      <div className="lp-plane near" style={d(38)}>
        {[["KV1-X31-16", "17,10 m", 12, 21], ["S3-R8-110", "58,40 m", 57, 11],
          ["VV1-X31-16", "33,92 m", 76, 38], ["S1-P2-75", "4,73 m", 63, 58]].map(([t, m, x, y], i) => (
          <span key={t as string} className="lp-chip" style={{ left: `${x}%`, top: `${y}%`, animationDelay: `${1.1 + i * 0.22}s` }}>
            <i style={{ background: ["#6ee7a5", "#f0abfc", "#60a5fa", "#fbbf24"][i] }} />
            {t}<b>{m}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

/* One of the three screens on the bench, leaning in space until the reader looks straight at it. */
function Screen({ turn, children, caption }: { turn: number; children: React.ReactNode; caption: React.ReactNode }) {
  const { tilt, handlers } = useTilt(7);
  const flat = tilt.over;
  return (
    <figure className="lp-bench-fig" {...handlers}
      style={{ transform: `rotateY(${flat ? tilt.ry : turn}deg) rotateX(${flat ? tilt.rx : 0}deg) `
        + `translateZ(${flat ? 34 : 0}px)`, ...tiltStyle(tilt, 0) }}>
      {children}
      <figcaption>{caption}</figcaption>
    </figure>
  );
}

/* Vad plattformen består av, och vägen in i var och en.
 *
 * Startsidan visade läsningen och lite av resten i förbigående. Men den som kommer hit vill veta vad som
 * finns - CAD, 3D, mängdning för hand, agenten, kalkylen, akademin - och sedan kunna gå in i den han kom för.
 * Varje kort är en egen sida med sin egen figur, sina siffror och sin guide. */
function Funktioner() {
  return (
    <section className="lp-sec lp-wrap" id="funktioner">
      <div className="lp-sec-head">
        <div className="lp-kicker">Plattformen</div>
        <RevealLines text="Sju rum, ett hus" />
        <p>
          Läsningen är kärnan, men en mängd blir sällan färdig i ett steg. Rita det som saknas, mät det som
          måste mätas för hand, fråga agenten, räkna fram anbudet — och lär dig läsa bladet under tiden.
        </p>
      </div>
      <div className="lp-feat">
        {FEATURES.map((f, i) => (
          <Link key={f.slug} to={`/funktioner/${f.slug}`} className={`lp-feat-card${i === 0 ? " lead" : ""}`}
            style={{ ["--ac" as any]: f.accent }}>
            <span className="lf-art"><FeatureArt id={f.art} accent={f.accent} /></span>
            <span className="lf-body">
              <span className="lp-mono">{f.kicker}</span>
              <b>{f.nav}</b>
              <i>{f.card}</i>
              <span className="lf-go">{tr("Läs mer")} <span aria-hidden="true">→</span></span>
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}

const ANCHORS = [
  { href: "#funktioner", label: "Plattformen" },
  { href: "#hur", label: "Så fungerar det" },
  { href: "#lager", label: "Tre lager" },
  { href: "#stilar", label: "Stilar" },
  { href: "#agent", label: "Agenten" },
  { href: "#ror", label: "Rörtyper" },
  { href: "#belagg", label: "Beläggen" },
];

export default function Landing() {
  useEffect(() => {
    document.body.classList.add("lp-dark");
    return () => document.body.classList.remove("lp-dark");
  }, []);
  const scrolled = useScrollProgress();
  useSmoothScroll();
  useParallax();
  return (
    <div className="lp">
      <SiteHeader anchors={ANCHORS} cta={{ to: "/login", label: "Starta projekt" }} />

      <div className="lp-rail" aria-hidden="true">
        <div className="lp-rail-fill" style={{ transform: `scaleY(${scrolled})` }} />
      </div>
      <div className="lp-scrollpct" aria-hidden="true">Skroll · {Math.round(scrolled * 100)} %</div>
      <ChapterBar chapters={ANCHORS} />

      <header className="lp-stage">
        <Stage />
        <h1 className="lp-huge">
          Mängden som<br />ritningen<br />redan säger
        </h1>
        <div className="lp-stage-foot">
          <p className="lp-mono">
            AI-plattform för VVS-mängdning ur ren vektor.<br />
            Ingen OCR i mätvägen — identitet endast via ledarlinjer.
          </p>
          <a className="lp-mono lp-arrow" href="#hur">{tr("Se hur det läser")} <span>→</span></a>
        </div>
      </header>

      <section className="lp-band">
        <p className="lp-band-lede">
          Ladda upp en VVS-ritning. Systemet läser sidans egen beteckningslista, följer varje ledarlinje till det
          rör den pekar på, och mäter i ritningens egen skala.
        </p>
        <div className="lp-screens lp-bench">
          <Screen turn={9} caption={<><b>{tr("Mängdning")}</b> {tr("beteckningsdriven tolkning direkt på ritningen")}</>}>
            <div className="lp-screen"><Drawing /></div>
          </Screen>
          <Screen turn={0} caption={<><b>{tr("Mängder")}</b> {tr("varje meter med sitt belägg kvar")}</>}>
            <div className="lp-screen lp-screen-table">
              <div className="lp-row head"><span>Beteckning</span><span>{tr("Sträckor")}</span><span>Totalt</span></div>
              {[["S3-R8-110", "5", "46,39"], ["KV1-X31-16", "3", "17,11"], ["VV1-X31-16", "5", "33,92"],
                ["S3-R8-75", "20", "22,42"], ["S1-P2-110", "1", "9,64"]].map((r) => (
                <div className="lp-row" key={r[0]}><span>{r[0]}</span><span>{r[1]}</span><span>{r[2]}</span></div>
              ))}
              <div className="lp-row sum"><span>Summa</span><span>34</span><span>212,57</span></div>
            </div>
          </Screen>
          <Screen turn={-9} caption={<><b>Facitkontroll</b> {tr("varje körning mäts mot handmängdad ritning")}</>}>
            <div className="lp-screen lp-screen-check">
              <div className="lp-row head"><span>Beteckning</span><span>Facit</span><span>{tr("Vårt")}</span><span>Avvikelse</span></div>
              {[["KV1-X31-16", "17,40", "17,10", "−0,30"], ["S3-R8-160", "16,30", "16,43", "+0,13"],
                ["VV1-X31-16", "34,10", "33,92", "−0,18"]].map((r) => (
                <div className="lp-row" key={r[0]}><span>{r[0]}</span><span>{r[1]}</span><span>{r[2]}</span><span>{r[3]}</span></div>
              ))}
              <div className="lp-ok">{tr("3,69 m samlad avvikelse på 213,70 m")}</div>
            </div>
          </Screen>
        </div>
      </section>

      <Figures />

      <Funktioner />

      <LandingScene />

      <LayerStack />

      <StyleFan />

      <section className="lp-sec lp-wrap lp-light" id="ror">
        <div className="lp-sec-head">
          <div className="lp-kicker">{tr("Rörtyper")}</div>
          <RevealLines text="Alla system på sidan, var för sig" />
          <p>
            Svensk ritstandard låter linjetypen berätta var röret ligger och beteckningen vilket system det är.
            Systemet läser båda — och håller isär tappvatten, spillvatten, värme och kyla i mängden.
          </p>
        </div>
        <div className="lp-legend">
          <table>
            <thead>
              <tr>
                <th>Linje</th>
                <th>Beteckning</th>
                <th>{tr("System och hur det ritas")}</th>
              </tr>
            </thead>
            <tbody>
              {LINES.map((l) => (
                <tr key={l.code}>
                  <td className="line">
                    <LineSample color={l.color} dash={l.dash} />
                  </td>
                  <td className="code">{l.code}</td>
                  <td>
                    {l.name} — <span style={{ color: "var(--lp-faint)" }}>{l.line}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="lp-under" style={{ marginTop: 16 }}>
          Linjetyperna följer svensk praxis (över golv heldragen, i eller under golv streckad, under tak
          punktstreckad). Men avgörandet tas alltid mot sidans egen beteckningslista — det är därför andra
          kontors stilar också går att läsa.
        </p>
      </section>

      <AgentShowcase />

      <EvidenceSection />

      <AcademySection />

      <section className="lp-sec lp-wrap lp-light">
        <div className="lp-quote">
          <p>
            “Tvetydigt är ett giltigt svar. Fel säkerhet är det inte. Där ritningen inte säger vilket rör en
            etikett menar får du frågan — inte en siffra som ser rätt ut.”
          </p>
          <p className="who">{tr("Principen hela motorn är byggd kring")}</p>
        </div>
      </section>

      <section className="lp-close lp-wrap">
        <RevealLines text="Ladda upp en ritning och se vad den säger" />
        <p>{tr("Ta en sida du redan mängdat för hand. Jämför. Det är den enda rimliga första körningen.")}</p>
        <div className="lp-cta">
          <Link className="lp-btn primary lg" to="/login">
            Kom igång
          </Link>
        </div>
      </section>

      <footer className="lp-wrap">
        <div className="lp-foot">
          <span className="lp-logo" style={{ fontSize: 14 }}>
            <svg width="18" height="18" viewBox="0 0 22 22" aria-hidden="true">
              <path d="M3 15 H8 V7 H14 V15 H19" stroke="#5b616c" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Dahl
          </span>
          <span className="sp" />
          <Link to="/hur-det-funkar">{tr("Hur det funkar")}</Link>
          <Link to="/architecture">{tr("Architecture")}</Link>
          <Link to="/priser">{tr("Priser")}</Link>
          <Link to="/utbildning">{tr("Utbildning")}</Link>
          <Link to="/om-oss">{tr("Om oss")}</Link>
          <Link to="/dokumentation">{tr("Dokumentation")}</Link>
          <Link to="/kontakt">{tr("Kontakta oss")}</Link>
          <Link to="/login">{tr("Logga in")}</Link>
        </div>
      </footer>
    </div>
  );
}
