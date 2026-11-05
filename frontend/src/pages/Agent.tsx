import { useCallback, useEffect, useRef, useState } from "react";
import { t as tr } from "../i18n";
import { Link } from "react-router-dom";
import { api } from "../api";

/* Agenten som egen plats, i hela fönstret.
 *
 * Inte analysens agent bakom en projektväljare: den här börjar tomt. Du drar in en handling i samtalet och
 * frågar. Filen blir en riktig ritning på ditt eget skrivbord - samma motor, samma credits, samma artefakter -
 * så svaret går att öppna i Analys och räkna vidare på, utan att du har lagt upp ett projekt.
 *
 * Formen är den ett samtal har: en spalt i mitten, frågan längst ned, filerna som brickor i rutan där du
 * skriver. Ingen sidopanel att sneglar åt, ingen rubrik som tar halva skärmen - det som står kvar på skärmen
 * är det som sagts.
 *
 * Samma löfte som överallt: modellen väljer vilken fråga som ställs till ritningen, verktygen svarar ur det som
 * lästs, och en siffra utan belägg blir "det står inte i handlingen".
 */

type Fil = {
  id: string; filnamn: string; sidor: number; storlek: number;
  jobb?: { id: string; status: string; steg: string; andel: number } | null;
};
type Verktyg = { namn: string; argument: any; resultat: any };
type Msg = { role: "user" | "agent"; text: string; tools?: Verktyg[]; jobs?: string[]; filer?: Fil[] };

const START = [
  "Vad är det här för blad?",
  "Läs ritningen och visa mängderna",
  "Vad kunde inte avgöras?",
  "Vad kostar rören enligt materialboken?",
];

