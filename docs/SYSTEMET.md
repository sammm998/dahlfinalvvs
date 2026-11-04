# Så fungerar systemet

Det här är dokumentet man läser för att förstå vad VVS Mängdning gör, hur det gör det, vilka AI-modeller som
används och exakt var, och vad det aldrig gör. Det är skrivet efter koden, inte före den: varje påstående går
att slå upp i den fil som nämns.

Kompletterande dokument: `ARCHITECTURE.md` (läsvägen steg för steg), `ANALYSARKITEKTUR.md` (vad som bär och
brister, med mätningar), `LATHUND.md` (mängdningsstandarden och vad av den som är genomfört), `LIMITATIONS.md`
(kända begränsningar), `RORTYPER.md`, `FLERVAGSANALYS.md`.

---

## 1. Principen

En mängd finns bara där ritningen själv pekar.

Systemet läser en ritnings egna vektorer - linjerna CAD-programmet skrev in i PDF:en - och bygger identitet
bara där tre saker möts: en beteckning bladet skriver, en ritad hänvisningslinje från den, och den graf
geometrin bildar. **Aldrig närhet.** Ett rör som ligger nära en etikett men som ingen linje pekar på får inget
namn. Det redovisas som *onämnt* - med sina meter - i stället för att gissas.

Därför är `AMBIGUOUS` ett giltigt svar. Två etiketter som båda kan äga en sträcka ger en tvetydig sträcka, inte
en gissning. Fel säkerhet är värre än ett saknat svar, för ett saknat svar syns och ett felaktigt gör det inte.

Allt upptäcks per ritning. Vilken penna som ritar rör, hur beteckningarna är byggda, vilken skala bladet har,
vilka lager som är text - ingenting av det är inställt i förväg. Två kontor ritar olika, och systemet läser
varje blad på bladets egna villkor.

---

## 2. Vad som händer med en ritning

Läsvägen, i den ordning den körs (`engine/vvs_engine/pipeline.py`):

| Steg | Vad | Var |
|---|---|---|
| 1 | **Extraktion.** PDF:ens vektorobjekt läses råa: linjer, kurvor (plattade), transformationer, XObjects, lager (OCG), sökbar text. Annotationer - någons påskrift ovanpå ritningen, till exempel en Bluebeam-mängdning - läggs åt sidan och redovisas för sig; de är aldrig det ritaren ritade. | `pdf/extract.py` |
| 2 | **Text.** Sökbar text läses som text. CAD-text som exporterats som streck (SHX-typsnitt) sätts ihop till tecken av streckens form, mot generiska referensalfabet. Ett tecken som inte går att läsa blir `?` - det repareras aldrig ur ett förväntat ord. | `text/` |
| 3 | **Beteckningar.** Textrader blir block, block blir etiketter. Grammatiken - hur det här kontoret bygger sina koder (system, material, dimension, kvalificerare) - upptäcks ur bladets egna etiketter och dess beteckningslista. | `semantics/annotation.py`, `semantics/grammar.py`, `semantics/legend.py` |
| 4 | **Hänvisningslinjer.** Från varje etiketts kant följs de ritade linjerna ut i bladet: raka, böjda, delade. En etikett utan linje pekar inte på något. | `semantics/leaders.py` |
| 5 | **Vilka pennor ritar rör.** Linjernas ändar röstar på de familjer (lager + penna) de rör vid. En familj blir rörgeometri bara om den är kedjelik och har stöd - lagernamnet bär systemets kod, markeringsstreck, eller tillräckligt många etiketter. Läsningen körs två gånger: först obegränsat, sedan med de pennor som visade sig vara *skrivpennor* undantagna. Bladets egna etiketter avgör vilken läsning som står. | `pipeline.py` |
| 6 | **Kontakt.** Var linjen möter röret: direkt, via ett markeringsstreck, via en symbol (stigare, brunn), via en samlingslinje - ett kort streck på skrivpennan som samlar flera etiketter ned till ett rör. | `semantics/attachment.py` |
| 7 | **Topologi.** Rörgeometrin blir en graf: mikroglapp överbryggas, T-korsningar delas, och en korsning är inte en anslutning - en linje som passerar går in på ena sidan av noden och ut på den andra. | `pipes/representation.py` |
| 8 | **Ägande.** Varje kedja i grafen får en identitet från de etiketter som når den, eller står som tvetydig eller onämnd. Dimensionsbyten sätts bara vid ritade markeringsstreck. En stump kortare än kontakttoleransen bär aldrig ett namn vidare. | `pipes/ownership.py` |
| 9 | **Skala och mått.** Skalan läses ur skaltexten och verifieras mot den ritade skalstocken; skiljer de sig är det en konflikt och inte ett medelvärde. Horisontella meter mäts längs geometrin. Vertikala meter finns bara med uttryckligt stöd - en våningshöjd användaren anger, eller höjdangivelser på bladet. | `measure/` |
| 10 | **Avstämning och artefakter.** Allt bladet ritade summeras: mätt, tvetydigt, påpekat men onämnt, onämnt, bortvalt. Summan ska stämma med det ritade, och avvikelsen redovisas i stället för att justeras bort. Allt skrivs som filer så att varje meter går att spåra bakåt (`why`). | `reconcile.py`, `output/` |

**Var varje rör börjar och slutar** (`pipes/frontier.py`, `pipe-extent-frontiers.json`). Varje ände på varje rör får
ett skäl: annan dimension, annat system, stigare, ritad komponent, bladets kant, fri ände - eller, där läsningen
tappar meter, oägd fortsättning och bruten kontinuitet. Ett rör delas i mätsektioner vid varje nod den inbyggda
läsaren sätter, så att en höjd kan knytas till rätt bit. En skarv där samma rör med samma namn fortsätter i nästa
sektion är ingen ände och redovisas inte som en (`SECTION_JOINT`); den räknas bara i `section_joints`. Förut stod
varje sådan skarv som "något läsningen inte kan sätta ord på", tolv tusen av korpusens femton tusen ändar, och de
verkliga ändarna syntes inte bland dem.

Efter mätningen kommer **granskningen** (`review/`): agenter som frågar om resultatet är trovärdigt - är det
ritade röret redovisat, finns bladets alla beteckningar i mängdtabellen, är längder och dimensioner fysiskt
rimliga, hänger nätet ihop, håller skalan. De ändrar ingenting; en granskning som kunde ändra resultatet skulle
dölja den oenighet den finns för att visa. En **domare** (`review/judge.py`) går igenom fynden och säger vad som
ska hända - utan modell, ur artefakterna, så samma läsning dömd två gånger ger samma domar.

**Schemablad.** Ett flödes- eller principschema, som bladet själv kallar schema i en rad som börjar med ordet
(`FLÖDESSCHEMA`, `PRINCIPSCHEMA`, `SYSTEMSCHEMA`, `FUNKTIONSSCHEMA`), ritas inte i skala. Linjerna visar vad som
hänger ihop, inte hur långt något är. Ett schema är därför inget misslyckat planblad:
- omdömet är SCHEMATIC, inte "ofullständig", och andelen rörnamn med meter gäller inte
- inget av dess rörnamn listas som missat; de står som rören schemat visar, och mängdas på planritningarna
- vyn frågar inte efter skala, och mängdtabellens rader står som SCHEMA
- komponenterna räknas, och i "Alla" ramas varje beteckning in
- läsningen betalas tillbaka som förut, med skälet att bladet är ett schema

**Ett antal skrivet isär är kodens antal.** Ett blad skriver buntarna vid en fördelare på två sätt: `4xKV1-X32-16`
och `6x VV1-X32-16`. Lästa som två ord var "6x" ingen kod, så raden togs för en anteckning och bunten den namnger
blev onämnd. En rad som skrev ännu en etikett bredvid, `8x KV1-X32-16 2xVV1-X32-16`, försvann hel. Mellanslaget är
bara mellanrum:
- antalet läses som där bladet skriver det ihop med koden
- två etiketter på en rad är två etiketter (`_counts_joined` i `semantics/annotation.py`)
- ett antal före något som inte är en kod, som `3x DUSCH-WC`, förblir en anteckning

**Determinism.** Samma blad läst två gånger ger samma signatur, och ett blad läst mellan två andra påverkas inte
av dem. Det prövas (`determinism.py`) och det gäller så länge ingen andra läsare kopplas in (se §3).

**Kontamineringsbrandväggen.** Produktionskoden får inte läsa facit eller referensritningar, och innehåller inga
ritningsspecifika literaler. Det skannas (`contamination.py`) och står som `PASS` i varje läsnings sammanfattning.

---

### 2b. Vad bladet förklarar i ord

En ritning kan säga en sak om rör utan att skriva den vid varje rör. Ett helt projekt skriver på varje blad
*"Kopplingsledningar från fördelare till apparat enligt tabell om inget annat anges"* och en tabell med
beteckningsstammen per system (VV01-X31, KV01-X31) och dimensionen per apparat (16), och drar sedan nittio korta
rör från fördelarskåpen till blandare, tvättställ och toaletter utan en enda etikett. Läsningen, som bara följer
hänvisningslinjer, ägde inget av det - fjortonhundra meter på trettiotre blad.

