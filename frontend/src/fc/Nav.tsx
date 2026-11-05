import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { LangSwitch } from "../components/SiteHeader";
import { t as tr } from "../i18n";

import { getToken } from "../api";
import gsap from "gsap";
import { EASE_REVEAL, prefersStill } from "./motion";
import { MagneticButton } from "./primitives";

/* Raden högst upp, och rummet bakom den.
 *
 * Navigeringen är två saker. Uppe ligger en tunn rad som aldrig tar plats: ordmärket, några länkar, och vägen
 * in i verktyget. Bakom MENY ligger hela vyn: fem stora nummer och fem stora ord.
 *
 * Det som gör en fullskärmsmeny användbar och inte bara stor:
 *   * Esc stänger den, och fokus går tillbaka till knappen som öppnade.
 *   * Fokus fastnar inne i den så länge den är öppen - annars tabbar man ut i en sida man inte ser.
 *   * Sidan bakom slutar rulla, utan att hoppa i sidled när rullisten försvinner.
 */

export const NAV_LINKS = [
  { to: "/plattformen", label: "Plattformen", n: "01" },
  { to: "/vpr", label: "VPR", n: "02" },
  // Den publika akademisidan, inte appens - /academy ligger bakom inloggningen, och en publik meny ska inte
  // skicka en besökare till en inloggningsruta när sidan den lovade faktiskt finns.
  { to: "/utbildning", label: "Academy", n: "03" },
  { to: "/architecture", label: "Architecture", n: "04" },
  { to: "/priser", label: "Priser", n: "05" },
  { to: "/om-oss", label: "Dahl", n: "06" },
  { to: "/kontakt", label: "Kontakt", n: "07" },
];