function kb(n: number) {
  return n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} kB`;
}

function lage(f: Fil) {
  const j = f.jobb;
  if (!j) return { txt: "inte läst", cls: "" };
  if (j.status === "COMPLETED") return { txt: "läst", cls: "ok" };
  if (j.status === "FAILED") return { txt: "gick inte att läsa", cls: "bad" };
  return { txt: `läser ${Math.round((j.andel || 0) * 100)} %`, cls: "run" };
}

function Papper() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" />
    </svg>
  );
}

export default function AgentPage() {
  const [files, setFiles] = useState<Fil[]>([]);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const [err, setErr] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const pick = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const drag = useRef(0);

  const load = useCallback(async () => {
    try { setFiles((await api.deskFiles()).filer || []); } catch (e: any) { setErr(e.message); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, busy]);
  useEffect(() => { box.current?.focus(); }, []);

  // en läsning tar en stund; så länge någon fil läser frågar sidan om läget, sedan slutar den
  useEffect(() => {
    const reading = files.some((f) => f.jobb && (f.jobb.status === "QUEUED" || f.jobb.status === "RUNNING"));
    if (!reading) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [files, load]);

  // rutan växer med texten, upp till en dryg halv skärm
  const grow = () => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  };
  useEffect(grow, [text]);

  const take = async (list: FileList | File[]) => {
    const arr = Array.from(list).filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (!arr.length) { setErr("Agenten läser PDF. Spara om filen som PDF och släpp den igen."); return; }
    setErr("");
    for (const f of arr) {
      try {
        const up = await api.deskUpload(f);
        setFiles((x) => [...x, up]);
      } catch (e: any) { setErr(e?.message || "filen kunde inte tas emot"); }
    }
    box.current?.focus();
  };

  const send = async (q: string) => {
    const fraga = q.trim();
    if (!fraga || busy) return;
    setText(""); setErr("");
    // vad som sagts tidigare, i modellens egna ord: roll och text. Sidan skickar det den vet; servern läser
    // bara det som går att läsa, så en tom rad fäller aldrig svaret.
    const historik = msgs.slice(-8).map((m) => ({ role: m.role === "user" ? "user" : "assistant", content: m.text }));
    const bifogade = files;
    setMsgs((m) => [...m, { role: "user", text: fraga, filer: bifogade }]);
    setBusy(true);
    try {
      const r = await api.deskAsk({ fraga, filer: files.map((f) => f.id), historik });
      setMsgs((m) => [...m, { role: "agent", text: r.svar || "(inget svar)", tools: r.verktyg ?? [], jobs: r.startade_lasningar ?? [] }]);
      if (r.filer) setFiles(r.filer);
    } catch (e: any) {
      setErr(e?.message || "agenten kunde inte svara");
    } finally { setBusy(false); box.current?.focus(); }
  };

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); }
  };

  const laste = files.filter((f) => f.jobb?.status === "COMPLETED");
  const tomt = !msgs.length;

  return (
    <div className="desk"
      onDragEnter={(e) => { e.preventDefault(); drag.current++; setOver(true); }}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={() => { drag.current = Math.max(0, drag.current - 1); if (!drag.current) setOver(false); }}
      onDrop={(e) => { e.preventDefault(); drag.current = 0; setOver(false); take(e.dataTransfer.files); }}>

      <header className="deskbar">
        <span className="org">Agenten</span>
        <span className="muted small">{tr("fristående · läser med samma motor som analysen")}</span>
        <div className="sp" />
        {!!files.length && (
          <button className="ghost small" onClick={() => setMsgs([])} disabled={busy || tomt}>{tr("Nytt samtal")}</button>
        )}
      </header>

      <div className="deskthread">
        <div className="deskcol">
          {tomt && (
            <div className="deskhello">
              <h1>Vad säger ritningen?</h1>
              <p className="lead">
                Släpp en PDF var som helst på sidan och fråga. Agenten svarar ur det som står i handlingen och
                säger vad den inte kunde avgöra. Den hittar inte på en siffra.
              </p>
              <div className="deskstart">
                {START.map((s) => <button key={s} className="chip" onClick={() => send(s)}>{s}</button>)}
              </div>
            </div>
          )}

          {msgs.map((m, i) => (
            <div key={i} className={`turn ${m.role}`}>
              {m.role === "user" ? (
                <div className="said">
                  {!!m.filer?.length && (
                    <div className="saidfiles">
                      {m.filer.map((f) => <span key={f.id} className="filechip small"><Papper /> {f.filnamn}</span>)}
                    </div>
                  )}
                  <div className="txt">{m.text}</div>
                </div>
              ) : (
                <div className="answered">
                  <div className="txt">{m.text}</div>
                  {!!m.jobs?.length && (
                    <p className="small muted">{tr("Läsningen är startad. Filen säger till här nedanför när den är klar.")}</p>
                  )}
                  {!!m.tools?.length && (
                    <details className="tools">
                      <summary>{m.tools.length === 1 ? "1 verktygsanrop" : `${m.tools.length} verktygsanrop`}</summary>
                      {m.tools.map((t, k) => (
                        <pre key={k} className="tool"><b>{t.namn}</b>({JSON.stringify(t.argument)}){"\n"}
                          {JSON.stringify(t.resultat, null, 1).slice(0, 1400)}</pre>
                      ))}
                    </details>
                  )}
                </div>
              )}
            </div>
          ))}

          {busy && <div className="turn agent"><div className="answered"><span className="dots"><i /><i /><i /></span></div></div>}
          <div ref={end} />
        </div>
      </div>

      <div className="deskfoot">
        <div className="deskcol">
          {err && <p className="error small">{err}</p>}
          <form className="composer" onSubmit={(e) => { e.preventDefault(); send(text); }}>
            {!!files.length && (
              <div className="attached">
                {files.map((f) => {
                  const l = lage(f);
                  return (
                    <span key={f.id} className={`filechip ${l.cls}`} title={`${f.sidor} sid · ${kb(f.storlek)}`}>
                      <Papper />
                      <span className="nm">{f.filnamn}</span>
                      <span className="st">{l.txt}</span>
                      {f.jobb?.status === "COMPLETED" && <Link to={`/jobs/${f.jobb.id}`} className="op">{tr("öppna")}</Link>}
                    </span>
                  );
                })}
              </div>
            )}
            <div className="row">
              <button type="button" className="round" title={tr("Bifoga PDF")} onClick={() => pick.current?.click()} disabled={busy}>+</button>
              <textarea ref={box} rows={1} value={text} placeholder={tr("Fråga om ritningen…")}
                        onChange={(e) => setText(e.target.value)} onKeyDown={onKey} disabled={busy} />
              <button type="submit" className="round send" disabled={busy || !text.trim()} title={tr("Fråga")}>↑</button>
            </div>
          </form>
          <p className="deskhint small muted">
            {laste.length > 1
              ? <>Enter skickar, Shift+Enter ny rad. Du kan be den <button className="linky" onClick={() => send(`Jämför ${laste[0].filnamn} med ${laste[1].filnamn}`)}>{tr("jämföra två blad")}</button>.</>
              : <>Enter skickar, Shift+Enter ny rad. Agentens svar tas ur den gemensamma AI-budgeten.</>}
          </p>
        </div>
      </div>

      <input ref={pick} type="file" accept="application/pdf" multiple hidden
             onChange={(e) => { if (e.target.files) take(e.target.files); e.currentTarget.value = ""; }} />

      {over && <div className="deskdrop"><div>{tr("Släpp ritningen här")}</div></div>}
    </div>
  );
}
