import { useRef, useState } from "react";
import { t as tr, lang } from "../i18n";

/* Demofilmerna: riktiga vyer ur den inloggade appen, inspelade på en riktig läsning, textade på svenska och
 * engelska. Filmen följer sidans språk. Varje film finns som WebM (VP9) och MP4 (H.264), så att den spelas i
 * alla webbläsare, och har en stillbild som syns innan den startas. */
export const DEMOS = [
  { id: "lasning", t: "Från ritning till mängd", d: "Systemet läser ritningen via beteckningarna. Tryck på en rad och se exakt vilka sträckor den kommer ur." },
  { id: "3d", t: "3D-modellen", d: "Samma läsning som en byggnad, med ritningen som golv och rören i sina system." },
  { id: "agent", t: "AI-agenten", d: "Fråga ritningen. Svaren kommer ur mängden, och sträckorna visas på bladet." },
  { id: "kalkyl", t: "Kalkylen", d: "Mängden blir material, normtid och anbudssumma, rad för rad." },
  { id: "cad", t: "CAD", d: "Rita väggar, dörrar, fönster och rum – i plan och 3D samtidigt." },
];

export default function Demos({ compact = false }: { compact?: boolean }) {
  const [on, setOn] = useState(0);
  const video = useRef<HTMLVideoElement>(null);
  const cur = DEMOS[on];
  const src = (ext: string) => `/demos/${cur.id}_${lang}.${ext}`;
  const pick = (i: number) => {
    setOn(i);
    // nästa film startar direkt när någon väljer den; den första väntar på ett tryck
    requestAnimationFrame(() => { const v = video.current; if (v) { v.load(); void v.play().catch(() => { /* kräver ett tryck */ }); } });
  };
  return (
    <section className={`fc-demo${compact ? " compact" : ""}`} id="demo">
      <div className="fc-demo-in">
        {!compact && (
          <header className="fc-demo-head">
            <p className="fc-label fc-label-on">{tr("Se hur det funkar")}</p>
            <h2 className="fc-display fc-display-md">{tr("Fem minuter i Dahl")}</h2>
            <p className="fc-body">{tr("Inspelat i appen på en riktig ritning – inga skisser, inga redigerade siffror.")}</p>
          </header>
        )}
        <div className="fc-demo-grid">
          <div className="fc-demo-player">
            <video key={cur.id} ref={video} controls playsInline preload="metadata" poster={`/demos/${cur.id}_${lang}.jpg`}>
              <source src={src("webm")} type="video/webm" />
              <source src={src("mp4")} type="video/mp4" />
            </video>
          </div>
          <ol className="fc-demo-list">
            {DEMOS.map((dm, i) => (
              <li key={dm.id}>
                <button className={i === on ? "on" : ""} onClick={() => pick(i)} aria-current={i === on}>
                  <span className="fc-num">0{i + 1}</span>
                  <span className="fc-demo-txt"><b>{tr(dm.t)}</b><span>{tr(dm.d)}</span></span>
                </button>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
