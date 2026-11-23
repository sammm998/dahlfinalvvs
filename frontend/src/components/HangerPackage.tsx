import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { t as tr, trf, locale } from "../i18n";

/* SmartHangers ur ett modellpaket (kravunderlaget): VS-, K- och A-modellen laddas upp tillsammans, läses i
 * bakgrunden, kontrolleras mot V1–V11 och räknas. Ett Stopp i kontrollrapporten stoppar beräkningen tills
 * modellen är rättad eller ett värde är angivet här (takhöjd per våning/zon eller en uppskattning). */

export const DISCIPLINES: [string, string][] = [["VS", "VS – rören"], ["K", "K – bjälklag, balkar, håltagningar"],
  ["A", "A – väggar, undertak"], ["Ö", "Övrig – hinder (el, ventilation)"]];

export function guessDiscipline(name: string): string {
  const toks = name.toUpperCase().match(/(?:^|[-_ .])([A-ZÅÄÖ]{1,3})(?=[-_ .\d])/g) || [];
  for (const raw of toks) {
    const t = raw.replace(/^[-_ .]/, "");
    if (["V", "VS", "VVS", "S", "P"].includes(t)) return "VS";
    if (["K", "KB", "KON"].includes(t)) return "K";
    if (["A", "AR", "ARK"].includes(t)) return "A";
    if (["E", "EL", "R", "L", "VE", "SP"].includes(t)) return "Ö";
  }
  return "VS";
}

const LEVEL_CLASS: Record<string, string> = { stopp: "error", varning: "warn", info: "" };

