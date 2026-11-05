import { Fragment, useEffect, useMemo, useState } from "react";

import { lang, num, t as tr, trf } from "../i18n";
/* Varje beteckning bladet skriver, oavsett disciplin - läget "Alla".
 *
 * VVS-läsningen svarar på en fråga: vilka rör, hur många meter. Den som valt "Alla" vill se allt bladet skriver:
 * rören, men också ventilerna, apparaterna, brandklasserna och rummen. Här står varje beteckning en gång med sin
 * mängd - meter för en ledning, styck för det som räknas, m² för ett rum med area i texten - och med var den står,
 * så att varje förekomst kan pekas ut på bladet.
 *
 * Rörens meter är VVS-läsningens, oförändrade. Det bladets egen förklaringslista inte förklarar står som
 * "granskas"; där motorns svenska referensdata känner koden visas dess ord, sagt som referensdata och aldrig som
 * bladets besked.
 */

type Place = { bbox: number[]; line: string; count: number };
type Entry = {
  name: string; kind: string; unit: string; quantity: number; labels: number; state: string; reasons: string[];
  description: string | null; described_by: string | null; discipline: string | null; places: Place[];
  description_en?: string | null;     // the reference data's own English term, where the hint comes from it
  runs?: number[][][];                // a run of another discipline: the lines the widened reading measured it on
  variants: { line: string; labels: number }[];
};
export type Register = {
  page?: number;
  entries: Entry[];
  totals: { entries: number; by_kind: Record<string, number>; metres: number; pieces: number; square_metres: number;
            to_review: number; wide_metres?: number };
  not_counted?: Record<string, number>;
  discipline?: string;     // the discipline the sheet was read as
  focus?: string | null;   // the kind of entry that discipline is about: the list opens on it
};

const KIND_SV: Record<string, string> = {
  ledning: "Ledning", komponent: "Komponent", klass: "Klass", rum: "Rum", okänd: "Okänd",
};
const KIND_CLASS: Record<string, string> = {
  ledning: "system", komponent: "component", klass: "klass", rum: "rum", okänd: "unknown",
};
const KIND_HINT: Record<string, string> = {
  ledning: "Mätt i meter av VVS-läsningen, på rören under just den beteckningen",
  komponent: "Räknad i styck: en per skriven etikett, och ett antal framför koden räknas som det antalet",
  klass: "En brandklass, eller en material- eller isolerklass ur förklaringslistan. Räknad i styck, en per gång den står",
  rum: "Den area rumsetiketten själv skriver",
  okänd: "Räknad i styck. Varken bladet eller referensdatan säger vad koden är",
};
const SAID_BY: Record<string, string> = {
  "förklaringslistan": "bladets förklaringslista", referensdata: "referensdata, inte bladet",
  rumsetiketten: "rumsetiketten",
};
// what was left out, in the singular and the plural
const NOT_COUNTED: [string, string, string][] = [
  ["legend_rows", "rad i förklaringslistan", "rader i förklaringslistan"],
  ["drawing_numbers", "ritningsnummer eller filnamn", "ritningsnummer och filnamn"],
  ["values", "mätvärde", "mätvärden"], ["placeholders", "mall som XX", "mallar som XX"],
  ["one_off_drawn_words", "enstaka läsning ur streck", "enstaka läsningar ur streck"],
  ["words", "ord läst som kod", "ord lästa som koder"],
];

