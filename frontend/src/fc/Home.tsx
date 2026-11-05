import { useRef, useState } from "react";
import { t as tr, num } from "../i18n";
import { Link } from "react-router-dom";
import gsap from "gsap";
import Nav, { Logo } from "./Nav";
import Preloader from "./Preloader";
import Demos from "./Demos";
import Blueprint, { RUNS, SYS } from "./Blueprint";
import {
  AppLink, ChapterIndicator, CountUp, CustomCursor, HorizontalGallery, LineReveal, MagneticButton,
  PinnedSection, RevealMedia, ScrollProgress, TechnicalLabel, WordReveal,
} from "./primitives";
import { EASE_REVEAL, useScene, useSmoothScroll } from "./motion";
import "./fc.css";
import "./home.css";

/* Dahls startsida, som en berättelse i fem kapitel.
 *
 * Sidan är inte en lista med funktioner. Den är resan en mängd gör: från bladet, genom läsningen, till
 * kalkylen - och sedan vidare till den som ska lära sig göra det själv. Varje kapitel är en scen med egen
 * koreografi, och kapitlen glider in i varandra i stället för att staplas.
 *
 * Språket är delat med avsikt. Displaytypografin och de tekniska etiketterna är engelska, för det är märkets
 * röst och namnet är engelskt. Allt man ska förstå - brödtext, knappar, akademin, verktyget - är svenska, för
 * det är språket arbetet görs på.
 */

const CHAPTERS = [
  { id: "kap-1", label: "The Future of Calculation" },
  { id: "kap-2", label: "From Drawing to Quantity" },
  { id: "kap-3", label: "Intelligence Built for VVS" },
  { id: "kap-4", label: "Learn. Measure. Calculate." },
  { id: "kap-5", label: "The Future Starts Here" },
];

/* ---------------------------------------------------------------- hjälten */

