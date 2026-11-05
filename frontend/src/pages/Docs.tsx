import { useEffect, useMemo, useState } from "react";
import { t as tr } from "../i18n";
import SiteHeader from "../components/SiteHeader";


type Sec = { id: string; h: string; body: JSX.Element };

const SECTIONS: Sec[] = [
  {
    id: "principen",
    h: "Principen",
    body: (
      <>
        <p>
          Systemet mängdar rör ur en VVS-ritning genom att läsa ritningens egen vektorgeometri. Det gissar aldrig
          en identitet utifrån närhet. Ett rör får ett namn bara när en riktig ledarlinje går från en beteckning
          till just den geometrin — annars redovisas det som oidentifierat eller tvetydigt.
        </p>
        <p className="pull">{tr("Tvetydigt är ett giltigt svar. Fel säkerhet är det inte.")}</p>
        <p>
          Det betyder att en siffra som står i mängden alltid har ett belägg bakom sig, och att det som saknas
          syns i stället för att fyllas i. En mängdning som ser komplett ut men är gissad är värre än en som säger
          var den inte räcker till.
        </p>
      </>
    ),
  },
  {
    id: "vad-som-lases",
    h: "Vad som läses — och vad som inte gör det",
    body: (
      <>
        <p>
          Indata är en <b>vektor-PDF</b>, alltså en ritning exporterad ur CAD. Varje streck finns då som geometri
          med sin penna, färg och sitt lager. En skannad eller bildbaserad PDF avvisas med besked: där finns inga
          vektorkoder att läsa, bara bildpunkter, och att mäta på bildpunkter vore att gissa.
        </p>
        <p>
          Ingen OCR förekommer i mätvägen. Där texten är ritad som streck i stället för tecken byggs bokstäverna
          tillbaka ur streckens former. OCR används enbart som andrahandsutlåtande för tecken formigenkänningen
          inte kunde namnge, och bara när OCR-ordet stämmer tecken för tecken med det vektorläsningen redan läst.
        </p>
      </>
    ),
  },
  {
    id: "lasningen",
    h: "Läsningen, steg för steg",
    body: (
      <>
        <ol className="steps">
          <li>
            <b>{tr("Läser vektorn.")}</b> Varje väg, dess penna, färg, lager och ordning tas ur PDF:en. Sidramen känns
            igen på sin form och räknas aldrig som rör.
          </li>
          <li>
            <b>{tr("Bygger tillbaka texten.")}</b> Streck grupperas till tecken, tecken till rader. Ett tecken namnges
            genom att dess form jämförs med referensalfabet — det egna inbäddade typsnittet först, när ritningen
            har ett.
          </li>
          <li>
            <b>{tr("Läser beteckningslistan.")}</b> Sidans egen lista säger vilka koder som är system, vilka som är
            material och vilka som är komponenter. Listan skriver komponentfamiljer med platshållare —
            <code>{tr("BXXX GOLVBRUNN")}</code> {tr("— så")} <code>B1</code> och <code>B221BL</code> känns igen som just den
            posten och aldrig som rör.
          </li>
          <li>
            <b>{tr("Läser beteckningarna.")}</b> Grammatiken lärs per ritning:
            <code>SYSTEM+löpnummer – MATERIAL – DIMENSION [/ISOLERING]</code>. Dimensionen kan stå inline eller på
            raden under, understruken; båda formerna viks in i samma identitet.
          </li>
          <li>
            <b>{tr("Hittar ledarlinjerna.")}</b> Från etikettens understrykning, ram eller radbas ut till den geometri
            linjen faktiskt rör, eller till symbolen den slutar i. Linjer som bara är ramstumpar sorteras bort.
          </li>
          <li>
            <b>{tr("Väljer rörfamiljer.")}</b> Geometri grupperas på (lager, pennbredd, färg) — inte på streckmönster,
            eftersom linjetypen på svenska ritningar säger <i>{tr("var röret ligger i höjdled")}</i>, inte vilket system
            det är. Vilka familjer som är rör avgörs av var ritningens egna ledarlinjer slutar.
          </li>
          <li>
            <b>{tr("Bygger topologi och äger rören.")}</b> Identiteten bärs längs nätet från den etikett som pekar på det,
            till den gräns ritningen själv sätter: en dimensionsändring, en systemgräns, en gren utan stöd.
          </li>
          <li>
            <b>{tr("Mäter.")}</b> I skalstockens egen skala, verifierad mot skaltexten. Stigare räknas som antal; deras
            meter kräver en våningshöjd, och den frågar systemet efter i stället för att anta en.
          </li>
        </ol>
      </>
    ),
  },
  {
    id: "agenterna",
    h: "Flera vägar till samma svar",
    body: (
      <>
        <p>
          Efter första läsningen läses sidan om längs andra vägar, som självständiga agenter med var sin logik.
          De ska nå samma svar; där de inte gör det är det en upplysning.
        </p>
        <ul className="defs">
          <li><b>pointing</b> — läser genom det etiketten pekar på: ledarlinjens ände och de märken den slutar i.</li>
          <li><b>writing</b> — läser genom vad ritningen skriver: etiketter som ligger utmed en sträcka i stället för att peka på den.</li>
          <li><b>closure</b> — läser genom nätets slutenhet: en sträcka som bara kan höra till en identitet därför att allt annat runt den redan är namngivet.</li>
        </ul>
        <p>
          Sedan en <b>{tr("korsläsning")}</b> {tr("som ställer svaren mot varandra, och en")} <b>granskning</b> som listar varje
          sträcka utan namn och varje etikett som inte nådde ett rör, med skäl. En andra väg får lägga till det
          den första missade — men aldrig döpa om något den första redan avgjort.
        </p>
        <p className="note">
          En fjärde väg, som lät en ledarlinje som stannat strax före ett stråk nå fram ändå, byggdes och togs
          bort igen: den valde fel linje ur ett knippe parallella rör och sexdubblade felet på referensritning A.
          Vägar som inte håller finns dokumenterade i <code>docs/FLERVAGSANALYS.md</code> med sin uppmätta kostnad.
        </p>
      </>
    ),
  },
  {
    id: "vagrar",
    h: "Reglerna som vägrar",
    body: (
      <>
        <p>{tr("Det mesta av arbetet ligger i att inte mäta fel saker. Varje regel är mätt fram, inte antagen.")}</p>
        <ul className="defs">
          <li>
            <b>{tr("Ritade föremål.")}</b> Ett rör ritas som en linje i mitten; en radiator eller en luftvärmare ritas som
            sina två långsidor. Två linjer en läsare ska skilja åt kan inte ritas närmare än ungefär en millimeter
            papper — ett stråk som skuggas hela vägen av sin egen familj därifrån är en kontur, inte ett rör.
          </li>
          <li>
            <b>Dubbelritat.</b> Samma linje ritad två gånger på samma penna är ett rör, inte två. På vissa ark är
            12–28 % av geometrin dubbelritad.
          </li>
          <li>
            <b>{tr("Etiketterna måste nå fram.")}</b> Saknar de accepterade familjerna lagernamn och ritningens egna
            rörbeteckningar ändå inte når dem, är det fel geometri som accepterats — hade det varit rören hade
            etiketterna hittat dem.
          </li>
          <li>
            <b>{tr("Identitet som rinner för långt.")}</b> En identitet får löpa vidare genom en korsning, men bara inom
            räckhåll för vad etiketterna själva avgränsar.
          </li>
          <li>
            <b>Knippeetiketten.</b> Där en etikett namnger fler system än ritningen ritar linjer redovisas
            sträckan som delad — längden går inte att fördela utan att hitta på en regel, och riktningen är inte
            konstant mellan ritningar.
          </li>
        </ul>
      </>
    ),
  },
  {
    id: "rattelser",
    h: "Rättelser, och vad de får lära ut",
    body: (
      <>
        <p>
          Fem saker går att ändra på en färdig läsning: rita ett rör motorn inte såg, förlänga ett förbi där det
          slutade, sudda det som mätts men inte är rör, flytta meter mellan beteckningar, eller sätta längden för
          hand. Rättelser läggs <i>{tr("ovanpå")}</i> läsningen — varje rad behåller motorns egen siffra, så det syns
          alltid vad som lästes och vad som ändrades.
        </p>
        <p>
          Vad en rättelse får lära ut är medvetet smalt. En läxa får bara avgöra ett fall som motorn själv kallat
          tvetydigt, till förmån för det svar en människa gav <i>{tr("i samma situation")}</i>. Den får aldrig skapa en
          sträcka, aldrig namnge geometri ingen ledarlinje nådde, aldrig röra något motorn är säker på, och aldrig
          erbjuda ett svar ritningens egna kandidater inte innehåller.
        </p>
        <p>
          Samma situation är en exakt träff, inte ett likhetsmått: pennan som geometrin är ritad med, skälet
          motorn gav upp, och beteckningens form med siffrorna borttagna. En situation som besvarats på två olika
          sätt lär ut ingenting — oenigheten är fyndet. Och förslag är förslag: mängden flyttar sig först när en
          människa godtar ett, och då som en rättelse i registret.
        </p>
      </>
    ),
  },
  {
    id: "belagg",
    h: "Beläggen",
    body: (
      <>
        <p>
          Varje mätt sträcka går att spåra bakåt. <b>Varför?</b> på en sträcka visar kedjan: beteckningen och dess
          källa, ledarlinjen och dess vägar i PDF:en, kontaktpunkten, de primitiver identiteten bars över, och
          gränsen som stoppade den.
        </p>
        <p>
          Varje körning skriver 29 artefakter: rörgeometri, topologi, fysiska rör, mängder, olösta fall,
          evidensgraf, korsläsning, granskning, avstämning, determinism, kontaminationsrapport, prestandarapport
          och fyra överlägg som PDF. Export finns som Excel, CSV, JSON, rapport och markerad PDF.
        </p>
      </>
    ),
  },
  {
    id: "validering",
    h: "Hur det valideras",
    body: (
      <>
        <p>{tr("Tre nivåer, och de körs om vid varje ändring som kan röra en siffra.")}</p>
        <ul className="defs">
          <li>
            <b>Facit.</b> Fyra ritningar handmängdade av en människa, med längd per beteckning. Systemet körs
            blint — hela vägen genom API:t som en användare gör det — och poängsätts först efteråt.
          </li>
          <li>
            <b>Stilbiblioteket.</b> Varje sida i varje ritning från elva projekterande kontor körs och jämförs
            mot förra körningen, så att en förbättring på ett ark inte tyst förstör ett annat.
          </li>
          <li>
            <b>{tr("Annoterade ark.")}</b> Handmarkerade masker per beteckning på fler ark, som oberoende svar på om
            rätt rör hittades på rätt plats.
          </li>
        </ul>
        <p className="note">
          Facit och annoteringar ligger utanför koden och läses aldrig av motorn. En kontaminationskontroll körs
          vid varje analys och intygar att produktionspaketet inte importerar valideringsdata.
        </p>
        <p>
          Ett samlat felvärde döljer de två felen som betyder något åt var sitt håll. Meter som saknas kostar
          kalkylatorn arbete; meter som systemet hittat på kostar pengar och förtroende, och ingen täckning i
          världen betalar för dem. Därför redovisas de var för sig.
        </p>
        <table className="docs-metrics">
          <thead>
            <tr><th>Ritning</th><th>{tr("Bet. P")}</th><th>{tr("Bet. R")}</th><th>{tr("Facit m")}</th><th>{tr("Ägda m")}</th><th>{tr("Falska m")}</th><th>{tr("Missade m")}</th></tr>
          </thead>
          <tbody>
            <tr><td>A</td><td>100 %</td><td>100 %</td><td>213,70</td><td>211,29</td><td>0,05</td><td>2,41</td></tr>
            <tr><td>C</td><td>100 %</td><td>100 %</td><td>17,60</td><td>17,38</td><td>0,00</td><td>0,23</td></tr>
            <tr><td>D</td><td>100 %</td><td>100 %</td><td>112,90</td><td>107,91</td><td>2,34</td><td>4,99</td></tr>
            <tr><td>E</td><td>100 %</td><td>100 %</td><td>50,90</td><td>49,47</td><td>0,30</td><td>1,43</td></tr>
            <tr className="sum"><td>Alla</td><td>100 %</td><td>100 %</td><td>395,10</td><td>386,05</td><td>2,70</td><td>9,06</td></tr>
          </tbody>
        </table>
        <p className="note">
          Täckning 97,7 % och falskt ägda 0,7 % — nästan allt av det senare på ritning D, där skalan själv står
          i konflikt. Av 477 beteckningar fästes 273 med verifierad ledarlinje, 28 lämnades tvetydiga och 54
          utan fäste: hållna tillbaka i stället för gissade. Siffrorna kommer ur{" "}
          <code>results/validation/metrics.py</code>, som körs på en blind körning och aldrig av motorn.
        </p>
        <p className="note">
          Tabellen mäts mot facits <b>{tr("Längd")}</b> — den utritade sträckan, som är det motorn tar fram. Facit har
          därutöver 268,40 m i en egen kolumn för stigare: antal gånger en våningshöjd som mängdaren antagit.
          Motorn räknar inte fram dem utan att få höjden, så de ingår varken i täckningen eller i felet. De står
          här för att inte försvinna ur en siffra som annars såg fullständig ut.
        </p>
      </>
    ),
  },
  {
    id: "ritningens-eget",
    h: "Vad som är ritningens eget — och vad som är kodens",
    body: (
      <>
        <p>
          En mängdningsmotor som bär på en konstant från ett kontors ritstil läser det kontoret, inte ritningar.
          Så gott som varje mått motorn arbetar med tas därför ur arket den läser.
        </p>
        <ul className="defs">
          <li>
            <b>Skalan</b> ur skalstocken och skaltexten, och de måste vara överens — annars sägs det.
          </li>
          <li>
            <b>Grammatiken</b> i beteckningarna upptäcks som mönster på sidan (<code>A9-A9-9</code> och dess
            släktingar) och räknas i frekvens. Det finns ingen inbyggd ordning system–material–dimension.
          </li>
          <li>
            <b>Beteckningslistan</b> läses på sidan när den finns, och säger vilka koder som är system och vilka
            som är objekt. Saknas den, eller ligger den på ett annat blad, faller läsningen tillbaka på
            mönsterstatistiken: listan gör läsningen säkrare, den är inget krav.
          </li>
          <li>
            <b>Glappen</b> i en streckad linje mäts på familjens egna avbrott och överbryggas bara i de avstånd
            ritningen själv använder om och om igen.
          </li>
          <li>
            <b>{tr("Hur nära två linjer får ligga")}</b> innan de läses som två sidor av ett ritat föremål sätts av
            ritningens egen penna, inte av millimeter på papper.
          </li>
          <li>
            <b>Linjetypen</b> läses — streck och glapp mäts per familj — men den delar inte familjen. I dessa
            exporter finns ingen streckkod i PDF:en alls, och när mönstret ändå byggs upp visar det sig att de
            heldragna bitarna inuti en streckad ledning är böjar och kopplingar på några tiotal punkter. Att
            dela på linjetyp skulle klippa av rör precis där de tydligast fortsätter.
          </li>
        </ul>
        <p className="note">
          Kvar som fasta tal finns PDF:ens egen räknenoggrannhet, standardens nominella rördimensioner, och
          statistiska trösklar av typen ”hur många gånger måste ritningen upprepa något innan det är ett mönster”.
          Inget av dem är hämtat från ett visst kontors stil.
        </p>
      </>
    ),
  },
  {
    id: "granser",
    h: "Vad systemet inte gör",
    body: (
      <>
        <ul className="defs">
          <li>{tr("Läser inte skannade ritningar. Utan vektorkoder finns inget att mäta.")}</li>
          <li>
            Antar ingen våningshöjd. Stigare räknas som antal tills du anger en höjd — och anger du en, följer
            det med i exporten att metrarna är antagna och inte mätta.
          </li>
          <li>{tr("Fördelar inte längden i en delad sträcka mellan systemen som delar den.")}</li>
          <li>{tr("Namnger inte geometri utifrån närhet, hur nära den än ligger.")}</li>
          <li>{tr("Låter inte en rättelse på en ritning bli en gissning på en annan.")}</li>
          <li>
            <b>{tr("Har en skala per sida, inte per ritningsdel.")}</b> Ett detaljutsnitt i egen skala mäts i planens
            skala. Motstridiga skaluppgifter redovisas som konflikt, men delas inte upp per område.
          </li>
          <li>
            <b>{tr("Överbryggar inte glapp i en böjd streckad linje.")}</b> Kurvor läses och mäts, men ett avbrott i en
            streckad kurva sluts bara där bitarna ligger på linje eller möts i ett hörn.
          </li>
          <li>
            <b>{tr("Delar inte en knippeetikett som räknar upp fler koder än ritningen ritar linjer.")}</b> Där räcker
            eliminering inte till, och fallet lämnas tvetydigt i stället för att fördelas.
          </li>
        </ul>
      </>
    ),
  },
  {
    id: "byggcad",
    h: "Ritbordet: hela byggnaden",
    body: (
      <>
        <p>
          Bredvid läsningen finns ett ritbord där en byggnad modelleras från grunden — inte bara rören. Modellen är
          en enda i millimeter: nivåer med sina egna höjder, rutnät, väggar med dörrar och fönster i sig, bjälklag,
          tak med nock, undertak, rum, trappor, pelare, balkar, grund, och installationerna — rör, kanaler,
          kabelstegar, utrustning med anslutningar. Planen och 3D-vyn är samma objekt: det som flyttas i den ena
          flyttar i den andra, och varje ändring är en transaktion som går att ångra.
        </p>
        <p className="pull">{tr("Ingen påhittad dimension. Det som inte står i modellen finns inte i filen.")}</p>
        <p>
          Mängderna räknas ur samma mått som ritar — en väggs yta är längd gånger höjd minus öppningarna, aldrig
          summan av trianglar — och servern räknar samma tal som webbläsaren, grupp för grupp. Ett material utan
          densitet ger ingen vikt. Kollisioner mellan discipliner listas med allvarlighet, och där ett rör går genom
          en vägg föreslås ett hål — som förslag, tills någon godkänner det. Snitt och fasader ritas ur modellen,
          ritningsblad får vyportar i egen skala och en namnruta, och mått som hängs på ett objekt följer det.
        </p>
        <p>
          In och ut i öppna format: IFC 4, GLB, SVG, DXF och PDF ut; DXF, SVG, IFC och referensnät (GLB, OBJ, STL)
          in, med ursprunget skrivet på varje objekt. Ett PDF-blad kan ligga som underlag — med den lästa
          handlingens skala om det är en sådan, annars uppmätt med två punkter, annars märkt som utan skala. DWG
          är ett slutet format och stöds inte; spara som DXF eller IFC.
        </p>
        <p className="note">
          Agenten vid ritbordet föreslår — en vägg med sina mått, en dörr i den, ett rum — och skriver aldrig
          själv. Saknas ett mått frågar den. Förslagen syns som spöken tills du godkänner dem.
        </p>
      </>
    ),
  },
  {
    id: "credits",
    h: "Credits – den gemensamma budgeten",
    body: (
      <>
        <p>
          Ingen köper credits och ingen läsning dras från ett eget saldo. Alla konton delar en <b>gemensam budget på
          10 000 kr</b> för det som faktiskt kostar pengar: anropen till AI-modellerna – agenten, röstsamtalet, andra
          blicken, AI-tilldelningen i analysen och AI-kontrollen av tekniska beskrivningar. Läsningen av ritningar och tekniska beskrivningar, projektanalysen,
          kalkylen, anbudet, mängdningsverktyget, CAD-rummet och exporterna ingår.
        </p>
        <p className="pull">{tr("Alla som loggar in ser samma sak: vad som är kvar, vad som använts, till vad och av vem.")}</p>
        <p>
          Under <a href="/credits">Credits</a> står taket, det använda och det som är kvar, uppdelat per del, per person
          och per modell, med filter för period och person och allt som CSV. Från 80 % ser alla en varning, och
          administratörerna får ett meddelande vid 80 %, 95 % och när budgeten är slut. Då pausas AI-funktionerna för
          alla tills taket höjs eller räkningen nollställs under Administration.
        </p>
        <p className="note">
          Ingenting i budgeten når läsningen. En kostnad kan aldrig flytta en meter.
        </p>
      </>
    ),
  },
];

