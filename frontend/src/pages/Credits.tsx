import { useEffect, useState } from "react";
import { t as tr, trf, locale } from "../i18n";
import { Link } from "react-router-dom";
import { api } from "../api";

/* Credits: den gemensamma budgeten.
 *
 * Alla konton delar en budget på 10 000 kr för det som faktiskt kostar pengar - anropen till AI-modellerna
 * (agenten, röstsamtalet, andra blicken och AI-tilldelningen i analysen). Ingen köper credits och ingen läsning
 * dras från ett eget saldo. Sidan visar samma sak för alla som loggar in: taket, vad som gått åt, vad som är kvar,
 * till vad, av vem och de senaste raderna - med filter för period, person och del, och allt som CSV. */

const DATE = new Intl.DateTimeFormat(locale(), { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

export const fmtCredits = (v: number) => v.toLocaleString(locale(), { maximumFractionDigits: 2 });
const kr = (v: number) => `${v.toLocaleString(locale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 })} kr`;

function Breakdown({ title, rows, label, total }: { title: string; rows: any[]; label: (r: any) => string; total: number }) {
  return (
    <section style={{ flex: "1 1 280px", minWidth: 0 }}>
      <h2>{title}</h2>
      <div className="tablewrap">
        <table className="qty">
          <thead><tr><th>{tr("Vad")}</th><th>{tr("Anrop")}</th><th>{tr("Använt")}</th><th>{tr("Andel")}</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key || "-"}>
                <td>{label(r)}</td>
                <td>{r.requests.toLocaleString(locale())}</td>
                <td>{kr(r.kr)}</td>
                <td>{total > 0 ? `${Math.round((r.kr / total) * 100)} %` : "–"}</td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={4} className="empty">{tr("Ingenting har använts än.")}</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const NO_FILTER = { since: "", until: "", who: "", source: "" };

export default function CreditsPage() {
  const [me, setMe] = useState<any>(null);
  const [err, setErr] = useState("");
  const [f, setF] = useState<Record<string, string>>(NO_FILTER);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.credits(f).then((r) => { setMe(r); setErr(""); }).catch((e) => setErr(e.message)); }, [f]);
  const csv = async () => {
    setBusy(true);
    try {
      const blob = await api.fetchBlob(api.creditsCsvPath(f));
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob); a.download = "ai-budget.csv"; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  if (!me) return <main>{err ? <p className="error">{err}</p> : tr("Laddar…")}</main>;
  const b = me.budget;
  const used = Math.min(100, b.used_pct ?? 0);
  const bar = b.exhausted ? "var(--red, #c0392b)" : b.warning >= 95 ? "#d35400" : b.warning >= 80 ? "#d68a00" : "var(--accent, #004976)";
  const filtered = Object.values(f).some(Boolean);
  const person = (k: string) => (k ? (k === me.me ? trf("{0} (du)", k) : k) : tr("Tjänsten själv"));
  return (
    <main>
      <p className="crumb"><Link to="/projekt">{tr("Projekt")}</Link> {tr("/ Credits")}</p>
      <div className="head">
        <div>
          <h1>Credits</h1>
          <p className="lead">
            {tr("Alla konton delar en gemensam budget. Det som kostar pengar är anropen till AI-modellerna – agenten, röstsamtalet, andra blicken och AI-tilldelningen i analysen – och de dras härifrån. Allt annat ingår.")}
          </p>
        </div>
        <div className="row">
          <div className="stat"><div className="k">{tr("Kvar")}</div><div className="v">{kr(b.remaining_kr)}</div></div>
          <div className="stat"><div className="k">{tr("Använt")}</div><div className="v">{kr(b.spent_kr)}</div></div>
          <div className="stat"><div className="k">{tr("Budget")}</div><div className="v">{kr(b.limit_kr)}</div></div>
        </div>
      </div>

      <div style={{ marginTop: 18 }}>
        <div style={{ height: 12, borderRadius: 6, background: "var(--line, #e3e8ec)", overflow: "hidden" }}
          role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(used)}>
          <div style={{ width: `${used}%`, height: "100%", background: bar }} />
        </div>
        <p className="muted small" style={{ marginTop: 6 }}>
          {trf("{0} % av budgeten använd · {1} anrop", used.toLocaleString(locale(), { maximumFractionDigits: 1 }), b.requests.toLocaleString(locale()))}
          {b.since ? ` · ${trf("sedan {0}", DATE.format(new Date(b.since)))}` : ""}
        </p>
      </div>

      <div className="rule" />
      <div className="row" style={{ gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label className="small">{tr("Från")}<br />
          <input type="date" value={f.since} onChange={(e) => setF({ ...f, since: e.target.value })} /></label>
        <label className="small">{tr("Till och med")}<br />
          <input type="date" value={f.until} onChange={(e) => setF({ ...f, until: e.target.value })} /></label>
        <label className="small">{tr("Person")}<br />
          <select value={f.who} onChange={(e) => setF({ ...f, who: e.target.value })}>
            <option value="">{tr("Alla")}</option>
            {b.people.map((p: string) => <option key={p || "-"} value={p || "-"}>{person(p)}</option>)}
          </select></label>
        <label className="small">{tr("Till vad")}<br />
          <select value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })}>
            <option value="">{tr("Allt")}</option>
            {b.sources.map((s: any) => <option key={s.key} value={s.key}>{tr(s.label)}</option>)}
          </select></label>
        {filtered && <button className="ghost small" onClick={() => setF(NO_FILTER)}>{tr("Rensa filter")}</button>}
        <button className="secondary small" disabled={busy} onClick={csv}>{busy ? tr("Hämtar…") : tr("Ladda ner CSV")}</button>
      </div>
      {filtered && (
        <p className="muted small" style={{ marginTop: 8 }}>
          {trf("Urvalet: {0} anrop för {1}.", b.filtered.requests.toLocaleString(locale()), kr(b.filtered.kr))}
        </p>
      )}
      {err && <p className="error">{err}</p>}

      <div style={{ display: "flex", gap: 24, flexWrap: "wrap", marginTop: 12 }}>
        <Breakdown title={tr("Till vad")} rows={b.by_source} total={b.filtered.kr} label={(r) => tr(r.label)} />
        <Breakdown title={tr("Av vem")} rows={b.by_user} total={b.filtered.kr} label={(r) => person(r.key)} />
      </div>
      <div style={{ marginTop: 28 }}>
        <Breakdown title={tr("Per modell")} rows={b.by_model} total={b.filtered.kr} label={(r) => r.key || "–"} />
      </div>

      <div className="rule" />
      <h2>{tr("Senaste användningen")}</h2>
      <div className="tablewrap">
        <table className="qty">
          <thead><tr><th>{tr("När")}</th><th>{tr("Vem")}</th><th>{tr("Till vad")}</th><th>{tr("Modell")}</th><th>{tr("Tokens")}</th><th>{tr("Kostnad")}</th></tr></thead>
          <tbody>
            {b.recent.map((r: any, i: number) => (
              <tr key={i}>
                <td>{DATE.format(new Date(r.at))}</td>
                <td>{r.user || tr("Tjänsten själv")}</td>
                <td>{tr(r.label)}</td>
                <td className="muted">{r.model}</td>
                <td>{r.tokens.toLocaleString(locale())}</td>
                <td>{kr(r.kr)}</td>
              </tr>
            ))}
            {b.recent.length === 0 && <tr><td colSpan={6} className="empty">{tr("Ingenting har använts än.")}</td></tr>}
          </tbody>
        </table>
      </div>
      <p className="muted small">{tr("Visar de senaste 60 raderna i urvalet. Hela urvalet finns i CSV-filen.")}</p>
    </main>
  );
}

/** Priset för ett blad innan läsningen. Läsningar dras inte längre från något saldo, så det finns inget att visa;
 *  komponenten finns kvar för sidorna som använder den. */
export function PriceTag({ drawingId, onQuote }: { drawingId: string; onQuote?: (q: any) => void }) {
  useEffect(() => {
    let on = true;
    api.price(drawingId).then((r) => { if (on) onQuote?.(r); }).catch(() => { /* inget pris att visa */ });
    return () => { on = false; };
  }, [drawingId]);
  return null;
}
