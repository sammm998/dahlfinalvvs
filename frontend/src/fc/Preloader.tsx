import { useEffect, useRef, useState } from "react";
import { t as tr } from "../i18n";
import gsap from "gsap";
import { EASE_EXIT, EASE_REVEAL, prefersStill } from "./motion";

/* Öppningen.
 *
 * En räknare från 0 till 100 medan sidans typsnitt och första bild laddas, och sedan en ridå som går upp.
 * Två saker gör den till en öppning i stället för en väntan:
 *
 *   * **Den ljuger inte.** Räknaren följer `document.fonts.ready` och första bilden. Är allt redan i cachen tar
 *     den slut nästan direkt - en förladdare som alltid tar två sekunder är bara två sekunder.
 *   * **Den går en gång.** Den visas vid första besöket på sidan, inte vid varje navigering inne på den. En
 *     ridå mellan två klick i samma meny är i vägen.
 *
 * Reducerad rörelse hoppar över alltihop och visar sidan.
 */

const SEEN = "fc-intro-seen";

export default function Preloader({ onDone }: { onDone?: () => void }) {
  const [gone, setGone] = useState(() => {
    if (typeof window === "undefined") return true;
    if (prefersStill()) return true;
    try { return sessionStorage.getItem(SEEN) === "1"; } catch { return false; }
  });
  const root = useRef<HTMLDivElement>(null);
  const num = useRef<HTMLSpanElement>(null);
  const bar = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (gone) { onDone?.(); return; }
    try { sessionStorage.setItem(SEEN, "1"); } catch { /* privat läge: då visas den igen, och det är rimligt */ }
    document.documentElement.classList.add("fc-loading");

    const box = { v: 0 };
    const write = () => { if (num.current) num.current.textContent = String(Math.round(box.v)).padStart(3, "0"); };
    write();

    // Räknaren går till 92 medan det laddas, och resten först när det faktiskt är klart.
    const crawl = gsap.to(box, { v: 92, duration: 2.2, ease: "power2.out", onUpdate: write });
    gsap.to(bar.current, { scaleX: 0.92, duration: 2.2, ease: "power2.out" });

    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      crawl.kill();
      const tl = gsap.timeline({
        onComplete: () => {
          document.documentElement.classList.remove("fc-loading");
          setGone(true);
          onDone?.();
        },
      });
      tl.to(box, { v: 100, duration: 0.42, ease: "power2.inOut", onUpdate: write })
        .to(bar.current, { scaleX: 1, duration: 0.42, ease: "power2.inOut" }, 0)
        .to(".fc-pre-row", { yPercent: -120, duration: 0.6, ease: EASE_EXIT, stagger: 0.05 }, "+=0.12")
        .to(root.current, { clipPath: "inset(0% 0% 100% 0%)", duration: 0.95, ease: EASE_REVEAL }, "-=0.3");
    };

    const ready = Promise.all([
      (document as Document & { fonts?: FontFaceSet }).fonts?.ready ?? Promise.resolve(),
      new Promise<void>((r) => {
        if (document.readyState === "complete") return r();
        window.addEventListener("load", () => r(), { once: true });
      }),
    ]);
    ready.then(finish);
    const cap = window.setTimeout(finish, 3600);      // en laddning som aldrig blir klar får inte låsa sidan
    return () => { window.clearTimeout(cap); crawl.kill(); document.documentElement.classList.remove("fc-loading"); };
  }, [gone, onDone]);

  if (gone) return null;
  return (
    <div ref={root} className="fc-pre" role="status" aria-label={tr("Laddar Dahl")}>
      <div className="fc-pre-in">
        <div className="fc-pre-row"><span className="fc-pre-mark">Dahl</span></div>
        <div className="fc-pre-row fc-pre-meta">
          <span className="fc-label">{tr("VVS / ESTIMATION / INTELLIGENCE")}</span>
          <span className="fc-pre-num"><span ref={num}>000</span></span>
        </div>
        <div className="fc-pre-row fc-pre-track"><div ref={bar} className="fc-pre-bar" /></div>
      </div>
    </div>
  );
}
