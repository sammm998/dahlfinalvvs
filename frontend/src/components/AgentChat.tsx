import { useEffect, useRef, useState } from "react";
import { lang, t as tr, locale } from "../i18n";
import { api } from "../api";

/* The agent, working against the reading rather than against a picture of it.
 *
 * Every number it says came out of a tool call over the artifacts the measurement wrote, so what it answers here
 * and what the takeoff table says are the same thing. The tools it used are shown under each answer, and the
 * runs it rests on can be lit up on the sheet - a claim you cannot point at is not an answer.
 */

type Msg = { role: "user" | "agent"; text: string; tools?: any[]; ids?: string[]; done?: string };

/* A change the agent proposed but has not made. It carries the call that produced it rather than its own
   numbers: accepting sends the call back, the server runs it again over this reading, and what it computes is
   what lands in the correction log. So there is no wire the metres could be edited on. */
type Proposal = { namn: string; argument: any; resultat: any };

function proposalsIn(tools: any[]): Proposal[] {
  return (tools || []).filter((t) => t?.resultat?.tillstand === "FORESLAGEN" && (t.resultat.forslag || []).length);
}

/* A first question is the hardest one to write, so the ones worth asking are on the surface - grouped the way a
   reader thinks: what does it measure, what should I check, what does this drawing say. */
/* Each button is one call into the reading, so it needs no model and cannot invent a number. Free text needs a
   model to choose the tool - that is the only difference between the two. */
type Quick = { text: string; tool: string; args?: any };
/* Sex frågor, lika stora, i två jämna spalter. Fjorton knappar i fyra grupper av olika bredd blev en vägg att läsa
   igenom; resten nås med en skriven fråga, och agenten väljer då verktyget själv. */
const QUICK: Quick[] = [
  { text: "Mängd per system", tool: "mangda", args: { gruppera_pa: "system" } },
  { text: "Mängd per beteckning", tool: "mangda", args: { gruppera_pa: "beteckning" } },
  { text: "Hitta olösta", tool: "hitta_olosta" },
  { text: "Granska läsningen", tool: "kontrollera_lasningen" },
  { text: "Vad kan ritas in?", tool: "hitta_omatt_geometri_att_rita" },
  { text: "Hur lästes skalan?", tool: "kontrollera_skala" },
];

/* Stegen agenten tog, i klartext.
 *
 * Raden sade "2 verktygsanrop" och gömde `lista_filer({})` bakom en triangel. Det säger ingenting om vad som
 * hände. Här står varje steg som en mening med sitt föremål - "Tittade i W-50-1-A-0011.pdf" - och listan är
 * öppen från början: den som undrar vad agenten gjorde ska se det utan att leta. Det råa anropet finns kvar
 * under varje rad för den som vill kontrollera exakt vad som skickades.
 */
const STEP_SAID: Record<string, (a: Record<string, unknown>) => string> = {
  lista_filer: () => "Listade filerna i samtalet",
  titta_i_filen: (a) => `Tittade i ${String(a.fil ?? "filen")}`,
  las_ritning: (a) => `Startade läsningen av ${String(a.fil ?? "ritningen")}`,
  mangder: (a) => `Hämtade mängderna ur ${String(a.fil ?? "läsningen")}`,
  fragorna: (a) => `Hämtade de olösta fallen i ${String(a.fil ?? "läsningen")}`,
  jamfor: (a) => `Jämförde ${String(a.fil_a ?? "A")} mot ${String(a.fil_b ?? "B")}`,
  rakna: (a) => `Räknade ut ${String(a.uttryck ?? "uttrycket")}`,
  material: (a) => `Slog upp "${String(a.sok ?? "")}" i Dahls katalog`,
};