`semantics/declarations.py` läser den regeln av form och av ritspråkets få ord för den (ett stycke som nämner
kopplingsledningar och säger "enligt tabell" eller "om inget annat anges", och under det en rad stammar med
talkolumner). Ägandet (`pipes/ownership.py`) tillämpar den sist av allt och bara på geometri som ingen annan
läsning rört: en primitiv som är **oägd** - aldrig tvetydig, aldrig en som en etikett nått - på en penna vars
lagernamn bär det förklarade systemet får den förklarade identiteten. Ett lager som två förklarade system skulle
kunna heta får inget. Varje sådan meter märks `DECLARED_CONNECTION_PIPE_BY_SHEET_TABLE` och redovisas som
`declared_m` på mängdraden, med `label_count` 0, så att en människa ser skillnaden på ett rör som pekats ut och
ett rör som förklarats. Regeln som lästes skrivs till `drawing-declarations.json`.

Det är inget närmaste-antagande: det är ritningens egen regel, skriven i ord, för exakt de rör ritaren inte
namngett. Utan tabellen ägs ingenting. Och regeln namnger kopplingsledningar, som är korta: en onämnd,
sammanhängande sträcka längre än `pipes.ownership.DECLARED_RUN_MAX_M` (15 m) på den förklarade pennan är en stam
vars etikett läsningen inte nådde, och den står kvar som onämnd i stället för att döpas efter tabellen.

### 2c. Vad som är ett rör: streck-prick, ventiler, dubbellinjer

Tre ritkonventioner som läsningen läser som geometri, inte som antaganden (`pipes/representation.py`,
`measure/measure.py`):

* **Streck-prick-linjen** är ett rör. Pricken är en och en halv punkt lång och exportens avrundning vrider den
  några grader, så den har ingen riktning att lita på; strecket vars stråle den ligger på gör anspråk på den
  (`DOT_MAX`), på geometrin ensam - en prick inom `DOT_GAP_MAX` på strålen hör till linjen oavsett om pennan
  ritar nog många prickar för att springan ska bli ett mönster. Då är springan streck-till-prick en springa av
  linjens stil och bryggas, även där en prick saknas och även i en svag knäck. Utan regeln blev nittio meter
  värmeledning tvåhundrafyrtiosju bitar.
* **En ventil i linjen** avslutar inte röret. Ritaren drar röret fram till ventilsymbolen, ritar ventilen med
  symbolpennan och drar vidare på andra sidan. Två fria, kollineära ändar med en liten symbol av en annan
  penna i springan (`SYMBOL_SPAN`, `SYMBOL_SIZE`) hör ihop: bryggan heter `symbol` i grafen och bär symbolens
  id.
* **En skrafferad figur** är inget rör. En radiator ritas som en tunn rektangel fylld med ett par dussin
  skrafferstreck, på en penna för sig, och den pennan vägdes som rör: varje hänvisningslinje som gick förbi en
  radiator fick en andra kandidatfamilj, ankaret blev tvetydigt, och metrarna på det riktiga röret gick till
  ingen. En knut av streck vars bläck är mer än `pipes.representation.FIGURE_INK` (6) gånger sin egen
  utsträckning står still och fyller sin ruta: den sätts åt sidan innan någon graf byggs och redovisas som
  avvisad med skälet `DRAWN_FIGURE_NOT_A_RUN`, med strecken kvar att titta på. Mätt över korpusen ligger
  rörpennor på 0,8-2,9 och skrafferade radiatorer på 8,8-15,7.
  Den andra läsaren tog strecken i en sådan figur för rörsträckor, och de lades till läsningens egen geometri.
  På ett blad mättes så fyllningen i tjugotvå radiatorer, ungefär tjugo meter, som värmerören som slutar vid dem.
  Den andra läsarens streck prövas nu med samma mått, på hela pennan, innan de läggs till (`merge_detection` i
  `source_rules/native_bridge.py`). De som står still redovisas som `native_strokes_of_drawn_figures`.
* **Ett rör ritat som två linjer** är ett rör. Ett grövre rör ritas som sina två kanter, ytterdiametern isär i
  bladets skala, och etiketten med ett streck på var kant namnger båda. Två sträckor med samma namn och samma
  penna sida vid sida längs större delen av den kortare, på det avstånd rörets diameter ger (1,6 × dy i skala,
  aldrig över `measure.measure.DOUBLE_LINE_MAX`), räknas en gång: den längre kanten bär metrarna, den andra
  redovisas som `double_line_m` på raden och i exporten. Avståndet följer dimensionen av ett skäl: ett DN16-rör
  är en punkt brett i 1:50 och kan inte ritas som två kanter, så två DN16-linjer några punkter isär är två
  kopplingsledningar i en bunt - och båda räknas. Utan känd dimension eller skala viks ingenting.
* **Ett rör ritat som sin kontur** är också ett rör. På ett sektionsblad i 1:20 ritas rören i skala, ofta i ett
  enda streck: längs ena kanten, runt änden och tillbaka längs den andra. Tre saker gäller då:
  * Hänvisningslinjen slutar mitt i röret, på centrumlinjen, och rör ingen kant. En ände mellan två långa,
    parallella kanter av *samma* streck, ett rörs bredd isär och utan något närmare på någon sida, har hittat sitt
    rör (kontakten `between_edges`, gränserna `semantics.attachment.EDGES_APART_MIN/MAX` och `EDGES_PARALLEL`).
    Mellan två olika streck - två rör bredvid varandra - har linjen inte sagt vilket, och då väljs inget.
  * Ett rör vars två kanter är samma streck mäts en gång (`own_second_edge_pt`): det som går bredvid sträckan
    själv på rörets avstånd går dit parvis, och hälften redovisas som `double_line_m`.
  * Ett namn som går vidare längs sammanhängande ritning går från kontur till kontur och från linje till linje.
    På ett sektionsblad ritat med en penna hänger golvet, en pelare och en tanks mantel ihop med rören, och utan
    den regeln mättes golvet som kallvatten. Regeln gäller bara en penna där mer än hälften av det etiketterna
    redan namngett är konturer (`OUTLINE_PEN_SHARE`). På en planritning är rören linjer, och ett streck som går
    ut till en armatur och tillbaka bredvid sig själv är ett rör: där tog regeln 43 m från ett blad.

  Läsningens egna hänvisningslinjer blir aldrig rör i grafen. På ett blad som skriver med samma penna som det
  ritar med tog den andra läsaren dem för rörsträckor, och när grafen delades vid ett markeringsstreck samlades
  pennan in igen med dem: varje hänvisningslinje hängde då ihop med röret den pekar på och mättes som det röret.
  Undantaget gäller bara hänvisningslinjerna i den läsning som behölls. Bokstäver och understrykningar räknas inte
  dit: på ett referensblad tog textläsningen streck i en streckad rörlinje för bindestreck, och de kom bara
  tillbaka genom de två vägarna. Och det gäller inte en sida läst ur bild: där är en spårad hänvisningslinje en
  del av skelettet, och den kan fortsätta in i röret den pekar på.
* **Ett tick-streck draget över två rör markerar båda.** Ticken är ritarens besked om vilket rör etiketten menar,
  draget tvärs över röret. Ett rör ritat i skala är två linjer, och två rör sida vid sida är det också. Korsar
  ticken - vid linjens ände eller längs den - exakt två parallella rörlinjer får båda en kontakt där ticken
  korsar dem (`_tick_across`), oavsett om linjen själv slutar på den ena eller mellan dem, och oavsett om
  linjerna är ritade med olika pennor. Ticken själv blir aldrig röret, inte heller där den är ritad med en
  rörpenna. Korsar ticken en linje gäller det som förut, tre eller fler är en bunt där varje rad har sin egen
  tick, och två linjer som möts under ticken är ett hörn - en radiators anslutning som svänger in i sin stump -
  som också läses som förut. Två kanter av samma rör räknas en gång av dubbellinjeregeln. Förut gjordes ticken
  till en punkt, och slutade linjen mellan kanterna togs ticken för en samlingslinje som nådde flera rör:
  etiketten blev tvetydig och inget rör fick namnet. Regeln gäller inte en sida läst ur bild, där ticken och
  linjerna är spårade ur pixlar: där tog den 1,4 och 2,4 procentenheter rätt längd från två rasterblad.
* **Ett rör som slutar mot en linje ger inte linjen sitt namn.** Där ett namngivet rör tar slut mot en linje som
  går rakt igenom korsningen - en apparats hölje, ett golv, kanten på ett annat rör - går namnet inte vidare in i
  linjen. Linjen som passerar är ingen gren av röret och får inte heller rörets namn som kandidat
  (`_resolve_family` i `pipes/ownership.py`), och den andra läsaren lämnar den också (`ends_against` i
  `native_assignment._settle_unowned`). En gren som lämnar ett rör som fortsätter genom korsningen tar som förut
  rörets namn. Utan regeln förde ett rör som gick in i en värmepump sitt namn runt hela värmepumpens hölje. Den
  andra läsarens del gäller inte en sida läst ur bild, där en spårad linje bryts upp i sådana korsningar som inte
  finns på ritningen: där tog den 0,7 procentenheter rätt längd från ett rasterblad.
