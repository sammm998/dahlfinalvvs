import { useEffect, useMemo, useRef, useState } from "react";
import { t as tr, locale } from "../i18n";
import { api } from "../api";

/* Materialboken.
 *
 * En mängd är meter och antal; en kalkyl är meter gånger pris. Det här är den andra halvan: artiklarna med
 * benämning, enhet, pris, vikt och klimatavtryck, sökbara på det sätt en rörläggare faktiskt söker - några ord i
 * valfri ordning, inte leverantörens stavning.
 *
 * Boken skickas aldrig hel till webbläsaren. Sökningen sker i tjänsten och bara det som frågades efter kommer
 * tillbaka; femtiofemtusen rader är för många för en sida och för få för en databas.
 */

type Row = {
  a: string; n: string; e: string; p: number | null; r: number | null;
  w: number | null; co2: number | null; gr: string; y: string; k: string; pre: string;
  dahl?: string; rsk?: string; page?: number | null; p_src?: string | null;   // Dahls katalog
};

const kr = (v: number | null) =>
  v == null ? "–" : v.toLocaleString(locale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const num = (v: number | null, d = 2) =>
  v == null ? "–" : v.toLocaleString(locale(), { maximumFractionDigits: d });

export default function MaterialPage() {
  const [q, setQ] = useState("");
  const [unit, setUnit] = useState("");
  const [group, setGroup] = useState("");
  const [net, setNet] = useState(true);
  const [data, setData] = useState<any>(null);
  const [page, setPage] = useState(0);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const timer = useRef<any>(null);
  const LIMIT = 60;

  // typing should not fire a request per keystroke; the book is searched once the hand stops
  useEffect(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setBusy(true);
      const qs = new URLSearchParams({ q, unit, group, limit: String(LIMIT), offset: String(page * LIMIT) });
      api.materials(qs.toString()).then(setData).catch((e) => setErr(e.message)).finally(() => setBusy(false));
    }, 220);
    return () => clearTimeout(timer.current);
  }, [q, unit, group, page]);

  useEffect(() => { setPage(0); }, [q, unit, group]);

  const rows: Row[] = data?.rows ?? [];
  const dahl = data?.book?.kind === "dahl";
  const pages = Math.ceil((data?.total ?? 0) / LIMIT);
  const price = (r: Row) => (r.p == null ? null : net && r.r ? r.p * (1 - r.r) : r.p);
  const sum = useMemo(() => rows.reduce((t, r) => t + (price(r) ?? 0), 0), [rows, net]);

  return (
    <main>
      <p className="crumb">Material</p>
      <div className="head">
        <div>
          <h1>Material</h1>
          <p className="lead">
            {data ? <>{data.book.n.toLocaleString(locale())} {tr("artiklar ur")} {data.book.source ?? tr("materialboken")}</>
              : "Laddar…"} · sök på några ord i valfri ordning, till exempel <code>{tr("110 pp mark")}</code>.
          </p>
        </div>
      </div>

      {err && <p className="error">{err}</p>}

      <div className="card" style={{ marginTop: 14 }}>
        <div className="matbar">
          <input className="grow" value={q} placeholder={tr("Sök benämning eller artikelnummer…")}
            onChange={(e) => setQ(e.target.value)} />
          <select value={unit} onChange={(e) => setUnit(e.target.value)}>
            <option value="">{tr("alla enheter")}</option>
            {(data?.units ?? []).map((u: string) => <option key={u} value={u}>{u}</option>)}
          </select>
          <select value={group} onChange={(e) => setGroup(e.target.value)}>
            <option value="">{tr("alla grupper")}</option>
            {(data?.groups ?? []).map((g: string) => <option key={g} value={g}>{g}</option>)}
          </select>
          <label className="check">
            <input type="checkbox" checked={net} onChange={(e) => setNet(e.target.checked)} />
            Pris efter rabatt
          </label>
        </div>
        <p className="muted" style={{ marginBottom: 0 }}>
          {busy ? "Söker…" : data ? <>{data.total.toLocaleString(locale())} träffar{data.total > LIMIT && <> · visar {page * LIMIT + 1}–{Math.min((page + 1) * LIMIT, data.total)}</>}</> : ""}
        </p>
      </div>

      <div className="card" style={{ marginTop: 14, paddingTop: 6 }}>
        <div className="tablewrap">
          <table className="qty">
            <thead>
              <tr>
                {dahl ? <><th>{tr("Dahl art.nr")}</th><th>{tr("RSK")}</th></> : <th>Artikel</th>}
                <th>{tr("Benämning")}</th><th>Enh</th>
                <th className="num">Pris</th><th className="num">Rabatt</th>
                <th className="num">Vikt</th><th className="num">{tr("kg CO₂e")}</th><th>Grupp</th>
                {dahl && <th className="num">{tr("Sida")}</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.a}-${r.dahl ?? ""}-${r.page ?? ""}`}>
                  {dahl ? <><td className="lf-mono">{r.dahl || "–"}</td><td className="lf-mono">{r.rsk || "–"}</td></>
                    : <td className="lf-mono">{r.a}</td>}
                  <td>{r.n}</td>
                  <td className="muted">{r.e || "–"}</td>
                  <td className="num" title={r.p_src === "materialsortering" ? tr("Priset kommer ur materialboken på samma RSK-nummer; katalogen skriver inget pris.") : undefined}>
                    {kr(price(r))}{r.p_src === "materialsortering" && <sup className="muted"> *</sup>}</td>
                  <td className="num muted">{r.r ? `${Math.round(r.r * 100)} %` : "–"}</td>
                  <td className="num muted">{num(r.w)}</td>
                  <td className="num muted">{num(r.co2)}</td>
                  <td className="muted">{r.gr || "–"}</td>
                  {dahl && <td className="num muted">{r.page ?? "–"}</td>}
                </tr>
              ))}
              {!rows.length && !busy && (
                <tr><td colSpan={dahl ? 10 : 8} className="empty">{tr("Inga artiklar matchar sökningen.")}</td></tr>
              )}
            </tbody>
            {rows.length > 0 && (
              <tfoot>
                <tr>
                  <th colSpan={dahl ? 4 : 3}>{tr("Summa på sidan")}</th>
                  <th className="num">{kr(sum)}</th>
                  <th colSpan={dahl ? 5 : 4}></th>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
        {pages > 1 && (
          <div className="row" style={{ marginTop: 12, alignItems: "center" }}>
            <button className="secondary small" disabled={page === 0 || busy} onClick={() => setPage(page - 1)}>{tr("← Föregående")}</button>
            <span className="muted">sida {page + 1} av {pages}</span>
            <button className="secondary small" disabled={page + 1 >= pages || busy} onClick={() => setPage(page + 1)}>{tr("Nästa →")}</button>
          </div>
        )}
      </div>
    </main>
  );
}
