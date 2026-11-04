import { useEffect, useMemo, useRef, useState } from "react";
import { identityColor, pipeColor } from "../palette";

export const identityKey = (r: any) => `${r.base}|DN${r.dn ?? "?"}`;
import { pipeRuns, runRows } from "../runs";
import { t as tr } from "../i18n";

const STATE_LABELS: Record<string, string> = { CONFIRMED: tr("BEKRÄFTAD"), AMBIGUOUS: tr("TVETYDIG"), NO_SCALE: tr("INGEN SKALA"),
  SCALE_UNSETTLED: "OAVGJORD SKALA", SCALE_FROM_THE_SET: "SKALA UR OMGÅNGEN", SCALE_FROM_PIPES: "SKALA MÄTT PÅ RÖREN", SCALE_MEASURED: "SKALA MÄTT PÅ BLADET", SCALE_GIVEN_BY_HAND: "ANGIVEN SKALA",
  UNSUPPORTED_STYLE: tr("EJ STÖDD STIL"), RISER_LABELS_ONLY: tr("ENDAST STIGARE"), IN_HATCHED_AREA: tr("I SKRAFFERAD YTA"),
  READ_FROM_IMAGE: tr("LÄST UR BILD"), UNNAMED: tr("ONÄMNT – GRANSKA") };

/* En rad utan skala har ingen meter - och noll är inte samma sak som okänt. Tabellen skrev 0,00 i varje
   meterkolumn på ett blad vars skala aldrig blev fastställd, vilket läses som "röret är noll meter långt"
   när sanningen är "hur långt det är går inte att säga än". */
const M = (v: number | null | undefined, noScale: boolean) => (noScale || v == null ? "–" : v.toFixed(2));

export const riserCount = (r: any, source: string) => (source === "labels" ? r.riser_count_from_labels : r.riser_count) ?? 0;

export const SLAB_RISER_M = 1.0;

/** Risers on a row split by kind: a storey each, or a metre up through the slab to a radiator. The engine proposes
    the split (riser_slab_count) and the reader may change it; an older reading marks the whole row by its height. */
export function riserSplit(r: any, risers: number): { storey: number; slab: number } {
  const proposed = r.riser_slab_count ?? (r.riser_height_m != null ? risers : 0);
  const slab = Math.max(0, Math.min(Number(proposed) || 0, risers));
  return { storey: risers - slab, slab };
}

export function riserMetres(r: any, risers: number, floorHeight: number): number {
  const { storey, slab } = riserSplit(r, risers);
  return storey * floorHeight + slab * SLAB_RISER_M;
}

export function withFloorHeight(rows: any[], floorHeight: number | null, includeHatched = false, riserSource = "labels",
                                includeDeclared = true): any[] {
  // vertical metres are never assumed by the engine; with a user-given floor height each riser counts height metres.
  // pipe drawn inside hatched areas is measured but kept out of the total unless the takeoff includes those areas.
  //
  // Förklarade kopplingsledningar är rör bladet namnger i ord i stället för med en etikett - "kopplingsledningar
  // från fördelare till apparat enligt tabell". Ritningen säger att de är där, så de räknas normalt med. Men en
  // mängdförteckning behöver inte ha dem med: de kan vara prissatta per apparat eller mätta på ett annat blad.
  // Därför går de att räkna bort, och då står kvar bara det en etikett pekat ut.
  return rows.map((r) => {
    const risers = riserCount(r, riserSource);
    const known = r.vertical_m !== "UNKNOWN" ? Number(r.vertical_m) : 0;
    // a radiator connection rises through the slab, about a metre; the others a storey
    // Med en höjd satt är en rad utan stigare en rad utan vertikal: 0 m, inte "okänt". Okänt är den bara när
    // ingen höjd är satt, och då vet läsningen verkligen inte hur högt bladets stigare går.
    const v = floorHeight && risers > 0 ? known + riserMetres(r, risers, floorHeight)
      : (r.vertical_m === "UNKNOWN" ? (floorHeight ? 0 : null) : known);
    const declared = Number(r.declared_m ?? 0);
    const h = Math.max(0, r.confirmed_horizontal_m - (includeDeclared ? 0 : declared))
      + (includeHatched ? Number(r.in_hatched_area_m ?? 0) : 0);
    const split = riserSplit(r, risers);
    return { ...r, risers_calc: risers, risers_storey: split.storey, risers_slab: split.slab,
             horizontal_calc: h, vertical_calc: v, total_calc: h + (v ?? 0) };
  });
}