export function PackageUpload({ projectId, onCreated }: { projectId: string; onCreated: (s: any) => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const [disc, setDisc] = useState<string[]>([]);
  const [estimate, setEstimate] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const inp = useRef<HTMLInputElement>(null);
  const pick = (fl: FileList | null) => {
    const arr = Array.from(fl || []);
    setFiles(arr); setDisc(arr.map((f) => guessDiscipline(f.name)));
  };
  const send = async () => {
    setBusy(true); setErr("");
    try {
      const s = await api.createHangerPackage(projectId, files, disc, {}, estimate);
      setFiles([]); setDisc([]); if (inp.current) inp.current.value = "";
      onCreated(s);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const mb = files.reduce((a, f) => a + f.size, 0) / 1e6;
  return (
    <div className="card" style={{ marginTop: 10, padding: 10 }}>
      <b>{tr("Modellpaket (rekommenderas): VS + K + A")}</b>
      <p className="muted small" style={{ maxWidth: 760 }}>{tr("Ladda upp VS-modellen med rören, K-modellen med bjälklag, balkar och håltagningar, och A-modellen med väggar och undertak – gärna andra disciplinernas modeller som hinder. Filerna läses i bakgrunden (en stor modell tar någon minut) och kontrolleras mot reglerna V1–V11 innan något räknas. Disciplinen läses ur filnamnet; ändra den om den blev fel.")}</p>
      <input type="file" multiple accept=".ifc,.zip,.ifczip" id="prefab-pkg" className="file" ref={inp} onChange={(e) => pick(e.target.files)} />
      <label className="pick small" htmlFor="prefab-pkg">{tr("Välj modellfiler")}</label>
      {files.length > 0 && (
        <div className="small" style={{ marginTop: 6 }}>
          {files.map((f, i) => (
            <div key={i} className="row" style={{ gap: 6, alignItems: "center" }}>
              <select value={disc[i]} onChange={(e) => setDisc(disc.map((d, j) => j === i ? e.target.value : d))}>
                {DISCIPLINES.map(([k, n]) => <option key={k} value={k}>{tr(n)}</option>)}
              </select>
              <span>{f.name}</span><span className="muted">{(f.size / 1e6).toLocaleString(locale(), { maximumFractionDigits: 1 })} MB</span>
            </div>))}
          {!disc.includes("K") && (
            <label style={{ display: "block", marginTop: 6 }}>{tr("Ingen K-modell: uppskatta underkant bjälklag så här många mm över det högsta röret i närheten (tomt = ange takhöjd per våning efteråt)")}<br />
              <input style={{ width: 90 }} value={estimate} onChange={(e) => setEstimate(e.target.value)} placeholder="t.ex. 150" /></label>)}
          <button className="small" style={{ marginTop: 6 }} disabled={busy || !disc.includes("VS")} onClick={send}>
            {busy ? trf("Laddar upp {0} MB…", mb.toLocaleString(locale(), { maximumFractionDigits: 0 })) : tr("Ladda upp och kontrollera")}</button>
          {!disc.includes("VS") && <span className="error small" style={{ marginLeft: 8 }}>{tr("Paketet behöver en VS-modell")}</span>}
        </div>)}
      {err && <p className="error small">{err}</p>}
    </div>
  );
}

export function PackageStatus({ setId, onDone, download }: { setId: string; onDone: () => void; download: (fmt: string) => void }) {
  const [pk, setPk] = useState<any>(null);
  const [heights, setHeights] = useState<Record<string, string>>({});
  const [slab, setSlab] = useState<Record<string, string>>({});
  const [estimate, setEstimate] = useState("");
  const [arts, setArts] = useState<any>(null);
  const [err, setErr] = useState("");
  const was = useRef<string>("");

  const fill = (p: any) => {
    setPk(p);
    setHeights(Object.fromEntries(Object.entries(p.manual_heights || {}).map(([k, v]) => [k, String(v)])));
    setSlab({ ...(p.zone_slab_types || {}) });
    setEstimate(p.estimate_above == null ? "" : String(p.estimate_above));
  };
  useEffect(() => {
    let stop = false;
    let timer: any;
    const tick = async () => {
      try {
        const p = await api.hangerPackage(setId);
        if (stop) return;
        setPk((old: any) => (old && old.job?.done && p.job?.done ? old : p));
        if (!was.current || p.job?.done) fill(p);
        if (p.job?.done && was.current && was.current !== "done") onDone();
        was.current = p.job?.done ? "done" : (p.job?.state || "x");
        if (!p.job?.done) timer = setTimeout(tick, 3000);
      } catch (e: any) { setErr(e.message); }
    };
    was.current = "";
    tick();
    return () => { stop = true; clearTimeout(timer); };
  }, [setId]);

  if (!pk) return null;
  const job = pk.job || {};
  const save = async (body: any) => {
    setErr("");
    try { const r = await api.hangerPackageSettings(setId, body); void r; was.current = "x"; setPk({ ...pk, job: { state: "köad", step: tr("räknar om"), done: false } });
      const poll = async () => { const p = await api.hangerPackage(setId); setPk(p); if (p.job?.done) { fill(p); onDone(); } else setTimeout(poll, 3000); };
      setTimeout(poll, 1500);
    } catch (e: any) { setErr(e.message); }
  };
  const num = (o: Record<string, string>) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(String(v).replace(",", "."))]));
  const vs = pk.validation_summary || {};
  const zones: string[] = pk.zones || [];
  return (
    <div className="card" style={{ marginTop: 10, padding: 10 }}>
      <div className="row" style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <b>{tr("Modellpaket")}</b>
        {pk.files.map((f: any) => <span key={f.name} className="badge small">{f.discipline}: {f.name}</span>)}
        <span className={`badge ${job.state === "klar" ? "ok" : job.state === "stoppad" || job.state === "fel" || job.state === "avbruten" ? "warn" : ""}`}>
          {tr(job.state || "–")}{job.step ? ` · ${tr(job.step)}` : ""}</span>
        {!job.done && <span className="muted small">{tr("uppdateras var tredje sekund")}</span>}
        {(job.state === "fel" || job.state === "avbruten") && <button className="secondary small" onClick={async () => { try { await api.hangerPackageRerun(setId); setPk({ ...pk, job: { state: "köad", done: false } }); setTimeout(async () => fill(await api.hangerPackage(setId)), 2000); } catch (e: any) { setErr(e.message); } }}>{tr("Läs om filerna")}</button>}
      </div>
      {pk.files_read?.length > 0 && (
        <div className="small muted" style={{ marginTop: 4 }}>
          {pk.files_read.map((f: any) => <div key={f.file_name}>{f.discipline}: {f.file_name} · {f.application || ""} · {f.timestamp || ""} · {trf("{0} rör, {1} bjälklag/balkar, {2} väggar, {3} håltagningar", f.pipes, f.ceilings, f.walls, f.openings)}</div>)}
        </div>)}

      {pk.validation?.length > 0 && (
        <details className="settings" style={{ marginTop: 8 }} open={job.state === "stoppad"}>
          <summary>{trf("Kontrollrapport V1–V11: {0} stopp, {1} varningar, {2} info", vs.stopp || 0, vs.varning || 0, vs.info || 0)}</summary>
          {pk.validation.map((f: any, i: number) => (
            <div key={i} className="small" style={{ marginTop: 4 }}>
              <span className={`badge small ${LEVEL_CLASS[f.level] || ""}`}>{f.rule} {tr(f.level)}</span> <b>{tr(f.title)}</b>
              <div className="muted">{tr(f.text)}{f.n ? ` · ${trf("{0} objekt (GlobalId i BCF-filen)", f.n)}` : ""}</div>
            </div>))}
        </details>)}
      {Object.keys(pk.findings_summary || {}).length > 0 && (
        <div className="small" style={{ marginTop: 6 }}>{tr("Beräkningens avvikelser")}: {Object.entries(pk.findings_summary).map(([k, v]) => `${k} ${v}`).join(" · ")}</div>)}

      <details className="settings" style={{ marginTop: 8 }} open={job.state === "stoppad"}>
        <summary>{tr("Värden när modellen inte räcker: takhöjd, bjälklagstyp, uppskattning")}</summary>
        <p className="muted small">{tr("Underkant bjälklag i mm (modellens höjder) per våning, eller per våning och zon. Används där K-modellen inte har något bjälklag ovanför röret och märks 'manuell' på varje hängare.")}</p>
        <div className="row small" style={{ gap: 8, flexWrap: "wrap" }}>
          {(pk.storeys || []).map((s: string) => (
            <label key={s}>{s}<br /><input style={{ width: 90 }} value={heights[s] || ""} onChange={(e) => setHeights({ ...heights, [s]: e.target.value })} /></label>))}
        </div>
        {zones.length > 0 && (<>
          <p className="muted small" style={{ marginTop: 8 }}>{tr("Bjälklagstyp per zon (styr ankaret och dess bärförmåga) – behövs där K-modellen inte anger typen:")}</p>
          <div className="row small" style={{ gap: 8, flexWrap: "wrap", maxHeight: 180, overflow: "auto" }}>
            {zones.slice(0, 200).map((z) => (
              <label key={z}>{z.replace("|", " · ")}<br />
                <select value={slab[z] || ""} onChange={(e) => setSlab({ ...slab, [z]: e.target.value })}>
                  <option value="">{tr("ur modellen/standard")}</option>
                  {(pk.slab_types || []).map((t: string) => <option key={t} value={t}>{t}</option>)}
                </select></label>))}
          </div></>)}
        {!pk.has?.K && (
          <label className="small" style={{ display: "block", marginTop: 8 }}>{tr("Uppskatta underkant bjälklag (mm över högsta röret i närheten) – för offert och mängd, inte för kapning")}<br />
            <input style={{ width: 90 }} value={estimate} onChange={(e) => setEstimate(e.target.value)} /></label>)}
        <button className="small" style={{ marginTop: 8 }} disabled={!job.done} onClick={() => save({ manual_heights: num(heights), zone_slab_types: slab, estimate_above: estimate === "" ? null : Number(estimate) })}>{tr("Spara och räkna om")}</button>
      </details>

      {(pk.groups?.split?.length > 0 || pk.groups?.merge?.length > 0) && (
        <div className="small" style={{ marginTop: 6 }}>
          {trf("Trapetsgruppering ändrad för hand: {0} rör hängs var för sig, {1} sammanslagningar", (pk.groups.split || []).length, (pk.groups.merge || []).length)}{" "}
          <button className="secondary small" disabled={!job.done} onClick={async () => { try { await api.hangerGroups(setId, { reset: true }); was.current = "x"; setPk({ ...pk, job: { state: "köad", done: false } }); setTimeout(async () => { const p = await api.hangerPackage(setId); fill(p); if (p.job?.done) onDone(); }, 2500); } catch (e: any) { setErr(e.message); } }}>{tr("Återställ grupperingen")}</button>
        </div>)}
      <div className="row small" style={{ gap: 6, flexWrap: "wrap", marginTop: 8 }}>
        <b>{tr("Utdata")}:</b>
        <button className="secondary small" disabled={!pk.n} onClick={() => download("csv")}>{tr("Punktlista (CSV)")}</button>
        <button className="secondary small" disabled={!pk.n} onClick={() => download("artiklar")}>{tr("Artikellista per zon med priser (Excel)")}</button>
        <button className="secondary small" disabled={!pk.validation?.length} onClick={() => download("rapport")}>{tr("Kontrollrapport (PDF)")}</button>
        <button className="secondary small" disabled={!pk.validation?.length} onClick={() => download("bcf")}>{tr("Kontrollrapport (BCF)")}</button>
        <button className="secondary small" disabled={!pk.n} onClick={() => download("dxf")}>{tr("Ritunderlag (DXF)")}</button>
        <button className="secondary small" disabled={!pk.n} onClick={async () => { try { setArts(await api.hangerArticles(setId)); } catch (e: any) { setErr(e.message); } }}>{tr("Visa artikelsumma")}</button>
      </div>
      {arts && (
        <div className="small" style={{ marginTop: 6 }}>
          <b>{trf("Summa {0} kr", Math.round(arts.totals.total).toLocaleString(locale()))}</b>
          {arts.totals.rows_without_price > 0 && <span className="badge warn small" style={{ marginLeft: 6 }}>{trf("{0} rader utan artikel eller pris", arts.totals.rows_without_price)}</span>}
          <div className="muted">{Object.entries(arts.totals.by_zone).slice(0, 30).map(([k, v]: [string, any]) => `${k}: ${Math.round(v).toLocaleString(locale())} kr`).join(" · ")}</div>
        </div>)}
      {err && <p className="error small">{err}</p>}
    </div>
  );
}