* **Ett aggregat ritat med rörpennan är inget rör.** Ett blad ritar sitt luftbehandlingsaggregat låda bredvid
  låda, varje låda med dubbel kant, med samma penna som värmeröret som matar det. Röret som slutar vid
  aggregatet hamnade i aggregatets knut. Knuten nådde då lika långt som röret, och bläcket räckte inte för att
  den skulle stå still. Aggregatet mättes därför som röret, runt varje låda: fyrtio meter på ett rör om sextio.
  - Ett objekts streck sluter sig. En sträcka gör det aldrig, för hur den än grenar sig är den ett träd. Strecken
    som ligger på en sluten slinga i knutens egen ritning vägs därför en gång till, för sig och med samma mått
    (`_closed_strokes` och `figure_pieces` i `pipes/representation.py`).
  - Ett objekt är större än en symbol i linjen (`SYMBOL_SIZE`, 30 pt). En ring i slutet av ett rör eller en
    ventilkropp sluter sig också, men röret fortsätter genom den. Utan gränsen togs en ring vid ett rör ritat som
    kontur på ett sektionsblad, och röret bakom ringen förlorade sitt namn.
  - Det som ligger helt inne i ett sådant objekt hör till objektet, till exempel fläkten med sitt kryss.
  - En ringledning runt ett rum och ett rör ritat som sin kontur är slingor med lite bläck för sin utsträckning.
    De står kvar som rör.

### 2d. Blad där all text är ritade streck

En del blad är plottade ur CAD utan ett enda tecken som text: beteckningar, förteckning, stämpel och skalstockens
siffror är streck. Läsningen tar texten ur strecken, och strecktexten förväxlar tecken som liknar varandra (O och 0,
S och 5, I och 1, B och 8). Dessa regler gör att ett sådant blad mängdas i stället för att stå på 0 %:

* **Förteckningens platshållare** (`semantics/legend.py`, `opens_with`). En förteckning kan skriva systemnumret som
  `XX` (`KVXX-3`, `VSXX-22`) och förklara det på en egen rad ("XX avser systembeteckning"). En etikett `KV02-3-15`
  öppnar då med koden: stammen, ett till tre tecken i numrets ställe och resten av koden, jämförda med tvillingarna
  utjämnade. Det som följer numret måste stämma (`VS02-22-12` öppnar inte med `VSXX-2`). Utan regeln användes ingen
  av förteckningens koder och varje etikett avvisades som inget rörnamn.
* **Stämpelns skala** (`measure/scale.py`, `ratios_in`). `SKALA 1:50 (A1) 1:100 (A3)` lästes som "1:5O I A1": parentesen
  blir ett I, och ett I där en siffra ska stå är en etta - 1:501. Där talet efter "1:" inte är någon skala man ritar i
  men blir en före en bokstav som läses som etta, är skalan det som står före. En stämpel som skriver formatet först,
  `A3=1:100`, säger detsamma som `1:100 (A3)`.
* **En penna som etiketterna märkt är ingen skrivpenna** (`pipeline.WRITING_PEN_TICKED_LABELS`, 2). En penna vars
  varje streck börjar eller slutar vid en textruta tas för skrift. Men värmerör ritade fram till små ringar vid
  radiatorerna slutade "vid text" när ringarna lästes som O. En hänvisningslinje sätter sitt märke på röret den pekar
  på, så en penna som två etiketter märkt ritar rör.
* **Ett blad som läser sin egen förteckning står rätt** (`pdf/orient.py`, `LIST_MIN`, 8). Vridningen väljer det håll
  där flest rörnamn läses. Läser bladet minst åtta av sina egna förteckningsrader som det ligger, och läser det
  vridna färre, vrids det inte: fler namn på tvären är tvillingläsningar, inte rör.

* **Den öppna fyran** (`text/recognize.py`, `_open_four`). Teknisk textning ritar 4:an öppen: diagonalen och den
  lodräta linjen möts inte, och tecknet sluter ingen yta. Mätt bara mot slutna fyror blev den "?", och varje
  beteckning med en fyra försvann (KB02-3-54, S54-75, RV51-40). Den öppna formen byggs ur samma alfabets slutna
  fyra: den lodräta linjen börjar mitt emellan spetsen och tvärstrecket.
* **Korta kodrader staplade i en lista** (`text/strokes.py`, `_stacked_baseline_angle(beside=True)`). "S54" över
  "S6" lästes som en kolumn och kastades. Bredvid en säker textrad räcker två rader, en med tre och en med två
  tecken, för att läsa dem som rader i grannradens riktning.
* **Mediet före LEDNING, genom olästa bokstäver** (`semantics/legend.py`, `role_from_words`). KALLVATTENLEDNING
  är kallvatten, och SPI??VATTEN?EDNING är spillvatten: ett efterled LEDNING skärs av, och högst två olästa
  tecken godtas i ordet.
* **Tätt satta rader hålls isär** (`text/strokes.py`, `_lines_by_full_letters`). Ett kommatecken vid en rads fot
  och lösa tvärstreck i nästa rads E och T band ihop två listrader till en rad frågetecken, och koden bredvid blev
  utan beskrivning och togs för en rubrik (VV1 TAPPVARMVATTEN, hela VENTILER-avsnittet). En sammanhållen rad som är
  högre än en textrad delas nu efter var dess bokstäver i full höjd står, och småbitarna går till närmaste rad. Ett
  skiljetecken vid fötterna på bokstäverna bredvid är radens egen interpunktion, inte en prick över bokstaven under.
* **En bit av ett ord ersätter inte ordet** (`semantics/annotation.py`, `_a_piece_of`). Ringen i ett Å, läst för
  sig som `O`, ersatte `PÅFYLLNINGSVENTIL` som om de vore samma text två gånger. Ett eller två tecken inne i en
  fullt läst rad av samma slag är en del av raden.
* **Listans rubriker säger vad koderna är** (`semantics/legend.py`, `role_from_heading`). Under SYSTEM står
  system, under MATERIAL och ISOLERINGTYP material- och isolerklasser. `S2 KALLVATTEN` under ISOLERINGTYP är
  isoleringen för kallvatten och inget kallvattensystem. En kod som står i två avsnitt (`S1` spillvatten och `S1`
  köldbärarisolering) öppnar ett rörnamn som det system ett av avsnitten säger att den är.
* **Listan slutar där den slutar** (`semantics/legend.py`, `_one_block`, `LIST_BREAK_ROWS` = 10). Samma vänsterkant
  löper ofta vidare ned i namnrutan, och konsultlistan (`V VVS-KONSULT AB`, `E ELKONSULT AB`) lästes som mer av
  listan: `V` blev ett system och bladets eget nummer `V50-02-421` mättes som ett rör, 184 m. Ett hopp mellan
  listans poster på mer än tio postavstånd avslutar ett block, och listan är det största blocket. Listans egna
  avsnitt ligger några rader isär och står kvar; på korpusens 33 blad föll bara noter och namnrutans rader bort.
* **Senare led i en parbeteckning** (`assign_roles`). I `VV02-3-/KV02-3-15` öppnar KV ett rör lika säkert som VV.
* **Systemnumret med siffror** (`number_as_listed`). Där en listkod säger att ett systemnummer står (KVXX-53),
  skrivs KVO1 som KV01.
* **Ett rörpar i vilken ordning som helst** (`pipes/ownership.py`, `identity_from_text`). `VV01-53-/KV01-53-20` och
  `KV01-53-/VV01-53-20` är samma par. Hållna i skriven ordning gjorde de anspråk på samma rör, och röret blev
  ingens.

* **En jämlike heter som rörpennorna** (`pipeline.PEER_FOLLOWS_THE_BEST_LAYERS`). Jämlike-regeln - en penna som
  bär en rimlig andel av etiketternas ändar tas som rör bredvid den bästa - är skriven för blad utan lagernamn.
  På ett blad där rören ligger på `v50_p270|V-55512` och arkitektens väggar på `A30_p270|A040` tog två
  hänvisningslinjer som slutade på en vägg väggarna som rör: 91 m vatten runt toaletterna, 68 m värme längs
  fasaden. Har pennorna lagernamn måste en jämlike följa den namnmall som bladets etiketter når mest, alla
  dess pennor tagna tillsammans. Detsamma gäller en penna som tas för att den bär en stor andel av märkena:
  inredningens `I40_p270|I050` bar sex märken av hänvisningslinjer på väg till rören och drog med sig 190 m
  onämnd "rörgeometri".
* **En höjd vars decimalkomma lästs som snedstreck är en höjd** (`semantics/annotation.py`, `ELEV_RE`).
  "VG+28,46" lästes "VG+28/46", blev en beteckning med dimension 28 och tävlade med rören den stod över.