function Hero() {
  const ref = useScene<HTMLElement>(({ root, still }) => {
    const head = root.querySelectorAll(".fc-hero-l .fc-line-in");
    const plan = root.querySelector(".fc-hero-plan");
    const meta = root.querySelectorAll(".fc-hero-meta > *");
    const foot = root.querySelector(".fc-hero-foot");

    if (still) return;

    // Öppningen: raderna reser sig, bladet ritar sig själv, etiketterna tänds en efter en.
    //
    // Rören ritas med sin egen streckning i stället för att tonas in. Det är skillnaden mellan en bild som
    // dyker upp och en ritning som blir till, och det är det senare sidan handlar om.
    const runs = root.querySelectorAll<SVGPathElement>(".fc-hero-plan .bp-run");
    runs.forEach((r) => {
      const len = r.getTotalLength();
      r.style.strokeDasharray = String(len);
      r.style.strokeDashoffset = String(len);
    });
    const leaders = root.querySelectorAll(".fc-hero-plan .bp-leader");
    gsap.set(leaders, { opacity: 0 });

    const tl = gsap.timeline({ delay: 0.15 });
    tl.from(head, { yPercent: 112, duration: 1.15, ease: EASE_REVEAL, stagger: 0.075 })
      .from(plan, { clipPath: "inset(100% 0% 0% 0%)", duration: 1.5, ease: EASE_REVEAL }, 0.25)
      .to(runs, { strokeDashoffset: 0, duration: 2.1, ease: "power2.inOut", stagger: 0.14 }, 0.55)
      .to(leaders, { opacity: 1, duration: 0.5, stagger: 0.1 }, 1.5)
      .from(meta, { opacity: 0, y: 12, duration: 0.6, stagger: 0.07 }, 0.75)
      .from(foot, { opacity: 0, y: 16, duration: 0.7 }, 0.95);

    // Rullningen: rubriken lämnar fortare än ritningen, etiketterna glider undan, och allt tonar bort innan
    // nästa kapitel tar över. Ingen hård kant mellan hjälten och det som kommer.
    const scrub = { trigger: root, start: "top top", end: "bottom top", scrub: 0.6 };
    gsap.to(".fc-hero-l", { yPercent: -28, opacity: 0.1, ease: "none", scrollTrigger: scrub });
    gsap.to(plan, { yPercent: -8, scale: 1.06, ease: "none", scrollTrigger: scrub });
    gsap.to(".fc-hero-meta", { yPercent: -60, opacity: 0, ease: "none", scrollTrigger: scrub });
    gsap.to(foot, { opacity: 0, ease: "none", scrollTrigger: { ...scrub, end: "40% top" } });
  }, []);

  return (
    <section ref={ref} className="fc-hero" id="kap-1">
      {/* Bakgrunden är filmen: två kalkylatorer framför ett blad. Bilden under den visas där filmen inte spelas
          (minskad rörelse, en webbläsare utan H.264) och medan den laddar. */}
      <div className="fc-hero-media" aria-hidden="true">
        <video className="fc-hero-video" src="/hero.mp4" poster="/hero-poster.jpg" autoPlay muted loop playsInline preload="auto" />
        <div className="fc-hero-shade" />
      </div>
      <div className="fc-hero-plan" aria-hidden="true"><Blueprint /></div>

      <div className="fc-hero-in">
        <p className="fc-label fc-hero-eyebrow">{tr("Dahl — Estimation / Intelligence")}</p>
        <h1 className="fc-hero-l fc-display fc-display-xl">
          <span className="fc-line"><span className="fc-line-in">{tr("THE FUTURE")}</span></span>
          <span className="fc-line"><span className="fc-line-in">{tr("OF VVS")}</span></span>
          <span className="fc-line"><span className="fc-line-in"><i className="fc-italic">calculation</i></span></span>
        </h1>
      </div>

      <div className="fc-hero-meta" aria-hidden="true">
        <TechnicalLabel k="System" v="VS01" />
        <TechnicalLabel k="DN" v="25" />
        <TechnicalLabel k="Length" v="12,48 m" />
        <TechnicalLabel k="Status" v="Beräknad" on />
        <TechnicalLabel k="Projekt" v="2407" />
      </div>

      <div className="fc-hero-foot">
        <p className="fc-lead">{tr("Från ritning till färdig kalkyl. Varje meter läst ur bladets egna beteckningar.")}</p>
        <div className="fc-hero-cta">
          <MagneticButton className="solid" href="/login">{tr("Enter Dahl")} <span aria-hidden="true">→</span></MagneticButton>
          <MagneticButton href="#kap-2">{tr("Se hur den läser")}</MagneticButton>
        </div>
      </div>
    </section>
  );
}

/* ---------------------------------------------------------------- kapitelskylt */

/* Kapitelskylten.
 *
 * Den låg förut som en egen skärm med luft över och under, och gjorde sidan till en trappa: en skylt, ett
 * tomt fält, en scen, ett tomt fält. Nu står den tätt mot det den introducerar - rubrik och ingress bredvid
 * varandra i stället för under - och scenen börjar direkt efter. */
function ChapterOpener({ n, title, sub, id }: { n: string; title: string; sub: string; id?: string }) {
  return (
    <section className="fc-chap" id={id}>
      <div className="fc-chap-rule" />
      <p className="fc-label">Chapter {n}</p>
      <div className="fc-chap-in">
        <LineReveal as="h2" className="fc-display fc-display-lg fc-chap-t" text={title} />
        <p className="fc-body fc-chap-s">{sub}</p>
      </div>
    </section>
  );
}

/* ---------------------------------------------------------------- systemet i bild
 *
 * Riktiga vyer ur den inloggade appen, inte illustrationer: den som funderar på att använda Dahl vill se
 * vad hon får. En flik per rum; bilden byts i samma ram, så ögat stannar på samma ställe medan innehållet växlar.
 * Bilderna är tagna ur en riktig läsning av ett riktigt blad (public/screens).
 */
