import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { lang, setLang, t as tr } from "../i18n";

/* En meny, överallt.
 *
 * Startsidan hade hörnknappar utan navigation och de publika sidorna en egen rad med länkar, så fältet högst
 * upp bytte utseende när man klickade sig vidare - man kom till en annan webbplats i stället för till nästa rum
 * i samma hus. Den här raden är densamma på varje sida: samma logotyp, samma länkar, samma knapp längst till
 * höger. Sidan man står på är tänd.
 *
 * Startsidans avsnittsankare hör bara hemma på startsidan, så de ligger i den utfällda menyn under en egen
 * rubrik i stället för i raden. Raden ser då likadan ut var man än är, och ankarna finns ändå kvar.
 */

export const PUBLIC_LINKS: { to: string; label: string }[] = [
  { to: "/hur-det-funkar", label: "Hur det funkar" },
  { to: "/architecture", label: "Architecture" },
  { to: "/priser", label: "Priser" },
  { to: "/utbildning", label: "Utbildning" },
  { to: "/om-oss", label: "Om oss" },
  { to: "/dokumentation", label: "Dokumentation" },
  { to: "/kontakt", label: "Kontakta oss" },
];

/* Språkväljaren. Två knappar, inte en meny: det finns två språk, och ett byte laddar om sidan så att varje
   sträng i appen kommer tillbaka på rätt språk i stället för hälften av dem. */
export function LangSwitch({ className = "" }: { className?: string }) {
  return (
    <div className={`lp-pill sh-lang ${className}`.trim()} role="group" aria-label={tr("Språk")}>
      <button type="button" aria-pressed={lang === "sv"} className={lang === "sv" ? "on" : ""}
        onClick={() => setLang("sv")} title={tr("Svenska")}>SV</button>
      <button type="button" aria-pressed={lang === "en"} className={lang === "en" ? "on" : ""}
        onClick={() => setLang("en")} title={tr("Engelska")}>EN</button>
    </div>
  );
}

function Mark({ size = 17, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 22 22" aria-hidden="true">
      <path d="M3 15 H8 V7 H14 V15 H19" stroke={color} strokeWidth="2.3" fill="none"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function SiteHeader({ anchors, cta }:
  { anchors?: { href: string; label: string }[]; cta?: { to: string; label: string } }) {
  const { pathname } = useLocation();
  const [menu, setMenu] = useState(false);
  const [lifted, setLifted] = useState(false);
  useEffect(() => setMenu(false), [pathname]);
  // raden lyfter fram ur bakgrunden när sidan rullar, så den syns över ljus ritning lika väl som över mörkt
  useEffect(() => {
    const on = () => setLifted(window.scrollY > 24);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  const start = cta ?? { to: "/login", label: tr("Logga in") };
  return (
    <>
      <div className={`lp-corners${lifted ? " lifted" : ""}`}>
        <button className="lp-pill sh-burger" aria-expanded={menu}
          aria-label={menu ? "Stäng menyn" : "Öppna menyn"} onClick={() => setMenu((m) => !m)}>
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            {menu
              ? <path d="M3 3 L13 13 M13 3 L3 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              : <path d="M2 4 H14 M2 8 H14 M2 12 H14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />}
          </svg>
          <span className="sh-burger-t">Meny</span>
        </button>

        <Link className="lp-logo lp-pill" to="/" aria-label={tr("Till startsidan")}>
          <Mark color="#6ee7a5" />
          {/* Ordmärket i ett eget element, så den smalaste skärmen kan behålla märket och släppa orden utan att
              släppa ikonen med dem. Namnet finns kvar för uppläsning via aria-label på länken. */}
          <span className="lp-logo-t">Dahl</span>
        </Link>

        <span className="lp-sp" />

        <nav className="sh-nav" aria-label="Sidor">
          {PUBLIC_LINKS.map((l) => (
            <Link key={l.to} to={l.to}
              className={pathname === l.to || pathname.startsWith(`${l.to}/`) ? "on" : ""}>
              {tr(l.label)}
            </Link>
          ))}
        </nav>

        <LangSwitch />

        <Link className="lp-pill lp-start" to={start.to}>{start.label} <span className="plus">→</span></Link>
      </div>

      {menu && (
        <div className="lp-menu sh-menu">
          <div className="sh-menu-in">
            <div className="sh-menu-col">
              <p className="lp-mono">Sidor</p>
              {PUBLIC_LINKS.map((l) => (
                <Link key={l.to} to={l.to} className={pathname === l.to ? "on" : ""}>{l.label}</Link>
              ))}
            </div>
            {!!anchors?.length && (
              <div className="sh-menu-col">
                <p className="lp-mono">{tr("På den här sidan")}</p>
                {anchors.map((a) => <a key={a.href} href={a.href} onClick={() => setMenu(false)}>{a.label}</a>)}
              </div>
            )}
            <div className="sh-menu-col">
              <p className="lp-mono">{tr("Kom igång")}</p>
              <Link to="/login" className="go">{tr("Logga in")}</Link>
              <Link to="/utbildning">{tr("Lär dig läsa ritningen")}</Link>
              <Link to="/kontakt">{tr("Kontakta oss")}</Link>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
