import { askAiModel } from "../aiChoice";
import { useEffect, useRef, useState } from "react";
import { t as tr, trf, locale } from "../i18n";
import { Link, useParams } from "react-router-dom";
import { api, fileSize } from "../api";
import { StatusBadge } from "../components/Status";
import Tilted from "../components/Tilted";
import { PriceTag } from "./Credits";
import { ContractFormChoice, DisciplineChoice, Discipline, FALLBACK_DISCIPLINES, ProjectBadges, AbtVariantChoice } from "../components/ProjectForm";
import TechSpecPanel from "../components/TechSpecPanel";
import OfferPanel from "../components/OfferPanel";
import PrefabPanel from "../components/PrefabPanel";
import { AbtPanel } from "../components/AbtRooms";

const DATE = new Intl.DateTimeFormat(locale(), { day: "2-digit", month: "short", year: "numeric" });

export default function ProjectPage() {
  const { id } = useParams();
  const [project, setProject] = useState<any>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState("");
  const [progress, setProgress] = useState("");
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const fileRef = useRef<HTMLInputElement>(null);
  const [ifcKey, setIfcKey] = useState(0);
  const [disciplines, setDisciplines] = useState<Discipline[]>(FALLBACK_DISCIPLINES);
  // vad nästa uppladdade ritning ska läsas som; tomt = projektets disciplin
  const [readAs, setReadAs] = useState("");
  // changing the contract form or the discipline afterwards: chosen here, said back, and only then sent
  const [changing, setChanging] = useState<{ contract_form: string; discipline: string; tech_spec: boolean; abt_variant: string } | null>(null);
  useEffect(() => { api.disciplines().then((d) => d?.length && setDisciplines(d)).catch(() => { /* bara VVS */ }); }, []);
  const load = () => api.project(id!).then(setProject).catch((e) => setErr(e.message));
  const saveForm = async () => {
    if (!changing) return;
    try { await api.setProjectForm(id!, { ...changing, tech_spec: changing.contract_form === "ABT06" && changing.tech_spec, abt_variant: changing.contract_form === "ABT06" ? changing.abt_variant : undefined, confirm: true }); setChanging(null); await load(); }
    catch (ex: any) { setErr(ex.message); }
  };
  // the list only changes while a reading is running, or just after an upload; otherwise it can sit still
  const live = (project?.drawings ?? []).some((d: any) =>
    d?.latest_job && d.latest_job.status !== "COMPLETED" && d.latest_job.status !== "FAILED");
  useEffect(() => {
    load();
    if (!live) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [id, live]);
  const upload = async () => {
    const files = Array.from(fileRef.current?.files ?? []); if (!files.length) return;
    setBusy(true); setErr(""); setNotice("");
    let uploaded = 0, duplicates = 0;
    const failed: File[] = [], errors: string[] = [];
    try {
      for (const [i, f] of files.entries()) {
        setProgress(`${i + 1} / ${files.length} · ${f.name}`);
        // en IFC-modell är ingen ritning: den läses till material i IFC-panelen nedanför
        const ifc = /\.(ifc|ifczip|zip)$/i.test(f.name);
        const list = /\.(eml|txt|docx|xlsx|xlsm|csv)$/i.test(f.name);
        try { const result = ifc ? await api.uploadIfc(id!, f) : list ? await api.uploadMaterialList(id!, f) : await api.upload(id!, f, readAs || undefined); if (result.duplicate) duplicates++; else uploaded++; if (ifc || list) setIfcKey((k) => k + 1); }
        catch (ex: any) { failed.push(f); errors.push(`${f.name}: ${ex.message}`); }
      }
      // clearing the field is tidying up after a finished upload, not part of it: if the input is gone by now
      // the upload still happened, and asserting it is there turns a success into an error message
      if (fileRef.current) {
        const remaining = new DataTransfer();
        failed.forEach(f => remaining.items.add(f));
        fileRef.current.files = remaining.files;
      }
      setPicked(failed.length ? trf("{0} filer valda", failed.length) : "");
      setErr(errors.join("\n"));
      setNotice(trf("{0} uppladdade · {1} fanns redan · {2} misslyckades", uploaded, duplicates, failed.length));
      await load();
    } finally { setBusy(false); setProgress(""); }
  };
  const startSelected = async () => {
    setBusy(true); setErr(""); setNotice("");
    const errors: string[] = [];
    const remaining = new Set(selected);
    try {
      const drawings = project.drawings.filter((d: any) => selected.has(d.id));
      // en fråga om modellen för hela omgången, inte en per ritning
      const aiModel = await askAiModel(drawings.length);
      if (!aiModel) return;
      for (const [i, d] of drawings.entries()) {
        setProgress(`${i + 1} / ${drawings.length} · ${d.filename}`);
        try { await api.analyze(d.id, undefined, 0, "combined", "auto", aiModel); remaining.delete(d.id); }
        catch (ex: any) { errors.push(`${d.filename}: ${ex.message}`); }
      }
      setSelected(remaining);
      setErr(errors.join("\n"));
      setNotice(trf("{0} analyser i kö", drawings.length - errors.length));
      await load();
    } finally { setBusy(false); setProgress(""); }
  };
  // en länk från Kom igång (#offert, #smarthangers ...) går till rätt del när sidan har laddat
  useEffect(() => {
    if (!project || !window.location.hash) return;
    const el = document.getElementById(window.location.hash.slice(1));
    if (el) { if (el.tagName === "DETAILS") (el as HTMLDetailsElement).open = true; window.setTimeout(() => el.scrollIntoView({ behavior: "smooth", block: "start" }), 80); }
  }, [!!project]);
  const canStart = (d: any) => !d.latest_job || ["COMPLETED", "FAILED"].includes(d.latest_job.status);
  if (!project) return <main>{err ? <p className="error">{err}</p> : "Laddar…"}</main>;
  // ABT 06 med bara teknisk beskrivning: inga ritningar att ladda upp eller läsa, bara beskrivningen
  const specOnly = project.abt_variant === "beskrivning";
  return (
    <main>
      <p className="crumb"><Link to="/projekt">Projekt</Link> / {project.name}</p>
      <div className="head">
        <div>
          <h1>{project.name}</h1>
          <p className="lead">{project.description || tr("Ritningar i projektet")}</p>
          <div className="row" style={{ gap: 8, marginTop: 8 }}>
            <ProjectBadges project={project} disciplines={disciplines} />
            {!changing && <button className="ghost small" onClick={() => setChanging({ contract_form: project.contract_form, discipline: project.discipline, tech_spec: !!project.tech_spec, abt_variant: project.abt_variant || "ritningar" })}>{tr("Ändra")}</button>}
          </div>
        </div>
        {!specOnly && <div className="row">
          <input type="file" accept="application/pdf,.pdf,image/png,image/jpeg,image/tiff,.png,.jpg,.jpeg,.tif,.tiff,.ifc,.ifczip,.zip,.eml,.txt,.docx,.xlsx,.xlsm,.csv" multiple disabled={busy} ref={fileRef} id="pdf" className="file"
            title={tr("Vektor-PDF läses ur ritningens egna linjer. En skanning eller bild läses ur bildpunkterna och ska granskas. En IFC-modell (.ifc eller .zip) läses till VVS-material.")}
            onChange={(e) => { const files = e.target.files; setPicked(files?.length === 1 ? files[0].name : files?.length ? trf("{0} filer valda", files.length) : ""); }} />
          <label className="pick" htmlFor="pdf">{picked || tr("Välj PDF, bild eller IFC…")}</label>
          <label className="small" title={tr("Vad ritningen ska läsas som. Ett projekt kan ha ritningar från flera discipliner.")}>{tr("Läs som")}{" "}
            <select value={readAs} onChange={(e) => setReadAs(e.target.value)}>
              <option value="">{trf("Projektets ({0})", tr(disciplines.find((x) => x.id === project.discipline)?.name || project.discipline || "VVS"))}</option>
              {disciplines.filter((x) => x.status === "active" && x.id !== project.discipline).map((x) => <option key={x.id} value={x.id}>{tr(x.name)}</option>)}
            </select></label>
          <button onClick={upload} disabled={busy || !picked}>{busy ? tr("Laddar upp…") : tr("Ladda upp")}</button>
          {/* En ritning i taget svarar med meter. Hela handlingen svarar med vad den består av. */}
          <Link to={`/projects/${project.id}/analys`}><button className="secondary">{tr("Analysera projektet")}</button></Link>
        </div>}
      </div>
      {changing && (
        <div className="card" style={{ marginTop: 18, maxWidth: 640 }}>
          <ContractFormChoice value={changing.contract_form} onChange={(v) => setChanging({ ...changing, contract_form: v })} name="contract-change" />
          {changing.contract_form === "ABT06" && <AbtVariantChoice variant={changing.abt_variant} techSpec={changing.tech_spec} onChange={(v, t) => setChanging({ ...changing, abt_variant: v, tech_spec: t })} name="abt-variant-change" />}
          <DisciplineChoice value={changing.discipline} onChange={(v) => setChanging({ ...changing, discipline: v })} disciplines={disciplines} name="discipline-change" />
          <p className="muted small">{tr("Bytet gäller nya läsningar i projektet. Läsningar som redan är gjorda ändras inte.")}</p>
          <div className="row" style={{ gap: 8 }}>
            <button onClick={saveForm} disabled={changing.contract_form === project.contract_form && changing.discipline === project.discipline && changing.tech_spec === !!project.tech_spec && changing.abt_variant === (project.abt_variant || "ritningar")}>{tr("Bekräfta ändringen")}</button>
            <button className="secondary" onClick={() => setChanging(null)}>{tr("Avbryt")}</button>
          </div>
        </div>
      )}
      <nav className="row small" aria-label={tr("Projektets delar")} style={{ gap: 6, flexWrap: "wrap", marginTop: 14 }}>
        <span className="muted">{tr("I projektet")}:</span>
        {!specOnly && <a className="chip" href="#ritningar">{trf("Ritningar och analys ({0})", project.drawings.length)}</a>}
        {!specOnly && <Link className="chip" to={`/projects/${project.id}/analys`}>{tr("Hela handlingen")}</Link>}
        <a className="chip" href="#material">{tr("Teknisk beskrivning och material")}</a>
        <a className="chip" href="#offert">{tr("Offert")}</a>
        <a className="chip" href="#smarthangers">{tr("SmartHangers (IFC)")}</a>
        {project.contract_form === "ABT06" && !specOnly && <a className="chip" href="#abt">{tr("ABT 06")}</a>}
        <Link className="chip" to="/start">{tr("Vad kan jag göra?")}</Link>
      </nav>
      <div id="material" style={{ scrollMarginTop: 12 }}>
        <TechSpecPanel project={project} />
        <TechSpecPanel key={`ifc-${ifcKey}`} project={project} source="ifc" />
      </div>
      <div id="offert" style={{ scrollMarginTop: 12 }}><OfferPanel project={project} /></div>
      <div id="smarthangers" style={{ scrollMarginTop: 12 }}><PrefabPanel project={project} /></div>
      {project.contract_form === "ABT06" && !specOnly && <div id="abt" style={{ scrollMarginTop: 12 }}><AbtPanel project={project} /></div>}
      {progress && <p role="status" aria-live="polite">{progress}</p>}
      {notice && <p role="status">{notice}</p>}
      {err && <p className="error" style={{ marginTop: 18, whiteSpace: "pre-line" }}>{err}</p>}

      {!specOnly && <>{project.drawings.length > 0 && <div className="row" style={{ marginTop: 18 }}>
        <button className="secondary small" disabled={busy} onClick={() => setSelected(new Set(project.drawings.filter((d: any) => canStart(d) && d.latest_job?.status !== "COMPLETED").map((d: any) => d.id)))}>{tr("Välj oanalyserade")}</button>
        <button className="secondary small" disabled={busy || !selected.size} onClick={() => setSelected(new Set())}>{tr("Avmarkera")}</button>
        <button disabled={busy || !selected.size} onClick={startSelected}>{trf("Analysera valda ({0})", selected.size)}</button>
        <span className="sub">{tr("Kontrollera att samma ritning inte väljs i flera revisioner.")}</span>
      </div>}

      <div className="rule" id="ritningar" style={{ scrollMarginTop: 12 }} />
      <h2 style={{ margin: "6px 0" }}>{tr("Ritningar")}</h2>
      <div className="list">
        {project.drawings.map((d: any, i: number) => (
          <Tilted as="article" deg={2.4} lift={6} className="item" key={d.id}>
            <div className="no"><input type="checkbox" aria-label={`${tr("Välj ritning")}: ${d.filename}`}
              checked={selected.has(d.id)} disabled={busy || !canStart(d)} onChange={e => {
                const next = new Set(selected); if (e.target.checked) next.add(d.id); else next.delete(d.id); setSelected(next);
              }} /> {String(i + 1).padStart(2, "0")}</div>
            <div>
              <Link className="ttl" to={`/drawings/${d.id}`}>{d.filename.replace(/\.pdf$/i, "")}</Link>
              <div className="sub">
                {d.n_pages} {d.n_pages === 1 ? tr("sida") : tr("sidor")} · {fileSize(d.size_bytes)}
                {" · "}{tr("läses som")} {tr(disciplines.find((x) => x.id === (d.discipline || project.discipline))?.name || d.discipline || project.discipline)}
                {d.latest_job && <> · {tr("senast")} <Link to={`/jobs/${d.latest_job.id}`}>{DATE.format(new Date(d.latest_job.created_at))}</Link></>}
              </div>
            </div>
            <div className="meta">
              {d.latest_job ? <StatusBadge job={d.latest_job} /> : <span className="badge">{tr("Ej analyserad")}</span>}
              <PriceTag drawingId={d.id} />
              <button className="secondary small" disabled={busy || !canStart(d)} onClick={async () => {
                setErr("");
                try { const j = await api.analyze(d.id); window.location.href = `/jobs/${j.id}`; }
                catch (ex: any) { setErr(ex.message); }
              }}>{tr("Analysera")}</button>
            </div>
          </Tilted>
        ))}
        {project.drawings.length === 0 && <div className="empty">{tr("Inga ritningar ännu — ladda upp den första.")}</div>}
      </div></>}
    </main>
  );
}