const SCREENS = [
  { id: "analys", t: "Läsningen", d: "Varje rör färgat efter sin beteckning, mängden bredvid. Tryck på en rad så visas exakt vilka sträckor och etiketter den kommer ur." },
  { id: "3d", t: "3D", d: "Samma läsning som en byggnad: rören i sina system, ritningen som golv, beteckningarna där rören går." },
  { id: "cad", t: "CAD", d: "Rita det som saknas: väggar, rum, öppningar, rör. Plan och 3D sida vid sida, med lager, mått och export till IFC och DXF." },
  { id: "kalkyl", t: "Kalkyl", d: "Mängden blir material ur grossistens bok och timmar ur Normtid VVS, rad för rad, med påslag och anbudssumma." },
  { id: "agent", t: "Agenten", d: "Fråga ritningen med röst eller text. Agenten markerar själv röret den pratar om och svarar med metrarna ur läsningen." },
];
function SystemScreens() {
  const [on, setOn] = useState(0);
  const cur = SCREENS[on];
  return (
    <section className="fc-scr" id="kap-1b">
      <div className="fc-scr-in">
        <header className="fc-scr-head">
          <p className="fc-label fc-label-on">{tr("Systemet i bild")}</p>
          <h2 className="fc-display fc-display-md">{tr("Ritningen in.")} <i className="fc-italic">{tr("Mängden, modellen och kalkylen ut.")}</i></h2>
        </header>
        <div className="fc-scr-tabs" role="tablist" aria-label={tr("Vyer i Dahl")}>
          {SCREENS.map((sc, i) => (
            <button key={sc.id} role="tab" aria-selected={i === on} className={i === on ? "on" : ""} onClick={() => setOn(i)}>
              <span className="fc-num">0{i + 1}</span> {tr(sc.t)}
            </button>
          ))}
        </div>
        <div className="fc-scr-stage">
          <figure className="fc-scr-frame">
            <div className="fc-scr-bar" aria-hidden="true"><i /><i /><i /><span>{window.location.host}/{cur.id}</span></div>
            {SCREENS.map((sc, i) => (
              <img key={sc.id} src={`/screens/${sc.id}.webp`} alt={tr(sc.t)} loading={i === 0 ? "eager" : "lazy"}
                className={i === on ? "on" : ""} />
            ))}
          </figure>
          <p className="fc-body fc-scr-cap">{tr(cur.d)}</p>
        </div>
      </div>
    </section>
  );
}

/* ---------------------------------------------------------------- påståendet som skrivs medan man rullar */

function StickyStatement() {
  const words = ["KALKYL", "SKA", "INTE", "VARA", "DET", "SOM", "BROMSAR", "DIG."];
  const ref = useRef<HTMLDivElement>(null);
  return (
    <PinnedSection
      height={300}
      className="fc-state fc-light"
      onProgress={(p) => {
        const el = ref.current;
        if (!el) return;
        const spans = el.querySelectorAll<HTMLElement>(".fc-state-w");
        // Orden tänds i takt med rullningen. Skrivet direkt på noden: en scen som sätter state per bildruta
        // renderar om hela sidan åtta gånger under en enda mening.
        spans.forEach((s, i) => {
          const at = i / spans.length;
          s.style.opacity = String(p > at ? 1 : 0.14);
        });
      }}
    >
      <div ref={ref} className="fc-state-in">
        <p className="fc-label">{tr("02 — Problemet")}</p>
        <p className="fc-state-t fc-display fc-display-lg">
          {words.map((w) => <span key={w} className="fc-state-w">{w} </span>)}
        </p>
        <p className="fc-body fc-state-b">
          En mängdning för hand tar dagar och går inte att granska i efterhand. Dahl läser bladet,
          visar vad den grundar varje meter på, och säger ifrån när ritningen är tvetydig.
        </p>
      </div>
    </PinnedSection>
  );
}

/* ---------------------------------------------------------------- mängdningen som sker framför ögonen */