* **Bara rörbeteckningar kan göra ett lager till ett annat systems** (`pipeline.CONFLICT_ONLY_WITH_PIPE_LABELS`).
  En snittmarkering skriver ritningen snittet står på, "V50-02-271", och dess V50 är samma prefix som bladets
  lager bär. Räknad som system gjorde den varje rörlager till "V50:s lager" och varje etikett till en
  konflikt - ett helt blad mätte ingenting. Bara system som bladets rörbeteckningar (enligt listan) namnger räknas.
* **Den andra läsarens streck följer rörlagren** (`source_rules.native_bridge.NATIVE_JOINS_THE_PIPE_LAYERS`). Den
  tar varje långt streck för rör. Planens bakgrund (`pr1_0200A|P-------O-`) kom tillbaka som 45 m onämnt rör på
  varje blad. På ett blad med lagernamn läggs strecken bara till pennor som tagits som rör, pennor vars lager heter
  som deras, eller pennor dess egna etiketter landar på.

* **Bladets anteckning om radiatorer** (`semantics/declarations.py`, `_declared_branch`; `pipes/ownership.py`,
  `_declare_branches`, `BRANCH_RUN_MAX_M` 6 m). "RADIATORER ANSLUTES MED DIM. 12 OM ANNAT EJ ANGIVES" är
  radiatoranslutningarnas etikett. En kort onämnd gren - eller en som lämnats i tvivel bara för att inget stod i
  dess fria ände - som på samma penna möter namngivna rör av ett enda namn, ett namn listan kallar värme, får det
  namnets stam i anteckningens dimension (VS02-22-15 ger VS02-22-12). Metrarna redovisas som deklarerade.

Ett inskannat blad med samma stämpel får ingen skala ur bilden: där skrivs skalan in för hand, och mängden granskas
alltid.

**Streckmönster på inskannade blad** (`pipes/representation.py`, `RASTER_TOL.gap_window`). Ett streck-prick-rör
fogas ihop genom glappen i sitt mönster, och mönstret är den glappstorlek som återkommer i pennan. På en sida läst
ur bild flyttar pixlarna glappen: samma glapp om 9 pt lästes som 8,75, 9,0 och 9,25 i nästan lika delar, ingen
enskild storlek nådde andelen ett mönster kräver, och en plan vars rör alla är streck-prick mätte 24 m. På en sida
läst ur bild räknas glapp inom en halv punkt som samma glapp; samma plan mäter nu 73 m. Vektorsidor räknas som förut.

**Spårarens krokar** (`pipes/representation.py`, `RASTER_TOL.end_hook`, `_end_strokes`). En spårad linje slutar i
en krok: den sista pixeln eller två böjer av mot ett hörn av bläcket, ett streck på en halv punkt snett mot
linjen. Sedd från änden pekade varje linje då åt fel håll, och inget glapp i den fogades ihop - inte där en
hänvisningslinje korsade röret och spåraren bröt det, inte mellan streck och prick. På en sida läst ur bild har
en fri ände nu riktningen från strecket kroken hänger i; samma plan går från 73 till 222 m. Exporterade vektorer
har inga krokar och läses som förut.

### 2e. Det som ska granskas mäts och markeras ändå

Det läsningen inte kan avgöra lämnades tidigare utanför: ett rör två etiketter namnger olika stod "påpekat men
onämnt", ett rör på en rörpenna som ingen etikett når var en grå linje och en siffra, och ett skannat blad vars
skala bara stod i stämpeln blev noll meter. Nu mäts det och markeras att granska, utan att något kallas
bekräftat som inte är det.

* **Skannat blad med skaltext** (`measure.scale.IMAGE_TEXT_SCALE_IS_MEASURED`). Bladet mäts på skaltexten. Varje rad
  heter LÄST UR BILD och skälet säger att skalan inte kunde mätas i bilden.
* **Bästa läsning bland kandidater** (`pipes.ownership.BEST_READING_AMONG_CANDIDATES`). En tvetydig sträcka mäts under
  det namn bladets etiketter stöder mest (etiketter på sträckan, namngivna grannsträckor). Metrarna står på
  namnets rad som `proposed_review_m`, "+ X att granska", utanför den bekräftade summan. Kandidaterna skrivs på
  sträckan, som ritas streckad med gul kant. Den tvetydiga redovisningen (`ambiguous_m`) står kvar.
* **Onämnt rör** (`pipes.ownership.UNNAMED_RUNS_ARE_ROWS`, `UNNAMED_PEN_NAMED_SHARE` 25 %). Onämnda sträckor på en
  penna där minst en fjärdedel av bläcket har namn blir raden "Onämnt rör (penna)", `unnamed_review_m`, utanför den
  bekräftade summan. En bakgrundspenna ger ingen rad. I läget "Alla" görs inga sådana rader.
* Läsningens egna tillstånd ändras inte. Förslagen byggs vid sidan av (`OwnershipResult.review_pipes`) och skrivs
  till `review-pipes.json`. Agenten, rättelserna och de inlärda reglerna arbetar på läsningens egna rör, och
  vyn ritar båda.

## 3. Vilka AI-modeller som används, och exakt hur

Det här är det viktigaste avsnittet att läsa rätt, så det är rakt.

**Mätningen använder ingen språkmodell.** Varje meter i mängdtabellen kommer ur geometri, hänvisningslinjer och
regler i Python. Ingenting i mätvägen når nätverket. Det är vad som gör läsningen deterministisk och möjlig att
spåra.

Det finns fyra ställen där en modell *kan* kopplas in, alla utanför mätvägen, alla avstängda utan nyckel, och
ingen av dem kan hitta på en meter:

**Valet innan en analys startar.** Rutan "Välj AI-modell" har GPT-6 Astra förvald och ifylld så snart tjänsten
har en OpenAI-nyckel; utan nyckel är "Utan AI" förvalt. Den som startar analysen kan alltid välja en annan modell
eller ingen, och det senaste egna valet kommer man ihåg i webbläsaren. Operatören kan stänga av förvalet med
`VVS_ASSIGNMENT_MODEL=0`.

**Vad modellen får se.** Varje fråga till den valda modellen bär hela bladet som översikt och inzoomade utsnitt
(320 pt av bladet, 768 bildpunkter) av allt frågan gäller: rörets egna punkter, varje kandidatbeteckning och
båda ändarna av dess hänvisningslinje. Ett anrop rymmer högst sex utsnitt; frågor spridda över fler delar av
bladet än så delas på flera anrop i följd, så att ingen beteckning, inget rör och ingen hänvisningslinje bara
syns i översikten (`backend/app/source_model.py`, `_zoom_groups`). Översikten är densamma i varje anrop och
cachas hos leverantören.

**Svepet över det som är kvar** (`completeness_check.py`, `AssignmentTransport.sweep`). Efter frågorna står ofta
något oförklarat kvar: ett onämnt rör ingen etikett når, en etikett som inte namngav något rör, frågor som taket
(`MAX_QUESTIONS`, 120) lämnade. De delar av bladet där sådant står och som modellen inte redan sett inzoomat visas
för den en gång, högst `SWEEP_MAX_TILES` (12) rutor, sex per anrop, alltså högst två extra anrop per blad. Ett
blad där allt är förklarat kostar inget. Modellen svarar bara med beteckningar den ser där och som läsningen inte
läste; en sådan erbjuds de onämnda rören vid den, bara om bladet självt skriver samma beteckning med dimension
någon annanstans, och det modellen namnger så står som att granska. Annat redovisas som "sett, inte läst".
Rutor, anrop och frågor taket lämnade står på raden "Läst med …". `VVS_SHEET_SWEEP=0` stänger av svepet.

**Taket på AI-kostnaden** (`backend/app/api_budget.py`, tabellen `api_spend`). Allt tjänsten lägger på
språkmodeller går mot ett tak, 10 000 kr från början:
- tilldelningen under en analys, kompletteringsfrågorna och svepet
- agenten och samtalsagentens textsvar
- andra läsaren och synkontrollen

Varje anrop frågar först om det får göras. Efteråt bokförs vad det kostade: anropets egna tokens gånger
modellens listpris och växelkursen. Raden bär priset den räknades med.

När summan sedan den senaste nollställningen når taket låses AI för hela tjänsten. Valrutan och varje
AI-funktion säger då att alla krediter för AI är förbrukade, och analyser kan fortfarande köras "Utan AI". En
pågående analys slutar fråga när taket nås och läser resten med reglerna.

En modell utan pris i prislistan får inte anropas. Prislistan, växelkursen, taket och nollställningen finns
under Administration → AI-kostnad, och utgångspriserna står med källa och datum. Röstassistentens samtal går
direkt mellan webbläsaren och OpenAI och syns inte i reskontran; taket avgör bara om ett samtal får starta.

### 3.1 Andra läsaren (`semantics/astra.py`, transport i `engine/tools/astra_transport.py`)

*Modell:* OpenAI, standard `gpt-6-astra` (miljövariabeln `VVS_SECOND_READER_MODEL`), via Responses-API:et.

