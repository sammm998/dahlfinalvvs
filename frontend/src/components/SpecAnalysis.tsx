import { useEffect, useState } from "react";
import { api } from "../api";
import { t as tr, trf } from "../i18n";

/* Det i beskrivningen som inte är mängder: projekt- och tekniska förutsättningar, gränsdragningslistan (levereras,
 * monteras, ansluts av vem), optioner och vilken entreprenadform handlingarna nämner. Här väljs också vad som gäller
 * när beskrivning och ritning säger olika mängder: flagga (ingen avgör), beskrivningen eller ritningen. */

export default function SpecAnalysis({ specId, project, onPriority }: { specId: string; project: any; onPriority: () => void }) {
  const [a, setA] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => { setA(null); api.techSpecAnalysis(specId).then(setA).catch((e: any) => setErr(e.message)); }, [specId]);
  if (err) return <p className="error small">{err}</p>;
  if (!a) return null;
  const c = a.contract || {};
  const setPrio = async (p: string) => { await api.setQuantityPriority(project.id, p); setA({ ...a, quantity_priority: p }); onPriority(); };
  const download = async () => {
    const b: Blob = await (api as any).fetchBlob(`/api/tech-specs/${specId}/boundaries.xlsx`);
    const x = document.createElement("a"); x.href = URL.createObjectURL(b); x.download = "gransdragning-forutsattningar.xlsx"; x.click();
  };
  const reqs = a.conditions.filter((x: any) => x.requirement);
  return (
    <div style={{ margin: "10px 0" }}>
      <div className="row small" style={{ gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        {c.guess && <span className={`badge ${c.differs ? "warn" : "ok"}`}>
          {c.differs ? trf("Handlingarna nämner {0}, projektet är {1} – kontrollera", c.guess, c.project) : trf("Handlingarna nämner {0}", c.guess)}</span>}
        <label>{tr("När beskrivning och ritning säger olika mängder")}:{" "}
          <select value={a.quantity_priority} onChange={(e) => setPrio(e.target.value)}>
            <option value="flagga">{tr("flagga – ingen avgör")}</option>
            <option value="beskrivning">{tr("beskrivningen går före")}</option>
            <option value="ritning">{tr("ritningen går före")}</option>
          </select></label>
        <button className="secondary small" onClick={download}>{tr("Gränsdragning och förutsättningar (Excel)")}</button>
      </div>
      <details className="settings" style={{ marginTop: 8 }}>
        <summary>{trf("Projekt- och tekniska förutsättningar ({0}, varav {1} krav)", a.conditions.length, reqs.length)}</summary>
        <table className="qty small" style={{ tableLayout: "fixed", width: "100%" }}><colgroup><col style={{ width: 130 }} /><col /><col style={{ width: 110 }} /></colgroup><tbody>
          {a.conditions.map((x: any, i: number) => <tr key={i}><td>{tr(x.kind)}{x.requirement && <span className="badge small warn" style={{ marginLeft: 4 }}>{tr("krav")}</span>}</td>
            <td style={{ whiteSpace: "normal" }}>{x.text}</td><td className="muted">{x.ama} s. {x.page}</td></tr>)}
        </tbody></table>
      </details>
      <details className="settings" style={{ marginTop: 6 }}>
        <summary>{trf("Gränsdragningslista ({0})", a.boundaries.length)}</summary>
        <table className="qty small">
          <thead><tr><th>{tr("Objekt / aktivitet")}</th><th>{tr("Levereras av")}</th><th>{tr("Monteras av")}</th><th>{tr("Ansluts av")}</th><th>{tr("Källa")}</th></tr></thead>
          <tbody>{a.boundaries.map((r: any, i: number) => <tr key={i} title={r.sources?.[0]?.text} style={{ whiteSpace: "normal" }}>
            <td>{r.object}{r.ingår_ej && <span className="badge small warn" style={{ marginLeft: 4 }}>{tr("ingår ej")}</span>}</td>
            <td>{r.levereras_av ? tr(r.levereras_av) : "–"}</td><td>{r.monteras_av ? tr(r.monteras_av) : "–"}</td><td>{r.ansluts_av ? tr(r.ansluts_av) : "–"}</td>
            <td className="muted">{r.sources?.[0]?.ama} s. {r.sources?.[0]?.page}</td></tr>)}</tbody>
        </table>
      </details>
      {a.options.length > 0 && <details className="settings" style={{ marginTop: 6 }}>
        <summary>{trf("Optioner ({0}) – särredovisas i offerten", a.options.length)}</summary>
        <ul className="small">{a.options.map((o: any, i: number) => <li key={i}>{o.text} <span className="muted">({o.ama} s. {o.page})</span></li>)}</ul>
      </details>}
    </div>
  );
}
