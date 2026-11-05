/* Det publika: startsidan, hur det funkar, priser, arkitektur, utbildning
 *
 * En rad per sträng, svensk nyckel först. Saknas en rad visas svenskan.
 */
export const publikt: Record<string, string> = {
  "Hur det funkar": "How it works",
  "Priser": "Pricing",
  "Utbildning": "Training",
  "Om oss": "About",
  "Dokumentation": "Documentation",
  "Hela systemet,": "The whole system,",
  "del för del": "part by part",
  "Vad som kör, vad varje del äger, hur en mening blir en meter - och vad ett blad kostar oss i drift.":
    "What runs, what each part owns, how a sentence becomes a metre - and what a sheet costs us to operate.",
  "Delarna": "The parts",
  "Vägen genom systemet": "The path through the system",
  "Läsarna": "The readers",
  "Hur vi vet": "How we know",
  "Vad ett blad kostar": "What a sheet costs",
  "processer: motor, tjänst, rum": "processes: engine, service, room",
  "läsare som måste vara överens": "readers that must agree",
  "mediankostnad per blad": "median cost per sheet",
  "Tre saker, med en gräns mellan sig som hålls": "Three things, with a boundary between them that holds",
  "Motorn": "The engine",
  "Tjänsten": "The service",
  "Rummet": "The room",
  "Från uppladdad fil till granskad mängd": "From uploaded file to reviewed quantity",
  "Två modeller, och regeln att de måste vara överens": "Two models, and the rule that they must agree",
  "59 blad med känd facit, mätta tre gånger om": "59 sheets with a known reference, measured three ways",
  "Vad ett blad kostar oss": "What a sheet costs us",
  "Driftkostnad": "Operating cost",
  "Följ en ritning genom läsningen": "Follow a drawing through the reading",
  "Läs dokumentationen": "Read the documentation",
  "Mått": "Measure",
  "Vad det jämför": "What it compares",
  "Var det står": "Where it lives",
  "Rad mot rad": "Row against row",
  "Dragning mot rör": "Run against pipe",
  "Sträcka mot sträcka": "Stretch against stretch",
  "Meter per beteckning mot referensen": "Metres per designation against the reference",
  "Varje mätt sträcka mot varje fysiskt rör": "Every measured stretch against every physical pipe",
  "Mängdarens egna mätlinjer mot vår geometri, på ritningen":
    "The estimator's own measuring lines against our geometry, on the drawing",
  "Blad": "Sheet",
  "Kostnad": "Cost",
  "Vad som dominerar": "What dominates",
  "Mediansidan": "The median sheet",
  "Blad som har öppna fall (39 %)": "Sheets with open cases (39 %)",
  "Snitt över alla blad": "Mean across all sheets",
  "Tätaste bladet som mätts": "Densest sheet measured",
  "processortid; inga öppna fall att fråga om": "processor time; no open cases to ask about",
  "modellanropen, median 4 frågor": "the model calls, median 4 questions",
  "dras upp av de täta bladen": "pulled up by the dense sheets",
  "1,08 miljoner banor och 54 öppna fall": "1.08 million paths and 54 open cases",
  "Processor": "Processor",
  "Modellanrop": "Model calls",
  "Lagring": "Storage",
  "Geometrin": "The geometry",
  "Enigheten": "The agreement",
  "Mängder": "Quantities",
  "Sträckor": "Runs",
  "4 %": "4 %",
  "8 %": "8 %",
  "88 %": "88 %",
  "Astra 6": "Astra 6",
  "Claude": "Claude",
  "pdf/ - varje streck ur filen med penna, färg, lager, streckning och ursprung":
    "pdf/ - every stroke from the file with its pen, colour, layer, dash pattern and provenance",
  "profile/ - bladets egna familjer: pennor, textstorlekar, ledarformer, skraffering":
    "profile/ - the sheet's own families: pens, text sizes, leader shapes, hatching",
  "text/ - bokstäver byggda tillbaka ur streck när CAD ritat dem i stället för att skriva dem":
    "text/ - letters rebuilt from strokes where CAD drew them instead of writing them",
  "semantics/ - beteckningar, förklaringslista, ledare och vad ledaren pekar på":
    "semantics/ - designations, the legend, leaders and what a leader points at",
  "pipes/ - topologi, ägande, fronter: vem sträckan tillhör och var den slutar":
    "pipes/ - topology, ownership, frontiers: who owns a run and where it ends",
  "measure/ - skala, mätning, lodrätt, mängdrader": "measure/ - scale, measurement, vertical, quantity rows",
  "review/ - agenter, OCR och syn som prövar det färdiga resultatet utan att flytta en meter":
    "review/ - agents, OCR and vision that test the finished result without moving a metre",
  "rules.py - varje gräns läsningen följer, samlad och beskriven på ritningens språk":
    "rules.py - every limit the reading follows, gathered and described in the drawing's language",
  "auth, projekt och ritningar; lagring på disk eller objektlager":
    "auth, projects and drawings; storage on disk or in an object store",
  "jobb med strömmad status - varje steg syns medan det händer":
    "jobs with streamed status - each step is visible while it happens",
  "artefakter ut som de skrevs, plus exporter (CSV, XLSX, Bluebeam-markering, anbud)":
    "artifacts as they were written, plus exports (CSV, XLSX, Bluebeam markup, tender)",
  "credits: vad en läsning drar, och återbetalning när den inte gav något":
    "credits: what a reading draws, and a refund when it gave nothing",
  "admin: systemhälsa, rättelser, inlärning, regler, prissättning":
    "admin: system health, corrections, learning, rules, pricing",
  "analysrummet: PDF-vy, lager, mängdtabell, tvetydigheter, agenten":
    "the analysis room: PDF view, layers, quantity table, ambiguities, the agent",
  "mängdningsverktyget: kalibrering, fångst, avdrag, markeringslista":
    "the take-off tool: calibration, snapping, deductions, markup list",
  "CAD-rummet: rita och redigera i stället för att ladda upp": "the CAD room: draw and edit instead of uploading",
  "kalkyl och anbud, projektanalys över hela handlingen": "costing and tender, project analysis across the whole set",
  "akademin och utbildningen": "the academy and the training",
  "Ett bibliotek utan webbserver, utan databas och utan nät. Den tar en PDF och lämnar artefakter. Allt som avgör en meter bor här, och ingenting här känner till en användare.":
    "A library with no web server, no database and no network. It takes a PDF and leaves artifacts. Everything that decides a metre lives here, and nothing here knows about a user.",
  "Konton, projekt, ritningar, jobb, resultat, exporter, credits och admin. Den kör motorn i en arbetartråd med en tidsbudget och skriver ned allt den får tillbaka.":
    "Accounts, projects, drawings, jobs, results, exports, credits and admin. It runs the engine in a worker thread with a time budget and writes down everything it gets back.",
  "Ritningen, mängden och beläggen bredvid varandra. Ingen siffra visas utan att gå att öppna: varje rad kan spåras till de vektorer den kom ur.":
    "The drawing, the quantity and the evidence side by side. No figure is shown that cannot be opened: every row can be traced back to the vectors it came from.",
  "Avgör allt den kan försvara. Säger TVETYDIGT när den inte kan. Ingen modell får röra det den avgjort.":
    "Decides everything it can defend. Says AMBIGUOUS when it cannot. No model may touch what it has decided.",
  "Får ett öppet fall och ritningens egna kandidater. Väljer en av dem eller svarar OKLART.":
    "Gets an open case and the drawing's own candidates. Picks one of them or answers UNCLEAR.",
  "Samma fråga, oberoende. Ser inte vad den andra svarat.":
    "The same question, independently. It does not see what the other answered.",
  "Fallet avgörs bara när båda pekar på samma kandidat. Är de oense, eller svarar bara den ena, står fallet kvar tvetydigt.":
    "The case is settled only when both point at the same candidate. If they disagree, or only one answers, the case stays ambiguous.",
  "17 s grundtid plus 1,5 s per tusen banor. Mediansidan 16 s.":
    "17 s of base time plus 1.5 s per thousand paths. The median sheet 16 s.",
  "Bara öppna fall frågas. 39 % av bladen har några alls; där de finns är medianen 4 frågor.":
    "Only open cases are asked about. 39 % of sheets have any at all; where they do, the median is 4 questions.",
  "Artefakterna, 5,8 MB för mediansidan, sparade i tolv månader.":
    "The artifacts, 5.8 MB for the median sheet, kept for twelve months.",
  "Motorn vet ingenting om konton, tjänsten vet ingenting om geometri, och rummet räknar aldrig själv. Gränsen är inte en smaksak: den är det som gör att en mängd kan läsas om, av någon annan, och bli densamma. Motorn kan köras från ett terminalfönster utan att något av det andra finns.":
    "The engine knows nothing about accounts, the service knows nothing about geometry, and the room never computes anything itself. The boundary is not a matter of taste: it is what lets a take-off be read again, by someone else, and come out the same. The engine runs from a terminal without any of the rest existing.",
  "Filen läggs undan och ett jobb skapas": "The file is put away and a job is created",
  "Tjänsten sparar ritningen, drar credits och lägger jobbet i kö. En skannad PDF avvisas direkt: där finns bara bildpunkter, och på bildpunkter gissar man.":
    "The service stores the drawing, draws credits and queues the job. A scanned PDF is refused outright: there are only pixels there, and on pixels one guesses.",
  "Arbetartråden kör motorn, med en tidsbudget": "The worker thread runs the engine, on a time budget",
  "Varje steg strömmas ut medan det händer. Går bladet över tidsbudgeten avbryts det och säger det, i stället för att hålla arbetaren för alltid.":
    "Each step is streamed out while it happens. A sheet that runs past the budget is stopped and says so, instead of holding the worker forever.",
  "Motorn skriver artefakter, inte slutsatser": "The engine writes artifacts, not conclusions",
  "Beteckningar, ledare, fästen, topologi, fysiska rör, fronter, mängdrader, bevisgraf, avstämning, determinism, kontaminationsrapport. Ungefär tjugo filer per blad, och mängden är bara en av dem.":
    "Designations, leaders, attachments, topology, physical pipes, frontiers, quantity rows, evidence graph, reconciliation, determinism, contamination report. About twenty files per sheet, and the quantity is only one of them.",
  "Granskningen prövar det färdiga": "The review tests the finished result",
  "Agenter läser resultatet mot bladet, OCR läser texten en andra gång, och synläsaren tittar på sidan. Ingen av dem flyttar en meter - de läser, de mäter inte.":
    "Agents read the result against the sheet, OCR reads the text a second time, and the vision reader looks at the page. None of them moves a metre - they read, they do not measure.",
  "Rummet visar mängden med sina belägg": "The room shows the quantity with its evidence",
  "Varje rad går att öppna: vilka rör, vilka etiketter, var de slutar och varför. Det tvetydiga står för sig och räknas inte in i tysthet.":
    "Every row opens: which pipes, which labels, where they end and why. The ambiguous stands apart and is never counted in silently.",
  "Rättelser sparas som rättelser": "Corrections are saved as corrections",
  "Det du ändrar skrivs som en ändring med ditt namn på, bredvid vad läsningen sa. Ingen siffra byts ut bakom ryggen på någon, och rättelserna är det som lär systemet nästa gång.":
    "What you change is written as a change with your name on it, beside what the reading said. No figure is swapped behind anyone's back, and the corrections are what teach the system next time.",
  "En språkmodell får aldrig skapa geometri här. Den får se ett fall som geometrin själv förklarat öppet, tillsammans med de kandidater ritningen erbjuder, och välja en av dem. Ett svar som inte står i listan kastas, tecken för tecken.":
    "A language model may never create geometry here. It is shown a case the geometry itself declared open, together with the candidates the drawing offers, and picks one of them. An answer that is not on the list is thrown away, character by character.",
  "Med en enda modell finns ändå en risk kvar: ett öppet fall har flera rimliga svar, och en modell som gissar fel förvandlar ett ärligt tvetydigt fall till ett självsäkert fel. Det är den dyraste sortens fel i en mängdning, för det ser ut som ett svar. Därför frågas två, oberoende av varandra.":
    "With a single model one risk remains: an open case has several reasonable answers, and a model that guesses wrong turns an honestly ambiguous case into a confident error. That is the most expensive kind of error in a take-off, because it looks like an answer. So two are asked, independently of each other.",
  "Kostnaden för det är två anrop i stället för ett på de fall som frågas alls, och vinsten är att en ensam modell inte kan skriva in ett fel. Går den ena inte att nå tystnar panelen i stället för att bli en ensam röst - fallet står kvar öppet, vilket är ett giltigt svar.":
    "The cost is two calls instead of one on the cases that are asked about at all, and the gain is that a single model cannot write an error in. If one cannot be reached the panel falls silent rather than becoming a lone voice - the case stays open, which is a valid answer.",
  "Utvecklingen går i grindar. En ändring körs blint över hela korpusen, körningen fryses med en hash av källkoden, och först därefter öppnas referensmängderna. Blir ändringen sämre backas den - fyra av de senaste sju gjorde det.":
    "Development goes in gates. A change is run blind across the whole corpus, the run is frozen with a hash of the source, and only then are the reference quantities opened. A change that measures worse is reverted - four of the last seven were.",
  "Referensmaterialet ligger utanför källkoden och motorn kan inte nå det. En skanner går igenom motorns alla filer före varje körning och vägrar om något av referensens ordförråd har läckt in.":
    "The reference material lives outside the source and the engine cannot reach it. A scanner walks every file of the engine before each run and refuses if any of the reference's vocabulary has leaked in.",
  "Det här är vad vi betalar för att läsa ett blad, inte vad någon betalar oss. Uppmätt på 305 blad, varje blad i en egen process, med två läsare inräknade. Kronorna kommer ur antaganden som står utskrivna i verktyget; byt ett antagande och talet räknas om.":
    "This is what we pay to read a sheet, not what anyone pays us. Measured over 305 sheets, one process each, with two readers counted. The kronor come from assumptions written out in the tool; change an assumption and the figure is recomputed.",
  "Processortiden räknas på en maskin med fyra kärnor vid 40 procents nyttjande, vilket ger 1,03 kr per kärntimme - tomgången ska bäras av de blad som faktiskt läses. Lagringen är artefakterna i tolv månader. Synläsaren är inte med i talen ovan: den kostar omkring 0,90 kr per sida och begärs för hand, inte automatiskt.":
    "Processor time is costed on a four-core machine at 40 % utilisation, which gives 1.03 kr per core-hour - the idle time is carried by the sheets that actually run. Storage is the artifacts for twelve months. The vision reader is not in the figures above: it costs about 0.90 kr per page and is asked for by hand, not automatically.",
  "Det betyder att kostnaden i praktiken styrs av hur mycket ritningen lämnar öppet, inte av hur stor den är. Ett blad som läsningen kan avgöra själv kostar ören. Varje gräns som skärps så att ett fall kan avgöras på ritningens egen geometri gör läsningen både bättre och billigare - det är samma arbete.":
    "So the cost is governed in practice by how much the drawing leaves open, not by how big it is. A sheet the reading can settle on its own costs pennies. Every limit tightened so that a case can be decided on the drawing's own geometry makes the reading both better and cheaper - it is the same work.",
  "Det finns en människa i slingan, på ett ställe: där läsningen säger TVETYDIGT. Det hon avgör sparas som en rättelse bredvid vad läsningen sa, och blir en lärdom som får avgöra samma sorts fall på ett annat blad - samma penna, samma ledarform, samma skäl, samma etikettform. Aldrig mer än så: en rättelse får aldrig skapa en sträcka eller ändra något motorn är säker på.":
    "There is a human in the loop, in one place: where the reading says AMBIGUOUS. What they decide is saved as a correction beside what the reading said, and becomes a lesson allowed to settle the same kind of case on another sheet - same pen, same leader shape, same reason, same label shape. Never more than that: a correction may never create a run or change something the engine is sure of.",

  // --- startsidan: märket, löftet, kapitlen ---------------------------------------------------------------
  "THE FUTURE": "THE FUTURE",
  "The future of calculation": "The future of calculation",
  "Intelligence built for VVS": "Intelligence built for HVAC",
  "VVS / ESTIMATION / INTELLIGENCE": "HVAC / ESTIMATION / INTELLIGENCE",
  "Dahl — Estimation / Intelligence": "Dahl — Estimation / Intelligence",
  "VPR — Vector Pipe Reading": "VPR — Vector Pipe Reading",
  "VPR System / 2026": "VPR System / 2026",
  "Architecture": "Architecture",
  "Enter Dahl": "Enter Dahl",
  "Explore education": "Explore education",
  "From drawing to quantity": "From drawing to quantity",
  "Chapter II — From Drawing to Quantity": "Chapter II — From Drawing to Quantity",
  "Chapter IV — Dahl Academy": "Chapter IV — Dahl Academy",
  "Chapter V": "Chapter V",
  "02 — Problemet": "02 — The problem",
  "Laddar Dahl": "Loading Dahl",
  "Byggd i Sverige": "Built in Sweden",
  "Vårt": "Our",
  "— så": "— like this",

  // --- vad läsningen gör ----------------------------------------------------------------------------------
  "Hur läsningen fungerar": "How the reading works",
  "Hur systemet läser en ritning": "How the system reads a drawing",
  "Se hur läsningen går till": "See how the reading is done",
  "Se hur den läser": "See how it reads",
  "Se hur det läser": "See how it reads",
  "Den läser bladet": "It reads the sheet",
  "Läser vektorn.": "Reads the vector.",
  "Bygger tillbaka texten.": "Rebuilds the text.",
  "Läser beteckningarna.": "Reads the designations.",
  "Läser beteckningslistan.": "Reads the designation list.",
  "Hittar ledarlinjerna.": "Finds the leaders.",
  "Väljer rörfamiljer.": "Picks pipe families.",
  "Bygger topologi och äger rören.": "Builds topology and owns the pipes.",
  "Mäter.": "Measures.",
  "Pekar på ritningen.": "Points at the drawing.",
  "Ritade föremål.": "Drawn objects.",
  "Annoterade ark.": "Annotated sheets.",
  "Andra blick.": "Second look.",
  "Bläcktillägg.": "Ink surcharge.",
  "Ingår.": "Included.",
  "Återbetalning.": "Refund.",
  "Ändrar ingenting.": "Changes nothing.",
  "Räknar aldrig själv.": "Never counts on its own.",
  "Etiketterna måste nå fram.": "The labels have to arrive.",
  "Identitet som rinner för långt.": "Identity that runs too far.",
  "Från streck till meter": "From stroke to metre",
  "Från etikett till meter, steg för steg": "From label to metre, step by step",
  "Från ritning till färdig kalkyl. Varje meter läst ur bladets egna beteckningar.":
    "From drawing to finished costing. Every metre read from the sheet's own designations.",
  "Ritningen läses steg för steg medan sidan skrollas":
    "The drawing is read step by step as the page scrolls",
  "Där röret slutar": "Where the pipe ends",
  "Inget rör slutar tyst": "No pipe ends silently",
  "Varje ställe ett rör slutar har ett skäl": "Every place a pipe ends has a reason",
  "skäl ett rör kan sluta av": "reasons a pipe can stop for",
  "steg i läsningen": "steps in the reading",
  "meter utan belägg": "metres without evidence",
  "En hänvisningslinje går från beteckningen till röret den namnger":
    "A leader runs from the designation to the pipe it names",
  "Den närmaste linjen är inte den som namnger": "The nearest line is not the one that names",
  "närmast — men ingen linje går hit": "nearest — but no line runs here",
  "onämnd — redovisas, mäts inte": "unnamed — reported, not measured",
  "rör i vägg — redovisas för sig": "pipe in wall — reported separately",
  "Skalan tas ur bladets egen skalstock": "The scale is taken from the sheet's own scale bar",
  "Skalan verifierad": "Scale verified",
  "Samma geometri, två representationer": "The same geometry, two representations",
  "System och hur det ritas": "System and how it is drawn",
  "Hur nära två linjer får ligga": "How close two lines may lie",
  "var röret ligger i höjdled": "where the pipe sits vertically",
  "Rör, koppar": "Pipe, copper",
  "Rörtyper": "Pipe types",
  "KV, VV och VVC": "KV, VV and VVC",
  "beteckningsdriven tolkning direkt på ritningen": "designation-driven reading straight on the drawing",
  "MÄNGD": "QUANTITY",
  "mängd": "quantity",
  "längd": "length",
  "Längd": "Length",
  "fråga": "question",
  "läsningen": "the reading",
  "med belägg": "with evidence",
  "rad för rad": "row by row",
  "stigare · 2 st": "risers · 2",
  "korsläsning": "cross-reading",
  "ovanpå": "on top",
  "Tre lager": "Three layers",
  "Varje meter vet vilket lager den kom ur": "Every metre knows which layer it came from",

  // --- exempel ur en ritning ------------------------------------------------------------------------------
  "KV1-X31-16 · 12,1 m": "KV1-X31-16 · 12.1 m",
  "VV1-X31-16 · 18,2 m": "VV1-X31-16 · 18.2 m",
  "VS1-S13-22 · 61,9 m": "VS1-S13-22 · 61.9 m",
  "S1-P2 · DN110 eller DN160 · 1,7 m": "S1-P2 · DN110 or DN160 · 1.7 m",
  "Bet. P": "Des. P",
  "Bet. R": "Des. R",
  "BXXX GOLVBRUNN": "BXXX GOLVBRUNN",
  "OF VVS": "OF VVS",
  "Planritning där rören markerats och mätts": "A floor plan with the pipes marked and measured",
  "Planritning med tappvatten, spillvatten och värme": "A floor plan with tap water, waste water and heating",

  // --- vad som aldrig händer ------------------------------------------------------------------------------
  "Vad som aldrig händer": "What never happens",
  "Vad den vägrar": "What it refuses",
  "Det läsningen vägrar": "What the reading refuses",
  "Ingen närhetsgissning": "No proximity guessing",
  "Ingen gissad skala": "No guessed scale",
  "Ingen modell som ritar": "No model that draws",
  "Tvetydigt är ett giltigt svar. Fel säkerhet är det inte.":
    "Ambiguous is a valid answer. Wrong certainty is not.",
  "Ett tvetydigt svar är ett svar. Ett gissat är det inte.":
    "An ambiguous answer is an answer. A guessed one is not.",
  "Principen hela motorn är byggd kring": "The principle the whole engine is built around",
  "Hittar aldrig på en beteckning.": "Never invents a designation.",
  "Namnger inte geometri utifrån närhet, hur nära den än ligger.":
    "Does not name geometry by proximity, however close it lies.",
  "Ingen påhittad dimension. Det som inte står i modellen finns inte i filen.":
    "No invented dimension. What the model does not state is not in the file.",
  "Har en skala per sida, inte per ritningsdel.": "Has one scale per page, not per drawing part.",
  "Läser inte skannade ritningar. Utan vektorkoder finns inget att mäta.":
    "Does not read scanned drawings. Without vector codes there is nothing to measure.",
  "Överbryggar inte glapp i en böjd streckad linje.": "Does not bridge gaps in a curved dashed line.",
  "Delar inte en knippeetikett som räknar upp fler koder än ritningen ritar linjer.":
    "Does not split a bundle label that lists more codes than the drawing draws lines.",
  "Fördelar inte längden i en delad sträcka mellan systemen som delar den.":
    "Does not divide the length of a shared stretch between the systems that share it.",
  "En kod bladet inte mängdar på avvisas, med de som finns.":
    "A code the sheet does not take off on is rejected, together with the ones that exist.",
  "Låter inte en rättelse på en ritning bli en gissning på en annan.":
    "Does not let a correction on one drawing become a guess on another.",
  "Samma ritning ger samma rör oavsett AB 04 eller ABT 06. Avtalsformen bor i kalkylen, aldrig i geometrin.":
    "The same drawing gives the same pipes under AB 04 or ABT 06. The contract form lives in the costing, never in the geometry.",
  "Ett rör får aldrig ett namn för att en etikett råkar ligga bredvid. Bara en riktig ledare ger identitet.":
    "A pipe is never given a name because a label happens to lie beside it. Only a real leader gives identity.",
  "En språkmodell får välja mellan kandidater ritningen erbjuder. Den får aldrig skapa geometri, DN eller meter.":
    "A language model may choose between candidates the drawing offers. It may never create geometry, DN or metres.",
  "Modellen väljer frågan, ritningen ger svaret": "The model picks the question, the drawing gives the answer",
  "Varje tal kommer ur ett verktyg som läser artefakterna mätningen skrev.":
    "Every number comes from a tool that reads the artifacts the measurement wrote.",
  "gissningar — identitet endast via riktiga ledarlinjer, aldrig närmaste rör":
    "guesses — identity only through real leaders, never the nearest pipe",

  // --- belägg och spårbarhet ------------------------------------------------------------------------------
  "Beläggen": "The evidence",
  "Evidens först": "Evidence first",
  "Bevis per rad": "Evidence per row",
  "Varje meter går att spåra tillbaka": "Every metre can be traced back",
  "varje meter med sitt belägg kvar": "every metre with its evidence intact",
  "Ingen meter utan belägg. Varje rad i mängden går att spåra till bladet.":
    "No metre without evidence. Every row in the quantity can be traced to the sheet.",
  "Mängden, beläggen, exporten. Var meter går att spåra tillbaka till bladet.":
    "The quantity, the evidence, the export. Every metre can be traced back to the sheet.",
  "Klicka på en rad i mängden och se exakt vilken etikett, vilken ledarlinje och vilka streck som gav den.":
    "Click a row in the quantity and see exactly which label, which leader and which strokes produced it.",
  "Läsningen säger vad den fann, vad den inte kunde avgöra, och varför.":
    "The reading says what it found, what it could not decide, and why.",
  "Inget är ändrat än.": "Nothing has been changed yet.",
  "Sparas där du är": "Saved where you are",

  // --- hur vi vet att det stämmer -------------------------------------------------------------------------
  "Att jämföra med": "To compare against",
  "Blint mätt": "Measured blind",
  "Facit m": "Reference m",
  "Ägda m": "Owned m",
  "Missade m": "Missed m",
  "Falska m": "False m",
  "Markerad PDF": "Marked PDF",
  "En ritning lästes fel": "A drawing was read wrong",
  "Flera läsningar": "Several readings",
  "Motorn körs innan facit öppnas. Varje ändring grindas mot hela korpusen.":
    "The engine runs before the reference is opened. Every change is gated against the whole corpus.",
  "Tre nivåer, och de körs om vid varje ändring som kan röra en siffra.":
    "Three levels, and they are re-run on every change that could touch a number.",
  "tester som måste hålla innan en siffra får ändras": "tests that must hold before a number may change",
  "sidor i stilbiblioteket, körda sida för sida vid varje ändring":
    "pages in the style library, run page by page on every change",
  "samlad avvikelse mot facit över fyra referensritningar":
    "total deviation from the reference across four reference drawings",
  "3,69 m samlad avvikelse på 213,70 m": "3.69 m total deviation on 213.70 m",
  "varje körning mäts mot handmängdad ritning": "every run is measured against a hand-taken-off drawing",
  "två vägar · samma svar": "two paths · the same answer",
  "som ställer svaren mot varandra, och en": "that sets the answers against each other, and one",
  "i samma situation": "in the same situation",
  "Det mesta av arbetet ligger i att inte mäta fel saker. Varje regel är mätt fram, inte antagen.":
    "Most of the work is in not measuring the wrong things. Every rule is measured into place, not assumed.",

  // --- vad plattformen mer är -----------------------------------------------------------------------------
  "Hela plattformen": "The whole platform",
  "Resten av plattformen": "The rest of the platform",
  "Nästa funktion": "Next feature",
  "Mängdning": "Take-off",
  "Mätverktyget: kalibrering, fångst och avdrag": "The measuring tool: calibration, snap and deduction",
  "Ritningen är sidan, verktygen i kanten": "The drawing is the page, the tools at the edge",
  "Rita i CAD": "Draw in CAD",
  "Plan, sektion, fasad och 3D ur samma modell": "Plan, section, elevation and 3D from one model",
  "Planen reser sig till en modell": "The plan rises into a model",
  "blir en byggnad": "becomes a building",
  "Väggar, stomme och installationer i en modell": "Walls, frame and services in one model",
  "En vägg vet att den är en vägg": "A wall knows that it is a wall",
  "Samma rör i tabellen och i modellen": "The same pipe in the table and in the model",
  "plan 1": "level 1",
  "plan 2": "level 2",
  "plan 3": "level 3",
  "In i kalkylen": "Into the costing",
  "Mängden blir ett anbud": "The quantity becomes a tender",
  "Anbudet granskas på skärmen innan det lämnar huset":
    "The tender is reviewed on screen before it leaves the building",
  "sida 1 · sammanställning": "page 1 · summary",
  "sida 2 · mängdförteckning": "page 2 · bill of quantities",
  "sida 3 · villkor": "page 3 · terms",
  "Excel och CSV": "Excel and CSV",
  "Ett samtal om ritningen": "A conversation about the drawing",
  "Fråga ritningen, och se var svaret kom ifrån": "Ask the drawing, and see where the answer came from",
  "Logga in och skriv i agenten på din analys - den ser samma belägg som du och svarar ur dem.":
    "Sign in and write to the agent on your reading - it sees the same evidence you do and answers from it.",
  "3 verktygsanrop ▸": "3 tool calls ▸",
  "Förslag": "Suggestions",
  "Genomför": "Run",
  "Översikt": "Overview",
  "Dina projekt": "Your projects",
  "Vägen in": "The way in",
  "Läs ett blad": "Read a sheet",
  "Läs mer": "Read more",
  "Pröva den": "Try it",
  "Se filmen": "Watch the film",
  "Se vad det kostar": "See what it costs",
  "Ladda upp en ritning": "Upload a drawing",
  "En figur som rör sig": "A figure that moves",

  // --- utbildningen ---------------------------------------------------------------------------------------
  "Kurserna i akademin": "The courses in the academy",
  "Sex moduler": "Six modules",
  "Till kurserna": "To the courses",
  "Till utbildningen": "To the training",
  "Öppna akademin": "Open the academy",
  "Utbildning för kontoret": "Training for the office",
  "Samma kurs för hela laget": "The same course for the whole team",
  "Lär dig mängda": "Learn to take off",
  "Lär dig läsa ritningen medan den läses": "Learn to read the drawing while it is being read",
  "Du ser läsningen steg för steg, och kan gå ett delmoment i akademin medan den kör.":
    "You watch the reading step by step, and can take a module in the academy while it runs.",
  "En föreläsning med sin figur och sin kontrollfråga": "A lecture with its figure and its check question",
  "Varje föreläsning visar det den handlar om som en levande ritning — en ledarlinje som hittar sitt rör, en stigare som blir meter — i stället för att beskriva det i ord.":
    "Every lecture shows what it is about as a living drawing — a leader finding its pipe, a riser becoming metres — instead of describing it in words.",
  "En kontrollfråga": "A check question",
  "Kontrollfrågor": "Check questions",
  "KONTROLLFRÅGA": "CHECK QUESTION",
  "Inte ett prov. En fråga som går att svara fel på, med förklaringen efteråt — för det är den man minns.":
    "Not an exam. A question you can get wrong, with the explanation afterwards — because that is the one you remember.",
  "varje moment slutar med en fråga och ett svar som förklarar varför":
    "every module ends with a question and an answer that explains why",
  "Övningar på riktiga blad": "Exercises on real sheets",
  "Övningstyper": "Exercise types",
  "Ett övningsblad": "A practice sheet",
  "para ihop beteckning och sträcka, och få rättat direkt":
    "match designation to run, and be marked straight away",
  "Dahl Certified": "Dahl Certified",
  "fortsätt nästa gång en ritning läses": "continue the next time a drawing is read",

  // --- priser ---------------------------------------------------------------------------------------------
  "Vad en läsning kostar": "What a reading costs",
  "Priser och större konto": "Pricing and larger accounts",
  "Priset står på ritningen. Inget dras förrän du trycker.":
    "The price is on the drawing. Nothing is deducted until you press.",
  "Credits köps i paket. Priser exklusive moms.": "Credits are bought in packages. Prices excluding VAT.",
  "credits att prova med": "credits to try with",
  "credits för ett A3-blad": "credits for an A3 sheet",
  "A3 och mindre": "A3 and smaller",
  "Större än A0": "Larger than A0",
  "Bäst värde": "Best value",
  "0,03 kr": "0.03 kr",
  "0,31 kr": "0.31 kr",
  "0,45 kr": "0.45 kr",
  "6,36 kr": "6.36 kr",
  "85 kr/m": "85 kr/m",
  "1 061 kr": "1,061 kr",
  "2 229 kr": "2,229 kr",
  "34 370 kr": "34,370 kr",
  "eller inte alls": "or not at all",
  "Projektanalysen över hela handlingen, kalkylen och anbudet, mängdningsverktyget, CAD-rummet, exporter och akademin kostar inga credits.":
    "The project reading across the whole document set, the costing and the tender, the measuring tool, the CAD room, exports and the academy cost no credits.",
  "En läsning som inte kunde ge en enda meter kostar ingenting.":
    "A reading that could not give a single metre costs nothing.",
  "Varje läsning kostar sitt pris - men en läsning som inte kunde ge en meter betalas tillbaka, så en omläsning med en skala du skrev in för hand kostar bara en gång.":
    "Every reading costs its price - but a reading that could not give a metre is refunded, so a re-read with a scale you entered by hand costs only once.",
  "Saknar bladet skala, eller går läsningen fel, får du tillbaka priset utan att fråga. Skälet står i din reskontra.":
    "If the sheet has no scale, or the reading goes wrong, you get the price back without asking. The reason is in your ledger.",
  "Det kostar ingenting att prova — ett nytt konto får credits att läsa ett par ritningar med.":
    "It costs nothing to try — a new account gets credits to read a couple of drawings with.",
  "Ja. Credits hör till kontot, inte till inloggningen. En firma med fyra rörläggare har en pott och fyra inloggningar.":
    "Yes. Credits belong to the account, not to the login. A firm with four plumbers has one pot and four logins.",
  "Nej. De ligger kvar på kontot tills de används.": "No. They stay on the account until they are used.",
  "Nej. Köp det paket som passar och fyll på när det behövs. Storkunder som vill ha en fast månadskostnad hör av sig.":
    "No. Buy the package that fits and top up when needed. Large customers who want a fixed monthly cost are welcome to get in touch.",
  "Köp faktureras till företaget med 30 dagars betalningstid. Credits finns på kontot i samma stund som köpet registreras.":
    "Purchases are invoiced to the company with 30 days to pay. Credits are on the account the moment the purchase is registered.",
  "Vanliga frågor": "Common questions",
  "Fråga oss om priset": "Ask us about the price",

  // --- kontakt och demo -----------------------------------------------------------------------------------
  "Prata med oss": "Talk to us",
  "Boka en genomgång": "Book a walkthrough",
  "Demo på egen ritning": "Demo on your own drawing",
  "Vad vi behöver för en demo": "What we need for a demo",
  "En ren vektor-PDF - exporterad ur CAD, inte skannad - och gärna er egen handmängdning av samma blad att jämföra med. Det är den enda rimliga första körningen.":
    "A clean vector PDF - exported from CAD, not scanned - and ideally your own hand take-off of the same sheet to compare against. That is the only sensible first run.",
  "Ta en sida du redan mängdat för hand. Jämför. Det är den enda rimliga första körningen.":
    "Take a page you have already taken off by hand. Compare. That is the only sensible first run.",
  "Ta ett blad du redan mängdat": "Take a sheet you have already taken off",
  "Börja med ett blad du redan mängdat": "Start with a sheet you have already taken off",
  "Vilken slags handlingar, hur många blad, vad ni mängdar i dag…":
    "What kind of documents, how many sheets, what you take off today…",
  "Skriv vilket blad och vilken beteckning. Varje meter i tjänsten bär sitt belägg, så en felläsning går att spåra till ett steg - och rättas generellt, inte bara på ert blad.":
    "Tell us which sheet and which designation. Every metre in the service carries its evidence, so a misreading can be traced to one step - and fixed generally, not just on your sheet.",
  "Vi använder uppgifterna bara för att svara dig.": "We use the details only to reply to you.",
  "Tack. Vi hör av oss.": "Thank you. We will be in touch.",
  "Företag": "Company",
  "Företaget": "The company",
  "Anna Lindqvist": "Anna Lindqvist",
  "Byggd för att göras, inte bläddras i": "Built to be done, not browsed",
  "En metodik, inte en mall": "A method, not a template",

  // --- när en sida inte finns -----------------------------------------------------------------------------
  "Den funktionen finns inte": "That feature does not exist",
  "Den föreläsningen finns inte": "That lecture does not exist",
  "Den sidan finns inte i akademin": "That page does not exist in the academy",
  "Adressen pekar på en kurs eller en föreläsning som inte finns. Kurserna står kvar där de var.":
    "The address points at a course or a lecture that does not exist. The courses are still where they were.",
  "Systemet i bild": "The system in pictures",
  "Ritningen in.": "The drawing in.",
  "Mängden, modellen och kalkylen ut.": "Quantities, model and costing out.",
  "Vyer i Dahl": "Views in Dahl",
  "Läsningen": "The reading",
  "Kalkyl": "Costing",
  "Agenten": "The agent",
  "Varje rör färgat efter sin beteckning, mängden bredvid. Tryck på en rad så visas exakt vilka sträckor och etiketter den kommer ur.": "Every pipe coloured by its designation, the quantity beside it. Tap a row to see exactly which runs and labels it comes from.",
  "Samma läsning som en byggnad: rören i sina system, ritningen som golv, beteckningarna där rören går.": "The same reading as a building: the pipes in their systems, the drawing as the floor, the designations where the pipes run.",
  "Rita det som saknas: väggar, rum, öppningar, rör. Plan och 3D sida vid sida, med lager, mått och export till IFC och DXF.": "Draw what is missing: walls, rooms, openings, pipes. Plan and 3D side by side, with layers, dimensions and export to IFC and DXF.",
  "Mängden blir material ur grossistens bok och timmar ur Normtid VVS, rad för rad, med påslag och anbudssumma.": "The quantity becomes material from the wholesaler’s book and hours from Normtid VVS, row by row, with markups and a tender total.",
  "Fråga ritningen med röst eller text. Agenten markerar själv röret den pratar om och svarar med metrarna ur läsningen.": "Ask the drawing by voice or text. The agent marks the pipe it is talking about and answers with the metres from the reading.",
  "Se hur det funkar": "See how it works",
  "Fem minuter i Dahl": "Five minutes in Dahl",
  "Inspelat i appen på en riktig ritning – inga skisser, inga redigerade siffror.": "Recorded in the app on a real drawing – no mock-ups, no edited figures.",
  "Från ritning till mängd": "From drawing to quantity",
  "3D-modellen": "The 3D model",
  "AI-agenten": "The AI agent",
  "Kalkylen": "Costing",
  "Systemet läser ritningen via beteckningarna. Tryck på en rad och se exakt vilka sträckor den kommer ur.": "The system reads the drawing through its designations. Tap a row and see exactly which runs it comes from.",
  "Samma läsning som en byggnad, med ritningen som golv och rören i sina system.": "The same reading as a building, with the drawing as the floor and the pipes in their systems.",
  "Fråga ritningen. Svaren kommer ur mängden, och sträckorna visas på bladet.": "Ask the drawing. The answers come from the takeoff, and the runs are shown on the sheet.",
  "Mängden blir material, normtid och anbudssumma, rad för rad.": "The quantity becomes material, standard time and a tender total, row by row.",
  "Rita väggar, dörrar, fönster och rum – i plan och 3D samtidigt.": "Draw walls, doors, windows and rooms – in plan and 3D at once.",
  "Skannade blad och bilder.": "Scanned sheets and images.",
  "En sida som läses ur en skanning eller en bild kostar {0} credit extra. Allt som läses ur bildpunkter ska granskas.": "A page read from a scan or an image costs {0} credit extra. Everything read from pixels must be reviewed.",
};