function stepSaid(namn: string, arg: Record<string, unknown>): string {
  const f = STEP_SAID[namn];
  if (f) return f(arg || {});
  // Ett verktyg utan egen mening får sitt namn läst som en: foresla_identitet blir "Föreslå identitet".
  const words = namn.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function Steps({ tools }: { tools: any[] }) {
  return (
    <details className="atools" open>
      <summary>{tools.length === 1 ? "Så här gjorde agenten" : `Så här gjorde agenten · ${tools.length} steg`}</summary>
      <ol className="asteps">
        {tools.map((t: any, j: number) => (
          <li key={j}>
            <span className="astep-n">{j + 1}</span>
            <span className="astep-t">{stepSaid(t.namn, t.argument)}</span>
            <code>{t.namn}({Object.entries(t.argument || {}).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")})</code>
          </li>
        ))}
      </ol>
    </details>
  );
}

/* Medan agenten arbetar.
 *
 * Tre prickar säger att något händer men inte att det tar tid, och en läsning gör det. Klockan räknar uppåt
 * och efter tio sekunder står det vad som är på gång. Inga påhittade steg: sidan vet inte vad modellen gör
 * just nu, och att låtsas är värre än att säga att det pågår.
 */
function Working() {
  const [s, setS] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setS((v) => v + 1), 1000);
    return () => window.clearInterval(t);
  }, []);
  return (
    <div className="abub agent" role="status">
      <div className="who">Agenten</div>
      <p className="dots"><i /><i /><i /></p>
      <p className="awork">
        {s < 10 ? "Väljer verktyg…" : s < 30 ? "Arbetar med ritningen…" : "Läsningen tar en stund — den fortsätter i bakgrunden."}
        {s >= 3 && <span className="awork-t"> {s} s</span>}
      </p>
    </div>
  );
}

