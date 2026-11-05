import { t as tr } from "../i18n";

/* Projektets två lägen: entreprenadformen och disciplinen.
 *
 * Båda väljs när projektet skapas och står sedan i projekthuvudet. Ett projekt som skapades innan valen fanns är
 * AB 04 och VVS - det är vad det alltid har varit - och läses precis som förut. Disciplinerna som inte är byggda
 * än syns som det de är, med "kommer", och går inte att välja: ett val som inte gör något vore ett löfte. */

export const CONTRACT_FORMS = [
  { id: "AB04", label: "AB 04 – utförandeentreprenad", lead: "Vi mäter de installationer som är ritade på bladen." },
  { id: "ABT06", label: "ABT 06 – totalentreprenad",
    lead: "Du projekterar själv. Vi räknar rum, ytor och enheter och kalkylerar med dina nyckeltal. Blad med ritade installationer mäts som vanligt." },
];

export const CONTRACT_LABEL: Record<string, string> = { AB04: "AB 04", ABT06: "ABT 06" };

export type Discipline = { id: string; name: string; status: string; kind: string; notes?: string };

// what the reader is shown when the list has not arrived: today's one discipline
export const FALLBACK_DISCIPLINES: Discipline[] = [{ id: "vvs", name: "VVS", status: "active", kind: "pipe" }];

const STATUS_NOTE: Record<string, string> = { beta: "beta", planned: "kommer", later: "senare" };

export function ContractFormChoice({ value, onChange, name = "contract" }: { value: string; onChange: (v: string) => void; name?: string }) {
  return (
    <fieldset className="choice">
      <legend>{tr("Entreprenadform")}</legend>
      {CONTRACT_FORMS.map((f) => (
        <label key={f.id} className={`choice-card${value === f.id ? " on" : ""}`}>
          <input type="radio" name={name} value={f.id} checked={value === f.id} onChange={() => onChange(f.id)} />
          <span><b>{tr(f.label)}</b><span className="muted small">{tr(f.lead)}</span></span>
        </label>
      ))}
    </fieldset>
  );
}

/* ABT 06 med teknisk beskrivning: projektet läser en beskrivning utan ritningar och tar ut allt material den
 * föreskriver. Valet finns bara för ABT 06 - där entreprenören själv projekterar ur beskrivningen. */
export function TechSpecChoice({ value, onChange, name = "tech-spec" }: { value: boolean; onChange: (v: boolean) => void; name?: string }) {
  return (
    <label className={`choice-card${value ? " on" : ""}`} style={{ marginBottom: 14 }}>
      <input type="checkbox" name={name} checked={value} onChange={(e) => onChange(e.target.checked)} />
      <span><b>{tr("Teknisk beskrivning")}</b>
        <span className="muted small">{tr("Analysera en teknisk beskrivning utan ritningar: allt material med kod, antal, fabrikat, typ och RSK, sökt i Dahls katalog.")}</span></span>
    </label>
  );
}

export function DisciplineChoice({ value, onChange, disciplines, name = "discipline" }:
  { value: string; onChange: (v: string) => void; disciplines: Discipline[]; name?: string }) {
  return (
    <fieldset className="choice">
      <legend>{tr("Disciplin")}</legend>
      <div className="chips">
      {disciplines.map((d) => {
        const off = d.status !== "active";
        return (
          <label key={d.id} className={`choice-chip${value === d.id ? " on" : ""}${off ? " off" : ""}`}
            title={off ? tr("Den här disciplinen är inte byggd än.") : ""}>
            <input type="radio" name={name} value={d.id} checked={value === d.id} disabled={off} onChange={() => onChange(d.id)} />
            {tr(d.name)}{off && <span className="muted small"> · {tr(STATUS_NOTE[d.status] ?? d.status)}</span>}
          </label>
        );
      })}
      </div>
      {/* "Alla" läser något annat än de andra: varje beteckning på bladet. Det sägs där valet görs. */}
      {(() => {
        const d = disciplines.find((x) => x.id === value);
        return d?.kind === "all" && d.notes ? <p className="muted small">{tr(d.notes)}</p> : null;
      })()}
    </fieldset>
  );
}

export function ProjectBadges({ project, disciplines }: { project: any; disciplines: Discipline[] }) {
  const d = disciplines.find((x) => x.id === project.discipline);
  return (
    <span className="row" style={{ gap: 6 }}>
      <span className="badge" title={tr("Entreprenadform")}>{CONTRACT_LABEL[project.contract_form] ?? project.contract_form}</span>
      <span className="badge" title={tr("Disciplin")}>{tr(d?.name ?? project.discipline)}</span>
      {project.tech_spec && <span className="badge">{tr("Teknisk beskrivning")}</span>}
    </span>
  );
}
