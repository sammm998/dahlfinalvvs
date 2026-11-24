/* Guiden: varje sak man kan göra i tjänsten, var den finns och hur den går till. Samma lista visas på
 * Kom igång-sidan (med knappar som tar en dit) och i dokumentationen (som text). Lägg till en rad här när en
 * funktion läggs till, så finns den på båda ställena. */

export type GuideAction =
  | { kind: "quick"; discipline: string; then: "analysis" | "radiators" }   // ladda upp en ritning och läs den
  | { kind: "project"; anchor: string }                                     // öppna en del av ett projekt
  | { kind: "project-analysis" }                                            // hela handlingen i ett projekt
  | { kind: "link"; to: string };                                           // en egen sida i tjänsten

export type GuideTask = {
  id: string;
  title: string;
  what: string;          // vad man får
  need: string;          // vad man behöver ha
  where: string;         // var det finns i menyerna
  steps: string[];       // så går det till
  action: GuideAction;
  admin?: boolean;
};

export type GuideGroup = { id: string; title: string; lede: string; tasks: GuideTask[] };

const pdfSteps = (_disc: string) => [
  "Välj eller skapa ett projekt.",
  "Ladda upp ritningen (PDF från CAD, eller bild/skanning) och välj vad den ska läsas som.",
  "Tryck Analysera och välj läsare. Läsningen tar från någon minut upp till en halvtimme per blad.",
  "Granska resultatet: allt som är osäkert står för sig. Exportera till Excel, CSV eller markerad PDF.",
];

