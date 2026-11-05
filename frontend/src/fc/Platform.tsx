import { Link } from "react-router-dom";

import { t as tr } from "../i18n";
import { FEATURES } from "../features";
import Nav from "./Nav";
import { AppLink, CustomCursor, LineReveal, MagneticButton, ScrollProgress, TechnicalLabel } from "./primitives";
import { useSmoothScroll } from "./motion";
import "./fc.css";
import "./home.css";
import "./platform.css";

/* Plattformen och VPR: de två sidor navigeringen lovade men aldrig hade.
 *
 * "Plattformen" och "VPR" stod i toppraden och i fullskärmsmenyn, men ingen av dem hade en rutt. Den som
 * klickade föll igenom till startsidan igen - sidan bytte adress men inte innehåll, och det gick inte att
 * förstå varför. De sju funktionssidorna fanns hela tiden under /funktioner/<namn>; det som saknades var
 * rummet som samlar dem.
 *
 * Plattformen är det rummet: en innehållsförteckning över vad systemet består av, i samma mörka publika
 * språk som startsidan, där varje rad leder till sin egen sida. VPR är läsningen - den del allt annat vilar
 * på - och får en sida som säger vad den gör och vad den vägrar att gissa.
 */

const STEG = [
  { n: "01", t: "Bläcket", d: "Bladets vektorer läses som de är ritade: varje streck, dess penna, dess lager, dess färg. Ingen bild, ingen tolkning av pixlar." },
  { n: "02", t: "Pennan", d: "Vilken penna som ritar rör avgörs av bladets egna etiketter - hur många av dem som pekar på den, och vad lagrets namn säger om systemet." },
  { n: "03", t: "Beteckningen", d: "Namnet läses ur bladet, inte ur en lista någon annan skrivit. Är typsnittet bäddat utan teckentabell byggs tabellen baklänges ur typsnittet självt." },
  { n: "04", t: "Hänvisningen", d: "En beteckning äger ett rör först när en hänvisningslinje faktiskt når fram till det. Aldrig närmaste rör - det är så en mängd blir fel utan att någon märker det." },
  { n: "05", t: "Metern", d: "Sträckan mäts i bladets egen skala, läst ur skalstocken när den finns. Varje meter går att spåra tillbaka till de streck den kom ur." },
];

const VAGRAR = [
  "Gissa vilket rör en beteckning menar när bladet inte säger det. Svaret blir tvetydigt, och det står det.",
  "Läsa en mängd ur ett facit, en filnamnsregel eller ett tidigare projekt. Bladet är enda källan.",
  "Mäta utan skala. Utan skalstock eller skaltext står metrarna kvar som punkter tills någon säger skalan.",
  "Tysta bort det som inte gick att läsa. Det som föll bort redovisas med skäl, blad för blad.",
];

function Chrome({ children }: { children: React.ReactNode }) {
  useSmoothScroll();
  return (
    <div className="lp fcpub fc-plat">
      <CustomCursor />
      <ScrollProgress />
      <Nav />
      {children}
      <footer className="fc-foot">
        <div className="fc-foot-links fc-plat-foot">
          <Link className="fc-link" to="/">Dahl</Link>
          <Link className="fc-link" to="/plattformen">Plattformen</Link>
          <Link className="fc-link" to="/vpr">VPR</Link>
          <Link className="fc-link" to="/utbildning">Academy</Link>
          <Link className="fc-link" to="/priser">Priser</Link>
          <Link className="fc-link" to="/kontakt">Kontakt</Link>
        </div>
      </footer>
    </div>
  );
}