*När:* bara för ett fall som motorn själv redan förklarat tvetydigt, och bara där ritningen erbjuder en kort
lista av verkliga kandidater. Frågan bär kandidaterna. Svaret måste vara en av dem, tecken för tecken -
`verify` vägrar allt annat. Modellen kan alltså aldrig namnge ett rör, en penna, en dimension eller en meter som
läsningen inte redan lagt fram; den kan bara göra `AMBIGUOUS` till ett av svaren som redan låg på bordet.

*Bevis:* varje avgjort fall skriver ned att en modell valde, mellan vilka kandidater och varför, så att en
läsare kan se det och säga emot.

*Av/på:* av utan `OPENAI_API_KEY`. Med nyckel: på. `VVS_SECOND_READER=false` stänger av oavsett; `true` tvingar
på bakom en proxy som fäster referensen. En läsning som rådfrågat den säger det, och påstår då inte
determinism.

### 3.2 Agenten (`backend/app/agent.py`, verktygen i `engine/vvs_engine/agent/tools.py`)

*Modell:* samma transport och modell som ovan (`agent_transport`).

*Delningen:* modellen bestämmer **vad** som ska frågas, verktygen bestämmer **vad svaret är**. Modellen ser
verktygens namn och deras svar - aldrig geometri den kunde hitta på ur. Varje siffra i chatten kommer ur ett
verktygsanrop över de artefakter mätningen skrev, så ett svar i chatten och en rad i mängdtabellen kan inte
skilja sig åt. 26 verktyg för en ritning (mängda, hitta rör, följ nätet, varför äger det här röret sina meter,
vad togs inte som rör, och fem `foresla_`-verktyg som bara föreslår), 8 för hela handlingen (projektagenten, `agent/project_tools.py`: hus, blad,
mängder per hus, versioner, ändringar, vad som bör tittas på).

*Förslag är ord.* Verktyg som föreslår en rättelse skriver ingenting: de säger vilken rättelse de skulle skriva
och vad läsningen säger att den kostar. Först när en människa godkänner körs samma anrop igen på servern, och
det som kommer ut är det som skrivs - metrarna i loggen är läsningens, aldrig modellens.

*De färdiga frågorna* i panelen går rakt in i verktygen utan modell. De kan inte hitta på en siffra. Fritext
behöver modellen för att välja verktyg; det är hela skillnaden.

### 3.3 Vision (`review/vision.py`)

*Modell:* samma, med bilder (`vision_transport`). Sidan renderas som bild, rutas in, och modellen får se den
tillsammans med läsningens egna sträckor ritade ovanpå.

*Vad den får göra:* titta och säga. Fynden är ord: "här ser det ut som om..." De kan aldrig bli geometri -
`vision.look` har ingen väg in i en läsning. Risken är kostnad och tid, aldrig en fel meter.

### 3.4 OCR (`review/ocr_check.py`) - ingen språkmodell

`rapidocr-onnxruntime`, en lokal teckenigenkännare. Två användningar: som en oberoende andra läsning av bladets
text i granskningen (finns det beteckningar vektorläsningen missade?), och för att namnge de tecken
streckigenkännaren inte kunde. Den läser aldrig ritningen på egen hand; vektorgeometrin förblir mätningens källa.

**Båda är avstängda som standard, och det är mätt.** Samma blad kört med och utan:

| blad | allt på | utan OCR-korsprov | utan teckenhjälp | ändrad mängd |
|---|---:|---:|---:|---|
| A (A1, 176 beteckningar) | 74,8 s | 58,1 s | 57,8 s | nej - identisk rad för rad |
| A0124 | 34,6 s | – | 17,4 s | nej |
| B0122 | 34,0 s | – | 18,7 s | nej |

Korsprovet **kan** aldrig ändra ett mått: granskningen får inte röra läsningen, och mängderna var byte för byte
lika med och utan. Teckenhjälpen **kunde** ha ändrat något men gjorde det inte: på A0124 löste den 0 av 59
okända tecken, på B0122 0 av 30, på A 3 av 24 - och mängden blev densamma i alla tre fallen. På de tyngre
bladen är den halva analystiden.

Vad man förlorar är alltså en varning, inte en meter. Slå på dem under **Administration → Vad läsningen kör**
(eller `VVS_REVIEW_OCR=true` / `VVS_OCR_ASSIST=true`) på en installation vars ritningar läses sämre - det syns i
granskningen, och analysen tar då ungefär dubbelt så lång tid.

### 3.4b Vad andra läsaren är värd, i meter

Andra läsaren (3.1) rör bara fall motorn förklarat tvetydiga. Över de 33 bladen i porten är det **179,5 m** -
2,9 % av facit, 14 % av det vi missar - och det är ett *tak*: så mycket skulle den flytta om den svarade rätt
på varje fråga. Ett fel svar gör i stället en saknad meter till en falsk, vilket är dyrare. Porten kördes utan
den (`consulted: false`), så 80,0 % täckning och 27,3 % falskt är siffror utan språkmodell.

De stora felkällorna ligger någon annanstans: deklarerade anslutningsrör som facit inte räknar, och lodräta
meter som tabellen har men planen inte ritar. Ingen av dem är en tvetydighet en modell kan avgöra.

**Var tiden faktiskt går** (blad A, 94 s): hänvisningslinjer och fästen 52,8 s, teckenrekonstruktion 5,3 s,
PDF-läsning 0,7 s, mätning 0,6 s. Att stänga av båda OCR-passen tar bort ungefär en tredjedel av tiden; resten
är geometri.

### 3.5 Vad som *inte* är AI: inlärningen (`learning.py`, `corrections.py`)

Systemet "blir smartare" av rättelser, men inte genom träning och inte genom en modell. Regeln är smal och
uttalad:

En rättelse får göra exakt en sak på ett senare blad: **avgöra ett fall motorn själv redan markerat tvetydigt**,
till förmån för det svar en människa gav i samma situation. Den får aldrig skapa en sträcka, aldrig namnge
geometri ingen linje nådde, aldrig ändra en sträcka motorn är säker på, och aldrig rösta ned ritningen.

"Samma situation" är inte en likhetspoäng. Det är exakt träff på sex saker, alla lästa ur ritningen: pennan
(bredd och färg, utan lagret), hur bladet ritar sina hänvisningslinjer, motorns eget skäl att stanna,
beteckningens form (bokstäver och skiljetecken, inte siffror), fallets topologi (räknat, inte koordinater), och
vilka kandidater bladet erbjöd. Matchar inte alla sex talar lärdomen inte - två blad som bara liknar varandra
är två olika ritningar. Att bredda avtrycket kan bara få lärdomar att tala mer sällan, vilket är den riktning
det är säkert att ha fel åt.

Adminsidans "Inlärning" visar precis det: vilka lärdomar som finns, hur många gånger var och en talat, och
vilka rättelser som inte bar någon lärdom alls.

### 3.6 Nycklar

Ingen nyckel finns i repot, i en fil, i en logg eller i ett svar. `OPENAI_API_KEY` läses ur miljön i det
ögonblick anropet görs och läggs på tråden, ingen annanstans. Bakom en agentproxy som fäster referensen efter
att anropet lämnat maskinen skickas ingen nyckel alls härifrån.

---

## 4. Rättelser: vad en människa kan ändra, och vad det får lära ut

En människa som läser samma blad ser saker ritningen säger på sätt motorn inte har någon regel för ännu. Fem
sorters rättelse finns (`corrections.py`): förläng en sträcka, rita en ny, sudda, byt beteckning, sätt mängden
för hand. De läggs *ovanpå* läsningen, aldrig i den: motorns egen siffra står kvar bredvid den rättade
(`engine_total_m`), så det alltid syns vad som lästes och vad som ändrades. Varje rättelse går att ångra.

Rättelsen sparas med den **situation** den gjordes i (§3.5). Det är servern som läser av situationen ur sina
egna artefakter - en påhittad situation från klienten avvisas - för en tom situation skulle tyst stänga av hela
inlärningen.

Exporterna bär den rättade läsningen, med motorns siffra bredvid. En fil som visade en siffra läsaren redan
avvisat på skärmen, i det dokument de prissätter ur, vore fel sorts fil.

---


**Böja ett streck.** Ett ritat rättelsestreck, en ritad förlängning eller en längd- eller ytmarkering kan böjas så att
den följer röret, både som utkast innan det sparas och i efterhand med "Ändra form":
- dra i ett **+** mitt på ett segment för en ny brytpunkt
- dra i en **ruta** för att flytta en punkt
- dubbelklicka på en ruta för att ta bort den

Punkterna fäster mot ritningens egna linjer ("Fäst mot ritningen", på som standard), och metrarna räknas om medan man
drar. En sparad rättelse får sin nya form via `PUT /api/drawings/{id}/corrections/{cid}/shape`. Typ och beteckning
står kvar, de tidigare formerna sparas i `earlier_shapes` och en ångrad rättelse kan inte böjas. Punktfunktionerna
finns i `frontend/src/edit/bend.ts`.

## 5. Projektanalysen: hela handlingen som en modell

