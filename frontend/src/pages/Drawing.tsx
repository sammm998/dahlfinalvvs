
import { useEffect, useState } from "react";
import { t as tr, locale } from "../i18n";
import { Link, useParams } from "react-router-dom";
import { api, fileSize } from "../api";
import { StatusBadge, stageText } from "../components/Status";
import Tilted from "../components/Tilted";
import { PriceTag } from "./Credits";

/** Whether anything on the page is still moving. A list of finished readings does not change on its own. */
function anythingRunning(jobs: any[]): boolean {
  return (jobs ?? []).some((j) => j && j.status !== "COMPLETED" && j.status !== "FAILED");
}

export default function DrawingPage() {
  const { id } = useParams();
  const [d, setD] = useState<any>(null);

  const [err, setErr] = useState("");
  const load = () => api.drawing(id!).then(setD).catch((e) => setErr(e.message));
  // Poll while a reading is running; stop when none is. A page of finished readings asked the server twenty
  // times a minute for an answer that could not change.
  const live = anythingRunning(d?.jobs);
  useEffect(() => {
    load();
    if (!live) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [id, live]);
  if (!d) return <main>{err ? <p className="error">{err}</p> : "Laddar…"}</main>;
  return (
    <main>
      <p className="crumb"><Link to={`/projects/${d.project_id}`}>Projekt</Link> {tr("/ Ritning")}</p>
      <div className="head">
        <div>
          <h1>{d.filename.replace(/\.pdf$/i, "")}</h1>
          <p className="lead">
            {d.n_pages} {d.n_pages === 1 ? "sida" : "sidor"} · {fileSize(d.size_bytes)} · SHA-256 {d.sha256.slice(0, 12)}…
          </p>
        </div>
        <div className="row">
          <button className="secondary" onClick={async () => { const b = await api.fetchBlob(api.fileUrl(d.id)); window.open(URL.createObjectURL(b)); }}>{tr("Öppna PDF")}</button>
          <PriceTag drawingId={d.id} />
          <button onClick={async () => {
            setErr("");
            try { await api.analyze(d.id, undefined, 0, "combined", "auto"); load(); }
            catch (ex: any) { setErr(ex.message); }
          }}>{tr("Ny analys")}</button>
        </div>
      </div>

      {err && <p className="error" style={{ marginTop: 18 }}>{err}</p>}
      <div className="rule" />
      <div className="list">
        {d.jobs.map((j: any, i: number) => (
          <Tilted as="article" deg={2.4} lift={6} className="item" key={j.id}>
            <div className="no">{String(i + 1).padStart(2, "0")}</div>
            <div>
              <Link className="ttl" to={`/jobs/${j.id}`} style={{ fontSize: 19 }}>
                {new Date(j.created_at).toLocaleString(locale())}
              </Link>
              <div className="sub">{stageText(j.stage) || j.stage}</div>
              {j.status !== "COMPLETED" && j.status !== "FAILED" && (
                <div className="progress" style={{ maxWidth: 280, marginTop: 10 }}>
                  <div style={{ width: `${Math.round(j.progress * 100)}%` }} />
                </div>
              )}
              {j.error && <div className="error" style={{ marginTop: 6 }}>{j.error.split("\n")[0]}</div>}
            </div>
            <div className="meta">
              <StatusBadge job={j} />
              <Link className="when" to={`/jobs/${j.id}`}>{j.status === "COMPLETED" ? "Visa resultat →" : "Följ →"}</Link>
              {j.status === "COMPLETED" && <Link className="when" to={`/jobs/${j.id}/kalkyl`}>{tr("Kalkylera →")}</Link>}
            </div>
          </Tilted>
        ))}
        {d.jobs.length === 0 && <div className="empty">{tr("Ingen analys körd ännu.")}</div>}
      </div>
    </main>
  );
}
