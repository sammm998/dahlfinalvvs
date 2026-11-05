import { Link } from "react-router-dom";
import { t as tr } from "../i18n";
import PublicFrame from "../components/PublicFrame";
import Demos from "../fc/Demos";
import "../fc/home.css";
import EvidenceSection from "../components/EvidenceSection";

/* Hur det funkar: läsningens kedja, steg för steg, i den ordning motorn faktiskt går - och var den stannar.
 * Ingenting här är marknadsföring av något som inte finns: varje steg motsvarar ett steg i motorn, och
 * skälkoderna är de som skrivs i pipe_extent_frontiers.json. */

const STEPS: { n: string; h: string; p: string; tag?: string }[] = [
  { n: "01", h: "Ritningen öppnas som vektorer", p: "Varje streck läses med sin penna, färg, sitt lager och sin streckning. En skannad PDF avvisas: där finns bara bildpunkter, och på bildpunkter gissar man.", tag: "RAW VECTOR PDF" },
  { n: "02", h: "Bladet får en profil", p: "Vilka pennor som finns, vilka textstorlekar, vilka streckmönster, hur ledare ritas, hur rör ritas. Allt härleds ur bladet självt - inga fasta tröskelvärden för en viss ritstil.", tag: "DRAWING PROFILE" },
  { n: "03", h: "Texten byggs tillbaka", p: "Där texten är riktig text läses den. Där CAD-programmet ritat bokstäverna som streck byggs de tillbaka: streck blir tecken, tecken blir rader, rader blir beteckningar.", tag: "TEXT / GLYPHS" },
  { n: "04", h: "Förklaringslistan läses", p: "Systemkoder, material, komponenter, linjetyper. Den används där den finns, och läsningen fungerar även när den saknas, är ofullständig eller ligger på ett annat blad.", tag: "LEGEND" },
  { n: "05", h: "Beteckning och DN", p: "Bladets egen grammatik för beteckningar upptäcks: var dimensionen står, hur den skrivs, vad som är en rörbeteckning och vad som är något annat. DN är en del av identiteten.", tag: "DESIGNATION · DN" },
  { n: "06", h: "Den riktiga ledaren", p: "Identitet sätts aldrig genom närhet. För varje beteckning söks den ledarlinje CAD-ritaren faktiskt drog - rak, bruten, i flera delar - och den följs till sin spets.", tag: "ACTUAL LEADER" },
  { n: "07", h: "Röret ledaren pekar på", p: "Vid spetsen avgörs vad som träffas: ett rör, en markör, en armatur, eller ingenting. En kontakt är inte en anslutning förrän den är verifierad.", tag: "ATTACHMENT" },
  { n: "08", h: "Hela röret följs", p: "Från fästpunkten följs röret genom böjar, avgreningar, exportglapp och streckade mönster - bara över verifierade fysiska kopplingar. En korsning är inte en koppling.", tag: "TOPOLOGY · CONTINUITY" },
  { n: "09", h: "Varje stopp får ett skäl", p: "Där röret slutar skrivs varför: en riktig DN-gräns, ingen fysisk fortsättning, en tvetydig avgrening, en korsning, ett glapp som inte gick att sluta. Inget rör slutar tyst.", tag: "FRONTIERS" },
  { n: "10", h: "Ett rör mäts en gång", p: "Två parallella linjer som ritar ett rör blir ett rör. Dubbelritad geometri mäts inte två gånger. Skalan tas ur bladet - stämpel, skalstock eller måttsättning - aldrig ur ett antagande.", tag: "CANONICAL · SCALE" },
  { n: "11", h: "Mängden, med belägg", p: "Beteckning, DN, antal, horisontellt, vertikalt, totalt, status. Vertikalt utan höjdbesked står som okänt, inte som noll. Varje rad kan öppnas: vad lästes, var, och varför.", tag: "QUANTITY · EVIDENCE" },
  { n: "12", h: "Du granskar och rättar", p: "Det tvetydiga står för sig. Du bekräftar, rättar eller lämnar. Rättelser sparas som sådana - de flyttar aldrig en meter i tysthet.", tag: "REVIEW · EXPORT" },
];

