import { t as tr, locale } from "../i18n";

/* Vilken modell som läste den här analysen och vad den kostade - samma rad för alla tre val, så att två läsningar
 * av samma ritning kan jämföras: mängden i tabellen, tokens och pris här. */
export function AiUsage({ usage }: { usage?: any }) {
  if (!usage) return null;
  const NUM = new Intl.NumberFormat(locale());
  const none = usage.model === "none";
  return (
    <p className="sub aiusage">
      {tr("Läst med")} <b>{tr(usage.label ?? usage.model)}</b>
      {!none && <> · {NUM.format(usage.requests)} {tr("anrop")} · {NUM.format(usage.tokens_in)} {tr("tokens in")}
        {usage.cached_tokens ? <> ({NUM.format(usage.cached_tokens)} {tr("från cache")})</> : null}
        {" · "}{NUM.format(usage.tokens_out)} {tr("tokens ut")}
        {" · "}{usage.kr ? `${NUM.format(usage.kr)} kr` : usage.usd == null ? tr("pris okänt") : `$${usage.usd.toFixed(2)}`}</>}
      {none && <> · {tr("ingen AI-kostnad")}</>}
      {!none && usage.missed_checked > 0 && <> · {tr("kontroll av missade")}: {NUM.format(usage.missed_named)} {tr("rör namngivna, att granska")}</>}
      {!none && usage.swept_tiles > 0 && <> · {tr("svep")}: {NUM.format(usage.swept_tiles)} {tr("rutor")}, {NUM.format(usage.sweep_requests ?? 0)} {tr("anrop")}</>}
      {!none && usage.missed_not_asked > 0 && <> · {NUM.format(usage.missed_not_asked)} {tr("frågor ej ställda (taket)")}</>}
      {usage.fell_back_to_rules && <> · {tr("modellen svarade inte, reglerna läste bladet")}</>}
    </p>
  );
}
