/* Vad plattformen består av, som innehåll i stället för som sidor.
 *
 * Startsidan visar funktionerna, och varje funktion har en egen sida. Båda läser härifrån, så en funktion kan
 * aldrig utlovas på startsidan utan att ha en sida - och en sida kan aldrig säga något annat än kortet som
 * ledde dit. Det som står här är det systemet faktiskt gör; siffrorna är uppmätta och står i results/.
 */

import { t as tr } from "./i18n";

export type Step = { n: string; h: string; p: string; art: string };
export type Key = { n: string; l: string };
export type Slab = { kicker: string; h: string; p: string; bullets?: string[]; art: string };

export type Feature = {
  slug: string;
  nav: string;            // kort namn i menyer och kort
  kicker: string;
  title: string;          // sidans rubrik, får radbrytas med \n
  lede: string;
  /** en rad på startsidans kort */
  card: string;
  art: string;            // vilken figur kortet och hjälten ritar
  accent: string;
  keys: Key[];
  slabs: Slab[];
  steps: { title: string; lede: string; items: Step[] };
  /** vart man går för att använda den */
  to: string;
  toLabel: string;
};

export const FEATURES: Feature[] = [
  {
    slug: "mangdning",
    nav: tr("Mängdning"),
    kicker: tr("Läsningen"),
    title: tr("Mängden som ritningen\nredan säger"),
    lede: tr("Ladda upp en VVS-ritning. Systemet läser bladets egen beteckningslista, följer varje hänvisningslinje till det rör den pekar på, och mäter i ritningens egen skala. Varje meter behåller sitt belägg."),
    card: tr("Beteckning, ledare, rör, skala — en mängd där varje rad går att öppna."),
    art: "read",
    accent: "#00b5e2",
    keys: [
      { n: "80,1 %", l: tr("av referensens meter återfunna över 59 uppmätta blad") },
      { n: "0", l: tr("gissningar — identitet endast via riktiga ledarlinjer") },
      { n: "589", l: tr("tester som måste hålla innan en siffra får ändras") },
    ],
    slabs: [
      {
        kicker: tr("Identitet"),
        h: tr("Ett rör får sitt namn av en linje, aldrig av närheten"),
        p: tr("Det närmaste röret är nästan alltid fel rör. För varje beteckning söks den hänvisningslinje ritaren faktiskt drog — rak, bruten, i flera delar — och den följs till sin spets. Träffar den ingenting står beteckningen kvar utan meter, och det syns."),
        bullets: [
          tr("Bladets egen förklaringslista avgör vilka koder som namnger rör"),
          tr("Texten byggs tillbaka även när CAD ritat bokstäverna som streck"),
          tr("En kontakt är inte en anslutning förrän den är verifierad"),
        ],
        art: "leader",
      },
      {
        kicker: tr("Utsträckning"),
        h: tr("Inget rör slutar tyst"),
        p: tr("Från fästpunkten följs röret genom böjar, avgreningar, exportglapp och streckmönster — bara över verifierade fysiska kopplingar. Där det slutar skrivs varför: dimensionen byter, systemet byter, geometrin tar slut, avgreningen är tvetydig."),
        bullets: [
          tr("En korsning är inte en koppling"),
          tr("Sexton skäl en sträcka kan sluta av, alla utskrivna"),
          tr("Det tvetydiga står som tvetydigt och mäts inte"),
        ],
        art: "frontier",
      },
      {
        kicker: tr("Mätning"),
        h: tr("Skalan tas ur bladet, aldrig ur ett antagande"),
        p: tr("Stämpel, skalstock eller måttsättning — och när de är oense står konflikten kvar i svaret. Rör som ligger i skrafferad vägg redovisas för sig, så du själv väljer om de ska räknas. Vertikalt utan höjdbesked står som okänt, inte som noll."),
        bullets: [
          tr("Två parallella linjer som ritar ett rör blir ett rör"),
          tr("Skrafferad vägg hittas oavsett hur kontoret lagt sina lager"),
          tr("Ingen mätning på bildpunkter: en skannad PDF avvisas med besked"),
        ],
        art: "scale",
      },
    ],
    steps: {
      title: tr("Från streck till meter"),
      lede: tr("Sex steg, i den ordning motorn faktiskt går."),
      items: [
        { n: "01", h: tr("Ritningen öppnas som vektorer"), p: tr("Varje streck med sin penna, färg, sitt lager och sin streckning."), art: "read" },
        { n: "02", h: tr("Bladet får en profil"), p: tr("Vilka pennor, texter, streckmönster och ritsätt just det här bladet använder."), art: "read" },
        { n: "03", h: tr("Beteckningarna läses"), p: tr("Text där det är text, återbyggda tecken där CAD ritat dem som streck."), art: "leader" },
        { n: "04", h: tr("Ledarna följs"), p: tr("Från varje beteckning till det rör linjen pekar på, och ingen annanstans."), art: "leader" },
        { n: "05", h: tr("Röret följs ut"), p: tr("Genom böjar och grenar, bara över kopplingar som går att belägga."), art: "frontier" },
        { n: "06", h: tr("Mängden skrivs"), p: tr("Med skalan ur bladet och belägget kvar för varje rad."), art: "scale" },
      ],
    },
    to: "/login",
    toLabel: tr("Läs en ritning"),
  },
  {
    slug: "cad",
    nav: tr("CAD"),
    kicker: tr("Ritbordet"),
    title: tr("Rita hela byggnaden,\ninte bara rören"),
    lede: tr("Ett fullständigt CAD-rum i webbläsaren: väggar, dörrar, fönster, bjälklag, tak, rum och trappor; pelare, balkar, plattor och grund; rör, kanaler, kabelstegar och utrustning med sina anslutningar."),
    card: tr("Väggar, stomme och installationer i en modell — med mängder som följer med."),
    art: "cad",
    accent: "#60a5fa",
    keys: [
      { n: "7", l: tr("faser byggda: arkitektur, konstruktion, vyer, MEP, mängder, import, export") },
      { n: "2D ↔ 3D", l: tr("samma modell, synkad åt båda håll") },
      { n: "IFC", l: tr("in och ut, tillsammans med DXF, SVG och GLB") },
    ],
    slabs: [
      {
        kicker: tr("Modellen"),
        h: tr("En byggnad, inte en samling streck"),
        p: tr("Nivåer, rutnät och lager håller ihop det. En vägg vet att den är en vägg, ett rum vet vilka väggar som omsluter det, och ett rör vet vad det är anslutet till. Därför kan mängderna räknas ur modellen i stället för att mätas av den."),
        bullets: [
          tr("Ångra och gör om genom hela sessionen"),
          tr("Revisioner sparas, ingenting skrivs över"),
          tr("Kommandorad för den som hellre skriver än klickar"),
        ],
        art: "cadmodel",
      },
      {
        kicker: tr("Vyerna"),
        h: tr("Plan, sektion, fasad och 3D — samma modell"),
        p: tr("Ändra i planen och sektionen följer med. Måttsättning och annotering hör till vyn, inte till geometrin, så ett mått ljuger aldrig om modellen. Blad läggs ut för utskrift när ritningen ska lämna skärmen."),
        bullets: [
          tr("3D-editor byggd på three.js"),
          tr("Kollisionskontroll mellan installation och stomme"),
          tr("Underlag från PDF, bild eller DXF att rita ovanpå"),
        ],
        art: "views",
      },
    ],
    steps: {
      title: tr("Så kommer du igång"),
      lede: tr("Från tomt blad till en modell med mängder."),
      items: [
        { n: "01", h: tr("Lägg upp nivåer och rutnät"), p: tr("Våningshöjder och axlar först — allt annat hänger på dem."), art: "cad" },
        { n: "02", h: tr("Rita eller importera stommen"), p: tr("Väggar och bjälklag för hand, eller ett underlag att rita ovanpå."), art: "cadmodel" },
        { n: "03", h: tr("Dra installationerna"), p: tr("Rör, kanaler och stegar med sina anslutningar och dimensioner."), art: "views" },
        { n: "04", h: tr("Läs av mängderna"), p: tr("De räknas ur modellen och uppdateras medan du ritar."), art: "cadmodel" },
      ],
    },
    to: "/cad",
    toLabel: tr("Öppna CAD-rummet"),
  },
  {
    slug: "3d",
    nav: tr("3D"),
    kicker: tr("Modellen"),
    title: tr("Se ritningen\nsom en byggnad"),
    lede: tr("När läsningen är klar reser sig planen. Rören lyfter från pappret med sina höjder, stigarna går genom bjälklagen, och du ser var systemet faktiskt går — inte bara var linjerna ligger."),
    card: tr("Planen reser sig: rör med höjd, stigare genom bjälklag, system för system."),
    art: "three",
    accent: "#a78bfa",
    keys: [
      { n: "1 klick", l: tr("från mängdtabellen till samma rör i modellen") },
      { n: "Per system", l: tr("tänd och släck KV, VV, VS, spill var för sig") },
      { n: "Höjder", l: tr("ur bladets egna CL- och VG-angivelser") },
    ],
    slabs: [
      {
        kicker: tr("Sambandet"),
        h: tr("Samma rör i tabellen och i rummet"),
        p: tr("Markera en rad i mängden och röret tänds i modellen. Klicka i modellen och raden rullar fram. Det är samma geometri hela vägen — ingen separat modell som kan hamna ur fas med mängden."),
        bullets: [
          tr("Lager att tända och släcka per system"),
          tr("Stigare ritas som stigare, inte som punkter"),
          tr("Det tvetydiga syns i sin egen färg"),
        ],
        art: "link3d",
      },
    ],
    steps: {
      title: tr("Så används den"),
      lede: tr("Tre saker 3D-vyn är bra på."),
      items: [
        { n: "01", h: tr("Förstå ett schakt"), p: tr("Var stigarna går och hur många de är, på en gång."), art: "three" },
        { n: "02", h: tr("Hitta det orimliga"), p: tr("Ett rör som går genom ett bjälklag där inget schakt finns syns direkt."), art: "link3d" },
        { n: "03", h: tr("Visa någon annan"), p: tr("En modell övertygar en beställare snabbare än en tabell."), art: "three" },
      ],
    },
    to: "/login",
    toLabel: tr("Se en läsning i 3D"),
  },
  {
    slug: "mangda",
    nav: tr("Mängda"),
    kicker: tr("För hand"),
    title: tr("Mängda själv,\nmed verktyg som håller"),
    lede: tr("Ibland ska man mäta för hand: en handling som inte är vektor, en del motorn lämnar tvetydig, eller en kontroll av det som redan lästs. Verktyget är byggt för att stå i nivå med det en mängdare är van vid."),
    card: tr("Kalibrering, fångst, ortho, avdrag och en markeringslista som går att redigera."),
    art: "measure",
    accent: "#fbbf24",
    keys: [
      { n: "Kalibrering", l: tr("mot ett känt mått på bladet") },
      { n: "Fångst", l: tr("mot ändpunkt, mitt, skärning och ortho") },
      { n: "Avdrag", l: tr("ytor och längder som ska bort ur summan") },
    ],
    slabs: [
      {
        kicker: tr("Arbetsbordet"),
        h: tr("Ritningen är sidan, inte en panel bland andra"),
        p: tr("PDF:en tar hela ytan. Verktygslådan ligger i kanten, markeringslistan i en egen flik, och det du mätt står kvar mellan sessionerna. Mätningar du gör kan läggas bredvid motorns egna, så de går att jämföra rad för rad."),
        bullets: [
          tr("Längd, area, antal och djup"),
          tr("Redigera en markering i efterhand, inte rita om den"),
          tr("Exporteras tillsammans med den lästa mängden"),
        ],
        art: "bench",
      },
    ],
    steps: {
      title: tr("Så mäter du"),
      lede: tr("Fyra steg, samma som på papper."),
      items: [
        { n: "01", h: tr("Kalibrera"), p: tr("Dra längs ett känt mått och skriv vad det är."), art: "measure" },
        { n: "02", h: tr("Välj verktyg"), p: tr("Längd, area, antal — och fångst om linjerna ska mötas exakt."), art: "measure" },
        { n: "03", h: tr("Mät"), p: tr("Ortho håller linjen rak när ritningen är det."), art: "bench" },
        { n: "04", h: tr("Rätta och räkna"), p: tr("Justera det som blev fel och läs summan per grupp."), art: "bench" },
      ],
    },
    to: "/mangda",
    toLabel: tr("Öppna mängdningen"),
  },
  {
    slug: "agent",
    nav: tr("Agenten"),
    kicker: tr("Samtalet"),
    title: tr("Fråga ritningen,\nfå svar med belägg"),
    lede: tr("Släpp in en PDF i samtalet och fråga. Agenten svarar ur det som står i handlingen, säger vad den inte kunde avgöra, och hittar aldrig på en siffra. Samma motor som analysen, samma artefakter, samma credits."),
    card: tr("Släpp in en ritning och fråga. Svaret kommer ur handlingen, inte ur en gissning."),
    art: "agent",
    accent: "#f0abfc",
    keys: [
      { n: "Verktyg", l: tr("modellen väljer frågan, verktygen svarar ur det lästa") },
      { n: "Ingen geometri", l: tr("en språkmodell får aldrig hitta på koordinater eller meter") },
      { n: "Spårbart", l: tr("varje verktygsanrop går att fälla ut och läsa") },
    ],
    slabs: [
      {
        kicker: tr("Gränsen"),
        h: tr("Modellen väljer frågan — ritningen ger svaret"),
        p: tr("Agenten får välja vilken fråga som ställs till bladet och hur svaret formuleras. Den får aldrig välja ett tal. Alla siffror kommer ur samma deterministiska läsning som mängdtabellen, och en siffra utan belägg blir «det står inte i handlingen»."),
        bullets: [
          tr("Jämför två blad mot varandra"),
          tr("Fråga varför en rad ser ut som den gör"),
          tr("Starta en läsning mitt i samtalet"),
        ],
        art: "chat",
      },
    ],
    steps: {
      title: tr("Bra frågor att börja med"),
      lede: tr("Fyra som visar vad den är till för."),
      items: [
        { n: "01", h: tr("Vad är det här för blad?"), p: tr("System, skala, vad handlingen omfattar."), art: "agent" },
        { n: "02", h: tr("Visa mängderna"), p: tr("Rad för rad, med det som inte kunde avgöras för sig."), art: "chat" },
        { n: "03", h: tr("Vad kunde inte avgöras?"), p: tr("Listan över det tvetydiga, och varför."), art: "chat" },
        { n: "04", h: tr("Vad kostar rören?"), p: tr("Mot materialboken, med priserna synliga."), art: "agent" },
      ],
    },
    to: "/agent",
    toLabel: tr("Öppna agenten"),
  },
  {
    slug: "kalkyl",
    nav: tr("Kalkyl"),
    kicker: tr("Anbudet"),
    title: tr("Från mängd\ntill anbud"),
    lede: tr("Mängden är halva jobbet. Kalkylen tar rören, lägger på material, arbete och påslag, och gör ett anbud du kan granska i webbläsaren innan det lämnar huset — neutralt mot AB 04 och ABT 06."),
    card: tr("Material, arbete och påslag ovanpå mängden — och ett anbud att granska på skärmen."),
    art: "calc",
    accent: "#fb923c",
    keys: [
      { n: "Materialbok", l: tr("priser per beteckning, som du kan flytta") },
      { n: "AB 04 / ABT 06", l: tr("avtalsformen bor i kalkylen, aldrig i geometrin") },
      { n: "Förhandsgranskning", l: tr("anbudet sida för sida innan det laddas ner") },
    ],
    slabs: [
      {
        kicker: tr("Uppdelningen"),
        h: tr("Geometrin är neutral, kalkylen tar ställning"),
        p: tr("Samma ritning ger samma rör oavsett entreprenadform. Det är först i kalkylen avtalsformen betyder något, och det är därför en ändring där aldrig kan flytta en meter i mängden."),
        bullets: [
          tr("Påslag per post eller över hela anbudet"),
          tr("Arbetstid per meter och dimension"),
          tr("Exporteras som PDF och som kalkylblad"),
        ],
        art: "tender",
      },
    ],
    steps: {
      title: tr("Så byggs anbudet"),
      lede: tr("Fyra steg från läst ritning till lämnat pris."),
      items: [
        { n: "01", h: tr("Mängden in"), p: tr("Rören som lästes, med det tvetydiga markerat."), art: "calc" },
        { n: "02", h: tr("Material på"), p: tr("Ur materialboken, med priser du själv styr."), art: "calc" },
        { n: "03", h: tr("Arbete och påslag"), p: tr("Per post eller över hela anbudet."), art: "tender" },
        { n: "04", h: tr("Granska och lämna"), p: tr("Sida för sida på skärmen, sedan som PDF."), art: "tender" },
      ],
    },
    to: "/login",
    toLabel: tr("Öppna kalkylen"),
  },
  {
    slug: "utbildning",
    nav: tr("Utbildning"),
    kicker: tr("VVS-akademin"),
    title: tr("Lär dig läsa ritningen,\ninte bara mängda den"),
    lede: tr("Nio kurser och tjugotvå föreläsningar, från vad ett VVS-system är till att mängda ett övningsblad själv och få det rättat. Varje föreläsning har en egen sida, en levande figur och en kontrollfråga."),
    card: tr("Nio kurser om att läsa en rörritning — med figurer som rör sig och övningar som rättas."),
    art: "learn",
    accent: "#67e8f9",
    keys: [
      { n: "9", l: tr("kurser i den ordning de bygger på varandra") },
      { n: "22", l: tr("föreläsningar, var och en med en egen sida") },
      { n: "2 h", l: tr("sammanlagt, gjort för att gå i småbitar") },
    ],
    slabs: [
      {
        kicker: tr("Formen"),
        h: tr("Byggd för att göras, inte bläddras i"),
        p: tr("Varje föreläsning visar det den handlar om som en levande ritning i stället för att beskriva det i ord, och avslutas med en fråga som går att svara fel på. Övningarna använder samma slags blad som tjänsten läser — ingen av dem går att klara genom att gissa på det som ligger närmast."),
        bullets: [
          tr("Stegen sparas på kontot, inte i webbläsaren"),
          tr("Läs utan konto, spara med"),
          tr("Samma kurs för hela kontoret"),
        ],
        art: "academy",
      },
    ],
    steps: {
      title: tr("Vad du kan efteråt"),
      lede: tr("Fyra saker kursen faktiskt lär ut."),
      items: [
        { n: "01", h: tr("Läsa en beteckning"), p: tr("System, material, dimension och isolering på tre sekunder."), art: "learn" },
        { n: "02", h: tr("Hitta i bladet"), p: tr("Namnruta, förklaringslista, skalstock, sektioner."), art: "academy" },
        { n: "03", h: tr("Mängda i ordning"), p: tr("Vad som räknas, vad som inte gör det, och varför."), art: "learn" },
        { n: "04", h: tr("Granska en maskinmängd"), p: tr("Se var den är säker och var den inte är det."), art: "academy" },
      ],
    },
    to: "/utbildning",
    toLabel: tr("Till akademin"),
  },
];

export const featureBySlug = (slug?: string) => FEATURES.find((f) => f.slug === slug) ?? null;