function TakeoffScene() {
  const ref = useRef<HTMLDivElement>(null);
  const run = RUNS[0];

  return (
    <PinnedSection
      height={420}
      id="kap-2-scen"
      className="fc-take fc-light"
      onProgress={(p) => {
        const el = ref.current;
        if (!el) return;
        const path = el.querySelector<SVGPathElement>("#trace");
        const plan = el.querySelector<HTMLElement>(".fc-take-plan");
        const metre = el.querySelector<HTMLElement>(".fc-take-m");
        const rows = el.querySelectorAll<HTMLElement>(".fc-take-row");
        const dots = el.querySelectorAll<SVGCircleElement>(".fc-take-dot");

        // Fem steg, i den ordning en mängdare faktiskt gör dem.
        const step = (a: number, b: number) => Math.max(0, Math.min(1, (p - a) / (b - a)));

        if (plan) plan.style.opacity = String(0.25 + 0.75 * step(0, 0.14));
        el.classList.toggle("lit", p > 0.16);                    // röret tänds, resten dämpas

        if (path) {
          const len = path.getTotalLength();
          const drawn = step(0.2, 0.62);
          path.style.strokeDasharray = String(len);
          path.style.strokeDashoffset = String(len * (1 - drawn));
          if (metre) metre.textContent = num(run.m * drawn, 2);
        }
        dots.forEach((d, i) => {
          const on = p > 0.24 + i * 0.09;
          d.style.opacity = on ? "1" : "0";
          d.style.transform = on ? "scale(1)" : "scale(0.2)";
        });
        rows.forEach((r, i) => {
          const on = p > 0.66 + i * 0.07;
          r.style.opacity = on ? "1" : "0";
          r.style.transform = on ? "translateY(0)" : "translateY(14px)";
        });
      }}
    >
      <div ref={ref} className="fc-take-in">
        <header className="fc-take-head">
          <p className="fc-label">{tr("Chapter II — From Drawing to Quantity")}</p>
          <h2 className="fc-display fc-display-md">{tr("Den läser bladet")} <i className="fc-italic">{tr("rad för rad")}</i></h2>
        </header>

        <div className="fc-take-stage">
          <div className="fc-take-plan"><Blueprint labels dims={false} /></div>
          <svg className="fc-take-over" viewBox="0 0 1200 760" aria-hidden="true">
            <path id="trace" d={run.d} stroke={SYS[run.sys]} strokeWidth={5} fill="none"
              strokeLinecap="round" strokeLinejoin="round" />
            {[[170, 580], [400, 580], [400, 300], [660, 300], [660, 210]].map(([x, y], i) => (
              <circle key={i} className="fc-take-dot" cx={x} cy={y} r={7} fill={SYS[run.sys]} />
            ))}
          </svg>
        </div>

        <aside className="fc-take-side">
          <div className="fc-take-read" aria-hidden="true">
            <TechnicalLabel k="Beteckning" v="KV1-X31-25" />
            <TechnicalLabel k="DN" v="25" />
            <TechnicalLabel k="Skala" v="1:50" />
            <p className="fc-take-mwrap"><span className="fc-take-m">0,00</span> <span>m</span></p>
          </div>

          <div className="fc-take-out">
            <p className="fc-label">{tr("In i kalkylen")}</p>
            <div className="fc-take-rows">
              <div className="fc-take-row"><span>KV1-X31-25</span><span>DN25</span><span>12,48 m</span></div>
              <div className="fc-take-row"><span>{tr("Rör, koppar")}</span><span>{tr("85 kr/m")}</span><span>{tr("1 061 kr")}</span></div>
              <div className="fc-take-row"><span>Montage</span><span>0,18 h/m</span><span>2,25 h</span></div>
              <div className="fc-take-row tot"><span>Summa</span><span /><span>{tr("2 229 kr")}</span></div>
            </div>
          </div>
        </aside>
      </div>
    </PinnedSection>
  );
}

/* ---------------------------------------------------------------- raden som rör sig med rullningen */

function Marquee({ words, dir = 1 }: { words: string[]; dir?: 1 | -1 }) {
  const ref = useScene<HTMLDivElement>(({ root, still }) => {
    if (still) return;
    const track = root.querySelector(".fc-mq-t");
    gsap.fromTo(track, { xPercent: dir > 0 ? 0 : -50 }, {
      xPercent: dir > 0 ? -50 : 0, ease: "none",
      scrollTrigger: { trigger: root, start: "top bottom", end: "bottom top", scrub: 0.8 },
    });
  }, [dir]);
  const line = words.join(" — ") + " — ";
  return (
    <div ref={ref} className="fc-mq" aria-hidden="true">
      <div className="fc-mq-t"><span>{line}</span><span>{line}</span></div>
    </div>
  );
}

