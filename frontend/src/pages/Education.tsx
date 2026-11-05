import { useEffect, useState } from "react";
import { t as tr } from "../i18n";
import { Link, useParams } from "react-router-dom";
import PublicFrame, { PubSection } from "../components/PublicFrame";
import { MODULES } from "../learn";
import Lecture, { findLesson, findModule, FLAT } from "../components/Lecture";
import { CourseGrid, CourseView, useProgress, courseMinutes } from "../components/Academy";
import { ac } from "../academy/api";
import { AppLink } from "../fc/primitives";

/* VVS-akademin utåt.
 *
 * Här fanns bara de fria föreläsningarna - en egen uppsättning kurser som bor i webbläsaren - och de
 * presenterades som hela akademin. Samtidigt växte den riktiga utbildningen i tjänsten: tio kurser med
 * övningar som rättas, en sluttenta och ett verifierbart certifikat. Den som klickade Academy i menyn kom till
 * de fria föreläsningarna, såg "9 kurser, 2 h" och fick aldrig veta att det andra fanns.
 *
 * Nu visar sidan utbildningen som den är, räknad ur tjänsten själv: så många kurser som faktiskt finns, inte
 * en siffra skriven här som blir fel så fort någon lägger till en. Föreläsningarna står kvar under den som det
 * de är - fritt läsbara, utan konto, utan rättning - i stället för att utge sig för att vara utbildningen.
 */

const BASE = "/utbildning";

type Katalog = {
  kurser: { slug: string; title: string; blurb: string; level: string; hours: number;
            moduler: number; lektioner: number; ovningar: number; modulnamn: string[] }[];
  totalt: { kurser: number; moduler: number; lektioner: number; ovningar: number; timmar: number };
  tenta: { slug: string; title: string; pass_pct: number; uppgifter: number;
           delar: { title: string; n: number; weight: number }[] } | null;
};

const NIVA: Record<string, string> = { grund: "Grund", fortsattning: "Fortsättning", avancerad: "Avancerad" };

/* ---------- katalogen ---------- */

