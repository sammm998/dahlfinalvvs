import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { t as tr, trf } from "../i18n";
import { GUIDE, QUICK_TASKS, type GuideTask } from "../guide";

/* Kom igång: allt man kan göra i tjänsten på ett ställe, och den kortaste vägen dit.
 *
 * Överst gör man det vanligaste direkt: välj vad som ska göras, vilket projekt (eller ett nytt) och filen –
 * ritningen laddas upp med rätt disciplin och läsningen startar. Under det står varje funktion med vad den ger,
 * vad den behöver, var den finns och hur den går till, med en knapp som tar en dit. */

export default function StartPage() {
  const nav = useNavigate();
  const [projects, setProjects] = useState<any[]>([]);
  const [disciplines, setDisciplines] = useState<any[]>([]);
  const [task, setTask] = useState<string>(() => new URLSearchParams(window.location.search).get("gora") || "vvs");
  const [projectId, setProjectId] = useState<string>("");
  const [newName, setNewName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<string>("");
  const quickRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.projects().then((p: any[]) => { setProjects(p); if (p.length) setProjectId(p[0].id); else setProjectId("new"); }).catch(() => setProjectId("new"));
    api.disciplines().then(setDisciplines).catch(() => {});
  }, []);

  const current = QUICK_TASKS.find((t) => t.id === task) || QUICK_TASKS[0];
  const discOk = (id: string) => !disciplines.length || disciplines.some((d) => d.id === id && d.status === "active");

  const ensureProject = async (): Promise<string> => {
    if (projectId && projectId !== "new") return projectId;
    const name = newName.trim() || (file ? file.name.replace(/\.[^.]+$/, "") : tr("Nytt projekt"));
    const disc = current.action.kind === "quick" ? current.action.discipline : "vvs";
    const p = await api.createProject(name, "", "AB04", discOk(disc) ? disc : "vvs");
    return p.id;
  };

  const run = async () => {
    if (!file || current.action.kind !== "quick") return;
    setErr("");
    try {
      setBusy(tr("Skapar projektet…"));
      const pid = await ensureProject();
      setBusy(trf("Laddar upp {0}…", file.name));
      const d = await api.upload(pid, file, current.action.discipline);
      const drawingId = d.id || d.drawing?.id;
      if (current.action.then === "radiators") { nav(`/drawings/${drawingId}#radiatorer`); return; }
      setBusy(tr("Startar läsningen…"));
      const j = await api.analyze(drawingId);
      nav(`/jobs/${j.id}`);
    } catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  };

  const go = (t: GuideTask) => {
    const a = t.action;
    if (a.kind === "link") { nav(a.to); return; }
    if (a.kind === "quick") { setTask(t.id); quickRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); return; }
    const pid = projectId && projectId !== "new" ? projectId : projects[0]?.id;
    if (!pid) { setErr(tr("Skapa ett projekt först – välj Nytt projekt ovan och ladda upp en ritning, eller gå till Projekt.")); quickRef.current?.scrollIntoView({ behavior: "smooth" }); return; }
    nav(a.kind === "project-analysis" ? `/projects/${pid}/analys` : `/projects/${pid}#${a.anchor}`);
  };

  return (
    <main>
      <h1>{tr("Kom igång")}</h1>
      <p className="lead" style={{ maxWidth: 820 }}>{tr("Allt du kan göra i Dahl, var det finns och hur det går till. Börja direkt här, eller välj en funktion nedan.")}</p>

      <div className="card" ref={quickRef} style={{ marginTop: 14, padding: 16, maxWidth: 980 }}>
        <h2 style={{ marginTop: 0 }}>{tr("Läs en ritning nu")}</h2>
        <div className="row" style={{ gap: 14, flexWrap: "wrap", alignItems: "flex-end" }}>
          <label className="small"><b>1.</b> {tr("Vad vill du göra?")}<br />
            <select value={task} onChange={(e) => setTask(e.target.value)} style={{ minWidth: 260 }}>
              {QUICK_TASKS.map((t) => <option key={t.id} value={t.id} disabled={t.action.kind === "quick" && !discOk(t.action.discipline)}>{tr(t.title)}</option>)}
            </select></label>
          <label className="small"><b>2.</b> {tr("Projekt")}<br />
            <select value={projectId} onChange={(e) => setProjectId(e.target.value)} style={{ minWidth: 220 }}>
              <option value="new">{tr("+ Nytt projekt")}</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select></label>
          {projectId === "new" && <label className="small">{tr("Projektets namn")}<br />
            <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder={tr("t.ex. Kv Najaden 1")} /></label>}
          <label className="small"><b>3.</b> {tr("Ritning (PDF eller bild)")}<br />
            <input type="file" accept="application/pdf,.pdf,image/png,image/jpeg,image/tiff,.png,.jpg,.jpeg,.tif,.tiff" onChange={(e) => setFile(e.target.files?.[0] || null)} /></label>
          <button disabled={!file || !!busy} onClick={run}>{busy || (current.action.kind === "quick" && current.action.then === "radiators" ? tr("Ladda upp och visa radiatorerna") : tr("Ladda upp och läs"))}</button>
        </div>
        <p className="muted small" style={{ marginBottom: 0, marginTop: 10 }}>{tr(current.what)}</p>
        {err && <p className="error small">{err}</p>}
      </div>

      {GUIDE.map((g) => (
        <section key={g.id} style={{ marginTop: 26 }}>
          <h2 style={{ marginBottom: 2 }}>{tr(g.title)}</h2>
          <p className="muted small" style={{ marginTop: 0 }}>{tr(g.lede)}</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(290px, 1fr))", gap: 12 }}>
            {g.tasks.map((t) => {
              const off = t.action.kind === "quick" && !discOk(t.action.discipline);
              return (
                <article key={t.id} className="card" style={{ padding: 14, display: "flex", flexDirection: "column", gap: 6, opacity: off ? 0.6 : 1 }}>
                  <b>{tr(t.title)}{t.admin && <span className="badge small" style={{ marginLeft: 6 }}>{tr("admin")}</span>}</b>
                  <span className="small">{tr(t.what)}</span>
                  <span className="small muted"><b>{tr("Du behöver")}:</b> {tr(t.need)}</span>
                  <span className="small muted"><b>{tr("Finns under")}:</b> {tr(t.where)}</span>
                  {open === t.id && <ol className="small" style={{ margin: "4px 0 0", paddingLeft: 18 }}>{t.steps.map((s) => <li key={s}>{tr(s)}</li>)}</ol>}
                  <div className="row" style={{ gap: 6, marginTop: "auto" }}>
                    <button className="small" disabled={off} onClick={() => go(t)}>{t.action.kind === "quick" ? tr("Börja") : tr("Öppna")}</button>
                    <button className="ghost small" onClick={() => setOpen(open === t.id ? "" : t.id)}>{open === t.id ? tr("Dölj stegen") : tr("Så går det till")}</button>
                  </div>
                </article>);
            })}
          </div>
        </section>
      ))}
      <p className="muted small" style={{ marginTop: 26 }}>{tr("Mer om hur läsningen fungerar")}: <Link to="/dokumentation">{tr("Dokumentation")}</Link> · <Link to="/hur-det-funkar">{tr("Hur det funkar")}</Link></p>
    </main>
  );
}