export default function Nav({ light = false }: { light?: boolean }) {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  // läses när menyn öppnas, inte en gång vid montering: den som loggar in i en annan flik ska få rätt meny
  const inne = open && !!getToken();
  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLButtonElement>(null);

  useEffect(() => { setOpen(false); }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const el = panel.current;
    if (!el) return;

    const pad = window.innerWidth - document.documentElement.clientWidth;
    const prev = document.body.style.cssText;
    document.body.style.overflow = "hidden";
    if (pad > 0) document.body.style.paddingRight = `${pad}px`;

    const still = prefersStill();
    const ctx = gsap.context(() => {
      if (still) return;
      // Båda ändarna skrivs ut. `from` lämnar målet underförstått - "dit där elementet redan står" - och när
      // den punkten läses medan rutan just monterats blev startvärdet också slutvärdet: menyraderna animerade
      // ned 108 % av sin egen höjd och stannade där, utanför radens överflow. Kvar syntes numren och linjerna,
      // och inte ett enda ord. `fromTo` säger var rörelsen slutar, och clearProps tar bort stilen efteråt så
      // att raden står med sitt eget utseende och hovringens förskjutning fungerar som den ska.
      const tl = gsap.timeline();
      tl.fromTo(el, { clipPath: "inset(0% 0% 100% 0%)" },
                { clipPath: "inset(0% 0% 0% 0%)", duration: 0.78, ease: EASE_REVEAL, clearProps: "clipPath" })
        .fromTo(".fc-menu-row .fc-line-in, .fc-menu-row-in", { yPercent: 108 },
                { yPercent: 0, duration: 0.85, ease: EASE_REVEAL, stagger: 0.06, clearProps: "transform" }, "-=0.42")
        .fromTo(".fc-menu-side > *", { opacity: 0, y: 14 },
                { opacity: 1, y: 0, duration: 0.5, stagger: 0.06, clearProps: "opacity,transform" }, "-=0.45");
    }, el);

    const focusable = () =>
      Array.from(el.querySelectorAll<HTMLElement>('a[href], button:not([disabled])')).filter((n) => n.offsetParent !== null);
    focusable()[0]?.focus();

    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setOpen(false); opener.current?.focus(); return; }
      if (e.key !== "Tab") return;
      const list = focusable();
      if (!list.length) return;
      const first = list[0], last = list[list.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      document.body.style.cssText = prev;
      ctx.revert();
    };
  }, [open]);

  return (
    <>
      <header className={`fc-nav${light ? " light" : ""}`}>
        <Link className="fc-nav-mark" to="/" aria-label={tr("Dahl, till startsidan")}>
          <Logo />
          <span>Dahl</span>
        </Link>
        <nav className="fc-nav-links" aria-label="Huvudmeny">
          {NAV_LINKS.slice(0, 4).map((l) => (
            <Link key={l.to} to={l.to} className={pathname.startsWith(l.to) ? "on" : ""} data-cursor="cta">{tr(l.label)}</Link>
          ))}
        </nav>
        <div className="fc-nav-right">
          <LangSwitch />
          <MagneticButton className="sm solid fc-nav-cta" href="/login">
            Enter Dahl <span aria-hidden="true">↗</span>
          </MagneticButton>
          <button ref={opener} className="fc-nav-menu" onClick={() => setOpen(true)}
            aria-expanded={open} aria-haspopup="dialog">
            <span className="fc-nav-menu-t">Meny</span>
            <span className="fc-nav-menu-i" aria-hidden="true"><i /><i /></span>
          </button>
        </div>
      </header>

      {open && (
        <div ref={panel} className="fc-menu" role="dialog" aria-modal="true" aria-label="Meny">
          <div className="fc-menu-top">
            <span className="fc-label">{tr("Dahl / Meny")}</span>
            <button className="fc-menu-x" onClick={() => { setOpen(false); opener.current?.focus(); }}>
              Stäng <span aria-hidden="true">✕</span>
            </button>
          </div>
          <div className="fc-menu-body">
            <ul className="fc-menu-list">
              {NAV_LINKS.map((l) => (
                <li key={l.to} className="fc-menu-row">
                  <Link to={l.to} data-cursor="cta">
                    <span className="fc-menu-n">{l.n}</span>
                    <span className="fc-menu-row-in">{l.label}</span>
                  </Link>
                </li>
              ))}
            </ul>
            {/* Genvägarna ska leda dit den som klickar faktiskt kan komma. Projekt och Academy ligger bakom
                inloggningen, så för den som inte är inloggad var "Dahl Academy" en resa till
                inloggningssidan - och för den som är inloggad ett hopp rakt från den mörka publika sidan in i
                det ljusa verktyget, utan något steg emellan. Utloggad pekar spalten därför på det publika:
                utbildningssidan och dokumentationen, med inloggningen först. Inloggad pekar den in i
                verktyget, där det ljusa läget är väntat. */}
            <div className="fc-menu-side">
              <p className="fc-label">{tr("Direkt in")}</p>
              {inne ? (
                <>
                  <Link className="fc-link" to="/projekt">Projekt</Link>
                  <Link className="fc-link" to="/academy">{tr("Dahl Academy")}</Link>
                  <Link className="fc-link" to="/mangda">{tr("Mängda ett blad")}</Link>
                </>
              ) : (
                <>
                  <Link className="fc-link" to="/login">{tr("Logga in")}</Link>
                  <Link className="fc-link" to="/utbildning">VVS-akademin</Link>
                  <Link className="fc-link" to="/priser">Priser</Link>
                </>
              )}
              <Link className="fc-link" to="/dokumentation">Dokumentation</Link>
              <p className="fc-label" style={{ marginTop: 28 }}>Kontakt</p>
              <a className="fc-link" href="https://www.dahl.se/" target="_blank" rel="noreferrer">dahl.se</a>
            </div>
          </div>
          <div className="fc-menu-foot">
            <span className="fc-label">{tr("Dahl / VPR System / 2026")}</span>
          </div>
        </div>
      )}
    </>
  );
}

/** Märket: två rör som möts i en nod. Samma figur som mängdningen bygger sina nät av. */
export function Logo({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M2 13.5h5.2V6h5.6v7.5H18" stroke="currentColor" strokeWidth="1.7" strokeLinecap="square" />
      <circle cx="7.2" cy="13.5" r="1.7" fill="currentColor" />
    </svg>
  );
}
