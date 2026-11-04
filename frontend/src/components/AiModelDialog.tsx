import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { lastAiModel, registerAiModelAsker, rememberAiModel } from "../aiChoice";
import { t as tr, trf } from "../i18n";

/* Innan en analys startar: vilken modell avgör rörens beteckningar - ingen, GPT-6 Astra, GPT-6.1 Sol, Claude Opus 5.5
 * eller Gemini Pro.
 * Samma ritning kan läsas en gång med varje, och raden "Läst med …" på analysen visar tokens och pris. En modell
 * servern saknar nyckel till går inte att välja, och det står varför. */

type Choice = { id: string; label: string; available: boolean; blocked?: string | null };

const NOTES: Record<string, string> = {
  "none": "Ritningens egna belägg avgör. Ingen AI-kostnad.",
  "gpt-6-astra": "OpenAI avgör de rör där beläggen ger flera möjliga beteckningar.",
  "gpt-6.1-sol": "OpenAI:s billigare modell avgör de rör där beläggen ger flera möjliga beteckningar.",
  "claude-opus-5-5": "Anthropic avgör de rör där beläggen ger flera möjliga beteckningar.",
  "gemini-pro": "Googles senaste Pro-modell avgör de rör där beläggen ger flera möjliga beteckningar.",
};

export default function AiModelDialog() {
  const [open, setOpen] = useState<{ count: number } | null>(null);
  const [choices, setChoices] = useState<Choice[]>([]);
  const [value, setValue] = useState<string>("gpt-6-astra");
  const [exhausted, setExhausted] = useState(false);
  const answer = useRef<((v: string | null) => void) | null>(null);

  useEffect(() => {
    registerAiModelAsker((count) => new Promise((resolve) => {
      answer.current = resolve;
      setOpen({ count });
      api.analysisOptions().then((o: any) => {
        const list: Choice[] = o.ai_models ?? [];
        setChoices(list);
        setExhausted(!!o.ai_budget_exhausted);
        // Förvalt: det man själv valde senast, annars serverns standard (GPT-6 Astra när nyckeln finns).
        const last = lastAiModel();
        const usable = (id: string | null | undefined) => !!id && list.some(c => c.id === id && c.available);
        setValue(usable(last) ? last! : usable(o.ai_default) ? o.ai_default
          : usable("gpt-6-astra") ? "gpt-6-astra" : "none");
      }).catch(() => { setChoices([{ id: "none", label: "Utan AI", available: true }]); setValue("none"); });
    }));
    return () => registerAiModelAsker(null);
  }, []);

  const close = (v: string | null) => {
    if (v) rememberAiModel(v);
    answer.current?.(v); answer.current = null; setOpen(null);
  };

  if (!open) return null;
  return (
    <div className="aidlg-back" onClick={() => close(null)}>
      <div className="aidlg card" role="dialog" aria-modal="true" aria-label={tr("Välj AI-modell")}
        onClick={(e) => e.stopPropagation()} onKeyDown={(e) => { if (e.key === "Escape") close(null); }}>
        <h3 style={{ marginTop: 0 }}>{tr("Välj AI-modell för analysen")}</h3>
        <p className="muted small">{open.count > 1 ? trf("Gäller alla {0} ritningar som startas nu.", open.count)
          : tr("Läs samma ritning med flera modeller för att jämföra mängder, tokens och pris.")}</p>
        {exhausted && <p className="aidlg-off" role="status"><b>{tr("Alla krediter för AI är förbrukade.")}</b>{" "}
          {tr("Analysen går lika bra utan AI - ritningens egna belägg avgör.")}</p>}
        <div className="aidlg-list" role="radiogroup">
          {(choices.length ? choices : [{ id: "none", label: "Utan AI", available: true }]).map(c => (
            <label key={c.id} className={`aidlg-opt${value === c.id ? " on" : ""}${c.available ? "" : " off"}`}>
              <input type="radio" name="aimodel" value={c.id} checked={value === c.id} disabled={!c.available}
                onChange={() => setValue(c.id)} />
              <span><b>{tr(c.label)}</b>{c.id === "gpt-6-astra" ? <span className="muted small"> · {tr("förvald")}</span> : null}<br />
                <span className="muted small">{c.available ? tr(NOTES[c.id] ?? "")
                  : c.blocked ? tr(c.blocked)
                  : tr("Inte ansluten på servern - nyckeln saknas i Railway.")}</span></span>
            </label>
          ))}
        </div>
        <div className="row" style={{ justifyContent: "flex-end", marginTop: 16 }}>
          <button className="secondary" onClick={() => close(null)}>{tr("Avbryt")}</button>
          <button autoFocus onClick={() => close(value)}>{tr("Starta analysen")}</button>
        </div>
      </div>
    </div>
  );
}
