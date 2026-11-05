import { useEffect, useState } from "react";
import { t as tr, trf, locale } from "../i18n";
import { Link } from "react-router-dom";
import { api } from "../api";

/* Credits: den gemensamma budgeten.
 *
 * Alla konton delar en budget på 10 000 kr för det som faktiskt kostar pengar - anropen till språkmodellerna
 * (agenten, andra blicken, den tekniska beskrivningen). Ingen köper credits och ingen läsning dras från ett eget
 * saldo. Sidan visar samma sak för alla som loggar in: taket, vad som gått åt, vad som är kvar, till vad, av vem
 * och de senaste raderna. */

const DATE = new Intl.DateTimeFormat(locale(), { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
const SOURCE: Record<string, string> = {
  agent: "Agenten", vision: "Andra blick", analysis: "Analys", tb: "Teknisk beskrivning", tech_spec: "Teknisk beskrivning",
  academy: "Lär dig VVS", cad: "CAD", desk: "Mängda",
};

export const fmtCredits = (v: number) => v.toLocaleString(locale(), { maximumFractionDigits: 2 });
const kr = (v: number) => `${v.toLocaleString(locale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 })} kr`;

function Breakdown({ title, rows, label, total }: { title: string; rows: any[]; label: (k: string) => string; total: number }) {
  return (
    <section style={{ flex: "1 1 280px", minWidth: 0 }}>
      <h2>{title}</h2>
      <div className="tablewrap">
        <table className="qty">
          <thead><tr><th>{tr("Vad")}</th><th>{tr("Anrop")}</th><th>{tr("Använt")}</th><th>{tr("Andel")}</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key || "-"}>
                <td>{label(r.key)}</td>
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

export default function CreditsPage() {
  const [me, setMe] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.credits().then(setMe).catch((e) => setErr(e.message)); }, []);
  if (!me) return <main>{err ? <p className="error">{err}</p> : tr("Laddar…")}</main>;
  const b = me.budget;
  const used = b.limit_kr > 0 ? Math.min(100, (b.spent_kr / b.limit_kr) * 100) : 100;
  const bar = b.exhausted ? "var(--red, #c0392b)" : used > 80 ? "#d68a00" : "var(--accent, #004976)";
  return (
    <main>
      <p className="crumb"><Link to="/projekt">{tr("Projekt")}</Link> {tr("/ Credits")}</p>
      <div className="head">
        <div>
          <h1>Credits</h1>
          <p className="lead">
            {tr("Alla konton delar en gemensam budget. Det som kostar pengar är anropen till AI-modellerna - agenten, andra blicken och läsningen av tekniska beskrivningar - och de dras härifrån. Analys av ritningar utan AI kostar ingenting.")}
          </p>
        </div>
        <div className="row">
          <div className="stat">
            <div className="k">{tr("Kvar")}</div>
            <div className="v">{kr(b.remaining_kr)}</div>
          </div>
          <div className="stat">
            <div className="k">{tr("Använt")}</div>
            <div className="v">{kr(b.spent_kr)}</div>
          </div>
          <div className="stat">
            <div className="k">{tr("Budget")}</div>
            <div className="v">{kr(b.limit_kr)}</div>
          </div>
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
        {b.exhausted && (
          <p className="error">{tr("Budgeten är slut. AI-funktionerna är pausade tills administratören höjer eller nollställer budgeten.")}</p>
        )}
      </div>

      <div className="rule" />
      <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
        <Breakdown title={tr("Till vad")} rows={b.by_source} total={b.spent_kr} label={(k) => tr(SOURCE[k] || k || "Övrigt")} />
        <Breakdown title={tr("Av vem")} rows={b.by_user} total={b.spent_kr}
          label={(k) => (k ? (k === me.me ? trf("{0} (du)", k) : k) : tr("Tjänsten själv"))} />
      </div>
      <div style={{ marginTop: 28 }}>
        <Breakdown title={tr("Per modell")} rows={b.by_model} total={b.spent_kr} label={(k) => k || "–"} />
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
                <td>{tr(SOURCE[r.source] || r.source || "Övrigt")}</td>
                <td className="muted">{r.model}</td>
                <td>{r.tokens.toLocaleString(locale())}</td>
                <td>{kr(r.kr)}</td>
              </tr>
            ))}
            {b.recent.length === 0 && <tr><td colSpan={6} className="empty">{tr("Ingenting har använts än.")}</td></tr>}
          </tbody>
        </table>
      </div>
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