export default function QuantityTable({ rows, selected, onSelect, floorHeight, includeHatched, onIncludeHatched, riserSource,
  includeDeclared = true, onIncludeDeclared, pipes = [], onPipeClick, meterPerPt, selectedPipe = null, onRiserSplit,
  schematic = false, section = false }: {
    rows: any[]; selected: string | null; onSelect: (key: string | null) => void; floorHeight: number | null;
    includeHatched: boolean; onIncludeHatched: (v: boolean) => void; riserSource: string;
    includeDeclared?: boolean; onIncludeDeclared?: (v: boolean) => void;
    pipes?: any[]; onPipeClick?: (p: any) => void; meterPerPt?: number | null;
    /** The pipe picked on the sheet: its designation opens and its own run is marked and brought into view. */
    selectedPipe?: string | null;
    /** The reader says how many of a row's risers go through the slab (a metre) rather than a storey. */
    onRiserSplit?: (row: any, slab: number) => void;
    /** The sheet is a flow or principle diagram: its rows have no metres because it is drawn without a scale. */
    schematic?: boolean; section?: boolean }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const runs = useMemo(() => pipeRuns(pipes), [pipes]);
  const pickedRun = useMemo(() => new Set(selectedPipe ? (runs.get(selectedPipe) ?? [selectedPipe]) : []), [selectedPipe, runs]);
  const pickedRow = useRef<HTMLTableRowElement | null>(null);
  useEffect(() => {
    if (!selectedPipe) return;
    const p = pipes.find((q: any) => q.physical_pipe_id === selectedPipe);
    if (p?.identity) setOpen(p.identity);
  }, [selectedPipe, pipes]);
  useEffect(() => {
    // after the run list has opened: the marked run is scrolled to, inside the table's own frame
    if (selectedPipe) pickedRow.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedPipe, open]);
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState<{ k: string; dir: 1 | -1 }>({ k: "designation", dir: 1 });
  const list = useMemo(() => {
    // en rad som varken har meter, stigare eller tvetydigt är en etikett utan rör - den säger ingenting i en mängd
    let l = withFloorHeight(rows, floorHeight, includeHatched, riserSource, includeDeclared).filter((r) =>
      r.total_calc > 0.005 || r.risers_calc > 0 || Number(r.ambiguous_m ?? 0) > 0.005 || Number(r.in_hatched_area_m ?? 0) > 0.005).filter((r) => (!q || r.designation.toLowerCase().includes(q.toLowerCase()) || String(r.dn).includes(q)) && (!status || r.state === status));
    l = [...l].sort((a, b) => { const va = a[sort.k], vb = b[sort.k]; return (va > vb ? 1 : va < vb ? -1 : 0) * sort.dir; });
    return l;
  }, [rows, q, status, sort, floorHeight, includeHatched, riserSource, includeDeclared]);
  const hatchedTotal = rows.reduce((s, r) => s + Number(r.in_hatched_area_m ?? 0), 0);
  const declaredTotal = rows.reduce((s, r) => s + Number(r.declared_m ?? 0), 0);
  const th = (k: string, label: string, unit?: string) => (
    <th onClick={() => setSort((s) => ({ k, dir: s.k === k ? (s.dir === 1 ? -1 : 1) : 1 }))}>
      {label}{sort.k === k ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
      {unit && <span className="unit">{unit}</span>}
    </th>
  );
  const tot = (f: string) => list.reduce((s, r) => s + (typeof r[f] === "number" ? r[f] : 0), 0);
  // bladet kunde inte ge en enda meter: då är varje meterruta ett streck, inte en nolla
  const noScale = rows.length > 0 && rows.every((r) => r.state === "NO_SCALE");
  return (
    <div>
      <div className="row" style={{ marginBottom: 8 }}>
        <input placeholder={tr("Sök beteckning/DN")} value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">{tr("Alla status")}</option><option value="CONFIRMED">CONFIRMED</option><option value="AMBIGUOUS">AMBIGUOUS</option><option value="NO_SCALE">NO_SCALE</option>
        </select>
        {hatchedTotal > 0 && (
          <label title={tr("Rör som är ritade inuti skrafferade ytor (väggsnitt, angränsande ritningsdel). Mäts alltid, men räknas normalt inte in i mängden.")}>
            <input type="checkbox" checked={includeHatched} onChange={(e) => onIncludeHatched(e.target.checked)} />
            {` Räkna med skrafferade ytor (${hatchedTotal.toFixed(2)} m)`}
          </label>
        )}
        {declaredTotal > 0 && onIncludeDeclared && (
          <label title={tr("Kopplingsledningar namngivna enligt ritningens standardangivelser i text eller tabell. De räknas med när geometrin har stöd för rätt system. Avmarkera om de prissätts separat per apparat.")}>
            <input type="checkbox" checked={includeDeclared} onChange={(e) => onIncludeDeclared(e.target.checked)} />
            {` Räkna med förklarade kopplingsledningar (${declaredTotal.toFixed(2)} m)`}
          </label>
        )}
      </div>
      {/* the takeoff has eleven columns and the panel beside a drawing is narrow: the table scrolls in its own
          frame, with the designation pinned, rather than pushing the panel sideways under the reader */}
      <div className="tablewrap">
      <table>
        <thead><tr>{th("designation", tr("Beteckning"))}{th("dn", "DN")}{th("label_count", tr("Etiketter"))}{th("physical_pipe_count", tr("Sträckor"))}{th("confirmed_horizontal_m", tr("Horisontellt"), "m")}{th("vertical_calc", tr("Vertikalt"), "m")}{th("total_calc", tr("Totalt"), "m")}{th("ambiguous_m", tr("Tvetydigt"), "m")}{th("in_hatched_area_m", tr("Skrafferat"), "m")}{th("risers_calc", tr("Stigare"))}{th("state", tr("Status"))}</tr></thead>
        <tbody>
          {list.flatMap((r) => [
            <tr key={identityKey(r)} className={`selectable ${selected === identityKey(r) ? "selected" : ""}`} onClick={() => onSelect(selected === identityKey(r) ? null : identityKey(r))}>
              <td><span style={{ display: "inline-block", width: 12, height: 12, borderRadius: 2, background: identityColor(identityKey(r)), marginRight: 6, verticalAlign: "middle" }} />{r.designation}</td><td>{r.dn ?? "?"}</td><td className="num" title={(r.declared_m ?? 0) > 0
                ? `${r.label_count ?? 0} verifierade beteckningar på ritningen. ${Number(r.declared_m).toFixed(1)} m är namngivna enligt ritningens standardangivelser för kopplingsledningar.`
                : "Antal verifierade beteckningar på ritningen för denna identitet"}>
                {r.label_count ?? "–"}{(r.declared_m ?? 0) > 0 && <span className="assumed"> {tr("standardangivelse")}</span>}{(r.double_line_m ?? 0) > 0 && <span className="assumed" title={`${Number(r.double_line_m).toFixed(1)} m är rörets andra ritade kant och räknas inte: ett grövre rör ritas som två linjer.`}> dubbellinje</span>}
              </td>
              <td className="num">
                {r.physical_pipe_count > 0 ? (
                  <button className="ghost small drill" title={tr("Visa varje sträcka för sig")}
                    onClick={(e) => { e.stopPropagation(); setOpen(open === identityKey(r) ? null : identityKey(r)); }}>
                    {r.physical_pipe_count} {open === identityKey(r) ? "▾" : "▸"}
                  </button>
                ) : r.physical_pipe_count}
              </td>
              {/* En rad som bara är stigare har inga vågräta meter, och en nolla där läses som en mätning.
                  Det är den inte. Samma slags etikett används på två sätt: vid en vask eller golvbrunn finns
                  ingen ledning i planet alls - röret går ned genom bjälklaget - men den används också där ett
                  rör kommer upp ur golvet och dras vidare längs väggen, och då finns ledningen och läsningen
                  kan ha missat den. Strecket säger att ingen vågrät sträcka hittades, utan att påstå vilket
                  av de två fallen det är. */}
              <td className="num">{r.state === "UNNAMED"
                ? <span className="assumed" title={tr("Ritat rör som ingen beteckning når. Metrarna är mätta och sträckorna visas streckade med gul kant på ritningen, men de ingår inte i totalen förrän någon gett dem ett namn.")}>
                    {M(r.unnamed_review_m, noScale)} {tr("onämnt")}</span>
                : r.state === "IN_HATCHED_AREA" && !(r.horizontal_calc > 0)
                ? <span className="muted" title={`Hela stråket är ritat inne i en skrafferad yta (${Number(r.in_hatched_area_m ?? 0).toFixed(2)} m). Skrafferingen är hur ritningen säger att en del inte redovisas här - en angränsande byggnadsdel eller ett annat skede - och mängden räknar inte i den. Bocka i "Räkna med skrafferade ytor" om den här ritningen menar något annat med sin skraffering.`}>–</span>
                : r.state === "RISER_LABELS_ONLY" && !(r.horizontal_calc > 0)
                ? <span className="muted" title={tr("Ingen vågrät sträcka hittad för den här etiketten. Den märker ett rör som går genom bjälklaget: antingen slutar det där (en vask, en golvbrunn) och det finns ingen ledning i planet, eller så fortsätter det längs väggen och läsningen har inte hittat den. Ritningen avgör det med strecket vid dimensionssiffran.")}>–</span>
                : M(r.horizontal_calc, noScale)}</td>
              <td className="num">{noScale || r.vertical_calc == null
                ? (r.risers_calc > 0
                  ? <span className="muted" title={tr("Stigarna är hittade; ange våningshöjd för att räkna om dem till meter")}>{`${r.risers_calc} st × höjd`}</span>
                  : <span className="muted" title={tr("Ritningen anger ingen höjd och inga stigare hittades")}>{tr("okänt")}</span>)
                : <>
                    {Number(r.vertical_calc).toFixed(2)}
                    {/* a height the reader typed is an assumption about the building, not something the sheet
                        says: the metre is shown, and marked for what it is */}
                    {floorHeight && r.risers_calc > 0 && (
                      <span className="assumed" title={`Antaget: ${r.risers_storey} stigare × ${String(floorHeight).replace(".", ",")} m våningshöjd`
                        + ` och ${r.risers_slab} upp genom bjälklag × ${String(SLAB_RISER_M).replace(".", ",")} m. Ritningen anger ingen höjd.`}> ant.</span>
                    )}
                  </>}</td>
              <td className="num strong">{M(r.total_calc, noScale)}
                {/* metres measured on a tentative reading are in the total, and said to be: the reader checks
                    those runs on the sheet (they are drawn broken, on an amber halo) */}
                {!noScale && (r.review_m ?? 0) > 0.005 && (
                  <span className="assumed" title={`${Number(r.review_m).toFixed(2)} m är mätta på bästa läsningen och bör kontrolleras på bladet. De visas streckade med gul kant.`}> varav {Number(r.review_m).toFixed(1)} att granska</span>
                )}
                {/* a run the labels left in doubt, measured under this name as the best reading: shown on the row
                    and on the sheet, but not in the total until someone has looked at it */}
                {!noScale && (r.proposed_review_m ?? 0) > 0.005 && (
                  <span className="assumed" title={`${Number(r.proposed_review_m).toFixed(2)} m pekas ut av flera beteckningar. De är mätta under den här, som har störst stöd, och visas streckade med gul kant. De ingår inte i totalen förrän någon har granskat dem.`}> + {Number(r.proposed_review_m).toFixed(1)} {tr("att granska")}</span>
                )}
                {!noScale && (r.inferred_m ?? 0) > 0.005 && (
                  <span className="assumed" title={`${Number(r.inferred_m).toFixed(2)} m har sitt namn härlett ur ritningens logik (fortsätter från ett namngivet rör, självfallsledningens nivåer, värdläsningen) snarare än från en egen etikett. Lagret Säkerhet visar dem gula.`}> · {Number(r.inferred_m).toFixed(1)} härlett</span>
                )}</td>
              <td className="num">{!noScale && r.ambiguous_m > 0 ? r.ambiguous_m.toFixed(2) : "–"}</td>
              <td className="num">{!noScale && (r.in_hatched_area_m ?? 0) > 0 ? Number(r.in_hatched_area_m).toFixed(2) : "–"}</td>
              <td className="num" title={`Ritade stigarsymboler: ${r.riser_count ?? 0} · etiketter med dimension på raden under: ${r.riser_count_from_labels ?? 0}`}>
                {r.risers_calc > 0 ? r.risers_calc : "–"}
                {/* Bladet ritar en stigare genom bjälklaget (1 m till radiatorn) och en hel våning likadant; hur
                    många av radens som är vilket säger läsaren, och det sparas som en rättelse. */}
                {r.risers_calc > 0 && onRiserSplit && (
                  <span className="assumed" onClick={(e) => e.stopPropagation()}
                    title={tr("Hur många av stigarna som går genom bjälklaget (1 m) i stället för en våning")}>
                    {" "}varav bjälklag{" "}
                    <input type="number" min={0} max={r.risers_calc} value={r.risers_slab} style={{ width: 44 }}
                      onChange={(e) => { const n = Math.max(0, Math.min(r.risers_calc, Math.round(Number(e.target.value) || 0)));
                        if (n !== r.risers_slab) onRiserSplit(r, n); }} />
                  </span>
                )}
              </td>
              <td><span className={`badge ${r.state === "CONFIRMED" ? "ok" : r.state === "AMBIGUOUS" || r.state === "RISER_LABELS_ONLY" || r.state === "IN_HATCHED_AREA" || r.state === "UNNAMED" ? "warn" : "bad"}`}>{r.state === "NO_SCALE" && schematic ? tr(section ? "SEKTION" : "SCHEMA") : STATE_LABELS[r.state] ?? r.state}</span></td>
            </tr>,
            ...(open === identityKey(r)
              ? runRows(pipes.filter((p: any) => p.identity === identityKey(r)), runs)
                  .sort((a: any, b: any) => (b.horizontal_m ?? 0) - (a.horizontal_m ?? 0))
                  .map((p: any, i: number) => {
                    const labels = p.supporting_anchors?.length ?? 0;
                    const bridged = (p.bridged_gap_pt ?? 0) * (meterPerPt ?? 0);
                    const mine = (p.run_ids ?? [p.physical_pipe_id]).some((id: string) => pickedRun.has(id));
                    return (
                      <tr key={`${identityKey(r)}-run-${p.physical_pipe_id}`} className={`run ${mine ? "selected" : ""}`}
                        ref={mine ? pickedRow : undefined} onClick={() => onPipeClick?.(p)}>
                        <td><span style={{ display: "inline-block", width: 12, height: 12, borderRadius: 2, background: pipeColor(p), marginRight: 6 }} />{String(i + 1).padStart(2, "0")} · rör{p.parts > 1 ? ` (${p.parts} delar)` : ""}</td>
                        <td colSpan={2} className="muted">
                          sida {(p.page ?? 0) + 1} · {labels} etikett{labels === 1 ? "" : "er"}
                          {p.needs_review && <span className="assumed"> · att granska</span>}
                        </td>
                        <td className="num muted">{p.graph_nodes?.length ?? ""}</td>
                        <td className="num">{p.horizontal_m == null ? "–" : p.horizontal_m.toFixed(2)}</td>
                        <td className="num muted">{typeof p.vertical_m === "number" ? p.vertical_m.toFixed(2) : "–"}</td>
                        <td className="num strong">{p.total_m == null ? "–" : p.total_m.toFixed(2)}</td>
                        <td colSpan={4} className="muted" style={{ fontSize: 12 }}>
                          {(p.section_levels ?? []).map((e: any) => `${e.level.kind}${e.level.value >= 0 ? "+" : ""}${e.level.value}`).join(" · ")}
                          {p.section_levels?.length ? " · " : ""}
                          {(p.reasons ?? []).slice(0, 2).join(" · ")}
                          {bridged > 0.005 ? `${p.reasons?.length ? " · " : ""}${bridged.toFixed(2)} m överbryggade streckglapp` : ""}
                        </td>
                      </tr>
                    );
                  })
              : []),
          ])}
        </tbody>
        <tfoot><tr><th>Summa</th><th></th><th className="num">{tot("label_count")}</th><th className="num">{tot("physical_pipe_count")}</th><th className="num">{M(tot("horizontal_calc"), noScale)}</th><th className="num">{M(tot("vertical_calc"), noScale)}</th><th className="num strong">{M(tot("total_calc"), noScale)}</th><th className="num">{M(tot("ambiguous_m"), noScale)}</th><th className="num">{M(tot("in_hatched_area_m"), noScale)}</th><th className="num">{tot("risers_calc")}</th><th></th></tr></tfoot>
      </table>
      </div>
    </div>
  );
}