// the engine says why in Swedish; the one reason with a number in it is said again with the number in its place
const reason = (r: string) => {
  const m = /^(\d+(?:\.\d+)?) m att granska$/.exec(r);
  return m ? trf("{0} m att granska", num(Number(m[1]))) : tr(r);
};
const amount = (e: Entry) => (e.unit === "st" ? String(Math.round(e.quantity)) : num(e.quantity, e.unit === "m" ? 2 : 1));
const unionOf = (places: Place[]) => places.length ? [
  Math.min(...places.map((p) => p.bbox[0])), Math.min(...places.map((p) => p.bbox[1])),
  Math.max(...places.map((p) => p.bbox[2])), Math.max(...places.map((p) => p.bbox[3])),
] : null;
// the box round a run's drawn lines
const spanOfRuns = (runs: number[][][]) => {
  const pts = runs.flat();
  return pts.length ? [Math.min(...pts.map((p) => p[0])), Math.min(...pts.map((p) => p[1])),
    Math.max(...pts.map((p) => p[0])), Math.max(...pts.map((p) => p[1]))] : null;
};

export default function AllDesignations({ register, onZoom, onShowPipe, onShowRuns, focus }: {
  register: Register;
  onZoom: (bbox: number[]) => void;
  onShowPipe?: (designation: string) => void;
  onShowRuns?: (runs: number[][][], bbox: number[]) => void;   // another discipline's run: its own lines
  focus?: { name: string; at: number } | null;                  // a frame picked on the sheet: its row, opened
}) {
  const [q, setQ] = useState("");
  // a discipline's own kind first - ducts for ventilation, symbols for electrical, rooms for building
  const [kind, setKind] = useState(register.focus || "alla");
  const [state, setState] = useState("alla");
  const [open, setOpen] = useState<string | null>(null);

  // A frame picked on the sheet opens its row here, with nothing filtered away in front of it.
  useEffect(() => {
    const e = focus ? (register.entries ?? []).find((x) => x.name === focus.name) : null;
    if (!e) return;
    const key = `${e.kind}/${e.name}`;
    setQ(""); setKind("alla"); setState("alla"); setOpen(key);
    window.setTimeout(() => document.querySelector(`[data-entry="${CSS.escape(key)}"]`)?.scrollIntoView({ block: "center" }), 50);
  }, [focus, register]);

  const shown = useMemo(() => (register.entries ?? []).filter((e) => {
    if (kind !== "alla" && e.kind !== kind) return false;
    if (state !== "alla" && e.state !== state) return false;
    const s = q.trim().toLowerCase();
    if (!s) return true;
    return `${e.name} ${e.description ?? ""} ${e.places.map((p) => p.line).join(" ")}`.toLowerCase().includes(s);
  }), [register, q, kind, state]);

  const tot = register.totals;
  const k = tot.by_kind ?? {};
  const notCounted = NOT_COUNTED.filter(([key]) => (register.not_counted?.[key] ?? 0) > 0);

  return (
    <div className="sheetview">
      <div className="card alldesignations">
        <div className="legendhead">
          <div>
            <h3>{tr("Alla beteckningar på bladet")}</h3>
            <p className="muted">
              {trf("{0} beteckningar: {1} ledningar med {2} m, {3} komponenter och klasser med {4} st, {5} rum med {6} m².",
                tot.entries, k.ledning ?? 0, num(tot.metres), (k.komponent ?? 0) + (k.klass ?? 0) + (k.okänd ?? 0),
                tot.pieces, k.rum ?? 0, num(tot.square_metres, 1))}
              {(tot.wide_metres ?? 0) > 0 && <>{" "}{trf("Av metrarna är {0} m andra ledningar, mätta i den vidgade läsningen.", num(tot.wide_metres ?? 0))}</>}
              {" "}
              {tot.to_review > 0 ? trf("{0} ska granskas.", tot.to_review) : tr("Ingen ska granskas.")}
            </p>
            <p className="muted">
              {tr("Rören är mätta precis som i VVS-läget. Allt annat räknas en gång per skriven etikett, och ett antal framför koden (4*TV103) räknas som det antalet. Det bladets förklaringslista inte förklarar står som granskas.")}
            </p>
            {notCounted.length > 0 && (
              <p className="muted">
                {tr("Räknas inte")}: {notCounted.map(([key, one, many]) => {
                  const n = register.not_counted![key];
                  return `${n} ${tr(n === 1 ? one : many)}`;
                }).join(", ")}.
              </p>
            )}
          </div>
          <div className="legendfilters">
            <input placeholder={tr("Sök kod eller ord…")} value={q} onChange={(e) => setQ(e.target.value)} />
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="alla">{tr("Alla slag")}</option>
              {Object.keys(KIND_SV).map((key) => (
                <option key={key} value={key}>{tr(KIND_SV[key])} ({k[key] ?? 0})</option>
              ))}
            </select>
            <select value={state} onChange={(e) => setState(e.target.value)}>
              <option value="alla">{tr("Alla status")}</option>
              <option value="säker">{tr("Säker")}</option>
              <option value="granskas">{tr("Granskas")}</option>
            </select>
          </div>
        </div>

        <div className="tablewrap">
          <table className="legendtable">
            <thead>
              <tr>
                <th>{tr("Beteckning")}</th><th>{tr("Slag")}</th><th className="num">{tr("Mängd")}</th>
                <th className="num">{tr("Etiketter")}</th><th>{tr("Status")}</th><th>{tr("Förklaring")}</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((e) => {
                const key = `${e.kind}/${e.name}`;
                const isOpen = open === key;
                return (
                  <Fragment key={key}>
                    <tr className={isOpen ? "open" : ""} data-entry={key} onClick={() => setOpen(isOpen ? null : key)}>
                      <td><b>{e.name}</b></td>
                      <td title={tr(KIND_HINT[e.kind] ?? "")}>
                        <span className={`rolepill ${KIND_CLASS[e.kind] ?? ""}`}>{tr(KIND_SV[e.kind] ?? e.kind)}</span>
                      </td>
                      <td className="num">{amount(e)} {e.unit === "st" ? tr("st") : e.unit}</td>
                      <td className="num">{e.labels || <span className="muted">–</span>}</td>
                      <td>
                        <span className={`badge small ${e.state === "säker" ? "ok" : "warn"}`}>
                          {e.state === "säker" ? tr("Säker") : tr("Granskas")}
                        </span>
                        {e.reasons.length > 0 && <div className="muted note">{e.reasons.map(reason).join(", ")}</div>}
                      </td>
                      <td>
                        {(lang === "en" && e.description_en) || e.description || <span className="muted">–</span>}
                        {e.described_by && e.description && (
                          <div className="muted note">{tr(SAID_BY[e.described_by] ?? e.described_by)}</div>
                        )}
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="detailrow">
                        <td colSpan={6}>
                          <div className="placeactions">
                            {e.places.length > 0 && (
                              <button className="small" onClick={() => { const b = unionOf(e.places); if (b) onZoom(b); }}>
                                {e.places.length > 1 ? trf("Visa alla {0} på bladet", e.places.length) : tr("Visa på bladet")}
                              </button>
                            )}
                            {e.kind === "ledning" && e.quantity > 0 && (e.runs?.length ? (
                              <button className="small" onClick={() => {
                                const b = spanOfRuns(e.runs!);
                                if (b) { if (onShowRuns) onShowRuns(e.runs!, b); else onZoom(b); }
                              }}>
                                {tr("Visa ledningen")}
                              </button>
                            ) : onShowPipe && (
                              <button className="small" onClick={() => onShowPipe(e.name)}>{tr("Visa ledningen")}</button>
                            ))}
                          </div>
                          {e.places.length === 0 ? (
                            <p className="muted">{tr("Raden kommer ur mängden. Namnet står inte utskrivet så på bladet.")}</p>
                          ) : (
                            <ul className="places">
                              {e.places.map((p, i) => (
                                <li key={i}>
                                  <button className="ghost placebtn" onClick={() => onZoom(p.bbox)}>{p.line}</button>
                                  {p.count > 1 && <span className="muted"> ×{p.count}</span>}
                                </li>
                              ))}
                            </ul>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
              {shown.length === 0 && (
                <tr><td colSpan={6} className="muted">{tr("Ingen beteckning matchar filtret.")}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