export default function AgentChat({ jobId, page, selection, onHighlight, onChanged, ask }: {
  jobId: string;
  page: number;
  selection: { pipeIds: string[]; bbox: number[] | null };
  onHighlight: (ids: string[]) => void;
  onChanged?: () => void;
  /** En fråga som lagts i rutan någon annanstans ifrån - från röret man just pekat ut på bladet. */
  ask?: string;
}) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  // Frågan som följde med från bladet läggs i rutan, inte i samtalet: den som pekat ut ett rör ska få läsa
  // frågan och ändra den innan den ställs. Den skrivs bara när rutan är tom, så att ingen text går förlorad.
  useEffect(() => { if (ask) setText((t) => (t.trim() ? t : ask)); }, [ask]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [listening, setListening] = useState(false);
  const [speak, setSpeak] = useState(false);
  const [writing, setWriting] = useState("");
  const rec = useRef<any>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);

  const send = async (q: string, quick?: Quick) => {
    const question = q.trim();
    if (!question || busy) return;
    setText(""); setErr("");
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setBusy(true);
    try {
      const r = quick
        ? await api.agentTool(jobId, quick.tool, quick.args ?? {})
        : await api.agent(jobId, {
          question, page, language: lang,
          pipe_ids: selection.pipeIds.length ? selection.pipeIds : undefined,
          bbox: selection.bbox ?? undefined,
        });
      const ids: string[] = r.markera?.ror_id ?? [];
      setMsgs((m) => [...m, { role: "agent", text: r.svar || "(inget svar)", tools: r.verktyg ?? [], ids }]);
      if (ids.length) onHighlight(ids);
      if (speak && r.svar) {
        try {
          const u = new SpeechSynthesisUtterance(r.svar);
          u.lang = locale();
          window.speechSynthesis.speak(u);
        } catch { /* a browser without speech simply stays quiet */ }
      }
    } catch (e: any) {
      setErr(e?.message || "agenten kunde inte svara");
    } finally {
      setBusy(false);
    }
  };

  /* Accepting a proposal. The card shows what would change; this is where it actually does. The reading keeps
     its own figures beside the corrected ones, and the correction can be undone under Rättelser. */
  const accept = async (i: number, p: Proposal) => {
    if (writing) return;
    setWriting(`${i}:${p.namn}`); setErr("");
    try {
      const r = await api.agentEdit(jobId, p.namn, p.argument, "godkänt i chatten");
      setMsgs((m) => m.map((x, j) => (j === i ? { ...x, done: r.sammanfattning || "Rättelsen är skriven." } : x)));
      onChanged?.();
    } catch (e: any) {
      setErr(e?.message || "rättelsen kunde inte skrivas");
    } finally {
      setWriting("");
    }
  };

  /* Voice in: the browser's own recogniser, so nothing is uploaded to reach it. */
  const toggleMic = () => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) { setErr("den här webbläsaren har ingen taligenkänning"); return; }
    if (listening) { rec.current?.stop(); setListening(false); return; }
    const r = new SR();
    r.lang = locale(); r.interimResults = true; r.continuous = false;
    r.onresult = (e: any) => {
      const said = Array.from(e.results).map((x: any) => x[0].transcript).join("");
      setText(said);
      if (e.results[e.results.length - 1].isFinal) { setListening(false); send(said); }
    };
    r.onerror = () => setListening(false);
    r.onend = () => setListening(false);
    rec.current = r;
    setListening(true);
    r.start();
  };

  const nSel = selection.pipeIds.length;
  return (
    <div className="agentchat">
      <div className="agentctx">
        <span className="dotlive" />
        <span>Sida {page + 1}</span>
        {nSel > 0 && <span className="sel">{nSel} markerade rör</span>}
        {selection.bbox && !nSel && <span className="sel">{tr("markerat område")}</span>}
        {msgs.length > 0 && (
          <button className="ghost small clear" onClick={() => { setMsgs([]); setErr(""); }}>Rensa</button>
        )}
      </div>

      <div className="agentlog">
        {msgs.length === 0 && (
          <div className="agentintro">
            <h4>{tr("Fråga ritningen")}</h4>
            <p>
              Knapparna nedan går rakt in i läsningen och svarar utan modell — de kan inte hitta på ett tal.
              Fri text behöver en modell som väljer verktyg åt dig. Markera något i ritningen först, så vet
              agenten vad ”det här” är.
            </p>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`abub ${m.role}`}>
            <div className="who">{m.role === "user" ? "Du" : "Agenten"}</div>
            <p>{m.text}</p>
            {m.tools && m.tools.length > 0 && <Steps tools={m.tools} />}
            {m.role === "agent" && proposalsIn(m.tools || []).map((p, k) => (
              <div key={`p${k}`} className={`proposal${m.done ? " done" : ""}`}>
                <div className="phead">
                  <span className="ptag">{tr("Förslag")}</span>
                  <span>{p.resultat.sammanfattning}</span>
                </div>
                <ul>
                  {(p.resultat.forslag || []).map((f: any, q: number) => <li key={q}>{f.text}</li>)}
                </ul>
                {p.resultat.stor_andring && (
                  <p className="pwarn">{tr("Ändringen rör mer än 50 m. Kontrollera att den är menad så.")}</p>
                )}
                {m.done ? (
                  <p className="pdone">{m.done} Rättelsen kan ångras under Rättelser.</p>
                ) : (
                  <div className="pbtns">
                    <button className="ask" disabled={!!writing} onClick={() => accept(i, p)}>
                      {writing === `${i}:${p.namn}` ? "Skriver…" : "Genomför"}
                    </button>
                    <span className="muted">{tr("Inget är ändrat än.")}</span>
                  </div>
                )}
              </div>
            ))}
            {m.ids && m.ids.length > 0 && (
              <button className="showbtn" onClick={() => onHighlight(m.ids!)}>
                Visa {m.ids.length} {m.ids.length === 1 ? "sträcka" : "sträckor"} på ritningen
              </button>
            )}
          </div>
        ))}
        {busy && <Working />}
        {err && <p className="error">{err}</p>}
        <div ref={end} />
      </div>

      <div className="agentquick grid">
        {QUICK.map((q) => (
          <button key={q.text} className="quickbtn" onClick={() => send(q.text, q)} disabled={busy}>{tr(q.text)}</button>
        ))}
      </div>

      <div className="agentbar">
        <textarea rows={2} value={text} placeholder={tr("Skriv en fråga, eller tryck på Tala…")}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }} />
        <div className="agentbtns">
          {/* words rather than glyphs: an emoji that a machine has no font for is a blank button */}
          <button className={`pillbtn${listening ? " on" : ""}`} onClick={toggleMic}
            title={listening ? "Lyssnar — tryck för att sluta" : "Tala i stället för att skriva"}>
            {listening ? "Lyssnar" : "Tala"}
          </button>
          <button className={`pillbtn${speak ? " on" : ""}`} onClick={() => setSpeak(!speak)}
            title={speak ? "Svaren läses upp" : "Läs upp svaren"}>{tr("Röst")}</button>
          <button className="ask" onClick={() => send(text)} disabled={busy || !text.trim()}>{tr("Fråga")}</button>
        </div>
      </div>
    </div>
  );
}
