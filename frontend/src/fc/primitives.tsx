import { createElement, useEffect, useRef, useState, type ReactNode } from "react";
import { locale } from "../i18n";
import { useNavigate } from "react-router-dom";

import { getToken } from "../api";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { splitChars, splitLines, splitWords } from "./split";
import {
  DURATION_MEDIUM, DURATION_SLOW, EASE_PRIMARY, EASE_REVEAL, isCoarse, prefersStill, scrollTo, useScene,
} from "./motion";

/* Dahls rörelsedelar.
 *
 * Varje del gör en sak och städar efter sig. Ingen av dem sätter React-state under rullning; det som rör sig
 * gör det genom gsap på en ref. Den som bett om mindre rörelse får innehållet direkt, utan resa.
 */

type El = keyof JSX.IntrinsicElements;

/* ---------------------------------------------------------------- text som kommer fram */

function useSplitReveal(
  how: (el: HTMLElement) => { lines: HTMLElement[]; inners: HTMLElement[]; restore: () => void },
  text: string,
  opts: { stagger: number; y: number; delay: number; start: string },
) {
  return useScene<HTMLElement>(({ root, still }) => {
    if (still) return;
    const split = how(root);
    if (!split.inners.length) return;
    gsap.set(split.inners, { yPercent: opts.y, display: "inline-block" });
    gsap.to(split.inners, {
      yPercent: 0,
      duration: DURATION_SLOW,
      ease: EASE_REVEAL,
      stagger: opts.stagger,
      delay: opts.delay,
      scrollTrigger: { trigger: root, start: opts.start, once: true },
    });
    // Delningen mäts mot en bredd. Byter bredden byter raderna, och masken måste läggas om.
    let t = 0;
    const onResize = () => {
      window.clearTimeout(t);
      t = window.setTimeout(() => { split.restore(); ScrollTrigger.refresh(); }, 180);
    };
    window.addEventListener("resize", onResize);
    return () => { window.removeEventListener("resize", onResize); window.clearTimeout(t); split.restore(); };
  }, [text]);
}

/** En rubrik som kommer fram rad för rad bakom sin egen kant. */
export function LineReveal(
  { as = "h2", text, className = "", stagger = 0.085, delay = 0, start = "top 86%" }:
  { as?: El; text: string; className?: string; stagger?: number; delay?: number; start?: string },
) {
  const ref = useSplitReveal(splitLines, text, { stagger, y: 108, delay, start });
  return createElement(as, { ref, className: `fc-rv ${className}`.trim() }, text);
}

/** Ord för ord. För korta rubriker där varje ord ska räknas för sig. */
export function WordReveal(
  { as = "h2", text, className = "", stagger = 0.045, delay = 0, start = "top 86%" }:
  { as?: El; text: string; className?: string; stagger?: number; delay?: number; start?: string },
) {
  const ref = useSplitReveal(splitWords, text, { stagger, y: 112, delay, start });
  return createElement(as, { ref, className: `fc-rv ${className}`.trim() }, text);
}

/** Tecken för tecken. Bara för etiketter och mycket korta ord. */
export function CharacterReveal(
  { as = "span", text, className = "", stagger = 0.022, delay = 0, start = "top 90%" }:
  { as?: El; text: string; className?: string; stagger?: number; delay?: number; start?: string },
) {
  const ref = useSplitReveal(splitChars, text, { stagger, y: 106, delay, start });
  return createElement(as, { ref, className: `fc-rv ${className}`.trim() }, text);
}

/* ---------------------------------------------------------------- ytor */

/** En bildyta som öppnar sig uppifrån medan innehållet krymper till sin rätta storlek. */
export function RevealMedia(
  { children, className = "", parallax = 0 }: { children: ReactNode; className?: string; parallax?: number },
) {
  const ref = useScene<HTMLDivElement>(({ root, still }) => {
    const inner = root.firstElementChild as HTMLElement | null;
    if (still || !inner) return;
    const tl = gsap.timeline({ scrollTrigger: { trigger: root, start: "top 84%", once: true } });
    tl.from(root, { clipPath: "inset(100% 0% 0% 0%)", duration: 1.3, ease: EASE_REVEAL })
      .from(inner, { scale: 1.16, duration: 1.5, ease: EASE_REVEAL }, 0);
    if (parallax > 0) {
      gsap.fromTo(inner, { yPercent: -parallax }, {
        yPercent: parallax, ease: "none",
        scrollTrigger: { trigger: root, start: "top bottom", end: "bottom top", scrub: true },
      });
    }
  }, []);
  return <div ref={ref} className={`fc-media ${className}`.trim()}>{children}</div>;
}