export const GUIDE: GuideGroup[] = [
  {
    id: "ritningar",
    title: "Mängda ur ritningar",
    lede: "Ladda upp en ritning och välj vad den ska läsas som. Samma uppladdning fungerar för alla discipliner.",
    tasks: [
      {
        id: "vvs", title: "Rör ur VVS-ritning", action: { kind: "quick", discipline: "vvs", then: "analysis" },
        what: "Meter rör per system och dimension, horisontellt och vertikalt, med belägg för varje meter.",
        need: "VS-ritning som PDF (helst exporterad ur CAD).",
        where: "Projekt → projektet → Ladda upp → Analysera",
        steps: pdfSteps("VVS"),
      },
      {
        id: "radiatorer", title: "Radiatorer och Altech-korsning", action: { kind: "quick", discipline: "vvs", then: "radiators" },
        what: "Radiatorer per hus med projekterad effekt, flöde och Kv, korsade mot Altech med skillnad i effekt, längd och höjd och Dahls priser.",
        need: "VS-planritning som PDF där radiatorerna är märkta (t.ex. TPv4 22-218 med 650W-57l/h-Kv0,25).",
        where: "Ritningen → Radiatorer och Altech-korsning, eller fliken Radiatorer i analysen",
        steps: [
          "Välj eller skapa ett projekt och ladda upp VS-ritningen.",
          "Radiatorerna läses direkt – ingen analys behövs. Välj temperaturer och vad som väger tyngst när Altech saknar storleken.",
          "Öppna Detaljer för en rad för att se varför Altech-modellen valdes och alternativen.",
          "Ladda ner Excel: sammanställning per hus, detaljlista, korsning, alternativ och källor.",
        ],
      },
      {
        id: "el", title: "El", action: { kind: "quick", discipline: "el", then: "analysis" },
        what: "Symboler och apparater i styck per beteckning; kabelstegar och ledningar med bredd i meter där en etikett namnger dem.",
        need: "El-ritning som PDF.",
        where: "Projekt → Ladda upp → Läs som: El → Analysera",
        steps: pdfSteps("El"),
      },
      {
        id: "ventilation", title: "Ventilation", action: { kind: "quick", discipline: "ventilation", then: "analysis" },
        what: "Kanaler per system och dimension (Ø och b×h) i meter; don, spjäll och aggregat i styck.",
        need: "Ventilationsritning som PDF.",
        where: "Projekt → Ladda upp → Läs som: Ventilation → Analysera",
        steps: pdfSteps("Ventilation"),
      },
      {
        id: "sprinkler", title: "Sprinkler", action: { kind: "quick", discipline: "sprinkler", then: "analysis" },
        what: "Sprinklerrör i meter med systemkoderna ur förklaringslistan; huvuden och ventilstationer i styck.",
        need: "Sprinklerritning som PDF.",
        where: "Projekt → Ladda upp → Läs som: Sprinkler → Analysera",
        steps: pdfSteps("Sprinkler"),
      },
      {
        id: "kyla", title: "Kyla", action: { kind: "quick", discipline: "kyla", then: "analysis" },
        what: "Köldbärare och kylmedel (KB, KM, KP) i meter; aggregat och komponenter i styck.",
        need: "Kylritning som PDF.",
        where: "Projekt → Ladda upp → Läs som: Kyla → Analysera",
        steps: pdfSteps("Kyla"),
      },
      {
        id: "bygg", title: "Bygg – rum och ytor", action: { kind: "quick", discipline: "bygg", then: "analysis" },
        what: "Rum med area ur rumsetiketterna (m²); dörrar, fönster och andra beteckningar i styck.",
        need: "Planritning (A) som PDF.",
        where: "Projekt → Ladda upp → Läs som: Bygg → Analysera",
        steps: pdfSteps("Bygg"),
      },
      {
        id: "alla", title: "Allt bladet skriver", action: { kind: "quick", discipline: "alla", then: "analysis" },
        what: "Varje beteckning på bladet oavsett disciplin: rören mäts som i VVS, allt annat listas, markeras och räknas.",
        need: "Vilken ritning som helst som PDF.",
        where: "Projekt → Ladda upp → Läs som: Alla → Analysera → fliken Alla beteckningar",
        steps: pdfSteps("Alla"),
      },
    ],
  },
  {
    id: "projektet",
    title: "Från mängd till offert och projekt",
    lede: "Det här görs i ett projekt, med det som redan är uppladdat och läst.",
    tasks: [
      {
        id: "offert", title: "Offert ur mängden", action: { kind: "project", anchor: "offert" },
        what: "Offert med Dahls artiklar och priser (netto efter kundens rabatter) ur projektets mängder och material.",
        need: "Minst en analyserad ritning eller materiallista. Dahls prisfil uppladdad (Offert → Offertdata).",
        where: "Projekt → projektet → Offert",
        steps: ["Öppna projektet och delen Offert.", "Välj kund – rabatterna hämtas.", "Gå igenom raderna: osäkra artikelval är markerade och kan bytas.", "Exportera offerten (Excel eller kundversion)."],
      },
      {
        id: "handling", title: "Hela handlingen på en gång", action: { kind: "project-analysis" },
        what: "Vad handlingen består av: blad, discipliner, revisioner och vad som saknas, innan något mängdas.",
        need: "Projektets ritningar uppladdade.",
        where: "Projekt → projektet → Analysera projektet",
        steps: ["Ladda upp alla blad i projektet.", "Tryck Analysera projektet.", "Välj vilka blad som ska mängdas."],
      },
      {
        id: "material", title: "Material ur IFC-modell eller materiallista", action: { kind: "project", anchor: "material" },
        what: "VVS-material ur en IFC-modell, eller ur en materiallista (Excel, CSV, Word, e-post), matchat mot Dahls katalog.",
        need: "IFC-fil (.ifc/.zip) eller en materiallista.",
        where: "Projekt → projektet → Ladda upp (IFC eller lista) → Material",
        steps: ["Ladda upp filen i projektet – IFC och listor känns igen själva.", "Granska matchningen mot Dahls artiklar.", "För över till offerten."],
      },
      {
        id: "smarthangers", title: "SmartHangers – prefabricerade upphängningar", action: { kind: "project", anchor: "smarthangers" },
        what: "Varje upphängning med läge, gängstångslängd, ankare, last, materiallista, QR-etikett och montageguide.",
        need: "VS-modell som IFC. Gärna också K-modell (bjälklag) och A-modell (väggar, undertak).",
        where: "Projekt → projektet → SmartHangers → Modellpaket",
        steps: ["Ladda upp VS, K och A tillsammans som modellpaket.", "Kontrollrapporten V1–V11 visar vad som saknas. Saknas K-modellen: ange takhöjd per våning eller uppskatta.", "Granska i planvyn och tabellen, godkänn.", "Exportera punktlista, artikellista, IFC, BCF, DXF och etiketter."],
      },
      {
        id: "abt", title: "ABT 06 – rum, krav och teknisk beskrivning", action: { kind: "project", anchor: "abt" },
        what: "Rum och utrustning ur ritningarna, kraven ur den tekniska beskrivningen och vad som ska ingå.",
        need: "Projekt med entreprenadform ABT 06, ritningar och/eller teknisk beskrivning.",
        where: "Projekt → projektet (ABT 06) → Teknisk beskrivning / ABT",
        steps: ["Skapa projektet som ABT 06 (eller byt under Ändra).", "Ladda upp den tekniska beskrivningen och ritningarna.", "Gå igenom rummen och kraven."],
      },
    ],
  },
  {
    id: "verktyg",
    title: "Verktyg",
    lede: "Egna sidor i menyn till vänster.",
    tasks: [
      {
        id: "mangda", title: "Mängda för hand", action: { kind: "link", to: "/mangda" },
        what: "Mät och räkna själv direkt på en PDF: längder, ytor och styck, med skala.",
        need: "En ritning.", where: "Menyn → Mängda", steps: ["Öppna Mängda och välj ritning.", "Sätt skalan.", "Mät och räkna – resultatet går att exportera."],
      },
      {
        id: "cad", title: "CAD och ritbord", action: { kind: "link", to: "/cad" },
        what: "Rita och granska i webbläsaren, eller bygg upp en hel byggnad och mängda ur den.",
        need: "Inget – eller en ritning att utgå från.", where: "Menyn → CAD", steps: ["Öppna CAD.", "Välj blad eller starta nytt."],
      },
      {
        id: "agent", title: "Agenten", action: { kind: "link", to: "/agent" },
        what: "Fråga om projektet, ritningarna eller VVS i vanlig text.",
        need: "Inget.", where: "Menyn → Agent", steps: ["Skriv din fråga."],
      },
      {
        id: "katalog", title: "Material och priser", action: { kind: "link", to: "/material" },
        what: "Sök i Dahls katalog med priser ur prisfilen.",
        need: "Inget.", where: "Menyn → Material", steps: ["Sök på benämning, RSK eller artikelnummer."],
      },
      {
        id: "lar", title: "Lär dig VVS", action: { kind: "link", to: "/lar" },
        what: "Kurser om ritningar, system och mängdning, med övningar och certifikat.",
        need: "Inget.", where: "Menyn → Lär dig VVS", steps: ["Välj en kurs och börja."],
      },
      {
        id: "credits", title: "Credits och budget", action: { kind: "link", to: "/credits" },
        what: "Vad läsningarna kostar och vad som är kvar av den gemensamma budgeten.",
        need: "Inget.", where: "Menyn → Credits", steps: ["Se förbrukning per analys."],
      },
      {
        id: "prisfil", title: "Prisfil och offertdata (administratör)", action: { kind: "project", anchor: "offert" }, admin: true,
        what: "Dahls prisfil (artiklar och grundrabatter), kunder och rabatter som offerter och korsningar räknar med.",
        need: "Administratörsroll.", where: "Projekt → valfritt projekt → Offert → Offertdata", steps: ["Öppna delen Offertdata.", "Ladda upp prisfilen (Excel med båda flikarna: artiklar och grundrabatter).", "Ladda upp kunder och rabatter. Det gäller alla projekt."],
      },
    ],
  },
];

export const QUICK_TASKS = GUIDE.flatMap((g) => g.tasks).filter((t) => t.action.kind === "quick");