/* ---------------------------------------------------------------- vad plattformen består av */

const PRODUCTS = [
  { n: "01", t: "VPR", d: "Läsningen. Varje meter spårbar till bladets eget bläck.", to: "/vpr",
    tags: ["Vektorläsning", "Beteckningar", "Bevis"] },
  { n: "02", t: "Mängdning", d: "Mät själv med fångst, ortho och avdrag — eller granska maskinens mängd.", to: "/plattformen",
    tags: ["Kalibrering", "Polyline", "Avdrag"] },
  { n: "03", t: "Kalkyl", d: "Material, tid, påslag och marginal. Anbudet som PDF innan du skickar det.", to: "/plattformen",
    tags: ["Materialbok", "Påslag", "Anbud"] },
  { n: "04", t: "Projekt", d: "Hela handlingen som en modell. Blad mot blad, revision mot revision.", to: "/plattformen",
    tags: ["Handling", "Revision", "Kollision"] },
  { n: "05", t: "Academy", d: "Lär dig mängda och kalkylera på riktiga ritningar. Certifiering ingår.", to: "/utbildning",
    tags: ["Övningar", "Sluttenta", "Certifikat"] },
];

function ProductShowcase() {
  return (
    <>
      <ChapterOpener n="III" id="kap-3" title={tr("Intelligence built for VVS")}
        sub="Fem delar, en produkt. Läsningen ger mängden, mängden ger kalkylen, kalkylen ger anbudet — och akademin gör att den som läser förstår vad den ser." />
      <HorizontalGallery className="fc-show">
        {PRODUCTS.map((p) => (
          <article key={p.n} className="fc-show-card" data-cursor="view">
            <header>
              <span className="fc-label">{p.n}</span>
              <h3 className="fc-display fc-display-md">{p.t}</h3>
            </header>
            <p className="fc-body">{p.d}</p>
            <ul className="fc-show-tags">{p.tags.map((t) => <li key={t} className="fc-label">{t}</li>)}</ul>
            <Link className="fc-link" to={p.to}>{tr("Läs mer")} <span aria-hidden="true">→</span></Link>
          </article>
        ))}
      </HorizontalGallery>
    </>
  );
}

/* ---------------------------------------------------------------- akademin */

function AcademyChapter() {
  return (
    <section className="fc-ac" id="kap-4">
      <div className="fc-ac-l">
        <p className="fc-label">{tr("Chapter IV — Dahl Academy")}</p>
        <LineReveal as="h2" className="fc-display fc-display-lg" text="KNOWLEDGE BECOMES PRECISION." />
        <p className="fc-body">
          En mängdare som inte förstår bladet kan inte granska en maskin som läst det. Academy lär ut
          ritningsläsning, mängdning och kalkyl på riktiga övningsritningar — du mäter själv, systemet rättar,
          och du ser exakt var du tappade metrarna.
        </p>
        <ul className="fc-ac-list">
          {[
            ["Interaktiva övningar", "Mängda rör direkt på ritningen. Tolerans ±2 %."],
            ["Komponentmarkering", "Hitta ventiler, brunnar och apparater i bladet."],
            ["Kalkylövningar", "Material, tid, påslag och marginal steg för steg."],
            ["Sluttenta och certifikat", "Rättad på servern. Verifierbart certifikat-ID."],
          ].map(([t, d]) => (
            <li key={t}><b>{t}</b><span>{d}</span></li>
          ))}
        </ul>
        <MagneticButton className="solid" href="/utbildning">{tr("Explore education")} <span aria-hidden="true">→</span></MagneticButton>
      </div>
      <div className="fc-ac-r">
        <RevealMedia className="fc-ac-cert">
          <div className="fc-cert">
            <div className="fc-cert-top">
              <span className="fc-cert-mark"><Logo size={16} /> Dahl</span>
              <span className="fc-label">Certificate</span>
            </div>
            <p className="fc-cert-name fc-serif">{tr("Anna Lindqvist")}</p>
            <p className="fc-cert-title">{tr("Dahl Certified")}<br /><i className="fc-italic">VVS Kalkyl &amp; Mängdning</i></p>
            <div className="fc-cert-grid">
              <TechnicalLabel k="Resultat" v="87 %" on />
              <TechnicalLabel k="Utfärdat" v="2026-03-14" />
              <TechnicalLabel k="ID" v="FC-VVS-7F4K92QX" />
            </div>
            <div className="fc-cert-rule" />
          </div>
        </RevealMedia>
        <div className="fc-ac-nums">
          <div><span className="fc-display fc-display-md"><CountUp to={5} /></span><p className="fc-label">Utbildningar</p></div>
          <div><span className="fc-display fc-display-md"><CountUp to={24} /></span><p className="fc-label">Moduler</p></div>
          <div><span className="fc-display fc-display-md"><CountUp to={18} /></span><p className="fc-label">{tr("Övningstyper")}</p></div>
        </div>
      </div>
    </section>
  );
}

