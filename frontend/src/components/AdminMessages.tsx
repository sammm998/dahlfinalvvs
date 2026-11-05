import { useEffect, useState } from "react";
import { t as tr, locale } from "../i18n";
import { api } from "../api";

/* Meddelanden: det som skrivits på kontaktsidan, och tjänstens egna meddelanden till administratörerna
 * (till exempel att AI-budgeten nått 80 %, 95 % eller är slut). */

const DATE = new Intl.DateTimeFormat(locale(), { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

export function Messages() {
  const [rows, setRows] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const load = () => api.adm("contact").then((r) => setRows(r.rows)).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  const set = async (id: string, status: string) => { try { await api.admPut(`contact/${id}`, { status }); load(); } catch (e: any) { setErr(e.message); } };
  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>{tr("Meddelanden från kontaktsidan")}</h3>
      {err && <p className="error">{err}</p>}
      <div className="tablewrap">
        <table className="qty">
          <thead><tr><th>{tr("När")}</th><th>Vem</th><th>{tr("Ämne")}</th><th>Meddelande</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.id}>
                <td>{DATE.format(new Date(m.created_at))}</td>
                <td>{m.name}<br /><a href={`mailto:${m.email}`}>{m.email}</a>{m.company && <><br /><span className="muted">{m.company}</span></>}</td>
                <td>{m.subject}</td>
                <td style={{ whiteSpace: "pre-wrap", maxWidth: 420 }}>{m.body}</td>
                <td><span className={`badge ${m.status === "ny" ? "warn" : m.status === "besvarad" ? "ok" : ""}`}>{m.status}</span></td>
                <td>
                  {m.status !== "besvarad" && <button className="ghost small" onClick={() => set(m.id, "besvarad")}>Besvarad</button>}
                  {m.status !== "stangd" && <button className="ghost small" onClick={() => set(m.id, "stangd")}>{tr("Stäng")}</button>}
                </td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={6} className="empty">{tr("Inga meddelanden än.")}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
