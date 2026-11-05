import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { t as tr, trf, locale } from "../i18n";

/* Teknisk beskrivning: allt material en beskrivning föreskriver, utan ritningar.
 *
 * Beskrivningen laddas upp här och läses till poster (vvs_engine/tb). Varje post visar vad beskrivningen skriver -
 * kod, antal, fabrikat, typ, RSK - och var den finns att köpa: hittad (RSK-nummer eller artikelnummer finns),
 * möjlig träff (fabrikat och modell finns i en benämning) eller saknas. För det som saknas skrivs ett mejlutkast.
 *
 * Posterna grupperas per kategori - AMA-rubriken, så att golvbrunnar av plast och av rostfritt står ihop - och
 * filtreras på kategori, fabrikat, slag och status. */

type Hit = { source: string; ref: string; name: string; why: string; page: number | null; price: number | null; unit: string };
type Item = {
  id: string; kind: string; code: string; name: string; quantity: number | null; unit: string; quantity_text: string;
  total_quantity: number | null; manufacturer: string; type: string; rsk: string[]; art_nr: string[]; or_equal: boolean;
  spec: Record<string, string>; text: string; category: string; subcategory: string; ama_code: string; page: number;
  parent: string; supplied_by: string; inferred: string;
  match: { status: "hittad" | "möjlig" | "saknas" | "allmänt" | "annan"; hits: Hit[]; in_catalog: boolean; note: string;
           rsk?: { value: string | null; kind: "förslag" | "storlek" | "ai"; name: string; sure?: boolean; before?: string | null;
                   variants?: { rsk: string; name: string; size: string | null }[] } | null;
           ai?: { ref: string; name: string; sure: boolean } };
};
type Draft = { maker: string; subject: string; text: string; html: string; mailto: string; eml: string; n: number;
               rows: { pos: string; code: string; name: string; qty: string; maker: string; spec: string; numbers: string }[] };

const KIND: Record<string, string> = {
  post: "Post", tillbehor: "Tillbehör", omnamnd: "Omnämnd produkt", krav: "Allmänt material", arbete: "Arbete",
};
const STATUS: Record<string, { label: string; cls: string }> = {
  hittad: { label: "Hittad", cls: "ok" }, "möjlig": { label: "Möjlig träff", cls: "warn" }, saknas: { label: "Saknas", cls: "bad" },
  "allmänt": { label: "Enligt ritning", cls: "" }, annan: { label: "Levereras av annan", cls: "" },
};

const qty = (it: Item) => {
  const q = it.total_quantity ?? it.quantity;
  if (q == null) return it.quantity_text || "–";
  return `${q.toLocaleString(locale(), { maximumFractionDigits: 2 })} ${it.unit || "st"}`;
};