/** En yta vars innehåll rör sig långsammare än sidan. Innehållet måste vara högre än ytan. */
export function ParallaxMedia(
  { children, className = "", amount = 12 }: { children: ReactNode; className?: string; amount?: number },
) {
  const ref = useScene<HTMLDivElement>(({ root, still }) => {
    const inner = root.firstElementChild as HTMLElement | null;
    if (still || !inner) return;
    gsap.fromTo(inner, { yPercent: -amount }, {
      yPercent: amount, ease: "none",
      scrollTrigger: { trigger: root, start: "top bottom", end: "bottom top", scrub: true },
    });
  }, [amount]);
  return <div ref={ref} className={`fc-par ${className}`.trim()}>{children}</div>;
}

/* ---------------------------------------------------------------- scener */

/**
 * En scen som står still medan sidan rullar förbi den.
 *
 * Yttre elementet är högt - `height` gånger vyhöjden - och det inre står fast i en vy. Rullningen blir då en
 * tidslinje: `onProgress` får 0..1 och ritar scenen, utan att komponenten renderas om en enda gång.
 */
export function PinnedSection(
  { children, height = 250, className = "", onProgress, id }:
  { children: ReactNode; height?: number; className?: string; onProgress?: (p: number, root: HTMLElement) => void; id?: string },
) {
  const ref = useScene<HTMLDivElement>(({ root, still }) => {
    const inner = root.querySelector<HTMLElement>(".fc-pin-in");
    if (!inner) return;
    if (still) { onProgress?.(1, root); return; }
    ScrollTrigger.create({
      trigger: root,
      start: "top top",
      end: "bottom bottom",
      onUpdate: (self) => onProgress?.(self.progress, root),
      onRefresh: (self) => onProgress?.(self.progress, root),
    });
  }, []);
  return (
    <section ref={ref} id={id} className={`fc-pin ${className}`.trim()} style={{ height: `${height}vh` }}>
      <div className="fc-pin-in">{children}</div>
    </section>
  );
}

/** En rad som visar hur långt ned på sidan man kommit. */
export function ScrollProgress() {
  const ref = useScene<HTMLDivElement>(({ root, still }) => {
    if (still) return;
    gsap.fromTo(root, { scaleX: 0 }, {
      scaleX: 1, ease: "none", transformOrigin: "left center",
      scrollTrigger: { start: 0, end: "max", scrub: 0.3 },
    });
  }, []);
  return <div className="fc-sp" aria-hidden="true"><div ref={ref} className="fc-sp-bar" /></div>;
}

/** Kapitelnumret, diskret i kanten. */
export function ChapterIndicator(
  { chapters, className = "" }: { chapters: { id: string; label: string }[]; className?: string },
) {
  const [at, setAt] = useState(0);
  useEffect(() => {
    // Vilket kapitel man är i är det sista vars början passerat, inte det som råkar vara aktivt just nu.
    // Mellan två kapitel finns luft - en scen som slutat och en som inte börjat - och ett "aktivt"-prov
    // svarade då ingenting alls och numret stod kvar på föregående kapitel hela vägen genom nästa.
    const triggers = chapters.map((c, i) =>
      ScrollTrigger.create({
        trigger: `#${c.id}`,
        start: "top 60%",
        onEnter: () => setAt(i),
        onEnterBack: () => setAt(i),
        onLeaveBack: () => setAt(Math.max(0, i - 1)),
      }));
    return () => triggers.forEach((t) => t.kill());
  }, [chapters]);
  return (
    <div className={`fc-ci ${className}`.trim()} aria-hidden="true">
      <span className="fc-ci-n">{String(at + 1).padStart(2, "0")}</span>
      <span className="fc-ci-sep">/</span>
      <span className="fc-ci-t">{String(chapters.length).padStart(2, "0")}</span>
      <span className="fc-ci-l">{chapters[at]?.label}</span>
    </div>
  );
}

/* ---------------------------------------------------------------- knappar och länkar */

/**
 * En knapp vars innehåll följer pekaren, mycket lite.
 *
 * Utslaget är en åttondel av avståndet till mitten och slutar helt när pekaren lämnar. Mer än så blir en
 * leksak; mindre märks inte. Ingenting av detta finns på en pekskärm, där det inte går att sikta ändå.
 */