export default function EducationPage() {
  const prog = useProgress(false);
  const lessons = FLAT.length;
  const minutes = MODULES.reduce((n, m) => n + courseMinutes(m), 0);
  // Utbildningen räknad ur tjänsten. Faller anropet får sidan stå kvar på föreläsningarna - den är fortfarande
  // sann om dem - i stället för att visa ett fel om något besökaren inte frågat efter.
  const [kat, setKat] = useState<Katalog | null>(null);
  useEffect(() => { ac.catalogue().then(setKat).catch(() => setKat(null)); }, []);
  const T = kat?.totalt;
  return (
    <PublicFrame
      kicker="Dahl Academy"
      title={<>Lär dig läsa ritningen —<br />inte bara mängda den</>}
      lede="Från vad ett VVS-system är till att mängda ett riktigt blad, få det rättat mot ritningens egen geometri och skriva en sluttenta som rättas på servern."
      anchors={[{ href: "#utbildningen", label: "Utbildningen" }, { href: "#tentan", label: "Tentan" },
                { href: "#kurser", label: "Fria föreläsningar" }, { href: "#kontor", label: "För kontor" }]}
      aside={
        <div className="pub-keys">
          <div className="pub-key"><div className="n">{T ? T.kurser : MODULES.length}</div><div className="l">kurser</div></div>
          <div className="pub-key"><div className="n">{T ? T.lektioner : lessons}</div><div className="l">lektioner</div></div>
          <div className="pub-key"><div className="n">{T ? T.ovningar : Math.round(minutes / 60)}</div><div className="l">{T ? "övningar" : "timmar"}</div></div>
        </div>
      }>

      {kat && (
        <PubSection id="utbildningen" kicker="Utbildningen"
          title={`${kat.totalt.kurser} kurser, ${kat.totalt.moduler} moduler, ${kat.totalt.ovningar} övningar som rättas`}
          lede="Kurserna bygger på varandra, men ingenting är låst — du kan börja var du vill. Varje övning rättas mot ritningens egen geometri, inte mot ett tal i en fil, så ett svar kan inte bli fel för att någon glömt uppdatera facit.">
          <ol className="pub-courselist">
            {kat.kurser.map((k, i) => (
              <li key={k.slug}>
                <AppLink to={`/academy/${k.slug}`}>
                  <span className="pub-cno">{String(i + 1).padStart(2, "0")}</span>
                  <span className="pub-cbody">
                    <span className="pub-clevel">{NIVA[k.level] ?? k.level} · {k.hours} h</span>
                    <strong>{k.title}</strong>
                    <span className="pub-cblurb">{k.blurb}</span>
                    <span className="pub-cmeta">
                      {k.moduler} moduler · {k.lektioner} lektioner{k.ovningar ? ` · ${k.ovningar} övningar` : ""}
                    </span>
                    {k.modulnamn.length > 0 && <span className="pub-cmods">{k.modulnamn.join(" · ")}</span>}
                  </span>
                  <span className="pub-carrow" aria-hidden="true">→</span>
                </AppLink>
              </li>
            ))}
          </ol>
        </PubSection>
      )}

      {kat?.tenta && (
        <PubSection id="tentan" kicker="Sluttentan" title={kat.tenta.title}
          lede={`${kat.tenta.uppgifter} uppgifter i ${kat.tenta.delar.length} delar. ${kat.tenta.pass_pct} % totalt och minst 60 % i varje del — en del går inte att lämna tom och räkna upp med de andra. Rättningen sker på servern; facit lämnar den aldrig.`}>
          <div className="pub-grid pub-three">
            {kat.tenta.delar.map((d) => (
              <div className="pub-card" key={d.title}>
                <span className="no">{d.weight} %</span>
                <h3>{d.title}</h3>
                <p>{d.n} uppgifter</p>
              </div>
            ))}
          </div>
          <p className="pub-cta">
            <AppLink className="lp-btn primary lg" to="/academy">{tr("Till utbildningen")}</AppLink>
          </p>
        </PubSection>
      )}

      <PubSection id="kurser" kicker="Fria föreläsningar"
        title={`${MODULES.length} föreläsningar du får läsa utan konto`}
        lede="Kortare texter med en levande figur och en kontrollfråga. De är inte utbildningen ovan — de rättas inte och de ger inget certifikat — men de går att läsa, spara och dela direkt.">
        <CourseGrid base={BASE} prog={prog} />
      </PubSection>

      <PubSection id="sa" kicker="Så är den upplagd" title={tr("Byggd för att göras, inte bläddras i")}>
        <div className="pub-grid pub-three">
          <div className="pub-card">
            <span className="no">01</span>
            <h3>{tr("En figur som rör sig")}</h3>
            <p>{tr("Varje föreläsning visar det den handlar om som en levande ritning — en ledarlinje som hittar sitt rör, en stigare som blir meter — i stället för att beskriva det i ord.")}</p>
          </div>
          <div className="pub-card">
            <span className="no">02</span>
            <h3>{tr("En kontrollfråga")}</h3>
            <p>{tr("Inte ett prov. En fråga som går att svara fel på, med förklaringen efteråt — för det är den man minns.")}</p>
          </div>
          <div className="pub-card">
            <span className="no">03</span>
            <h3>{tr("Övningar på riktiga blad")}</h3>
            <p>Samma slags ritningar som tjänsten läser: förklaringslistor, beteckningar, ledare, streckade rör. Ingen övning går att klara genom att gissa på det som ligger närmast.</p>
          </div>
        </div>
      </PubSection>

      <PubSection id="kontor" kicker="För kontor" title={tr("Samma kurs för hela laget")}
        lede="Varje inloggning på ett konto har sin egen kursgång och sina egna utmärkelser. Den som driver kontoret ser vilka moment som gåtts.">
        <p className="pub-cta">
          <Link className="lp-btn primary lg" to={`${BASE}/${MODULES[0].id}/${MODULES[0].lessons[0].id}`}>
            Läs första föreläsningen
          </Link>
          <Link className="lp-btn ghost lg" to="/kontakt">{tr("Utbildning för kontoret")}</Link>
        </p>
      </PubSection>
    </PublicFrame>
  );
}

/* ---------- en kurs ---------- */

export function EducationCoursePage() {
  const { modul } = useParams();
  const prog = useProgress(false);
  const found = findModule(modul);
  if (!found) return <NotFound />;
  return (
    <PublicFrame bare>
      <CourseView m={found.module} mi={found.mi} base={BASE} prog={prog} />
    </PublicFrame>
  );
}

/* ---------- en föreläsning ---------- */

export function EducationLessonPage() {
  const { modul, lektion } = useParams();
  const at = findLesson(modul, lektion);
  if (!at) return <NotFound />;
  return (
    <PublicFrame bare>
      <Lecture at={at} base={BASE} locked />
    </PublicFrame>
  );
}

function NotFound() {
  return (
    <PublicFrame kicker="VVS-akademin" title={tr("Den föreläsningen finns inte")}
      lede="Adressen pekar på något akademin inte har. Kurserna står kvar där de var.">
      <PubSection tight>
        <p className="pub-cta"><Link className="lp-btn primary lg" to={BASE}>{tr("Till kurserna")}</Link></p>
      </PubSection>
    </PublicFrame>
  );
}
