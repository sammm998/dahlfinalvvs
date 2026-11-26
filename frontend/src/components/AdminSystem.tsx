import { useEffect, useState } from "react";
import { t as tr, locale } from "../i18n";
import { api } from "../api";

const bytes = (v: number | null | undefined) => {
  if (v == null) return "–";
  const u = ["B", "kB", "MB", "GB", "TB"]; let i = 0; let x = v;
  while (x >= 1024 && i < u.length - 1) { x /= 1024; i++; }
  return `${x.toLocaleString(locale(), { maximumFractionDigits: i ? 1 : 0 })} ${u[i]}`;
};

/* Vad som kör och hur det mår: bara fakta som går att kontrollera. En läsning är bara kontrollerbar om man kan
 * säga vilken kod som gjorde den, och en andra läsare bara om man kan säga om den nås. */
export function SystemHealth() {
  const [h, setH] = useState<any>(null);
  const [v, setV] = useState<any>(null);
  const [err, setErr] = useState("");
  const [cleaning, setCleaning] = useState(false);
  const [cleaned, setCleaned] = useState<any>(null);
  const [purgeText, setPurgeText] = useState("");
  const [purged, setPurged] = useState<any>(null);
  const purgeAll = () => {
    if (!window.confirm(tr("Alla ritningar, analyser, SmartHangers-uppsättningar, beskrivningar, listor och offerter tas bort för alla konton. Det går inte att ångra. Fortsätt?"))) return;
    setCleaning(true);
    api.admPost("system/purge-all", { confirm: purgeText })
      .then((r) => { setPurged(r); setPurgeText(""); return api.adm("system").then(setH); })
      .catch((e) => setErr(e.message))
      .finally(() => setCleaning(false));
  };
  const cleanUp = () => {
    if (!window.confirm(tr("Ta bort äldre körningar av samma ritning, misslyckade körningar och detektorns cache? Den senaste körningen av varje ritning står kvar."))) return;
    setCleaning(true);
    api.admPost("system/cleanup", {})
      .then((r) => { setCleaned(r); return api.adm("system").then(setH); })
      .catch((e) => setErr(e.message))
      .finally(() => setCleaning(false));
  };
  useEffect(() => {
    api.adm("system").then(setH).catch((e) => setErr(e.message));
    api.version().then(setV).catch(() => { /* versionen är inte livsviktig */ });
  }, []);
  if (err) return <p className="error">{err}</p>;
  if (!h) return <p className="muted">{tr("Laddar…")}</p>;
  const up = h.started_at ? Math.round((Date.now() - new Date(h.started_at).getTime()) / 3600000) : null;
  const tiles = [
    { k: "Byggning", v: h.build ?? v?.version ?? "okänd", s: `Python ${h.python} · PyMuPDF ${h.pymupdf ?? "?"}` },
    { k: "Andra läsaren", v: h.second_reader.on ? "nås" : "av", s: h.second_reader.why, tone: h.second_reader.on ? "good" : "" },
    { k: "Läsningar just nu", v: `${h.jobs.RUNNING} pågår`, s: `${h.jobs.QUEUED} i kö · ${h.workers ?? "?"} trådar`, tone: h.jobs.QUEUED > 3 ? "bad" : "" },
    { k: "Läsningar totalt", v: String(h.jobs.COMPLETED), s: `${h.jobs.FAILED} misslyckade`, tone: h.jobs.FAILED > h.jobs.COMPLETED * 0.1 ? "bad" : "" },
    { k: "Lagret", v: bytes(h.storage.used_bytes), s: `${bytes(h.storage.free_bytes)} ledigt` },
    { k: "Databasen", v: h.database.kind, s: h.database.size_bytes != null ? bytes(h.database.size_bytes) : "storlek okänd" },
    { k: "Flyttade regler", v: String(h.rules_moved), s: "gäller varje ny läsning" },
    { k: "Uppe sedan", v: up == null ? "–" : up < 48 ? `${up} h` : `${Math.round(up / 24)} dygn`, s: h.started_at?.slice(0, 16).replace("T", " ") },
  ];
  return (
    <>
      <div className="adm-stats">
        {tiles.map((t) => (
          <div key={t.k} className={`adm-stat${t.tone ? ` ${t.tone}` : ""}`}>
            <div className="k">{t.k}</div><div className="v">{t.v}</div>{t.s && <div className="s">{t.s}</div>}
          </div>
        ))}
      </div>
      <section className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>{tr("Rensa lagret")}</h3>
        <p className="muted">
          {tr("Tar bort äldre körningar av samma ritning, misslyckade körningar, kvarlämnade arbetsmappar, detektorns cache och SmartHangers råa modellfiler som redan är lästa. Den senaste körningen av varje ritning, alla ritningar, alla uppsättningar och alla projekt står kvar.")}
        </p>
        <button className="btn" onClick={cleanUp} disabled={cleaning}>{cleaning ? tr("Rensar…") : tr("Rensa")}</button>
        {cleaned && (
          <p style={{ marginBottom: 0 }}>
            {tr("Ledigt före")}: {bytes(cleaned.free_before)} · {tr("efter")}: <b>{bytes(cleaned.free_after)}</b>
          </p>
        )}
      </section>
      <section className="card" style={{ marginTop: 16, borderLeft: "4px solid #d64545" }}>
        <h3 style={{ marginTop: 0 }}>{tr("Töm alla ritningar och modeller")}</h3>
        <p className="muted">
          {tr("Tar bort alla ritningar med analyser, alla SmartHangers-uppsättningar med modeller, tekniska beskrivningar, materiallistor och offerter – för alla konton. Konton, projekt (tomma), prisfil, kunder, SmartHangers-reglerna, Dahls katalog och CAD-blad står kvar. Går inte att ångra.")}
        </p>
        <div className="row" style={{ gap: 8, alignItems: "center" }}>
          <input value={purgeText} onChange={(e) => setPurgeText(e.target.value)} placeholder={tr("skriv RENSA")} style={{ width: 140 }} />
          <button className="btn" onClick={purgeAll} disabled={cleaning || purgeText.trim().toUpperCase() !== "RENSA"}>{cleaning ? tr("Rensar…") : tr("Töm lagret")}</button>
        </div>
        {purged && <p style={{ marginBottom: 0 }}>{tr("Borttaget")}: {purged.drawings} {tr("ritningar")}, {purged.hanger_sets} {tr("SmartHangers-uppsättningar")}, {purged.tech_specs} {tr("beskrivningar/listor")}, {purged.offers} {tr("offerter")} · {purged.freed_mb} MB {tr("frigjort")}</p>}
      </section>
      <section className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>{tr("Vad som styr en läsning")}</h3>
        <p className="muted" style={{ marginBottom: 0 }}>
          Motorn läser ritningens egna vektorer; reglerna under <b>Regler</b> är de enda ratten som finns, och varje
          flyttad regel står med skäl och bild. Ingenting på företagssidan - planer, rabatter, partners - når
          läsningen. Byggningen och andra läsaren går att kontrollera utan inloggning på <code>/api/version</code>.
        </p>
      </section>
    </>
  );
}