export function MagneticButton(
  { children, className = "", onClick, href, to, pull = 0.18, ...rest }:
  { children: ReactNode; className?: string; onClick?: () => void; href?: string; to?: string; pull?: number },
) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || isCoarse() || prefersStill()) return;
    const inner = el.querySelector(".fc-mag-in");
    const move = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      const dx = e.clientX - (r.left + r.width / 2);
      const dy = e.clientY - (r.top + r.height / 2);
      gsap.to(el, { x: dx * pull, y: dy * pull, duration: 0.5, ease: EASE_PRIMARY });
      if (inner) gsap.to(inner, { x: dx * pull * 0.4, y: dy * pull * 0.4, duration: 0.5, ease: EASE_PRIMARY });
    };
    const leave = () => {
      gsap.to(el, { x: 0, y: 0, duration: 0.7, ease: "elastic.out(1, 0.5)" });
      if (inner) gsap.to(inner, { x: 0, y: 0, duration: 0.7, ease: "elastic.out(1, 0.5)" });
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerleave", leave);
    return () => {
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerleave", leave);
      gsap.killTweensOf([el, inner].filter(Boolean) as Element[]);
    };
  }, [pull]);
  const cls = `fc-btn fc-mag ${className}`.trim();
  const body = <span className="fc-mag-in">{children}</span>;
  if (href) return <a ref={ref as never} className={cls} href={href} data-cursor="cta" {...rest}>{body}</a>;
  if (to) {
    return (
      <a ref={ref as never} className={cls} href={to} data-cursor="cta"
        onClick={(e) => { e.preventDefault(); onClick?.(); }} {...rest}>{body}</a>
    );
  }
  return <button ref={ref as never} type="button" className={cls} onClick={onClick} data-cursor="cta" {...rest}>{body}</button>;
}

/** En länk vars understrykning dras från vänster och lämnar åt höger. */
export function AnimatedLink(
  { children, className = "", ...rest }: { children: ReactNode; className?: string } & Record<string, unknown>,
) {
  return <a className={`fc-link ${className}`.trim()} data-cursor="cta" {...rest}>{children}</a>;
}

/* ---------------------------------------------------------------- siffror */

/**
 * En siffra som räknas upp när den kommer i bild.
 *
 * Talet skrivs rakt i noden i stället för i state: en uppräkning genom React är sextio omritningar i sekunden
 * av ett helt träd för att byta fyra tecken. Slutvärdet står i `aria-label`, så en uppläsare hör resultatet
 * och inte resan.
 */
export function CountUp(
  { to, decimals = 0, suffix = "", prefix = "", duration = 1.6, className = "" }:
  { to: number; decimals?: number; suffix?: string; prefix?: string; duration?: number; className?: string },
) {
  const fmt = (v: number) =>
    prefix + v.toLocaleString(locale(), { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) + suffix;
  const ref = useScene<HTMLSpanElement>(({ root, still }) => {
    if (still) { root.textContent = fmt(to); return; }
    const box = { v: 0 };
    root.textContent = fmt(0);
    gsap.to(box, {
      v: to, duration, ease: EASE_PRIMARY,
      onUpdate: () => { root.textContent = fmt(box.v); },
      scrollTrigger: { trigger: root, start: "top 90%", once: true },
    });
  }, [to, decimals, suffix, prefix]);
  return <span ref={ref} className={`fc-num ${className}`.trim()} aria-label={fmt(to)} />;
}

/** Ritningens röst: SYSTEM / VS01. Etikett till vänster, värde till höger. */
export function TechnicalLabel(
  { k, v, on = false, className = "" }: { k: string; v: string; on?: boolean; className?: string },
) {
  return (
    <span className={`fc-tl ${className}`.trim()}>
      <span className="fc-tl-k">{k}</span>
      <span className="fc-tl-s">/</span>
      <span className={`fc-tl-v${on ? " on" : ""}`}>{v}</span>
    </span>
  );
}

/* ---------------------------------------------------------------- pekaren */

/**
 * En egen muspekare på desktop.
 *
 * En prick som följer med, och en ring som släpar efter. Över något som går att öppna växer ringen och får
 * ett ord. Den byggs aldrig på en pekskärm och aldrig för den som bett om mindre rörelse - och den ersätter
 * inte systemets pekare där man skriver, för en textmarkör säger något som en prick inte kan.
 */
export function CustomCursor() {
  useEffect(() => {
    if (isCoarse() || prefersStill()) return;
    const dot = document.createElement("div");
    dot.className = "fc-cur-dot";
    const ring = document.createElement("div");
    ring.className = "fc-cur-ring";
    ring.innerHTML = '<span class="fc-cur-t"></span>';
    document.body.append(dot, ring);
    document.body.classList.add("fc-has-cursor");
    const label = ring.querySelector(".fc-cur-t") as HTMLElement;

    const qdx = gsap.quickTo(dot, "x", { duration: 0.08, ease: "none" });
    const qdy = gsap.quickTo(dot, "y", { duration: 0.08, ease: "none" });
    const qrx = gsap.quickTo(ring, "x", { duration: 0.42, ease: EASE_PRIMARY });
    const qry = gsap.quickTo(ring, "y", { duration: 0.42, ease: EASE_PRIMARY });

    const move = (e: PointerEvent) => {
      qdx(e.clientX); qdy(e.clientY); qrx(e.clientX); qry(e.clientY);
      const t = (e.target as HTMLElement)?.closest?.("[data-cursor]") as HTMLElement | null;
      const kind = t?.dataset.cursor || "";
      const text = kind === "view" ? "VISA" : kind === "cta" ? "→" : kind === "drag" ? "DRA" : "";
      if (label.textContent !== text) label.textContent = text;
      ring.classList.toggle("on", !!kind);
    };
    const down = () => ring.classList.add("down");
    const up = () => ring.classList.remove("down");
    window.addEventListener("pointermove", move, { passive: true });
    window.addEventListener("pointerdown", down);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerdown", down);
      window.removeEventListener("pointerup", up);
      document.body.classList.remove("fc-has-cursor");
      dot.remove(); ring.remove();
    };
  }, []);
  return null;
}

