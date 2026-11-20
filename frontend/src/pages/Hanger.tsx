import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { t as tr, trf } from "../i18n";
import { statusColor } from "../components/PrefabPanel";

/* En hängare i taget, för produktionen och för montaget. QR-koden på etiketten öppnar den här sidan.
 *
 * Produktion (?läge=produktion): den måttsatta vyn (takjärnet med hål och klammerlägen, pendlarnas längder),
 * materialet, egenkontrollen, "Klar + etikett" och nästa. Paus, materialbrist, avvikelse och omarbete loggas.
 * Montage: våning, zon, referensmått, höjd och rören; markera monterad, ej möjlig, avvikelse eller omarbete med
 * kommentar och foto. Allt loggas med datum, tid och användare. */

const CHECKS = ["Kaplängder enligt mått", "Hålbild kontrollerad", "Klammer rätt dimension", "Muttrar åtdragna", "Etikett fäst"];

function Drawing({ h }: { h: any }) {
  const tj = h.takjarn;
  const rod = h.rods?.[0]?.length_mm || 0;
  const W = 520, H = 230;
  if (!tj) {
    return (
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: 560, background: "#fff", border: "1px solid #ddd" }}>
        <line x1={0} y1={14} x2={W} y2={14} stroke="#555" strokeWidth={3} />
        <line x1={W / 2} y1={14} x2={W / 2} y2={150} stroke="#333" strokeWidth={4} />
        <circle cx={W / 2} cy={170} r={20} fill="none" stroke="#2f6fdf" strokeWidth={4} />
        <text x={W / 2 + 10} y={85} fontSize={14}>{h.rods?.[0]?.size} · {rod} mm</text>
        <text x={W / 2 + 28} y={175} fontSize={13}>{h.pipes?.[0]?.material} {h.pipes?.[0]?.dn || h.pipes?.[0]?.od}</text>
      </svg>);
  }
  const L = tj.length_mm, sx = (W - 60) / L, x0 = 30;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: 560, background: "#fff", border: "1px solid #ddd" }}>
      <line x1={0} y1={14} x2={W} y2={14} stroke="#555" strokeWidth={3} />
      {tj.rod_holes_mm.map((x: number, i: number) => <g key={i}>
        <line x1={x0 + x * sx} y1={14} x2={x0 + x * sx} y2={130} stroke="#333" strokeWidth={4} />
        <text x={x0 + x * sx + (i ? -8 : 8)} y={70} fontSize={12} textAnchor={i ? "end" : "start"}>{h.rods?.[i]?.size} · {h.rods?.[i]?.length_mm} mm</text></g>)}
      <rect x={x0} y={130} width={L * sx} height={16} fill="#c9ced6" stroke="#555" />
      {tj.clamps.map((c: any, i: number) => <g key={i}>
        <circle cx={x0 + c.at_mm * sx} cy={130 - Math.max(8, c.od * 0.25) - (c.rise_mm ? 8 : 0)} r={Math.max(8, c.od * 0.25)} fill="none" stroke="#2f6fdf" strokeWidth={3} />
        <text x={x0 + c.at_mm * sx - 12} y={172} fontSize={12}>{c.at_mm}</text>
        <text x={x0 + c.at_mm * sx - 12} y={186} fontSize={10} fill="#666">Ø{Math.round(c.od)}{c.rise_mm ? ` +${c.rise_mm}` : ""}</text></g>)}
      <line x1={x0} y1={205} x2={x0 + L * sx} y2={205} stroke="#333" />
      <text x={x0 + L * sx / 2 - 30} y={222} fontSize={13}>{tj.profile.split(" (")[0]} {L} mm</text>
      <text x={x0} y={196} fontSize={10} fill="#666">{trf("hål {0} / {1} mm", tj.rod_holes_mm[0], tj.rod_holes_mm[1])}</text>
    </svg>);
}

