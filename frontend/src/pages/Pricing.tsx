import { t as tr } from "../i18n";
import { Link } from "react-router-dom";
import PublicFrame from "../components/PublicFrame";

/* Priser: ingenting att köpa.
 *
 * Alla konton delar en gemensam budget på 10 000 kr för det som faktiskt kostar pengar - anropen till
 * AI-modellerna. Ingen köper credits och ingen läsning dras från ett eget saldo; den som loggar in ser under
 * Credits hur mycket som är kvar, vad som använts, till vad och av vem. */

export default function PricingPage() {
  return (
    <PublicFrame kicker={tr("Priser")} title={<>{tr("Ingenting att köpa.")}<br />{tr("En gemensam budget för alla.")}</>}
      lede={tr("Alla konton delar en budget på 10 000 kr för AI-anropen. Ingen köper credits, och ingen läsning dras från ett eget saldo.")}
      aside={
        <div className="pub-keys">
          <div className="pub-key"><div className="n">10 000 kr</div><div className="l">{tr("gemensam AI-budget")}</div></div>
          <div className="pub-key"><div className="n">0 kr</div><div className="l">{tr("för att läsa en ritning")}</div></div>
        </div>
      }>
      <section className="pub-sec">
        <div className="lp-kicker">{tr("Så fungerar det")}</div>
        <h2>{tr("Det som kostar pengar dras från budgeten – allt annat ingår")}</h2>
        <div className="pub-grid pub-three">
          <div className="pub-card flat"><h3>{tr("Ingår")}</h3><p>{tr("Analys av ritningar, projektanalysen, kalkylen och anbudet, mängdningsverktyget, CAD-rummet, materialet, exporter och akademin.")}</p></div>
          <div className="pub-card flat"><h3>{tr("Ur budgeten")}</h3><p>{tr("Anropen till AI-modellerna: agenten, andra blicken och läsningen av tekniska beskrivningar.")}</p></div>
          <div className="pub-card flat"><h3>{tr("Synligt för alla")}</h3><p>{tr("Under Credits ser alla som loggar in vad som är kvar, vad som använts, till vad och av vem.")}</p></div>
        </div>
        <p className="pub-cta">
          <Link className="lp-btn primary lg" to="/login">{tr("Logga in")}</Link>
          <Link className="lp-btn ghost lg" to="/kontakt">{tr("Prata med oss")}</Link>
        </p>
      </section>
    </PublicFrame>
  );
}