/* ---------------------------------------------------------------- vågrätt galleri */

/**
 * En rad som flyttar sig i sidled medan sidan rullar nedåt. Bara på desktop: på en telefon blir samma
 * innehåll en vanlig lodrät lista, för en sida som kapar rullningen på en telefon är en sida man lämnar.
 */
export function HorizontalGallery(
  { children, className = "", id }: { children: ReactNode; className?: string; id?: string },
) {
  const ref = useScene<HTMLDivElement>(({ root, still }) => {
    const track = root.querySelector<HTMLElement>(".fc-hg-track");
    if (!track || still || window.innerWidth < 900) return;
    const span = () => Math.max(0, track.scrollWidth - window.innerWidth + 80);
    gsap.to(track, {
      x: () => -span(),
      ease: "none",
      scrollTrigger: {
        trigger: root, start: "top top", end: () => `+=${span()}`,
        pin: true, scrub: 0.6, invalidateOnRefresh: true, anticipatePin: 1,
      },
    });
  }, []);
  return (
    <section ref={ref} id={id} className={`fc-hg ${className}`.trim()}>
      <div className="fc-hg-track">{children}</div>
    </section>
  );
}

/** Hoppa dit, genom samma rullning som allt annat. */
export function JumpLink({ to, children, className = "" }: { to: string; children: ReactNode; className?: string }) {
  return (
    <a className={className} href={to} data-cursor="cta"
      onClick={(e) => { e.preventDefault(); scrollTo(to); }}>{children}</a>
  );
}

export { DURATION_MEDIUM, EASE_PRIMARY, EASE_REVEAL };

/* En länk in i verktyget, från en sida där besökaren kan vara utloggad.
 *
 * Publika sidor pekar på "Mängda", "CAD", "Projekt" - rum som ligger bakom inloggningen. Utloggad hamnade man
 * på inloggningssidan utan att den visste vart man var på väg, så efter inloggningen kom man till projekt-
 * listan i stället för dit man klickade. Åtta länkar på de publika sidorna gjorde så.
 *
 * Nu bär vägen med sig målet: utloggad går länken till /login?next=<målet>, och inloggningen fortsätter dit
 * när den är klar. Inloggad går den rakt fram. Läget läses vid klicket, inte vid renderingen, så den som
 * loggat in i en annan flik inte skickas till inloggningen i onödan.
 */
export function AppLink({ to, children, className, ...rest }:
    { to: string; children: React.ReactNode; className?: string } & Record<string, unknown>) {
  const nav = useNavigate();
  return (
    <a
      href={to}
      className={className}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;   // öppna i ny flik ska fungera
        e.preventDefault();
        nav(getToken() ? to : `/login?next=${encodeURIComponent(to)}`);
      }}
      {...rest}
    >
      {children}
    </a>
  );
}