export default function HangerPage() {
  const { setId = "", hid = "" } = useParams();
  const [q] = useSearchParams();
  const prod = q.get("läge") === "produktion";
  const nav = useNavigate();
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  const [comment, setComment] = useState("");
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const photo = useRef<HTMLInputElement>(null);

  const load = () => api.hanger(setId, hid).then(setD).catch((e: any) => setErr(e.message));
  useEffect(() => { setD(null); setChecks({}); setComment(""); load(); }, [setId, hid]);
  const go = (id: string | null) => id && nav(`/montage/${setId}/${encodeURIComponent(id)}${prod ? "?läge=produktion" : ""}`);
  const act = async (body: any, thenNext = false) => {
    setBusy(true); setErr("");
    try {
      const r = await api.patchHanger(setId, hid, { ...body, comment: comment || undefined });
      setD(r); setComment("");
      if (thenNext) go(r.next);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const label = async () => {
    const b: Blob = await (api as any).fetchBlob(`/api/hanger-sets/${setId}/export.pdf?ids=${encodeURIComponent(hid)}`);
    window.open(URL.createObjectURL(b), "_blank");
  };
  const upload = async () => {
    const f = photo.current?.files?.[0]; if (!f) return;
    setBusy(true);
    try { await api.hangerPhoto(setId, hid, f, comment); setComment(""); await load(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  if (err && !d) return <main className="container"><p className="error">{err}</p></main>;
  if (!d) return <main className="container"><p className="muted">{tr("Laddar…")}</p></main>;
  const h = d.hanger;
  const allChecked = CHECKS.every((c) => checks[c]);
  return (
    <main className="container" style={{ maxWidth: 720 }}>
      <div className="row" style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <Link to={`/projects/${d.set.project_id}`} className="small">← {tr("projektet")}</Link>
        <span style={{ flex: 1 }} />
        <input placeholder={tr("Sök ID, t.ex. P2-014")} value={search} onChange={(e) => setSearch(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && search && go(search)} style={{ width: 150 }} />
        <Link className="button secondary small" to={`/montage/${setId}/${encodeURIComponent(hid)}${prod ? "" : "?läge=produktion"}`}>{prod ? tr("Montageläge") : tr("Produktionsläge")}</Link>
      </div>
      <div className="card" style={{ marginTop: 10, borderLeft: `8px solid ${statusColor(h.status, h.deviation)}` }}>
        <div className="row" style={{ alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
          <h1 style={{ margin: 0, fontSize: 34 }}>{h.id}</h1>
          <span className="badge">{tr(h.status)}{h.deviation ? ` · ${tr(h.deviation)}` : ""}</span>
          <span className="muted small">{trf("{0} av {1}", d.index, d.of)} · {d.set.name} · {tr("revision")} {h.revision}</span>
        </div>
        <div style={{ fontSize: 17, marginTop: 6 }}>
          <b>{h.storey}</b> · {h.zone} · {tr(h.kind)}{h.pack ? ` · ${trf("kolli {0}, nr {1}", h.pack.kolli, h.pack.seq)}` : ""}
        </div>
        <div className="small" style={{ marginTop: 4 }}>
          {tr("Läge i modellen")}: X {h.position.x} · Y {h.position.y} · {h.reference?.text}<br />
          {tr("Tak")} {h.ceiling_z ?? "?"} mm ({tr(h.height_source)}) · {tr("pendel")} {h.rods?.map((r: any) => `${r.size} ${r.length_mm ?? "?"} mm`).join(" + ")}
          {h.takjarn && <> · {tr("takjärn")} {h.takjarn.length_mm} mm</>}<br />
          {tr("Rör")}: {h.pipes.map((p: any) => `${p.system || ""} ${p.material} ${p.dn || p.od} (${tr("centrum")} z ${p.centre_z})`).join(", ")}
        </div>
        {h.flags?.map((f: string) => <div key={f} className="badge warn small" style={{ marginTop: 4, marginRight: 4 }}>{tr(f)}</div>)}
      </div>

      <div style={{ marginTop: 10 }}><Drawing h={h} /></div>

      {prod && (
        <div className="card" style={{ marginTop: 10 }}>
          <b>{tr("Material")}</b>
          {h.bom.map((b: any, i: number) => (
            <div key={i} className="row small" style={{ gap: 8, padding: "4px 0", borderBottom: "1px solid var(--line, #eee)" }}>
              <span style={{ flex: 1, minWidth: 0 }}>{b.text}</span><b>{b.qty} {tr("st")}</b>{b.length_mm ? <b>{b.length_mm} mm</b> : null}
            </div>))}
          <b style={{ display: "block", marginTop: 8 }}>{tr("Egenkontroll")}</b>
          {CHECKS.map((c) => <label key={c} className="check" style={{ display: "block" }}><input type="checkbox" checked={!!checks[c]} onChange={(e) => setChecks({ ...checks, [c]: e.target.checked })} />{tr(c)}</label>)}
        </div>)}

      <textarea placeholder={tr("Kommentar (följer med nästa markering)")} value={comment} onChange={(e) => setComment(e.target.value)} style={{ width: "100%", marginTop: 10, minHeight: 50 }} />
      {err && <p className="error">{err}</p>}
      <div className="row" style={{ gap: 8, flexWrap: "wrap", marginTop: 6 }}>
        {prod ? <>
          <button disabled={busy || !allChecked} onClick={async () => { await act({ status: "producerad", comment: `${tr("egenkontroll")}: ${CHECKS.length}/${CHECKS.length}` }); await label(); }}>{tr("Klar + etikett")}</button>
          {["paus", "materialbrist", "avvikelse", "omarbete"].map((x) => <button key={x} className="secondary" disabled={busy} onClick={() => act({ deviation: x })}>{tr(x)}</button>)}
        </> : <>
          <button disabled={busy} onClick={() => act({ status: "monterad" }, true)} style={{ background: "#1f9d55" }}>{tr("Monterad → nästa")}</button>
          {["ej möjlig", "avvikelse", "omarbete"].map((x) => <button key={x} className="secondary" disabled={busy} onClick={() => act({ deviation: x })}>{tr(x)}</button>)}
          <input type="file" accept="image/*" capture="environment" id="h-photo" className="file" ref={photo} onChange={upload} />
          <label className="pick" htmlFor="h-photo">{tr("Foto")}</label>
        </>}
      </div>
      <div className="row" style={{ gap: 8, marginTop: 12 }}>
        <button className="secondary" disabled={!d.prev} onClick={() => go(d.prev)}>← {tr("Föregående")}</button>
        <button className="secondary" disabled={!d.next} onClick={() => go(d.next)}>{tr("Nästa")} →</button>
      </div>
      {h.history?.length > 0 && (
        <details style={{ marginTop: 12 }} className="small"><summary>{trf("Historik ({0})", h.history.length)}</summary>
          {h.history.slice().reverse().map((e: any, i: number) => <div key={i} className="muted">{String(e.at).replace("T", " ").slice(0, 16)} · {e.user} · {tr(e.action || "")}{e.to && typeof e.to === "string" ? ` → ${tr(e.to)}` : ""}{e.deviation ? ` · ${tr(e.deviation)}` : ""}{e.comment ? ` · ${e.comment}` : ""}</div>)}
          {h.photos?.length > 0 && <div>{trf("{0} foton", h.photos.length)}</div>}
        </details>)}
    </main>
  );
}