export default function Docs() {
  const [active, setActive] = useState(SECTIONS[0].id);
  useEffect(() => {
    document.body.classList.add("lp-dark");
    return () => document.body.classList.remove("lp-dark");
  }, []);
  useEffect(() => {
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => e.isIntersecting && setActive(e.target.id)),
      { rootMargin: "-20% 0px -70% 0px" },
    );
    SECTIONS.forEach((s) => {
      const el = document.getElementById(s.id);
      if (el) io.observe(el);
    });
    return () => io.disconnect();
  }, []);
  const nav = useMemo(() => SECTIONS.map((s) => ({ id: s.id, h: s.h })), []);
  return (
    <div className="lp docs">
      <SiteHeader anchors={nav.map((n) => ({ href: `#${n.id}`, label: n.h }))} />

      <header className="pub-hero">
        <div className="pub-hero-in">
          <div>
            <p className="lp-eyebrow"><span className="dot" />Dokumentation</p>
            <h1 className="pub-h1">{tr("Hur systemet läser en ritning")}</h1>
            <p className="pub-lede">
              Vad som läses, i vilken ordning, vad som får bli en siffra och vad som aldrig får det.
            </p>
          </div>
        </div>
      </header>

      <div className="docs-light">
      <div className="docs-body">
        <nav className="docs-nav">
          {nav.map((n) => (
            <a key={n.id} href={`#${n.id}`} className={active === n.id ? "on" : ""}>{n.h}</a>
          ))}
        </nav>
        <main>
          {SECTIONS.map((s) => (
            <section key={s.id} id={s.id} className="docs-sec">
              <h2>{s.h}</h2>
              {s.body}
            </section>
          ))}
          <p className="docs-end">
            Frågor som inte besvaras här hör hemma i <code>docs/</code> i källkoden — där ligger rörtyperna,
            flervägsanalysen och körningarna över hela stilbiblioteket, med siffror.
          </p>
        </main>
      </div>
      </div>
    </div>
  );
}
