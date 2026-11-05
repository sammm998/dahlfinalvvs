import { useEffect, useRef, useState } from "react";
import { t as tr } from "../i18n";
import { Link, useLocation } from "react-router-dom";
import "../landing.css";
import "../fc/fc.css";
import "../fc/public.css";
import SiteHeader, { PUBLIC_LINKS } from "./SiteHeader";
import Nav from "../fc/Nav";
import { CustomCursor, LineReveal, ScrollProgress } from "../fc/primitives";
import { useSmoothScroll } from "../fc/motion";
import { DahlLogo } from "./DahlLogo";

/* Ramen kring de publika sidorna.
 *
 * Priser, om oss, hur det funkar, utbildning och kontakt ska vara rum i samma hus som startsidan, inte fem
 * hemsidor. Ramen bär därför samma sak som startsidan gör: Dahls typsnitt och färger, samma rad högst
 * upp med sin fullskärmsmeny, samma mjuka rullning, samma muspekare, och en hjälte med kapitelskyltens rytm -
 * etikett, stor rubrik som kommer fram rad för rad, ingress bredvid i stället för under.
 *
 * Att ramen bär det och inte varje sida är hela poängen: en ny sida får rummet gratis, och en ändring i huset
 * når alla rum på en gång.
 *
 * Den gamla raden (SiteHeader) ligger kvar för de vyer som ber om den med `legacyHeader` - akademins gamla
 * lärandevy använder dess ankarmeny - men ingen publik sida gör det längre.
 */

export { PUBLIC_LINKS };

export default function PublicFrame({ kicker, title, lede, children, wide = false, aside, anchors, bare,
  legacyHeader = false }: {
  kicker?: string; title?: any; lede?: any; children: any; wide?: boolean;
  /** den gamla raden med sin ankarmeny, för vyer som behöver den */
  legacyHeader?: boolean;
  /** sidan har ett eget huvud och vill inte ha ramens hjälte ovanför det */
  bare?: boolean;
  /** det som står bredvid rubriken: en siffra, en figur, ett par nycklar */
  aside?: any;
  /** avsnitt på sidan, till menyns andra spalt */
  anchors?: { href: string; label: string }[];
}) {
  const { pathname } = useLocation();
  useSmoothScroll();
  // Mörkt som grund, ljust som andning: vart tredje avsnitt, med början på det andra, står på papper. Det sätts
  // här och inte i varje sida, så att en ny sida får samma rytm utan att någon räknar avsnitt för hand.
  const body = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = body.current; if (!el) return;
    const mark = () => el.querySelectorAll(".pub-body > .pub-sec, .pub-body > section").forEach((sec, i) => {
      sec.classList.toggle("fc-light", i % 3 === 1); sec.classList.toggle("pub-lit", i % 3 === 1); sec.classList.toggle("fc-bleed", i % 3 === 1);
    });
    mark();
    const mo = new MutationObserver(mark); mo.observe(el, { childList: true, subtree: false });
    return () => mo.disconnect();
  }, [pathname]);
  useEffect(() => {
    document.body.classList.add("lp-dark");
    window.scrollTo(0, 0);
    return () => document.body.classList.remove("lp-dark");
  }, [pathname]);
  return (
    <div className="lp pub fcpub">
      {legacyHeader ? <SiteHeader anchors={anchors} /> : <Nav />}
      <CustomCursor />
      <ScrollProgress />

      {bare ? <div className="pub-bare" /> : (
        <header className="pub-hero">
          <div className="fc-grid" aria-hidden="true" />
          <div className="pub-hero-in">
            <div>
              {kicker && <p className="fc-label">{kicker}</p>}
              {typeof title === "string"
                ? <LineReveal as="h1" className="pub-h1 fc-display fc-display-lg" text={title} />
                : <h1 className="pub-h1 fc-display fc-display-lg">{title}</h1>}
            </div>
            <div className="pub-hero-r">
              {lede && <p className="pub-lede fc-lead">{lede}</p>}
              {aside && <div className="pub-hero-aside">{aside}</div>}
            </div>
          </div>
        </header>
      )}

      {/* sidan står i mörker; vart tredje avsnitt läggs på papper (se effekten ovan) */}
      <div className="pub-light" ref={body}>
        <main className={`pub-body${wide ? " wide" : ""}`}>{children}</main>
      </div>

      <footer className="pub-foot">
        <div className="pub-foot-in">
          <div className="pub-foot-brand">
            <span className="lp-logo" style={{ fontSize: 15 }}>
              <DahlLogo height={22} title="Dahl" />
            </span>
            <p>{tr("Mängden som ritningen redan säger. Varje meter med sitt belägg kvar.")}</p>
          </div>
          <nav aria-label="Sidor">
            <p className="lp-mono">Sidor</p>
            {PUBLIC_LINKS.map((l) => <Link key={l.to} to={l.to}>{l.label}</Link>)}
          </nav>
          <nav aria-label={tr("Kom igång")}>
            <p className="lp-mono">{tr("Kom igång")}</p>
            <Link to="/login">{tr("Logga in")}</Link>
            <Link to="/utbildning">VVS-akademin</Link>
            <Link to="/kontakt">{tr("Kontakta oss")}</Link>
          </nav>
        </div>
        <div className="fc-foot-mark" aria-hidden="true"><DahlLogo height="1em" className="fc-foot-logo" /></div>
      </footer>
    </div>
  );
}