En enkel analys läser en ritning och svarar med meter. Projektanalysen (`handling.py`, `backend/app/projects_api.py`)
läser alla blad i ett projekt och svarar med vad handlingen består av: hus, discipliner, skeden, versioner,
vad som hör ihop och vad som inte gick att avgöra.

Läsningen är billig med flit - den läser namnrutorna, inte geometrin, sekunder per blad - och den har en egen kö
så att den aldrig står bakom en halvtimmes mängdning.

**Ett före och ett efter får aldrig hittas på.** Ett par påstås bara när handlingarna själva bär ordningen: en
revisionsbeteckning, ett revisionsdatum, ett handlingsdatum eller ett skede. Ett tal i filnamnet är ingen
revision (`Hus A (2).pdf` är vad en webbläsare gör), och två handlingar från samma dag med samma status är två
discipliner i samma skede, inte två versioner. Det som inte går att ordna står som oklart, med vad det verkar
vara.

**Ändringsregistret** jämför två *läsningar*, inte två ritningar. Att en beteckning bara finns på ena bladet är
starkt. Att dess meter skiljer sig är svagt - två läsningar av samma oförändrade rör rör sig något - och under en
halvmeter eller fem procent räknas skillnaden inte som en ändring. Saknas läsningen på någon sida finns ingen
lista alls: att fylla i den saknade sidan med noll skulle göra hela den lästa sidan till "tillkommet".

Mängderna summeras **per hus och aldrig över projektet**: hus A och hus B har var sin beteckningslista.

Varje fält läsningen kom fram till går att rätta för hand, och rättelsen ligger kvar när analysen körs om. En
mapp som hette "Hus B" visade sig innehålla hus C:s ritningar - läsningen hade rätt och mappnamnet fel - men den
har inte alltid rätt.

---

## 5b. Läget "Alla": varje beteckning på bladet

Ett projekt kan läsas i disciplinen **Alla** i stället för VVS (`disciplines/data/alla.json`). Rören läses och
mäts exakt som i VVS, och en VVS-läsning får ingenting av det här. Bredvid mängden skrivs ett register över varje
beteckning bladet skriver, oavsett disciplin (`register.py`, filen `all-designations.json`):

- **ledning**, i meter: det VVS-läsningen mätte på rören under just den beteckningen, med samma status
- **komponent**, i styck: en per skriven etikett. Ett antal framför koden räknas som det antalet (`4*TV103`)
- **klass**, i styck: en brandklass (`EI60`), eller en material- eller isolerklass som förklaringslistan förklarar
  och som står för sig själv. En tagg som börjar med en sådan kod och ett nummer (`SHG613-V52`) är en komponent.
- **rum**, i m²: den area rumsetiketten själv skriver (`abt/rooms.py`)
- **okänd**, i styck: det som varken bladet eller motorns referensdata säger vad det är

Det bladets egen förklaringslista inte förklarar står som **granskas**. Känner motorns svenska referensdata
koden visas dess ord bredvid, sagt som referensdata och aldrig som bladets besked.

En kod hör till den rad i listan som skriver den:
1. koden själv, eller den kod ett rörnamn börjar med (`KV1` i `KV1-K1-22`)
2. annars den familj listan skriver med platshållare, så att `B12ML` är listans `BXXX GOLVBRUNN`
3. annars, för ett rörnamn, systemkoden följd av systemets nummer (`KV` + `1`)

En kod som står ensam är aldrig en längre form av en kortare. En stomlinjes `A200` är inte listans `A`, och
`BL101` är inget `B`. En rad vars bokstäver lästs en och en ur streck förklarar ingenting.

Det som inte räknas:
- förklaringslistans egna rader
- ritningsnummer och filnamn
- mallar som `XX`
- mätvärden, eftersom ett decimaltal är ett värde och aldrig ett namn
- höjder: ett höjdord ur referensdatan (`level_references.json`: CL, VG, UK, ÖK, FG …) följt av ett tal, som
  `CL3441` för "CL 3441 ÖFG"
- ord: ett led med åtta bokstäver eller fler, även när ett bindestreck fäster det vid en kod (en rubriks
  `VS-INSTALLATIONER`)
- text som ligger utanför ritningens vyfönster och inte syns på bladet

Där bladet skriver sina etiketter som text kan strecken läsa fram en kod som inte finns, till exempel en mätares
ring läst som `O1`. En sådan kod räknas bara där bladet ger den stöd: den återkommer, den står också som text, eller
ett rör är mätt under den. Hur ett blad skriver avgörs av de flesta av dess etiketter ute på bladet. Ett blad ritat
med streck kan ha stomlinjernas bokstäver som text, och det gör inte strecken tvivelaktiga.

En not bredvid ett namn hör inte till namnet. `S3-P5-110 (L)` är `S3-P5-110`, och noten står kvar på raden där den
skrivs.

Ett namn som slutar på en klass och har storleken på raden under är mängdens namn. `KV1-K1/S2` över `22` är
`KV1-K1-22/S2`, som mängden skriver det och som bladet skriver det på en rad, och båda skrivsätten är samma rad med
mängdens meter. En ventiltagg med två storlekar (`SAV102-20/25`) står kvar som den är skriven.

Ur streck läses ett tecken ibland som sin tvilling. I en kod läst ur streck är ett O mellan två siffror en nolla, så
`RAD1O1` är `RAD101`, och en nolla mellan två bokstäver är ett O. `M0BIL` är alltså ordet MOBIL och ingen kod.

Registret visas i analysvyns flik "Alla beteckningar", där varje förekomst kan pekas ut på bladet. I ritningsvyn
ritar lagret "Alla beteckningar", som är på från start, in varje beteckning i sitt slags färg, som i den markerade
PDF:en: blått för ledning, grönt för komponent, brunt för klass, turkost för rum och orange för okänd kod. Ramen är
streckad där beteckningen ska granskas. Andra discipliners ledningar ritas streckade där de mättes, och ett klick på
en ram öppnar raden i fliken. Registret ritas också som rutor på den markerade PDF:en och exporteras som bladet "Alla
beteckningar" i Excel och i JSON-exporten. En VVS-läsning har inget register och inget sådant lager.

**Andra discipliners ledningar** mäts i en andra, vidgad läsning av samma blad (`widened_runs` i `pipeline.py`).
VVS-läsningen namnger en ledning bara med en kod som bladets lista kallar ett system, och räknar en etikettfamilj som
rör bara om etiketterna bär en DN. En kanal skrivs `TL01-Ø250` eller `FL01-400x200`, en kabelstege med sin bredd och
ett brandsläckningsrör med en kod som VVS-listan aldrig nämner. För VVS-läsningen namnger ingen av dem något.

Den andra läsningen använder värdena under `wide` i `disciplines/data/alla.json`, och bara där:
- En etikett som bladets lista inte nämner får namnge en ledning när den är skriven som en ledning: med ett
  kanalmått (`Ø250`, `400x200`, där bredden står först och är den bredd planen ritar) eller med en systemkod ur
  den svenska tabellen (BRL, KB, G …). En kod med löpnummer och storlek och inget mer är en tagg för en ventil
  eller en apparat (`AVT101-32`). Den räknas och mäts aldrig.
- Bara en etikett som bär en storlek eller ett system namnger en ledning. En tagg (ett uttags `UT1`, ett dons
  `TD01`) pekar på en sak. En elritning skriver långt fler taggar än ledningar, och räknade som ledningsnamn var
  taggarna de flesta av bladets etiketter utan att någon av dem nådde en ledning. Då förkastades läsningen, och
  kabelstegarna mättes inte alls.
- Bara en etikett som namnger en ledning ger en ledning dess namn. Det bladets lista förklarar som en sak räknas,
  också där taggen bär en storlek som en kanals (`TD101-Ø100`) och saken är ritad med kanalernas penna.
- En ledning ritad som sina två kanter mäts en gång. Kanalens eget mått avgör hur långt isär kanterna ligger.

Det den andra läsningen mäter behålls bara på linjer som VVS-läsningen inte tog, och bara under namn som mängden
inte redan har. En not som läsningen behållit bredvid namnet ändrar inte namnet: `S3-P5-160 (L)` är mängdens
`S3-P5-160`. Det som behålls står i registret som en ledning att granska, aldrig i mängden. Fliken tänder dess
linjer, och den markerade PDF:en ritar dem streckade. VVS-läsningen och dess filer är desamma som utan den. Den
andra läsningen frågar ingen modell och är deterministisk.

Gränser: en kanal ritad som en sluten kontur får sina ändar med i längden, alltså kanalens bredd en gång per
ände. Andra discipliners meter är prövade på syntetiska blad. Riktiga el-, ventilations- och sprinklerblad med en
mängdning saknas än.

---

## 6. Mängda för hand (mät, räkna, markera)

**Mängda** är en egen flik i sidomenyn och ett eget arbetsbord (`/mangda`, `frontend/src/pages/Takeoff.tsx`):
bladet till vänster, verktyget till höger. Det ligger vid sidan av läsningen, aldrig i den; de två redovisas var
för sig (eget blad i Excel-filen, eget namn i JSON:en). Fliken **Markera** på en läsning finns kvar för den som
vill rita medan hon läser.