/* ---------------------------------------------------------------- slutet */

function FinalChapter() {
  return (
    <section className="fc-end" id="kap-5">
      <div className="fc-grid" aria-hidden="true" />
      <p className="fc-label">{tr("Chapter V")}</p>
      <WordReveal as="h2" className="fc-display fc-display-xl fc-end-t" text="READY TO CALCULATE DIFFERENTLY?" />
      <div className="fc-end-cta">
        <MagneticButton className="solid" href="/login">{tr("Enter Dahl")} <span aria-hidden="true">→</span></MagneticButton>
        <MagneticButton href="/kontakt">{tr("Boka en genomgång")}</MagneticButton>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="fc-foot">
      <div className="fc-foot-links">
        <div>
          <p className="fc-label">Plattformen</p>
          <Link className="fc-link" to="/plattformen">{tr("Översikt")}</Link>
          <Link className="fc-link" to="/vpr">VPR</Link>
          <Link className="fc-link" to="/utbildning">Academy</Link>
          <Link className="fc-link" to="/priser">Priser</Link>
        </div>
        <div>
          <p className="fc-label">{tr("Företaget")}</p>
          <Link className="fc-link" to="/om-oss">{tr("Om oss")}</Link>
          <Link className="fc-link" to="/kontakt">Kontakt</Link>
          <Link className="fc-link" to="/dokumentation">Dokumentation</Link>
        </div>
        <div>
          <p className="fc-label">Konto</p>
          <Link className="fc-link" to="/login">{tr("Logga in")}</Link>
          <AppLink className="fc-link" to="/projekt">Projekt</AppLink>
        </div>
      </div>
      <div className="fc-foot-mark" aria-hidden="true">{tr("DAHL")}</div>
      <div className="fc-foot-base">
        <span className="fc-label">{tr("VPR System / 2026")}</span>
        <span className="fc-label">{tr("Byggd i Sverige")}</span>
      </div>
    </footer>
  );
}

/* ---------------------------------------------------------------- sidan */

export default function Home() {
  useSmoothScroll();
  return (
    <div className="fc">
      <Preloader />
      <CustomCursor />
      <ScrollProgress />
      <Nav />
      <ChapterIndicator chapters={CHAPTERS} />

      <Hero />
      <ChapterOpener n="I" title={tr("The future of calculation")}
        sub="Dahl läser en VVS-ritning som en mängdare gör det: via beteckningarna och deras hänvisningslinjer, aldrig via närmaste streck. Det som inte går att avgöra får heta tvetydigt." />
      <SystemScreens />
      <Demos />
      <StickyStatement />

      <ChapterOpener n="II" id="kap-2" title={tr("From drawing to quantity")}
        sub="Ritningen in, mängdförteckningen ut — med varje meter spårbar tillbaka till det bläck den kom ur." />
      <TakeoffScene />
      <Marquee words={["MÄT", "BERÄKNA", "KONTROLLERA", "LEVERERA"]} />

      <ProductShowcase />
      <Marquee words={["VPR", "MÄNGDNING", "KALKYL", "PROJEKT", "ACADEMY"]} dir={-1} />

      <AcademyChapter />
      <FinalChapter />
      <Footer />
    </div>
  );
}
