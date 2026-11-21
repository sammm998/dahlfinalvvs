import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { t as tr, trf } from "../i18n";

/* SmartHangers-uppsättningar i andras projekt där du har en roll: montören, lagret och produktionen hittar sina
 * här (eller via QR-koden på etiketten). Vad du får göra står i rollerna. */
const ROLE_NAMES: Record<string, string> = { projektadmin: "Projektadministratör", granskare: "Granskare", kalkyl: "Sälj/kalkyl",
  produktion: "Produktion", lager: "Lager/pack", montor: "Montör" };

export default function SharedHangerSets() {
  const [sets, setSets] = useState<any[]>([]);
  useEffect(() => { api.sharedHangerSets().then(setSets).catch(() => setSets([])); }, []);
  if (!sets.length) return null;
  const dl = async (id: string, fmt: string) => {
    const b: Blob = await (api as any).fetchBlob(`/api/hanger-sets/${id}/export.${fmt}`);
    const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = `smarthangers.${fmt}`; a.click();
  };
  return (
    <section className="card" style={{ marginTop: 24 }}>
      <h2 style={{ margin: 0 }}>{tr("SmartHangers – delade med mig")}</h2>
      {sets.map((s) => (
        <div key={s.id} className="row small" style={{ gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 8 }}>
          <b>{s.project_name} · {s.name}</b><span className="muted">{tr("revision")} {s.revision} · {trf("{0} hängare", s.n)}</span>
          {s.my_roles.map((r: string) => <span key={r} className="badge small">{tr(ROLE_NAMES[r] || r)}</span>)}
          {s.first && <Link className="chip" to={`/montage/${s.id}/${s.first}`}>{tr("Montageguide")}</Link>}
          {s.first && <Link className="chip" to={`/montage/${s.id}/${s.first}?läge=produktion`}>{tr("Produktionsvy")}</Link>}
          <button className="secondary small" onClick={() => dl(s.id, "xlsx")}>{tr("Material, kapplan, packlista (Excel)")}</button>
          <button className="secondary small" onClick={() => dl(s.id, "pdf")}>{tr("Etiketter med QR (PDF)")}</button>
        </div>))}
    </section>
  );
}