Verktygen är de en mängdare behöver: **längd**, polylinje och frihand, med *multiplikator* och *tillägg* (en
stigare räknad som en punkt bär ändå sina meter); **yta**, rektangel och moln, med *avdrag* för hål i ytan och
*djup* som gör kvadratmetrarna till kubikmeter; **antal**, där varje klick får sitt löpnummer inom lagret; och
**anteckning**. Varje markering bär lager och beteckning, listan summerar per lager, verktyg och beteckning, och
hela listan går att ta ut som CSV.

**Skalan** kommer ur läsningen av bladet - men går den inte att läsa, eller gäller den inte för ett urklipp,
mäter mängdaren upp den själv: dra en linje över något vars längd är känd och skriv måttet. Den uppmätta skalan
går före läsningens för det bladet och den sidan, varje markering på sidan räknas om i den, och varje rad säger
vilken skala den mättes i. Utan skala står måttet i punkter, aldrig i påhittade meter.

**Verktygslådan** sparar förval - lager, beteckning, djup, multiplikator - som följer med till nästa blad.

Måtten räknas på servern ur punkterna och bladets egen skala (`backend/app/markups.py`) - aldrig i webbläsaren,
för ett mått klienten räknar fram går inte att härleda till någonting. Utan en färdig läsning finns ingen
skala, och då står det "ingen skala" i stället för påhittade meter. En ytas omkrets räknas aldrig in i
meterraden. En struken markering står kvar i lagret så att den går att få tillbaka.

---

## 6b. Kalkyl och anbud

Knappen **Kalkylera →** i analysens flikrad (och på ritningssidan efter en färdig analys) leder till kalkylens
egen sida, `/jobs/{id}/kalkyl`. Den gör mängden till pris, i två steg som hålls isär så att varje krona går att
spåra till en rad på ritningen (`backend/app/calc.py`):

*Material.* Varje beteckning matchas mot materialboken (55 000 artiklar med nettopris). Bladets egen
förklaringslista säger vad materialkoden betyder ("R8 = LEDNINGAR AV ROSTFRIA RÖR"), men boken använder andra
ord ("rostfritt rör", "rf AISI 304", "EN1.4432"), så förklaringen läses först till en *materialklass* (pex,
koppar, rostfri, pp, pe, pvc, gjut, galv, stål) och boken söks på klassens egna ord, som metervara, i rätt
dimension - DN för plaströr och rostfria avloppsrör, ytterdiametern för övriga metallrör. Bland träffarna går
ett riktigt pris före ett tomt, sedan den som bär flest av förklaringens egna ord (står det RIR vinner
rör-i-rör), sedan det billigaste. Matchningen är ett förslag med alternativ bredvid - den som räknar väljer, och
valet sparas. Där förklaringen inte säger vad röret är gjort av föreslås inget: alternativen i rätt dimension
finns att välja bland, men ett rör i fel material prissatt med säker min är värre än en tom ruta, så raden står
som förbehåll tills någon valt.

*Arbete.* Timmarna kommer ur Normtid VVS (`vvs_engine/normtid.py`): grundtid per meter efter ytterdiameter och
material, tillägg för skarvmetod och höjd, avvikelseanalysens bedömning av objektet. Stigare räknas som en
våningshöjd där ritningen inte anger höjden. Där boken inte har någon tid står det, och timmen skrivs för hand -
en gissad normtid är värre än ingen, för den ser ut som ett besked. Tabellerna är avlästa ur boken och ska
kontrolleras mot utgåvan innan ett anbud lämnas; det står i gränssnittet.

Sedan spill (kalkylmängd = netto + spill), påslag på material och arbete var för sig, och moms - allt utskrivet.
Det som sparas är valen och antagandena, aldrig resultatet: talen räknas om ur läsningen varje gång, med kundens
rättelser ovanpå, så kalkylen och bladet aldrig visar två olika meter.

**Anbudet** skrivs ur den sparade kalkylen som en formgiven PDF i A4, satt i Liberation Sans. Kroppen -
inledning, specifikation rad för rad, förutsättningar, avtalsvillkor, förbehåll, underskrift - flödas av PyMuPDF
Story; huvudet (mörkt block med anbudsnummer, datum, giltighet, beställare, referens), summeringskortet (exkl.
moms, moms, att betala) och foten med sidnummer ritas ovanpå med sid-API:et, eftersom Story ritar om ett blocks
bakgrund överst på varje följande sida. **Avtalsvillkoren** väljs i kalkylen: ABT 06, AB 04, ABS 18,
Hantverkarformuläret 17 eller inget; valet ger anbudet en villkorsrubrik med entreprenörens vanliga förbehåll under
det regelverket (ÄTA, garantitid, ansvar) - anbudets egna formuleringar, inte avtalstexten. Rader utan artikel
eller normtid står som förbehåll, liksom det onämnda röret och det som inte ingår (fittings, genomföringar,
isolering som egen post, rivning). **Förhandsgranskningen** i appen visar anbudets sidor som bilder ur samma PDF
som laddas ner (`/calc/anbud/sida-{n}.png`) - det dokument som skickas, inte en efterlikning av det.

---

## 6c. CAD-rummet (rita på bladet, markeringslista, status)

**CAD** är en egen flik i sidomenyn och ett eget rum (`/cad`, `frontend/src/pages/Cad.tsx`). Det är
varken läsning eller mängdning: här ritas *frågor* på bladet - ett moln runt något som inte stämmer, en
anteckning, ett kontrollmått - och sedan arbetas listan tills varje fråga har ett svar.

**Markeringslistan** (`frontend/src/components/MarkupsList.tsx`) är rummets arbetsbord: sortering på sida,
verktyg, ämne, lager, mått och status; filter på fritext, sida, lager, verktyg och status; status ändrad på en
rad eller på många på en gång; och radering. Urvalet följer med åt båda hållen - väljs en rad bläddrar bladet
dit och zoomar in på markeringen, pekas en markering ut på bladet hoppar listan dit.

En fråga hör till **handlingen och inte till bladet**: listan läser alla sidor (`?all_pages=true`) och säger
vilken sida raden hör hemma på. Statusflödet är **öppen → åtgärdad → godkänd**, med **avvisad** för den fråga
vars svar är att ingen åtgärd behövs; färgen syns både i listan och på bladet, och sammanställningen högst upp
räknar hur många som står i varje läge.

Att svara i listan (`PATCH`) rör aldrig geometrin, och därför räknas måttet inte om: ett svar är ord, inte en
ny mätning. Ska markeringen mätas om ritas den om på bladet. Ett svep över flera markeringar är helt eller
inte alls - träffar id-listan något som inte finns på handlingen avvisas hela anropet, så att den som markerade
tjugo rader aldrig behöver gissa vilka sjutton som gick igenom. Listan går att ta ut som CSV med ämne, status,
kommentar och källa, hela handlingen eller ett blad.

Måtten räknas av samma mätmotor som mängdningen använder (`engine/vvs_engine/takeoff/`). En granskning som
räknade själv skulle kunna komma till ett annat tal än mängden, och då vore den ingen granskning.

---

## 7. Akademin

Nio kurser, tjugotvå steg, femton kunskapsfrågor och tre fristående övningar med facit
(`frontend/src/learn.ts`, `components/Learn*.tsx`). Sidan har tre delar och visar en åt gången: **Kurser**, med
kurslistan som en gång till vänster - nummer, framstegsstapel, låsta märkta - och den valda kursens steg till
höger; **Öva**, de fristående övningarna; **Utmärkelser**. Kurserna tas i ordning - den man är på står öppen, de
framför är låsta tills den är gjord, men varje låst kurs går att öppna ändå. I väntan på en läsning visas samma
akademi i ett kompakt läge, som kort, utan navigering.

Framstegen ligger på kontot (`backend/app/academy.py`), inte i webbläsaren, så man fortsätter där man slutade
även från en annan dator. Poängen räknas på servern ur stegen själva - rätt på första försöket är värt mer än
rätt till slut - och utmärkelserna prövas mot tabellen. Ett resultat klienten får bestämma är ett önskemål.

---

## 8. Adminportalen

Allt som styr tjänsten står här, i tre delar som aldrig blandas ihop (`backend/app/admin.py`,
`frontend/src/pages/Admin.tsx`). Portalen är ett skal: sektionerna i en gång till vänster, sidan till höger, och
märken i gången på det som väntar på någon.

*Läsningen:* **överblick** med "att ta hand om" - misslyckade läsningar, en kö som växer, regler flera konton
flyttat åt samma håll, öppna utbetalningar - och kurvan per dygn, där staplarna är hur mycket som lästs och
linjen hur långt läsningen kom; att staplarna växer säger något om marknadsföringen, att linjen sjunker säger att
något gått sönder. Sedan **läsningar** (varje blad, hur långt det kom, hur lång tid det tog), **rättelser** med
sin situation, **inlärningen**, **reglerna** och **antagandena**.

