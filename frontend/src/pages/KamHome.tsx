import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { t as tr, trf } from "../i18n";

/* KAM: förhandlingarna. Den årliga prisförhandlingen ersätter arbetsboken med Justeringsvy och Varukorgsanalys;
 * den enkla prisjusteringen (en kunds statistik mot ny prislista) finns kvar under /kam/enkel. */
const STATUS: Record<string, string> = { utkast: "Utkast", attest: "Väntar på attest", godkand: "Attesterad", avslagen: "Avslagen", registrerad: "Registrerad" };

export default function KamHomePage() {
  const nav = useNavigate();
  const [list, setList] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const [f, setF] = useState({ customer: "", kundnr: "", name: "", valid_from: "" });
  useEffect(() => { api.negList().then((r: any) => setList(r.negotiations)).catch((e: any) => setErr(e.message)); }, []);
  const create = async () => {
    try { const n = await api.negCreate(f); nav(`/kam/${n.id}`); } catch (e: any) { setErr(e.message); }
  };
  return (
    <main>
      <h1>{tr("KAM – prisförhandling")}</h1>
      <p className="lead" style={{ maxWidth: 900 }}>{tr("Den årliga prisförhandlingen med en KAM-kund: läs in underlaget, se kundens hela korg per produktområde och kalkylgrupp, justera rabatterna med direkt effekt på pris och marginal, låt verktyget peka ut grupper där ni tappar försäljning eller marginal, och presentera effekten för kunden.")}</p>
      <p className="warn small">{tr("Simulerad: ingen skarp koppling till M3 ännu – underlaget läses ur filer.")}</p>
      {err && <p className="error small">{err}</p>}
      <div className="row" style={{ gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
        <section className="card" style={{ flex: "0 0 320px", padding: 14 }}>
          <h2 style={{ marginTop: 0 }}>{tr("Ny förhandling")}</h2>
          {(["customer", "kundnr", "name", "valid_from"] as const).map((k) => (
            <label key={k} className="small" style={{ display: "block", marginBottom: 6 }}>{tr({ customer: "Kund", kundnr: "Kundnummer", name: "Namn (valfritt)", valid_from: "Gäller från" }[k])}<br />
              <input value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} style={{ width: "100%" }} placeholder={k === "valid_from" ? "2027-02-01" : ""} /></label>))}
          <button className="small" disabled={!f.customer && !f.name} onClick={create}>{tr("Skapa och läs in underlag")}</button>
          <p className="small muted" style={{ marginTop: 14 }}>{tr("Bara en kunds statistik mot ny prislista?")} <Link to="/kam/enkel">{tr("Enkel prisjustering")}</Link></p>
        </section>
        <section className="card" style={{ flex: "1 1 520px", padding: 14 }}>
          <h2 style={{ marginTop: 0 }}>{tr("Förhandlingar")}</h2>
          {list.length === 0 && <p className="muted small">{tr("Inga förhandlingar ännu.")}</p>}
          <table className="qty small"><tbody>{list.map((n) => (
            <tr key={n.id}><td><Link to={`/kam/${n.id}`}><b>{n.name}</b></Link><div className="muted">{n.customer} {n.kundnr ? `· ${n.kundnr}` : ""}</div></td>
              <td><span className="badge small">{tr(STATUS[n.status] || n.status)}</span></td>
              <td className="muted">{trf("{0} justerade grupper", n.n_adjusted)}</td><td className="muted">{(n.updated_at || "").slice(0, 10)}</td></tr>))}</tbody></table>
        </section>
      </div>
    </main>
  );
}
