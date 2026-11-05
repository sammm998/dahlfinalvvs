/* Akademins ram - kursinnehållet är på svenska, se docs/SPRAK.md §7
 *
 * En rad per sträng, svensk nyckel först. Saknas en rad visas svenskan.
 */
export const akademi: Record<string, string> = {

  // --- akademins ram --------------------------------------------------------------------------------------
  "Lär dig läsa och mängda en rörritning": "Learn to read and take off a pipe drawing",
  "Ritningens delar, en i taget": "The parts of the drawing, one at a time",
  "Tillbaka till Academy": "Back to Academy",
  "Tillbaka till akademin": "Back to the academy",
  "Tillbaka till utbildningen": "Back to the training",
  "Tillbaka till utbildningarna": "Back to the courses",
  "← Tillbaka": "← Back",
  "Andra kurser": "Other courses",
  "Nästa kurs": "Next course",
  "Föregående kurs": "Previous course",
  "Föregående": "Previous",
  "Nästa lektion →": "Next lesson →",
  "Sista föreläsningen": "The last lecture",
  "Markera som läst": "Mark as read",
  "Var du är": "Where you are",
  "Din nivå": "Your level",
  "Senaste aktivitet": "Latest activity",
  "Utmärkelser": "Awards",
  "Övningar gjorda": "Exercises done",
  "upp till 50 XP": "up to 50 XP",
  "Låst": "Locked",
  "· låst": "· locked",
  "Öppna ändå": "Open anyway",
  "Logga in för att spara var du är.": "Sign in to save where you are.",
  "Hämtar utbildningen…": "Loading the training…",
  "Hämtar lektionen…": "Loading the lesson…",
  "Hämtar ditt läge…": "Loading your progress…",
  "Hämtar frågor…": "Loading questions…",
  "Hämtar certifikatet…": "Loading the certificate…",
  "Förbereder tentan…": "Preparing the exam…",
  "Till verktyget": "To the tool",

  // --- övningar och prov ----------------------------------------------------------------------------------
  "Öva": "Practise",
  "Öva själv": "Practise on your own",
  "Kontrollfråga": "Check question",
  "Ditt svar": "Your answer",
  "Rätta": "Mark",
  "Rätt mängd": "Correct quantity",
  "Din mängd": "Your quantity",
  "Att veta": "Worth knowing",
  "Börja om": "Start over",
  "Gör ett nytt quiz": "Take a new quiz",
  "Skriv sluttentan": "Sit the final exam",
  "Svaren sparas automatiskt": "Answers are saved automatically",
  "Godkända": "Passed",
  "Alla utplacerade.": "All placed.",
  "Den här övningstypen kan inte visas här.": "This exercise type cannot be shown here.",
  "Klicka en symbol, klicka sedan dess namn. Klicka krysset för att lossa ett par.":
    "Click a symbol, then click its name. Click the cross to unpair.",
  "Klicka på symbolerna · Tabb och Enter fungerar också":
    "Click the symbols · Tab and Enter work too",
  "Övningsblad med fyra sträckor": "Practice sheet with four runs",
  "4 STRÄCKOR": "4 RUNS",
  "Läs av sträckan": "Read off the run",
  "Sträcka": "Run",
  "Mängd": "Quantity",
  "Område": "Area",
  "1 st": "1",
  "2 st": "2",
  "3 st": "3",

  // --- certifikatet ---------------------------------------------------------------------------------------
  "Dina certifikat": "Your certificates",
  "Öppna certifikatet": "Open the certificate",
  "Certificate of Competence": "Certificate of Competence",
  "Härmed intygas att": "This is to certify that",
  "har genomfört och godkänts i": "has completed and passed",
  "Utfärdat": "Issued",
  "Giltigt till": "Valid until",
  "Kopiera ID": "Copy the ID",
  "Skriv ut / spara som PDF": "Print / save as PDF",
  "Spara som PDF": "Save as PDF",
  "Verifiera ett Dahl-certifikat": "Verify a Dahl certificate",
  "Du är Dahl Certified. Certifikatet är utfärdat och går att verifiera med sitt id.":
    "You are Dahl Certified. The certificate is issued and can be verified by its id.",

  // --- figurerna: beteckningen ----------------------------------------------------------------------------
  "Beteckningen KV1-X31-16 byggs ihop av sina tre delar":
    "The designation KV1-X31-16 is built from its three parts",
  "SYSTEM · tappkallvatten 1": "SYSTEM · cold tap water 1",
  "MATERIAL · står i bladets lista": "MATERIAL · stated in the sheet's legend",
  "DIMENSION · 16 mm": "DIMENSION · 16 mm",
  "BLADETS EGEN FÖRKLARINGSLISTA": "THE SHEET'S OWN LEGEND",
  "Förklaringslistan säger vad varje kod är": "The legend says what each code is",
  "Listan är bladets": "The legend belongs to the sheet",
  "bladets förklaringslista säger vilket varje kod är": "the sheet's legend says which each code is",
  "En omgång skriver": "One office writes",
  "den en gång, på ett": "it once, on one",
  "blad, och låter": "sheet, and lets",
  "resten stå på den.": "the rest rely on it.",
  "eget ordförråd.": "own vocabulary.",
  "Systemkoder öppnar dimensionerade beteckningar, komponentkoder står ensamma":
    "System codes open dimensioned designations, component codes stand alone",
  "MED DIMENSION, OCH EN LINJE TILL ETT RÖR → RÖRSYSTEM":
    "WITH A DIMENSION, AND A LINE TO A PIPE → PIPE SYSTEM",
  "STÅR ENSAM UTE PÅ BLADET → KOMPONENT": "STANDS ALONE OUT ON THE SHEET → COMPONENT",

  // --- figurerna: hänvisningslinjen och stigaren ----------------------------------------------------------
  "En hänvisningslinje som träffar röret, och en som inte gör det":
    "A leader that hits the pipe, and one that does not",
  "slutar PÅ röret — sträckan får sitt namn": "ends ON the pipe — the run gets its name",
  "slutar i luften — sträckan blir onämnd": "ends in mid-air — the run stays unnamed",
  "skillnaden mellan en sträcka": "the difference between a run",
  "som räknas och en som inte gör det.": "that counts and one that does not.",
  "En rad betyder sträcka, två rader betyder stigare": "One row means a run, two rows mean a riser",
  "ALLT PÅ EN RAD": "ALL ON ONE ROW",
  "DIMENSIONEN PÅ RADEN UNDER": "THE DIMENSION ON THE ROW BELOW",
  "en sträcka i planet": "a run in the plan",
  "dimensionen på raden under → stigare": "the dimension on the row below → riser",
  "en stigare i den punkten": "a riser at that point",
  "två rader i mängden, inte en.": "two rows in the quantity, not one.",
  "En ring i planen är en ledning som går mellan våningar":
    "A ring in the plan is a pipe running between storeys",
  "En stigare är en punkt i planen och en höjd i sektionen":
    "A riser is a point in the plan and a height in the section",
  "I PLANEN — EN PUNKT": "IN THE PLAN — A POINT",
  "I HUSET — EN HÖJD": "IN THE BUILDING — A HEIGHT",
  "stigare — höjd matas in": "riser — height entered by hand",
  "× våningshöjd": "× storey height",
  "räknas som antal": "counted as a number",
  "mäts i meter": "measured in metres",
  "höjden står inte på ritningen — antalet räknas, höjden matas in":
    "the height is not on the drawing — the count is read, the height is entered",
  "ritningen anger nästan aldrig höjden — antalet räknas, höjden matas in":
    "the drawing almost never states the height — the count is read, the height is entered",

  // --- figurerna: dimension, isolering, bunt, skalstock ---------------------------------------------------
  "DN mäter ungefär insidan, dy mäter utsidan": "DN measures roughly the inside, dy the outside",
  "DN — insida": "DN — inside",
  "DN — ungefär insidan": "DN — roughly the inside",
  "dy — utsida": "dy — outside",
  "dy — ytterdiameter": "dy — outer diameter",
  "För ögat är skillnaden": "To the eye the difference is",
  "några millimeter.": "a few millimetres.",
  "För en mängdning är den": "For a take-off it is",
  "samma tal, två olika mått — fel material i kalkylen, inte fel längd":
    "the same number, two different measures — the wrong material in the costing, not the wrong length",
  "plast och koppar": "plastic and copper",
  "stål och gjutjärn": "steel and cast iron",
  "Isoleringen ligger utanpå röret och ändrar inte dimensionen":
    "The insulation sits outside the pipe and does not change the dimension",
  "Isolerklassen står i beteckningen,": "The insulation class is in the designation,",
  "Den ändrar inte dimensionen,": "It does not change the dimension,",
  "och den ändrar inte metrarna.": "and it does not change the metres.",
  "Den säger hur tjockt skalet är.": "It says how thick the shell is.",
  "Ett rör med två isolerklasser är": "A pipe with two insulation classes is",
  "Kallvatten, varmvatten och cirkulation dras i bunt":
    "Cold water, hot water and circulation run in a bundle",
  "KV — fram till tappstället": "KV — up to the tap point",
  "VV — fram till tappstället": "VV — up to the tap point",
  "VVC — tillbaka, så varmvattnet inte kallnar": "VVC — back, so the hot water does not go cold",
  "Tre parallella rör och en etikett med hänvisningslinje":
    "Three parallel pipes and one label with a leader",
  "i schaktet ligger de några cm isär — bara etiketten skiljer dem åt":
    "in the shaft they lie a few cm apart — only the label tells them apart",
  "Skalstocken följer pappret, den utskrivna skalan gör det inte":
    "The scale bar follows the paper, the printed scale does not",
  "Skalstocken ligger på samma papper och kan inte ljuga.":
    "The scale bar is on the same paper and cannot lie.",
  "Den utskrivna skalan står kvar och blir fel.": "The printed scale stays put and becomes wrong.",
  "SKALSTOCK · 5 M": "SCALE BAR · 5 M",
  "Tre sträckor och en skalstock": "Three runs and a scale bar",
  "En sträcka spåras och metrarna räknas fram": "A run is traced and the metres are counted out",
  "krympte med — den gäller": "shrank by — it holds",
  "men pappret är halverat": "but the paper is halved",

  // --- figurerna: lager, självfall, egenkontroll -----------------------------------------------------------
  "Varje sorts geometri på sitt eget lager": "Each kind of geometry on its own layer",
  "ett lager per system — och byggnaden för sig": "one layer per system — and the building on its own",
  "Tryckledningar går åt alla håll, självfall måste luta":
    "Pressure pipes run in any direction, gravity drains must fall",
  "Vatten faller i stammen medan luft går upp genom den":
    "Water falls in the stack while air rises through it",
  "Fyra egenkontroller som fångar nästan alla fel":
    "Four self-checks that catch almost every error",
  "en balans som halkar är nästan alltid sträckor utan namn":
    "a balance that slips is almost always runs without a name",
};