const REASONS = [
  ["REAL_DN_BOUNDARY", "dimensionen byter"], ["REAL_SYSTEM_BOUNDARY", "systemet byter"], ["NO_PHYSICAL_CONTINUATION", "röret tar slut"],
  ["EXPORT_GAP_UNRESOLVED", "ett glapp som inte gick att sluta"], ["DASH_GAP_UNRESOLVED", "ett streckmönster som inte gick att följa"],
  ["FITTING_UNRESOLVED", "en armatur mellan två delar"], ["CURVE_BREAK", "en båge som inte hängde ihop"], ["REPRESENTATION_TRANSITION", "ritsättet byter"],
  ["AMBIGUOUS_T", "en T-koppling utan bevis"], ["AMBIGUOUS_BRANCH", "en avgrening utan egen identitet"], ["CROSSING", "två linjer som bara korsar varandra"],
  ["CONFLICTING_ANCHOR", "två beteckningar gör anspråk"], ["PIPE_FAMILY_BREAK", "pennan byter"], ["LOW_PIPE_CONFIDENCE", "för lite som säger rör"],
];

export default function HowItWorksPage() {
  return (
    <PublicFrame kicker="Hur det funkar" title={<>Från streck till meter,<br />med belägg för varje steg</>}
      lede="Läsningen går i tolv steg. Varje steg lämnar spår som går att öppna, och där den inte kan gå vidare säger den varför."
      anchors={[{ href: "#steg", label: "De tolv stegen" }, { href: "#skal", label: "Varför ett rör slutar" }]}
      aside={
        <div className="pub-keys">
          <div className="pub-key"><div className="n">{STEPS.length}</div><div className="l">{tr("steg i läsningen")}</div></div>
          <div className="pub-key"><div className="n">{REASONS.length}</div><div className="l">{tr("skäl ett rör kan sluta av")}</div></div>
          <div className="pub-key"><div className="n">0</div><div className="l">{tr("meter utan belägg")}</div></div>
        </div>
      } wide>
      <section className="pub-sec" id="demo">
        <div className="pub-sec-head">
          <div className="lp-kicker">{tr("Se hur det funkar")}</div>
          <h2>{tr("Fem minuter i Dahl")}</h2>
          <p className="pub-sec-lede">{tr("Inspelat i appen på en riktig ritning – inga skisser, inga redigerade siffror.")}</p>
        </div>
        <Demos compact />
      </section>
      <section className="pub-sec">
        <ol className="pub-steps">
          {STEPS.map((s) => (
            <li key={s.n} className="pub-step">
              <span className="no">{s.n}</span>
              <div>
                {s.tag && <span className="lp-mono pub-tagline">{s.tag}</span>}
                <h3>{s.h}</h3>
                <p>{s.p}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="pub-sec">
        <div className="lp-kicker">{tr("Där röret slutar")}</div>
        <h2>{tr("Inget rör slutar tyst")}</h2>
        <p className="pub-p">
          Varje gång läsningen slutar följa ett rör skriver den ned var och varför, med de vektorer den tittade på.
          Det är skillnaden mellan en mängd man kan granska och en man får tro på. Skälen är dessa:
        </p>
        <div className="pub-reasons">
          {REASONS.map(([code, text]) => <div key={code}><code>{code}</code><span>{text}</span></div>)}
        </div>
      </section>

      <div className="pub-embed"><EvidenceSection /></div>

      <section className="pub-sec">
        <div className="lp-kicker">{tr("Vad som aldrig händer")}</div>
        <div className="pub-grid pub-three">
          <div className="pub-card flat"><h3>{tr("Ingen närhetsgissning")}</h3><p>{tr("Ett rör får aldrig ett namn för att en etikett råkar ligga bredvid. Bara en riktig ledare ger identitet.")}</p></div>
          <div className="pub-card flat"><h3>{tr("Ingen gissad skala")}</h3><p>Ingen ritning antas vara 1:50. Saknas skalan står det, och du kan skriva in den - då står det också.</p></div>
          <div className="pub-card flat"><h3>{tr("Ingen modell som ritar")}</h3><p>{tr("En språkmodell får välja mellan kandidater ritningen erbjuder. Den får aldrig skapa geometri, DN eller meter.")}</p></div>
        </div>
        <p className="pub-cta">
          <Link className="lp-btn primary lg" to="/login">{tr("Ladda upp en ritning")}</Link>
          <Link className="lp-btn ghost lg" to="/dokumentation">{tr("Läs dokumentationen")}</Link>
        </p>
      </section>
    </PublicFrame>
  );
}
