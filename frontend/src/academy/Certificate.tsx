import { useEffect, useState } from "react";
import { t as tr } from "../i18n";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ac } from "./api";
import "./academy.css";

/* Certifikatet, och verifieringen av det.
 *
 * Certifikatet är ett dokument och inte en skärmbild: samma sida bär både vyn och utskriften, och
 * utskriftsreglerna gör den till ett A4-ark utan gränssnitt runt om. "Ladda ned PDF" är webbläsarens egen
 * utskrift till PDF - det är det enda sättet som ger ett ark som ser likadant ut som det på skärmen utan att
 * dra in ett helt PDF-bibliotek i paketet, och det säger sidan rakt ut i stället för att låtsas.
 *
 * Verifieringen är öppen och kräver ingen inloggning. Ett certifikat som bara innehavaren kan visa bevisar
 * ingenting. Det som visas är det som behövs för att lita på det - namn, utbildning, datum, id - och
 * ingenting mer.
 */

function Sheet({ c }: { c: { holder: string; title: string; code: string; issued: string; score?: number } }) {
  return (
    <article className="cert" aria-label={`Certifikat ${c.code}`}>
      <div className="cert-in">
        <header className="cert-top">
          <span className="cert-mark">
            <svg width="17" height="17" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M2 13.5h5.2V6h5.6v7.5H18" stroke="currentColor" strokeWidth="1.7" strokeLinecap="square" />
              <circle cx="7.2" cy="13.5" r="1.7" fill="currentColor" />
            </svg>
            Dahl
          </span>
          <span className="cert-label">{tr("Certificate of Competence")}</span>
        </header>

        <p className="cert-pre">{tr("Härmed intygas att")}</p>
        <p className="cert-name">{c.holder}</p>
        <p className="cert-for">{tr("har genomfört och godkänts i")}</p>
        <p className="cert-title">
          Dahl Certified<br />
          <i>VVS Kalkyl &amp; Mängdning</i>
        </p>

        <div className="cert-grid">
          <div><span className="cert-label">Utbildning</span><b>{c.title}</b></div>
          {c.score !== undefined && <div><span className="cert-label">Resultat</span><b>{c.score} %</b></div>}
          <div><span className="cert-label">{tr("Utfärdat")}</span><b>{String(c.issued).slice(0, 10)}</b></div>
          <div><span className="cert-label">Certifikat-ID</span><b className="cert-code">{c.code}</b></div>
        </div>

        <footer className="cert-foot">
          <div className="cert-rule" />
          <p className="cert-label">
            Verifiera på {window.location.host}/verifiera med certifikat-ID {c.code} · Dahl VPR System
          </p>
        </footer>
      </div>
    </article>
  );
}

/* ---------------------------------------------------------------- mitt certifikat */

export function CertificatePage() {
  const { code } = useParams();
  const [c, setC] = useState<any>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    ac.certificates()
      .then((d) => {
        const hit = d.certifikat.find((x: any) => x.code === code);
        if (!hit) throw new Error("Certifikatet hör inte till ditt konto");
        setC(hit);
      })
      .catch((e) => setErr(String(e.message || e)));
  }, [code]);

  if (err) return <div className="acx"><p className="acx-err">{err}</p>
    <p><Link className="fc-btn sm" to="/academy">{tr("Tillbaka till Academy")}</Link></p></div>;
  if (!c) return <div className="acx"><p className="acx-load">{tr("Hämtar certifikatet…")}</p></div>;

  return (
    <div className="acx cert-page">
      <header className="acx-top no-print">
        <Link className="acx-brand" to="/academy">Dahl <span>Academy</span></Link>
        <nav className="acx-crumb"><span>Certifikat</span></nav>
        <div className="cert-acts">
          <button className="fc-btn sm" onClick={() => window.print()}>{tr("Skriv ut / spara som PDF")}</button>
          <button className="fc-btn sm" onClick={() => navigator.clipboard?.writeText(c.code)}>{tr("Kopiera ID")}</button>
          <Link className="fc-btn sm" to={`/verifiera?id=${c.code}`}>Verifiera</Link>
        </div>
      </header>
      <Sheet c={c} />
      <p className="cert-note no-print">
        Utskriften blir ett A4-ark utan menyer. Välj <b>{tr("Spara som PDF")}</b> i utskriftsdialogen för en fil.
      </p>
    </div>
  );
}

/* ---------------------------------------------------------------- verifieringen, öppen för alla */

export function VerifyPage() {
  const [sp, setSp] = useSearchParams();
  const [code, setCode] = useState(sp.get("id") || "");
  const [out, setOut] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  const look = async (v: string) => {
    if (!v.trim()) return;
    setBusy(true);
    setOut(null);
    try { setOut(await ac.verify(v.trim())); }
    catch { setOut({ giltigt: false, skal: "Kunde inte nå verifieringen" }); }
    finally { setBusy(false); }
  };

  // körs en gång: en id i adressen ska slås upp direkt, men inte om på varje omritning
  useEffect(() => { if (sp.get("id")) look(sp.get("id")!); }, []);

  return (
    <div className="acx cert-verify">
      <header className="acx-top">
        <Link className="acx-brand" to="/">Dahl</Link>
        <nav className="acx-crumb"><span>Verifiering</span></nav>
      </header>

      <section className="vfy">
        <p className="fc-label">Certifikatkontroll</p>
        <h1 className="fc-display fc-display-md">{tr("Verifiera ett Dahl-certifikat")}</h1>
        <p className="acx-lead">
          Skriv in certifikat-ID:t som står på certifikatet. Kontrollen kräver ingen inloggning.
        </p>
        <form className="vfy-form" onSubmit={(e) => { e.preventDefault(); setSp({ id: code }); look(code); }}>
          <label>
            <span className="fc-label">Certifikat-ID</span>
            <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())}
              placeholder="FC-VVS-XXXXXXXX" spellCheck={false} autoComplete="off" />
          </label>
          <button className="fc-btn solid" disabled={busy || !code.trim()}>{busy ? "Kontrollerar…" : "Verifiera"}</button>
        </form>

        {out && (
          <div className={`vfy-out ${out.giltigt ? "ok" : "no"}`} role="status">
            <p className="vfy-badge">
              <span aria-hidden="true">{out.giltigt ? "✓" : "✕"}</span>
              {out.giltigt ? "Giltigt Dahl-certifikat" : "Inget giltigt certifikat"}
            </p>
            {out.giltigt ? (
              <dl className="vfy-dl">
                <div><dt>Innehavare</dt><dd>{out.holder}</dd></div>
                <div><dt>Utbildning</dt><dd>{out.title}</dd></div>
                <div><dt>{tr("Utfärdat")}</dt><dd>{out.issued}</dd></div>
                <div><dt>Certifikat-ID</dt><dd className="cert-code">{out.code}</dd></div>
                {out.expires && <div><dt>{tr("Giltigt till")}</dt><dd>{out.expires}</dd></div>}
              </dl>
            ) : (
              <p>{out.skal}</p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