export function PlatformPage() {
  return (
    <Chrome>
      <header className="fc-plat-head">
        <p className="fc-label">Plattformen</p>
        <LineReveal as="h1" className="fc-display fc-display-lg"
          text={"Sju delar som\nläser samma blad"} />
        <p className="fc-body fc-plat-lede">
          Läsningen ger mängden, mängden ger kalkylen, kalkylen ger anbudet. Varje del står på samma geometri —
          bladets egna streck — så att ett tal längst ut i kedjan går att följa hela vägen tillbaka till bläcket
          det kom ur.
        </p>
        <div className="fc-plat-cta">
          <MagneticButton className="solid" href="/login">{tr("Enter Dahl")} <span aria-hidden="true">↗</span></MagneticButton>
          <Link className="fc-link" to="/hur-det-funkar">{tr("Hur det funkar")} <span aria-hidden="true">→</span></Link>
        </div>
      </header>

      <section className="fc-plat-index" aria-label="Delarna">
        <ol>
          {FEATURES.map((f, i) => (
            <li key={f.slug}>
              <Link to={`/funktioner/${f.slug}`} data-cursor="cta">
                <span className="fc-label fc-plat-n">{String(i + 1).padStart(2, "0")}</span>
                <span className="fc-plat-t">{f.nav}</span>
                <span className="fc-body fc-plat-d">{f.card}</span>
                <span className="fc-plat-arrow" aria-hidden="true">→</span>
              </Link>
            </li>
          ))}
        </ol>
      </section>

      <section className="fc-plat-open" aria-label={tr("Vägen in")}>
        <div>
          <p className="fc-label">{tr("Vägen in")}</p>
          <h2 className="fc-display fc-display-md">{tr("Börja med ett blad du redan mängdat")}</h2>
          <p className="fc-body">
            Då ser du skillnaden mot din egen siffra direkt, rad för rad, med bladets streck bakom varje meter.
          </p>
        </div>
        <div className="fc-plat-open-links">
          <AppLink className="fc-link" to="/mangda">{tr("Mängda ett blad")} <span aria-hidden="true">→</span></AppLink>
          <AppLink className="fc-link" to="/cad">{tr("Rita i CAD")} <span aria-hidden="true">→</span></AppLink>
          <AppLink className="fc-link" to="/projekt">{tr("Dina projekt")} <span aria-hidden="true">→</span></AppLink>
          <Link className="fc-link" to="/utbildning">{tr("Lär dig mängda")} <span aria-hidden="true">→</span></Link>
        </div>
      </section>
    </Chrome>
  );
}

export function VprPage() {
  return (
    <Chrome>
      <header className="fc-plat-head">
        <p className="fc-label">{tr("VPR — Vector Pipe Reading")}</p>
        <LineReveal as="h1" className="fc-display fc-display-lg"
          text={"Varje meter\nspårbar till bläcket"} />
        <p className="fc-body fc-plat-lede">
          VPR är läsningen som allt annat vilar på. Den läser ritningens vektorer — inte en bild av dem — och
          binder varje mätt meter till de streck den kom ur, till beteckningen som namngav den och till
          hänvisningslinjen som pekade dit.
        </p>
        <div className="fc-plat-meta">
          <TechnicalLabel k="Läser" v="Vektor-PDF" />
          <TechnicalLabel k="Källa" v="Bladet, inget annat" />
          <TechnicalLabel k="Svar" v="Meter eller skäl" on />
        </div>
      </header>

      <section className="fc-plat-steps" aria-label="Kedjan">
        <p className="fc-label">{tr("Från streck till meter")}</p>
        <ol>
          {STEG.map((s) => (
            <li key={s.n}>
              <span className="fc-label">{s.n}</span>
              <h3 className="fc-display fc-plat-step-t">{s.t}</h3>
              <p className="fc-body">{s.d}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="fc-plat-refuse" aria-label={tr("Det läsningen vägrar")}>
        <div>
          <p className="fc-label">{tr("Vad den vägrar")}</p>
          <h2 className="fc-display fc-display-md">{tr("Ett tvetydigt svar är ett svar. Ett gissat är det inte.")}</h2>
        </div>
        <ul>
          {VAGRAR.map((v) => <li key={v} className="fc-body">{v}</li>)}
        </ul>
      </section>

      <section className="fc-plat-open" aria-label={tr("Vägen in")}>
        <div>
          <p className="fc-label">{tr("Pröva den")}</p>
          <h2 className="fc-display fc-display-md">{tr("Ta ett blad du redan mängdat")}</h2>
          <p className="fc-body">{tr("Läsningen säger vad den fann, vad den inte kunde avgöra, och varför.")}</p>
        </div>
        <div className="fc-plat-open-links">
          <AppLink className="fc-link" to="/mangda">{tr("Läs ett blad")} <span aria-hidden="true">→</span></AppLink>
          <Link className="fc-link" to="/funktioner/mangdning">{tr("Hur läsningen fungerar")} <span aria-hidden="true">→</span></Link>
          <Link className="fc-link" to="/plattformen">{tr("Hela plattformen")} <span aria-hidden="true">→</span></Link>
        </div>
      </section>
    </Chrome>
  );
}
