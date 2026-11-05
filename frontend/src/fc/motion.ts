import { useEffect, useLayoutEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";

/* Dahls rörelse, på ett ställe.
 *
 * Tre regler bär hela systemet:
 *
 *   1. **Ingen React-state per bildruta.** Allt som rör sig gör det genom en ref och gsap; komponenten
 *      renderas en gång och sedan aldrig mer under rullningen. En scen som sätter state på varje scrollhändelse
 *      renderar om hela trädet sextio gånger i sekunden, och det är den vanligaste orsaken till att en
 *      "smooth" sida hackar.
 *   2. **Allt städas.** Varje hook returnerar en `gsap.Context` som dödas när komponenten lämnar. Utan det
 *      överlever ScrollTrigger sin egen komponent, mäter ett element som inte finns och kastar.
 *   3. **Reducerad rörelse får innehållet direkt.** Ingen resa, inget väntande, ingen dold text. Det är inte en
 *      nedbantad version - det är samma sida utan koreografi.
 */

gsap.registerPlugin(ScrollTrigger);

export const EASE_PRIMARY = "power3.out";
export const EASE_REVEAL = "expo.out";
export const EASE_EXIT = "power3.in";
export const DURATION_FAST = 0.28;
export const DURATION_MEDIUM = 0.62;
export const DURATION_SLOW = 1.1;

/** Den som bett om mindre rörelse, eller sitter på en maskin som inte klarar den. */
export function prefersStill(): boolean {
  if (typeof window === "undefined") return true;
  return !!window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
}

/** Pekdon utan hovring: telefon och platta. Där byggs inga muspekare och inga magneter. */
export function isCoarse(): boolean {
  if (typeof window === "undefined") return true;
  return !!window.matchMedia?.("(pointer: coarse)")?.matches;
}

/* ---------------------------------------------------------------- mjuk rullning */

let lenis: Lenis | null = null;

/** Den enda Lenis-instansen. Sidor frågar efter den; ingen skapar en till. */
export function getLenis(): Lenis | null {
  return lenis;
}

/**
 * Mjuk rullning för hela dokumentet, med ScrollTrigger kopplad till den.
 *
 * Lenis flyttar sidan själv i stället för att låta webbläsaren göra det, och ScrollTrigger måste då få veta
 * att den ska mäta mot Lenis klocka och inte mot sin egen. Utan `ScrollTrigger.update` i Lenis-slingan ligger
 * varje fastnålad scen en bildruta efter innehållet, vilket syns som att texten glider mot sin egen bakgrund.
 */
export function useSmoothScroll(enabled = true) {
  useEffect(() => {
    if (!enabled || prefersStill() || isCoarse()) return;
    const l = new Lenis({
      duration: 1.05,
      easing: (t: number) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      smoothWheel: true,
      touchMultiplier: 1.6,
    });
    lenis = l;
    l.on("scroll", ScrollTrigger.update);
    const tick = (time: number) => l.raf(time * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);
    return () => {
      gsap.ticker.remove(tick);
      l.destroy();
      lenis = null;
    };
  }, [enabled]);
}

/** Hoppa till ett element eller en punkt genom samma rullning som allt annat. */
export function scrollTo(target: string | HTMLElement | number, offset = 0) {
  const l = getLenis();
  if (l) { l.scrollTo(target as never, { offset, duration: 1.2 }); return; }
  const el = typeof target === "string" ? document.querySelector(target) : target;
  if (typeof el === "number") window.scrollTo({ top: el + offset, behavior: "smooth" });
  else if (el instanceof HTMLElement) window.scrollTo({ top: el.offsetTop + offset, behavior: "smooth" });
}

/* ---------------------------------------------------------------- scenbyggaren */

/**
 * En scen: gsap i ett sammanhang som städas, med elementet som rot.
 *
 * `build` körs en gång när elementet finns. Allt som skapas där hör till sammanhanget och dör med det, så en
 * komponent kan aldrig lämna en ScrollTrigger efter sig. Får `build` reducerad rörelse som andra argument kan
 * den välja att bara sätta sluttillståndet.
 */
export function useScene<T extends HTMLElement = HTMLDivElement>(
  build: (ctx: { root: T; still: boolean; gsap: typeof gsap; ScrollTrigger: typeof ScrollTrigger }) => void,
  deps: unknown[] = [],
) {
  const ref = useRef<T>(null);
  useLayoutEffect(() => {
    const root = ref.current;
    if (!root) return;
    const still = prefersStill();
    const ctx = gsap.context(() => build({ root, still, gsap, ScrollTrigger }), root);
    return () => ctx.revert();
    // scenen byggs om bara när den som äger den säger till: `build` sluts om sin egen render och skulle annars
    // byggas om varje gång komponenten renderade, vilket river och reser varje ScrollTrigger på nytt
  }, deps);
  return ref;
}

/* ---------------------------------------------------------------- vanliga rörelser */

/** Något som kommer fram underifrån bakom sin egen kant när det rullas in i bild. */
export function riseIn(targets: gsap.TweenTarget, still: boolean, extra: gsap.TweenVars = {}) {
  if (still) { gsap.set(targets, { clearProps: "all" }); return; }
  return gsap.from(targets, {
    yPercent: 110,
    duration: DURATION_SLOW,
    ease: EASE_REVEAL,
    stagger: 0.075,
    ...extra,
  });
}

/** En bildyta som öppnar sig uppifrån och ned medan innehållet krymper till sin rätta storlek. */
export function revealMedia(wrap: Element, inner: Element | null, still: boolean, trigger?: Element) {
  if (still) return;
  const tl = gsap.timeline({
    scrollTrigger: { trigger: trigger || wrap, start: "top 82%", once: true },
  });
  tl.from(wrap, { clipPath: "inset(100% 0% 0% 0%)", duration: 1.25, ease: EASE_REVEAL });
  if (inner) tl.from(inner, { scale: 1.16, duration: 1.45, ease: EASE_REVEAL }, 0);
  return tl;
}

/** Ett format som rör sig långsammare än sidan. Sparsamt: två av tio ytor, inte tio av tio. */
export function parallax(inner: Element, still: boolean, amount = 12) {
  if (still) return;
  return gsap.fromTo(inner, { yPercent: -amount }, {
    yPercent: amount,
    ease: "none",
    scrollTrigger: { trigger: inner.parentElement || inner, start: "top bottom", end: "bottom top", scrub: true },
  });
}