export default function TechSpecPanel({ project }: { project: any }) {
  const [specs, setSpecs] = useState<any[]>([]);
  const [active, setActive] = useState<string>("");
  const [data, setData] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [maker, setMaker] = useState("");
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const [hideOthers, setHideOthers] = useState(false);
  const [open, setOpen] = useState<string>("");
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [mail, setMail] = useState<{ drafts: Draft[]; n: number; ids?: string[] } | null>(null);
  const [tab, setTab] = useState(0);
  const [copied, setCopied] = useState("");
  const [to, setTo] = useState("");
  const [catalog, setCatalog] = useState<any>(null);
  const [catUrl, setCatUrl] = useState("");
  const [catBusy, setCatBusy] = useState(false);
  const [catMsg, setCatMsg] = useState("");
  const [aiOn, setAiOn] = useState<boolean>(() => { try { return localStorage.getItem("vvs.tb.ai") !== "0"; } catch { return true; } });
  const [aiBusy, setAiBusy] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const catFile = useRef<HTMLInputElement>(null);

  const loadList = async (pick?: string) => {
    const rows = await api.techSpecs(project.id);
    setSpecs(rows);
    const id = pick || active || rows[0]?.id || "";
    setActive(id);
  };
  useEffect(() => { loadList().catch((e) => setErr(e.message)); api.catalog().then(setCatalog).catch(() => { /* bara materialboken */ }); }, [project.id]);
  useEffect(() => {
    if (!active) { setData(null); return; }
    setBusy(true);
    api.techSpec(active).then((d) => { setData(d); setChosen(new Set()); }).catch((e) => setErr(e.message)).finally(() => setBusy(false));
  }, [active]);

  const upload = async () => {
    const f = file.current?.files?.[0];
    if (!f) return;
    setBusy(true); setErr("");
    try {
      const s = await api.uploadTechSpec(project.id, f); await loadList(s.id); if (file.current) file.current.value = "";
      if (aiOn && s.status === "COMPLETED" && !s.ai) await runAi(s.id);
    }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const runAi = async (id = active) => {
    setAiBusy(true); setErr("");
    try { await api.techSpecAi(id); setData(await api.techSpec(id)); }
    catch (e: any) { setErr(e.message); } finally { setAiBusy(false); }
  };
  const decide = async (key: string, accept: boolean) => {
    try { await api.techSpecMissed(active, key, accept); setData(await api.techSpec(active)); }
    catch (e: any) { setErr(e.message); }
  };
  const toggleAi = (v: boolean) => { setAiOn(v); try { localStorage.setItem("vvs.tb.ai", v ? "1" : "0"); } catch { /* bara den här gången */ } };

  const items: Item[] = data?.items ?? [];
  const shown = useMemo(() => {
    const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    return items.filter((it) =>
      (!cat || it.category === cat) && (!maker || it.manufacturer === maker) && (!kind || it.kind === kind)
      && (!status || it.match.status === status) && (!hideOthers || !it.supplied_by || it.supplied_by.startsWith("Ingår"))
      && words.every((w) => `${it.code} ${it.name} ${it.manufacturer} ${it.type} ${it.rsk.join(" ")} ${it.text}`.toLowerCase().includes(w)));
  }, [items, q, cat, maker, kind, status, hideOthers]);
  const groups = useMemo(() => {
    const m = new Map<string, Item[]>();
    for (const it of shown) { const k = it.category || tr("Övrigt"); m.set(k, [...(m.get(k) ?? []), it]); }
    return [...m.entries()];
  }, [shown]);
  const counts = data?.facets?.status?.reduce((o: any, s: any) => ({ ...o, [s.value]: s.n }), {}) ?? {};

  const draft = async (ids?: string[], keepTab = false) => {
    setErr("");
    try { const m = await api.techSpecMail(active, { ids, to }); setMail({ ...m, ids }); if (!keepTab) setTab(0); setCopied(""); }
    catch (e: any) { setErr(e.message); }
  };
  const d: Draft | undefined = mail?.drafts?.[Math.min(tab, (mail?.drafts?.length ?? 1) - 1)];
  const saveEml = (x: Draft) => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([x.eml], { type: "message/rfc822" }));
    a.download = `${x.subject.replace(/[\\/:*?"<>|]+/g, "").slice(0, 80)}.eml`; a.click();
  };
  const copyTable = async (x: Draft) => {
    try {
      const W = window as any;
      if (W.ClipboardItem && navigator.clipboard?.write) {
        await navigator.clipboard.write([new W.ClipboardItem({ "text/html": new Blob([x.html], { type: "text/html" }),
          "text/plain": new Blob([x.text], { type: "text/plain" }) })]);
      } else await navigator.clipboard?.writeText(x.text);
      setCopied(x.maker);
    } catch { setCopied(""); }
  };
  const csv = async () => {
    const b: Blob = await (api as any).fetchBlob(`/api/tech-specs/${active}/items.csv`);
    const a = document.createElement("a"); a.href = URL.createObjectURL(b);
    a.download = `material-${(data?.filename || "beskrivning").replace(/\.pdf$/i, "")}.csv`; a.click();
  };
  const importCatalog = async (how: "url" | "file") => {
    setCatBusy(true); setCatMsg("");
    try {
      const r = how === "url" ? await api.catalogImport(catUrl || catalog?.catalog_url)
        : await api.catalogUpload(catFile.current!.files![0]);
      setCatMsg(trf("Katalogen är inläst: {0} sidor, {1} rader.", r.pages, r.lines));
      setCatalog(await api.catalog());
      if (active) setData(await api.techSpec(active));
    } catch (e: any) { setCatMsg(e.message); } finally { setCatBusy(false); }
  };

  return (
    <section className="card tspec" style={{ marginTop: 18 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2 style={{ margin: 0 }}>{tr("Teknisk beskrivning")}</h2>
          <p className="muted small" style={{ maxWidth: 640 }}>
            {tr("Beskrivningen läses utan ritningar: varje post med kod, antal, fabrikat, typ, RSK och specifikation, tillbehören under \"Härtill\", produkter som kravtexten nämner, allmänt material och arbete. Allt söks i materialboken och Dahls katalog.")}
          </p>
        </div>
        <div className="row">
          <input type="file" accept="application/pdf,.pdf" ref={file} id="tspec-file" className="file" onChange={() => setErr("")} />
          <label className="pick" htmlFor="tspec-file">{tr("Välj beskrivning (PDF)…")}</label>
          <label className="check small" title={tr("Letar efter det läsaren kan ha missat och väljer rätt artikel i katalogen där det finns flera. Bara text och bara det osäkra skickas, så det kostar några öre per beskrivning ur den gemensamma budgeten.")}>
            <input type="checkbox" checked={aiOn} onChange={(e) => toggleAi(e.target.checked)} />{tr("AI-kontroll")}
          </label>
          <button onClick={upload} disabled={busy || aiBusy}>{aiBusy ? tr("AI-kontroll…") : busy ? tr("Läser…") : tr("Läs beskrivningen")}</button>
        </div>
      </div>

      <p className="muted small tspec-src">
        {tr("Söks i")}: <b>{catalog?.materialbok?.label ?? tr("Materialboken")}</b>
        {catalog?.materialbok?.n ? ` (${catalog.materialbok.n.toLocaleString(locale())} ${tr("artiklar")})` : ""}
        {" · "}
        {catalog?.katalog
          ? <><b>{tr("Dahls produktkatalog")}</b> ({catalog.katalog.pages ? `${catalog.katalog.pages} ${tr("sidor")}` : `${(catalog.katalog.n ?? 0).toLocaleString(locale())} ${tr("artiklar")}`})</>
          : <span>{tr("Dahls produktkatalog är inte inläst än")}</span>}
      </p>
      <details className="settings tspec-cat">
        <summary>{tr("Läs in Dahls katalog")}</summary>
        <div className="row" style={{ marginTop: 8 }}>
          <input className="grow" value={catUrl} placeholder={catalog?.catalog_url ?? "https://katalog.dahl.se/…"} onChange={(e) => setCatUrl(e.target.value)} />
          <button className="secondary small" disabled={catBusy} onClick={() => importCatalog("url")}>{catBusy ? tr("Läser in…") : tr("Hämta från länken")}</button>
          <input type="file" accept="application/pdf,.pdf" ref={catFile} id="cat-file" className="file" onChange={() => importCatalog("file")} />
          <label className="pick small" htmlFor="cat-file">{tr("…eller ladda upp katalogen som PDF")}</label>
        </div>
        <p className="muted small">{tr("Katalogen gäller för hela tjänsten och för beskrivningar som redan är lästa. Bara en administratör kan läsa in den.")}</p>
        {catMsg && <p className="small">{catMsg}</p>}
      </details>

      {err && <p className="error">{err}</p>}

      {specs.length > 1 && (
        <div className="chips" style={{ marginTop: 10 }}>
          {specs.map((s) => (
            <button key={s.id} className={`chip${s.id === active ? " on" : ""}`} onClick={() => setActive(s.id)}>
              {s.filename} <i>{s.stats?.items ?? 0}</i>
            </button>
          ))}
        </div>
      )}
      {!specs.length && <p className="empty">{tr("Ingen beskrivning uppladdad än. Välj en PDF ovan.")}</p>}

      {data && (
        <>
          <div className="row tspec-head" style={{ marginTop: 14, gap: 10, flexWrap: "wrap" }}>
            <b>{data.title || data.filename}</b>
            <span className="badge">{trf("{0} sidor", data.n_pages)}</span>
            <span className="badge">{trf("{0} poster", items.length)}</span>
            <span className="badge ok">{trf("{0} hittade", counts["hittad"] ?? 0)}</span>
            <span className="badge warn">{trf("{0} möjliga", counts["möjlig"] ?? 0)}</span>
            <span className="badge bad">{trf("{0} saknas", counts["saknas"] ?? 0)}</span>
            {data.status === "FAILED" && <span className="error">{data.error}</span>}
            <span style={{ flex: 1 }} />
            <button className="secondary small" onClick={csv}>{tr("Exportera CSV")}</button>
            <button className="secondary small" onClick={async () => { if (confirm(tr("Ta bort beskrivningen?"))) { await api.deleteTechSpec(active); setActive(""); await loadList(""); } }}>{tr("Ta bort")}</button>
          </div>

          <div className="tspec-ai" style={{ marginTop: 12, padding: "10px 12px", border: "1px solid var(--line, #e3e8ec)", borderRadius: 8 }}>
            <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "center" }}>
              <b>{tr("AI-kontroll")}</b>
              {data.ai ? (
                <span className="muted small">
                  {trf("{0} poster fick ett val i katalogen · {1} möjligen missade · {2} godkända", data.ai.picked, data.ai.missed.length, data.ai.accepted)}
                  {" · "}
                  {data.ai.calls === 0
                    ? tr("ur cachen, utan kostnad")
                    : trf("kostade {0} kr ({1} anrop)", Number(data.ai.kr).toLocaleString(locale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 }), data.ai.calls)}
                </span>
              ) : <span className="muted small">{tr("Inte körd. Letar efter det som kan ha missats och väljer artikel där katalogen har flera – för några öre.")}</span>}
              <span style={{ flex: 1 }} />
              <button className="secondary small" disabled={aiBusy} onClick={() => runAi()}>
                {aiBusy ? tr("Kör…") : data.ai ? tr("Kör igen") : tr("Kör AI-kontroll")}
              </button>
            </div>
            {data.ai?.missed?.length > 0 && (
              <div className="tablewrap" style={{ marginTop: 8 }}>
                <table className="qty">
                  <thead><tr><th>{tr("Möjligen missat")}</th><th>{tr("Fabrikat")}</th><th>{tr("Typ")}</th><th>{tr("Sida")}</th><th>{tr("Står i beskrivningen")}</th><th></th></tr></thead>
                  <tbody>
                    {data.ai.missed.map((m: any) => (
                      <tr key={m.key}>
                        <td>{m.name}</td><td>{m.manufacturer_text || "–"}</td><td>{m.type || "–"}{m.rsk ? ` · RSK ${m.rsk}` : ""}</td>
                        <td>{m.page}</td><td className="muted small">{m.line_text}</td>
                        <td style={{ whiteSpace: "nowrap" }}>
                          <button className="small" onClick={() => decide(m.key, true)}>{tr("Lägg till")}</button>{" "}
                          <button className="ghost small" onClick={() => decide(m.key, false)}>{tr("Avfärda")}</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="muted small">{tr("Förslag från AI:n, kontrollerade mot raden de står på. Det du lägger till blir en post utan antal – antalet tas ur ritning eller beskrivning.")}</p>
              </div>
            )}
          </div>

          <div className="matbar" style={{ marginTop: 12 }}>
            <input className="grow" placeholder={tr("Sök kod, benämning, fabrikat, RSK…")} value={q} onChange={(e) => setQ(e.target.value)} />
            <select value={cat} onChange={(e) => setCat(e.target.value)} aria-label={tr("Kategori")}>
              <option value="">{tr("alla kategorier")}</option>
              {data.facets.categories.map((c: any) => <option key={c.value} value={c.value}>{c.value || tr("Övrigt")} ({c.n})</option>)}
            </select>
            <select value={maker} onChange={(e) => setMaker(e.target.value)} aria-label={tr("Fabrikat")}>
              <option value="">{tr("alla fabrikat")}</option>
              {data.facets.manufacturers.filter((m: any) => m.value).map((m: any) => <option key={m.value} value={m.value}>{m.value} ({m.n})</option>)}
            </select>
            <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label={tr("Slag")}>
              <option value="">{tr("alla slag")}</option>
              {data.facets.kinds.map((k: any) => <option key={k.value} value={k.value}>{tr(KIND[k.value] ?? k.value)} ({k.n})</option>)}
            </select>
            <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label={tr("Status")}>
              <option value="">{tr("alla statusar")}</option>
              {data.facets.status.map((s: any) => <option key={s.value} value={s.value}>{tr(STATUS[s.value].label)} ({s.n})</option>)}
            </select>
            <label className="check"><input type="checkbox" checked={hideOthers} onChange={(e) => setHideOthers(e.target.checked)} />{tr("Dölj det andra levererar")}</label>
          </div>

          <div className="row" style={{ margin: "10px 0", gap: 8 }}>
            <button className="small" onClick={() => draft()} disabled={!(counts["saknas"] > 0)}>{trf("Mejlutkast för det som saknas ({0})", counts["saknas"] ?? 0)}</button>
            <button className="secondary small" onClick={() => draft([...chosen])} disabled={!chosen.size}>{trf("Mejlutkast för valda ({0})", chosen.size)}</button>
            <span className="muted small">{trf("Visar {0} av {1}", shown.length, items.length)}</span>
          </div>

          {groups.map(([g, rows]) => (
            <div key={g} className="tspec-group">
              <h3>{g} <span className="muted small">· {rows.length}</span></h3>
              <div className="tablewrap">
                <table className="qty tspec-table">
                  <thead><tr>
                    <th></th><th>{tr("Kod")}</th><th>{tr("Benämning")}</th><th className="num">{tr("Antal")}</th>
                    <th>{tr("Fabrikat")}</th><th>{tr("Typ")}</th><th>{tr("RSK")}</th><th>{tr("Status")}</th><th>{tr("Träff")}</th><th>{tr("Sida")}</th>
                  </tr></thead>
                  <tbody>
                    {rows.map((it) => {
                      const st = STATUS[it.match.status];
                      const h = it.match.hits[0];
                      return [
                        <tr key={it.id} className={`tspec-row k-${it.kind}${open === it.id ? " open" : ""}`} onClick={() => setOpen(open === it.id ? "" : it.id)}>
                          <td onClick={(e) => e.stopPropagation()}>
                            <input type="checkbox" aria-label={trf("Välj {0}", it.code || it.name)} checked={chosen.has(it.id)}
                              onChange={(e) => { const n = new Set(chosen); if (e.target.checked) n.add(it.id); else n.delete(it.id); setChosen(n); }} />
                          </td>
                          <td className="lf-mono">{it.code || "–"}</td>
                          <td>
                            {it.kind === "tillbehor" && <span className="muted">↳ </span>}{it.name}
                            {it.kind !== "post" && <span className="badge small" style={{ marginLeft: 6 }}>{tr(KIND[it.kind])}</span>}
                            {it.supplied_by && <span className="badge small warn" style={{ marginLeft: 6 }}>{it.supplied_by.startsWith("Ingår") ? it.supplied_by : trf("Levereras av {0}", it.supplied_by)}</span>}
                          </td>
                          <td className="num">{qty(it)}</td>
                          <td>{it.manufacturer || "–"}</td>
                          <td>{it.type || "–"}{it.or_equal && <span className="muted small"> {tr("el. likv.")}</span>}</td>
                          <td className="lf-mono tspec-rsk">
                            {it.rsk.length ? it.rsk.join(", ")
                              : it.match.rsk?.kind === "ai" ? <span title={it.match.rsk.name}><i>{it.match.rsk.value}</i> <span className={`badge small${it.match.rsk.sure ? "" : " warn"}`}>{it.match.rsk.sure ? tr("AI-val") : tr("AI-val, kontrollera")}</span></span>
                              : it.match.rsk?.value ? <span title={it.match.rsk.name}><i>{it.match.rsk.value}</i> <span className="badge small">{tr("förslag")}</span></span>
                              : it.match.rsk?.kind === "storlek" ? <span className="badge small warn">{trf("välj storlek ({0})", it.match.rsk.variants?.length ?? 0)}</span>
                              : "–"}
                          </td>
                          <td><span className={`badge ${st.cls}`}>{tr(st.label)}</span></td>
                          <td className="tspec-hit">{h ? <>{h.ref} · {h.name}{h.source === "katalog" && <span className="muted small"> ({tr("katalogen")})</span>}</> : <span className="muted small">{it.match.note ? tr(it.match.note.startsWith("Levereras av") ? "Ingår ej i VS" : it.match.note) : "–"}</span>}</td>
                          <td className="muted">{it.page}</td>
                        </tr>,
                        open === it.id && (
                          <tr key={it.id + "-d"} className="tspec-detail"><td colSpan={10}>
                            <p className="small" style={{ whiteSpace: "normal" }}>{it.text || "–"}</p>
                            {Object.keys(it.spec).length > 0 && <p className="small"><b>{tr("Specifikation")}:</b> {Object.entries(it.spec).map(([k, v]) => `${k} ${v}`).join(" · ")}</p>}
                            <p className="small muted">{it.ama_code} {it.subcategory} · {tr("sida")} {it.page}{it.inferred && <> · {it.inferred}</>}</p>
                            {it.match.rsk?.kind === "storlek" && (
                              <div className="small tspec-sizes"><b>{tr("Beskrivningen anger ingen storlek – välj:")}</b>
                                <ul>{it.match.rsk.variants?.map((v) => <li key={v.rsk}><b className="lf-mono">{v.rsk}</b> {v.name}</li>)}</ul>
                              </div>
                            )}
                            {it.match.hits.length > 0 && (
                              <ul className="small tspec-hits">
                                {it.match.hits.map((x, i) => <li key={i}><b>{x.ref}</b> {x.name} <span className="muted">– {x.source === "katalog" ? tr("Dahls katalog") : tr("materialboken")}, {x.why}{x.price != null && <>, {x.price.toLocaleString(locale(), { maximumFractionDigits: 2 })} kr/{x.unit || "st"}</>}</span></li>)}
                              </ul>
                            )}
                            {(it.match.status === "saknas" || it.match.status === "möjlig") && <button className="secondary small" onClick={() => draft([it.id])}>{tr("Mejlutkast för den här")}</button>}
                          </td></tr>
                        ),
                      ];
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </>
      )}

      {mail && d && (
        <div className="tspec-mailwrap" role="dialog" aria-label={tr("Prisförfrågningar")} onClick={() => setMail(null)}>
          <div className="card tspec-mail" onClick={(e) => e.stopPropagation()}>
            <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ margin: 0 }}>{trf("Prisförfrågningar · {0} artiklar till {1} fabrikat", mail.n, mail.drafts.length)}</h3>
              <button className="ghost small" onClick={() => setMail(null)}>{tr("Stäng")}</button>
            </div>
            <p className="muted small" style={{ margin: "6px 0 10px" }}>{tr("En förfrågan per fabrikat. Öppna den i e-posten, ladda ner den som utkast eller kopiera tabellen.")}</p>
            <div className="chips tspec-makers">
              {mail.drafts.map((x, i) => (
                <button key={x.maker} className={`chip${i === tab ? " on" : ""}`} onClick={() => setTab(i)}>{x.maker} <i>{x.n}</i></button>
              ))}
            </div>
            <div className="tspec-mailhead">
              <label>{tr("Till")}<input value={to} placeholder={tr("leverantörens e-post")} onChange={(e) => setTo(e.target.value)}
                onBlur={() => draft(mail.ids, true)} /></label>
              <label>{tr("Ämne")}<input value={d.subject} readOnly /></label>
            </div>
            <div className="tspec-preview" dangerouslySetInnerHTML={{ __html: d.html }} />
            <div className="row" style={{ gap: 8, marginTop: 12, flexWrap: "wrap" }}>
              <a href={d.mailto}><button>{tr("Öppna i e-posten")}</button></a>
              <button className="secondary" onClick={() => saveEml(d)}>{tr("Ladda ner som e-postutkast")}</button>
              <button className="secondary" onClick={() => copyTable(d)}>{copied === d.maker ? tr("Kopierad ✓") : tr("Kopiera med tabell")}</button>
            </div>
            <p className="muted small" style={{ marginBottom: 0 }}>{tr("Utkastet (.eml) öppnas i Outlook eller Apple Mail med tabellen på plats. Länken till e-posten bär bara texten.")}</p>
          </div>
        </div>
      )}
    </section>
  );
}