*Företaget:* konton och planer, partners och ambassadörer med två procenttal (rabatten till kunden och
provisionen till partnern, satta var för sig), utbetalningar räknade i ören ur samma funktion som visar
provisionen - beloppet skrivs aldrig av från en skärm - kundvård, innehåll (CMS), A/B-prov med Wilson-intervall
så att ett prov utan tillräckligt underlag säger det, och heatmap.

*Systemet:* byggningen som kör, om andra läsaren nås, kön och trådarna, lagret, databasen och hur många regler
som flyttats. Bara fakta som går att kontrollera; byggningen och andra läsaren svarar dessutom utan inloggning
på `/api/version`.

Ingenting på företagssidan får avgöra hur en ritning läses. Den dagen en rabattsats kan flytta en meter går det
inte längre att svara på varför en mängd blev som den blev.

**Reglerna** (`rules.py`) är öppna: varje tröskel läsningen använder står med namn, förklaring, enhet,
standardvärde, tillåtet intervall och en levande figur som visar vad den handlar om. De bodde förr per konto, i
en egen inställningssida; nu bor de i portalen och gäller **tjänsten**. Alla som är inloggade får läsa katalogen -
en mängd som inte går att ifrågasätta är inget belägg - men bara administratören flyttar en regel, med skäl och
gärna en skärmbild av fallet, eftersom en flyttad regel gäller varje ritning som läses härnäst. Varje läsning
skriver ned vilka regler den kördes med (`ServiceSetting`, `backend/app/main.py`).

**Antagandena** är inte regler för hur ritningen läses utan för hur det lästa räknas ihop: våningshöjden en
stigare räknas som, om stigare räknas ur etiketter eller ritade symboler, och om rör i skrafferade ytor ingår i
den vågräta mängden. De sätts av administratören för tjänsten och är utgångsläget i varje ny läsning; den som
tittar på en enskild läsning kan avvika för just den, och exporten säger vad den räknat med.

## 9. Säkerhet

* Inloggning med JWT; lösenord hashade med bcrypt.
* **Nyckeln som undertecknar bevisen** har ett standardvärde i källkoden, och tjänsten **vägrar starta på en
  driftplattform** så länge det står kvar (`config.demand_a_real_secret`). Ett bevis undertecknat med en publik
  sträng är inget bevis.
* Broms mot gissning: efter tio fel på en adress inom en kvart svarar tjänsten 429, också på rätt lösenord.
  Räknat per adress och per avsändare. En okänd adress kostar lika lång tid som en känd med fel lösenord, så
  svarstiden inte avslöjar vilka konton som finns.
* Varje id-bärande väg prövar ägarskap; en annan användares projekt, ritning, jobb, markering eller
  projektanalys svarar 404.
* Uppladdningar läses bit för bit och stoppas vid 200 MB innan de ligger i minnet. En lösenordsskyddad, tom
  eller icke-PDF avvisas med en mening. En stackspårning når aldrig felrutan.
* Lagrets nycklar och webbappens filvägar prövas mot roten *med avskiljaren emellan* - ett prefix utan
  avskiljare släpper igenom grannen.
* Adminvägar kräver rollen `admin` (partners ser sina egna rader via `current_staff`). Rollen kommer från
  servern, aldrig från webbläsaren.

---

## 10. Drift

En container (`Dockerfile`, `railway.json`): webbappen byggs, motorn och API:t installeras, och API:t serverar
webbappen själv. Lokalt: `docker compose up` ger PostgreSQL, API och nginx. Se `README.md` och `.env.example`.

Miljö som betyder något: `VVS_SECRET_KEY` (krävs i drift), `VVS_DATABASE_URL` (SQLite som standard, PostgreSQL
i compose), `VVS_STORAGE_ROOT`, `VVS_WORKER_THREADS` (mängdningens kö), `VVS_ANALYSIS_DEADLINE_S` (tidsbudget per
blad), `OPENAI_API_KEY` och `VVS_SECOND_READER` (§3), `VVS_RUN_REVIEW`/`VVS_REVIEW_OCR`/`VVS_OCR_ASSIST`
(granskningen).

**Andraläsarna.** `OPENAI_API_KEY` ger Astra-läsaren, `ANTHROPIC_API_KEY` ger Claude-läsaren. Är båda satta
frågas båda om varje öppet fall, oberoende av varandra, och fallet avgörs **bara när de väljer samma kandidat**
ur ritningens egen lista; är de oense, eller svarar bara den ena, står fallet kvar tvetydigt. `VVS_SECOND_READERS`
väljer vilka som används (`auto`, `none`, `astra`, `claude`, `astra,claude`), och modellnamnen sätts med
`VVS_SECOND_READER_MODEL` respektive `VVS_CLAUDE_MODEL`. En nyckel läses ur miljön i anropsögonblicket och
skrivs aldrig ned, loggas aldrig och kommer aldrig tillbaka i ett resultat.

I Railway sätts de som miljövariabler på tjänsten; ingen av dem hör hemma i en fil i repot. Behöver bara en
läsare användas räcker det att sätta den ena nyckeln - panelen faller då tillbaka till den ensamma läsaren och
beter sig som förut.

SQLite körs i WAL-läge med väntetid, så att mätningens framsteg och API:ts läsningar samsas.

`/api/version` säger vilken byggning som kör, vilka andraläsare som är konfigurerade, om de går att nå och om
enighet krävs - utan inloggning, för en läsning är bara kontrollerbar om man kan säga vilken kod som gjorde den
och vem som fick vara med och avgöra det öppna.

---

## 11. Hur det valideras, och var det står

Ett facit-set på 33 ritningar från flera kontor, med mängdarens egna utsättningar som referens, ligger utanför
repot och nås aldrig av produktionskoden. En grind kör hela setet genom den riktiga tjänsten - registrera,
ladda upp, mängda, läs av API:t - och poängsätts efteråt av ett skript som aldrig kör motorn.

Två tal bär: **täckning** (andel av facits meter läsningen äger under rätt namn) och **falskhet** (meter under
fel namn, i andel av facit). Bara de system facit faktiskt täcker poängsätts.

Kurvan över de senaste rättelserna, en regel i taget:

| grind | regel | täckning | falskt |
|---|---|---|---|
| 45 | samlarlinjen bär ledaren till röret | 56,1 % | 12,5 % |
| 46 | bladets tabell namnger de onämnda kopplingsledningarna (§2b) | 76,5 % | 22,2 % |
| 47 | streck-prick-linjen är ett rör; en ventil avslutar det inte (§2c) | 79,5 % | 27,5 % |
| 48 | dubbellinjen viks ihop - för brett: DN16-buntar vek sig också | 72,7 % | 22,7 % |
| 49 | dubbellinjen följer diametern i skala; pricken bryggas på geometrin; tabellen namnger bara korta sträckor | 79,7 % | 26,8 % |
| 50 | skrafferade figurer (radiatorer) vägs inte som rör (§2c) | 80,0 % | 27,3 % |

Senaste grinden är alltså **80,0 % täckning, 27,3 % falskt**, 270 av 365 beteckningar rätt.

Det falska steg med täckningen, och det är den siffran som ska ner. Där den kommer ifrån, blad för blad:
en del är facit-policy som läsningen inte kan veta (kopplingsledningar och avloppsgrenar som facit inte räknat
på vissa blad men på andra; rör ritade utanför bladets egen del av byggnaden, bortom "DEL 21 | DEL 22"-linjen,
som facit inte tar med), en del är riktiga överanspråk: värmeledningar där DN15-etiketterna flödar in i en
DN22-stam som bara har en egen etikett vid stigaren, och rör ritade som par (tillopp och retur på samma penna)
där facit räknar paret en gång. Nästa steg är kända: ventilernas egna beteckningar (AV601-22, RV601-15) som
dimensionsgräns i linjen, och bladets delgräns som klippning.

Det som fattas i täckningen är till största delen det systemet vägrar gissa: rör som ingen hänvisningslinje når,
och blad exporterade utan lagernamn där väggar och rör ritas med samma penna. Där står metrarna som *onämnda*
med sina siffror, och en människa kan rita in dem med en rättelse som sedan lär ut det den kan.

Dessutom: närmare trehundra automatiska prov (motor, API, gränssnitt), ett rökprov som klickar igenom hela webbappen med
konsolen öppen, determinismprovet, kontamineringsskanningen, och en isolationsprövning som prövar varje
id-bärande väg med fel ägare.

---

## 12. Vad systemet inte gör

* Det läser inte skannade eller bildbaserade PDF:er. Det gissar aldrig ur bildpunkter.
* Det hittar inte på en anslutning där linjer bara korsas, en meter där ingen linje pekar, en vertikal längd
  utan höjd, en revision ur ett filnamn, eller ett före och ett efter ur två discipliner.
* Det låter ingen modell avgöra en meter, och ingen rättelse skapa en.
* Det mängdar inte fittings, genomföringar, isolering som egen post, status (nytt/befintligt/rivs) eller
  beställningsmängd i handelslängder. Det står i `LATHUND.md` vad som är gjort och vad som inte är det.
