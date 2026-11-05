import { Link, useParams } from "react-router-dom";
import { t as tr } from "../i18n";
import PublicFrame from "../components/PublicFrame";
import FeatureArt from "../components/FeatureArt";
import FeatureFilm from "../components/FeatureFilm";
import { FEATURES, featureBySlug, type Feature } from "../features";
import { useInView } from "../components/lp-motion";
import { useParallax, useSmoothScroll } from "../components/lp-smooth";
import RevealLines from "../components/Reveal";

/* En sida per funktion.
 *
 * Startsidan säger vad plattformen består av; den här sidan visar en sak i taget och visar den ordentligt.
 * Ordningen är den man faktiskt vill ha den i: vad det är, hur det ser ut, vad det har gett, hur det fungerar,
 * en film som spelar guiden, guiden i skrift, och vägen in.
 *
 * Figuren är alltid det systemet faktiskt gör - inget fotografi, ingen illustration av något annat. Ett
 * skärmavbild åldras dagen efter; en figur som ritar läsningen gör det inte.
 */

function Reveal({ children, delay = 0 }: { children: any; delay?: number }) {
  const { ref, seen } = useInView<HTMLDivElement>();
  return (
    <div ref={ref} className={`ft-rise${seen ? " in" : ""}`} style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}

function Slab({ s, accent, flip }: { s: Feature["slabs"][number]; accent: string; flip: boolean }) {
  return (
    <section className={`ft-slab${flip ? " flip" : ""}`}>
      <Reveal>
        <figure className="ft-art">
          <span data-par={flip ? -26 : 26} style={{ display: "block" }}>
            <FeatureArt id={s.art} accent={accent} />
          </span>
        </figure>
      </Reveal>
      <Reveal delay={90}>
        <div className="ft-said">
          <p className="lp-kicker" style={{ color: accent }}>{s.kicker}</p>
          <RevealLines text={s.h} />
          <p className="ft-p">{s.p}</p>
          {!!s.bullets?.length && (
            <ul className="ft-list">
              {s.bullets.map((b) => <li key={b}><span style={{ background: accent }} />{b}</li>)}
            </ul>
          )}
        </div>
      </Reveal>
    </section>
  );
}

export default function FeaturePage() {
  const { slug } = useParams();
  const f = featureBySlug(slug);
  useSmoothScroll();
  useParallax();
  if (!f) return <Missing />;
  const others = FEATURES.filter((o) => o.slug !== f.slug);
  const i = FEATURES.findIndex((o) => o.slug === f.slug);
  const next = FEATURES[(i + 1) % FEATURES.length];
  return (
    <PublicFrame bare wide>
      <article className="ft" style={{ ["--ac" as any]: f.accent }}>
        <header className="ft-head">
          <div className="ft-head-l">
            <p className="lp-eyebrow"><span className="dot" style={{ background: f.accent }} />{f.kicker}</p>
            <RevealLines as="h1" text={f.title.replace("\n", " ")} />
          </div>
          <div className="ft-head-r">
            <p className="ft-lede">{f.lede}</p>
            <div className="ft-cta">
              <Link className="lp-btn primary lg" to={f.to}>{f.toLabel} <span aria-hidden="true">→</span></Link>
              <a className="lp-btn ghost lg" href="#film">{tr("Se filmen")}</a>
            </div>
          </div>
        </header>

        <Reveal>
          <figure className="ft-hero-art">
            <FeatureArt id={f.art} accent={f.accent} />
            <figcaption>{f.card}</figcaption>
          </figure>
        </Reveal>

        <section className="ft-keys">
          {f.keys.map((k, n) => (
            <Reveal key={k.l} delay={n * 80}>
              <div className="ft-key">
                <div className="n" style={{ color: f.accent }}>{k.n}</div>
                <div className="l">{k.l}</div>
              </div>
            </Reveal>
          ))}
        </section>

        {f.slabs.map((s, n) => <Slab key={s.h} s={s} accent={f.accent} flip={n % 2 === 1} />)}

        <section className="ft-steps" id="film">
          <Reveal>
            <div className="ft-steps-head">
              <p className="lp-kicker" style={{ color: f.accent }}>Guide</p>
              <RevealLines text={f.steps.title} />
              <p className="ft-p">{f.steps.lede}</p>
            </div>
          </Reveal>
          <Reveal delay={80}>
            <FeatureFilm steps={f.steps.items} accent={f.accent} title={f.steps.title} />
          </Reveal>
          <ol className="ft-steps-list">
            {f.steps.items.map((it, n) => (
              <Reveal key={it.n} delay={n * 50}>
                <li>
                  <span className="no" style={{ color: f.accent }}>{it.n}</span>
                  <h3>{it.h}</h3>
                  <p>{it.p}</p>
                </li>
              </Reveal>
            ))}
          </ol>
        </section>

        <section className="ft-close">
          <Reveal>
            <RevealLines text={f.toLabel} />
            <p className="ft-p">{tr("Det kostar ingenting att läsa en ritning – AI-delarna tas ur en gemensam budget som alla ser.")}</p>
            <div className="ft-cta">
              <Link className="lp-btn primary lg" to={f.to}>{f.toLabel} <span aria-hidden="true">→</span></Link>
              <Link className="lp-btn ghost lg" to="/priser">{tr("Se vad det kostar")}</Link>
            </div>
          </Reveal>
        </section>

        <section className="ft-more">
          <div className="ft-more-head">
            <p className="lp-kicker">{tr("Resten av plattformen")}</p>
            <Link className="ft-next" to={`/funktioner/${next.slug}`}>
              <span className="lp-mono">{tr("Nästa funktion")}</span><b>{next.nav} <span aria-hidden="true">→</span></b>
            </Link>
          </div>
          <div className="ft-more-grid">
            {others.map((o) => (
              <Link key={o.slug} className="ft-more-card" to={`/funktioner/${o.slug}`}>
                <span className="fm-art" style={{ ["--ac" as any]: o.accent }}>
                  <FeatureArt id={o.art} accent={o.accent} />
                </span>
                <span className="fm-txt">
                  <b>{o.nav}</b>
                  <i>{o.card}</i>
                </span>
              </Link>
            ))}
          </div>
        </section>
      </article>
    </PublicFrame>
  );
}

function Missing() {
  return (
    <PublicFrame kicker="Funktioner" title={tr("Den funktionen finns inte")}
      lede="Adressen pekar på något plattformen inte har.">
      <section className="pub-sec tight">
        <p className="pub-cta"><Link className="lp-btn primary lg" to="/">{tr("Till startsidan")}</Link></p>
      </section>
    </PublicFrame>
  );
}