/** En sektion med samma rytm som startsidans: etikett, rubrik, innehåll. */
export function PubSection({ id, kicker, title, lede, children, tight }: {
  id?: string; kicker?: string; title?: any; lede?: any; children?: any; tight?: boolean;
}) {
  return (
    <section id={id} className={`pub-sec${tight ? " tight" : ""}`}>
      {(kicker || title) && (
        <div className="pub-sec-head">
          {kicker && <div className="lp-kicker">{kicker}</div>}
          {title && <h2>{title}</h2>}
          {lede && <p className="pub-sec-lede">{lede}</p>}
        </div>
      )}
      {children}
    </section>
  );
}

/** En text som en administratör kan ha skrivit om i innehållsverktyget; annars den inbyggda. */
export function usePublished(slug: string): { title: string; body: string } | null {
  const [c, setC] = useState<{ title: string; body: string } | null>(null);
  useEffect(() => {
    fetch(`/api/content/${slug}`).then((r) => (r.ok ? r.json() : null)).then((j) => j && setC(j)).catch(() => { /* inbyggd text */ });
  }, [slug]);
  return c;
}

/* Löpande text som en uppslagen sida i stället för en spalt.
 *
 * En rubrik och styckena under den hör ihop, så de sätts ihop till ett avsnitt: rubriken står kvar i vänstra
 * spalten medan texten löper i den högra. Det som står före den första rubriken är ingressen och får hela
 * bredden. Grupperingen sker här och inte i varje sida, så en text som en administratör skriver i
 * innehållsverktyget får samma form som den inbyggda. */
export function Prose({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);
  const lead: string[] = [];
  const secs: { h: string; ps: string[] }[] = [];
  for (const b of blocks) {
    if (b.startsWith("## ")) secs.push({ h: b.slice(3), ps: [] });
    else if (secs.length) secs[secs.length - 1].ps.push(b);
    else lead.push(b);
  }
  return (
    <>
      {!!lead.length && (
        <div className="prose-lead">
          <div className="say"><p>{lead[0]}</p></div>
          <div className="rest">{lead.slice(1).map((t, i) => <p key={i}>{t}</p>)}</div>
        </div>
      )}
      {secs.map((s, i) => (
        <section className="prose-sec" key={i}>
          <h2>{s.h}</h2>
          <div className="prose-col">{s.ps.map((t, k) => <p key={k}>{t}</p>)}</div>
        </section>
      ))}
    </>
  );
}
