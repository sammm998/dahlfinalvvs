# Flera discipliner: Sprinkler, Kyla, Ventilation – och senare El och Bygg

Steg 0 enligt uppdraget: nuläge, föreslagen arkitektur, migreringar, risker och fasplan. Ingen produktionskod är
skriven för det här än. Planen är godkänd i sin helhet; varje fas avslutas ändå med en sammanfattning och väntar
på underlag där det saknas.

**Det som gäller genom alla faser:** väljer man VVS fungerar allt exakt som idag. VVS-läsningen, VVS-mängden och
VVS-exporterna ändras inte, och golden-tester och korpusspärren visar det efter varje steg. Ventiler (`AVxxx`,
`SVxx` …) i en VVS-mängd lämnas som idag; räkning av komponenter (st) finns bara i de nya, separata disciplinerna.

## 1. Nuläge – var det ligger

| Del | Var |
|---|---|
| Läsningens kedja | `backend/app/jobs.py` → `analysis_worker.analyze_isolated` (egen process) → `engine/vvs_engine/pipeline.py` (`prepare_page`, `analyze_page`). Namnet "Meridian" finns inte i koden. |
| Inmatning | `pdf/classify.py` klassar sidan (vector/raster/mixed); `pdf/extract.py:161` avvisar rastersidor med `UnsupportedInputError`. |
| Text | `text/` (vektorglyfer, SHX, OCR-stöd); etikettdetektorn `models/pipestudio-labels.onnx` körs på rasterrutor. |
| Förklaringslista | `semantics/legend.py` – hittas på formen; koder får rollen system, komponent eller material av hur bladet använder dem. |
| Beteckningsparser | `semantics/grammar.py` hittar bladets egna mönster (inga värden hårdkodade, men dimensionen antas vara ett heltal – DN). Vendorad parser i `source_rules/pipestudio/vvs.py` (ändras aldrig). |
| Systemkatalog | `source_rules/data/system_designations.json` (26 koder: KV, VV, VVC, S, D, VS, VP … samt KB, KM, FK, BRL). |
| Hänvisningslinjer, koppling | `semantics/leaders.py`, `semantics/attachment.py`, `source_rules/native_*`. |
| Skala | `measure/scale.py` (text, skalstock, mått, rörbredd, schema). |
| Mätning | `measure/measure.py` – mängdrader i meter (`confirmed_horizontal_m`, vertikalt, stigare, DN, skrafferat, dubbellinje). |
| Artefaktversioner | `output/schema.py` (`ARTIFACT_SCHEMA`, `upgrade`). |
| Inställningar per läsning | `vvs_engine/rules.py`: `using()` binder värden till läsningens tråd (ContextVar). |
| Datamodell | `backend/app/db.py`; schemaändringar via `create_all` plus `_ADDED_COLUMNS` (ingen Alembic). `Project` har namn, beskrivning och `analysis_mode`. |
| Exporter | `main.py` (`/api/jobs/{id}/export/{fmt}`) och `exports.py`: xlsx, csv, json, rapport, markerad pdf, kontroll-pdf. |
| Kalkyl/anbud | `calc.py` och `vvs_engine/normtid.py` (Normtid VVS: timmar per meter efter dimension och material). |
| Material | Dahls produktkatalog (`backend/app/data/dahl_catalog.json.gz`) med priser ur Dahls uppladdade prislista; den gamla materialboken är borttagen. |
| Credits | `credits.py` – pris per blad efter format och bläck; återbetalning när läsningen inte gav en enda meter. |
| UI | `pages/Projects.tsx` (skapa projekt: namn, beskrivning), `Project.tsx`, `Analysis.tsx`, `components/QuantityTable.tsx`, `three/model.ts`, `pages/Takeoff.tsx` (manuell mängdning: m, m², m³, st). |

**Avvikelser mot hur produkten beskrivs:** Wikells-export finns inte i koden. "Bluebeam" förekommer bara som
ord i texter – det finns ingen markeringsexport med PDF-annoteringar. Materialboken är inte redigerbar per
företag; det som finns är artikelval per kalkyl.

## 2. Där VVS är hårdkodat

**Motorn**
- `source_rules/data/system_designations.json` – systemkoder med `line_count` (enkel/dubbel ledning).
- `source_rules/systems.py:29` och `source_rules/swedish.py:65` – självfall: system som börjar på S eller D (utom SL).
- `pipes/direction.py:36-43` – `GRAVITY_SYSTEMS`, `CIRCULATING_SYSTEMS`, `OWN_LABEL_SYSTEMS`.
- `semantics/attachment.py:118` – BSAB-lagren 52BB/52BC/52BD → KV/VV/VVC.
- `measure/measure.py:425-427` – stigare genom bjälklag gäller VS med S-material.
- `pipeline.py:2233` (`APPARATUS_HEADS`: AV, SV, RV …) och `pipeline.py:2274` (rörnamn ur standardsystem).
- `semantics/legend.py:507` – `COMPONENT_HEADS` (svenska ord för komponenter).
- Stigare och våningshöjden 2,8 m; DN som heltal i grammatik, mätning och 3D.
- Agentens och granskningens prompter ("Swedish HVAC/plumbing (VVS) drawing", `backend/app/solver.py:33`).
- Etikettmodellen är tränad på VVS-etiketter.

**Backend**
- `main.py` – skapa projekt utan disciplin; uppladdning tar bara `.pdf`.
- `exports.py:14` – kolumnerna (DN, Horisontellt m, Vertikalt m, Stigare …).
- `credits.py` – återbetalningen räknar meter.
- `calc.py`, `normtid.py` – timmar per meter efter DN.
- `cad_export.py:80` – färger efter KV/VV/S; akademin och `data/swedish-vvs-knowledge.json`.

**Frontend**
- `QuantityTable.tsx` (kolumner), `Analysis.tsx` (stigare, våningshöjd, DN), `three/model.ts:50` (rörradie ur DN),
  navigeringen "Lär dig VVS".

**Redan generiskt och återanvändbart:** skalverifieringen, förklaringslistan, grammatiken som hittar bladets egna
mönster, hänvisningslinjer och koppling, den manuella mängdningen (m, m², m³, st), disciplinbokstaven i
ritningsnumret (`vvs_engine/handling.py:41`: A, V/W, L = luftbehandling, E, B …), `rules.using()`,
artefaktversioneringen samt etikettdetektor och OCR på rasterrutor.

**Referensdata som redan finns** (svensk praxis, `reference_sources/swedish-vvs-drawings-main/data`):
`system_designations`, `sanitary_fixtures`, `valves`, `discipline_codes`.

## 3. Föreslagen arkitektur

1. **Disciplinregister** – nytt paket `engine/disciplines/` med en JSON-fil per disciplin: id, namn, status
   (aktiv/beta/planerad), slag (rör/kanal/symbol/yta), systemkoder, grammatik och dimensionsformat (DN, Ø, b×h),
   rubriker i förklaringslistan, komponenter, mättyper, katalogfilter, exportmappning och credit-faktor.
   Konfigurationen binds per läsning på samma sätt som `rules.using()`. **VVS-konfigurationen är exakt dagens
   konstanter:** de hårdkodade mängderna ovan läses via `value(...)` med identiska standardvärden, så en
   VVS-läsning ser samma tal som idag. Avvikelser per företag och projekt (`discipline_overrides`) gäller bara
   andra discipliner än VVS.
2. **Mättyper** – `LENGTH` (m), `AREA` (m²), `COUNT` (st) och förberedd `VOLUME` (m³). En rad i de nya
   disciplinerna:
   `{discipline, source_type, system, designation, dimension{format, value}, measures[{type, unit, value,
   derivation, state, confidence}], evidence{label, leader, geometry, scale}, state, reasons}`.
   En kanal bär till exempel meter, m² plåt (omkrets × längd) och m² isolering. VVS-artefakterna lämnas som de
   är; en vy-adapter ger dem `measures` där en gemensam lista behöver det.
3. **Kedjan** – `discipline in ('', 'vvs')` går dagens anropskedja oförändrad. Sprinkler och kyla återanvänder
   rörläsaren med sin konfiguration; ventilation får en kanalläsare som bygger vidare på dubbellinje- och
   rörbreddslogiken.
4. **UI** – disciplinval när projektet skapas (VVS förvalt; El och Bygg visas som "kommer senare"), åsidosättning
   per ritning vid uppladdning, filter per disciplin i mängdlistan och korrekta enheter överallt (m, m², st). Nya
   discipliner får en generisk mängdtabell; VVS-tabellen är orörd.
5. **Exporter** – VVS-filerna är byte-identiska med idag. Nya discipliner får ett generiskt blad: disciplin,
   källtyp, system, beteckning, dimension, mått, enhet, värde, härledning, status. Wikells och Bluebeam byggs när
   formaten är bestämda.
6. **Katalog** – materialboken filtreras per disciplin (artikelgrupp); redigering per företag kräver en egen
   tabell och föreslås separat.
7. **Credits (förslag, beslutas före implementation)** – samma pris per blad som idag (format och bläck) med en
   faktor per disciplin som administratören kan ändra (startvärde 1,0). Återbetalningen generaliseras till
   "läsningen gav ingen mängd av något slag" (m, m² eller st). Rastersidor kostar +1 credit.

### Skannade underlag och bilder (inmatning, oberoende av disciplin)

Idag avvisas rastersidor med flit. Förslaget är en inmatningsadapter som bara körs där dagens kod avvisar:

1. Bilder (PNG, JPG, TIFF) tas emot och läggs som en PDF-sida; sidstorleken tas ur DPI. Saknas DPI kan skalan
   bara komma ur skalstock, mått eller handinmatning.
2. Förbehandling: räta upp, avbrusa, binarisera.
3. Vektorisering: linjesegment med uppskattad linjebredd och streckmönster.
4. Text: etikettdetektorn på rasterrutor och OCR.
5. Primitiverna och textraderna matas in i samma läsning – grammatik, hänvisningslinjer, mätning och skala
   återanvänds.

**Förtroende:** allt som läses ur en bild markeras "granskas" med skäl och konfidens, och skalan måste vara
verifierad. Vektor-PDF:er påverkas inte. **Utvärdering:** de 15 facitbladen rastreras (150–300 dpi, med lutning,
brus och oskärpa) och mäts mot samma facit; riktiga skanningar behövs för slutlig validering.

## 4. Migreringar

- `projects.discipline`, `drawings.discipline`, `analysis_jobs.discipline` som `VARCHAR(24) DEFAULT ''` via
  `_ADDED_COLUMNS`. `''` betyder VVS, så varje befintligt projekt är oförändrat VVS.
- Ny tabell `discipline_overrides` via `create_all`.
- Inga dataomskrivningar; gamla artefakter läses som idag (`output/schema.py`).

## 5. Risker

- **Determinism:** detektorn går på två trådar; resultatet bekräftas lika vid två körningar innan golden-testerna
  låses.
- **Dold påverkan på VVS:** spärras av golden-tester (syntetiska, incheckade) och korpusspärren (verkliga blad,
  utanför repot).
- **Klientritningar i ett publikt repo:** bara syntetiska fixtures checkas in.
- **Kanaler:** kräver en ny detektor; precisionen är okänd tills det finns facit.
- **Exportförväntningar:** Wikells- och Bluebeam-export finns inte idag.
- **Koder:** beteckningar skiljer sig mellan beställare och konsulter; därför är de data per disciplin, företag
  och projekt – aldrig hårdkodade antaganden.

## 6. Fasplan

**Fas 1 – refaktorering utan beteendeändring** (gemensam med ABT 06, se `docs/abt06-plan.md`)
1. Golden-tester först: syntetiska fixtures med fullständiga `quantities.json`, `physical-pipes.json`,
   `reading-coverage.json`, xlsx-celler och csv-bytes i `engine/tests/golden/`; lokalt dessutom korpusens
   facitblad med artefakthashar.
2. Disciplinregistret med VVS; de hårdkodade konstanterna flyttas till VVS-konfigurationen med noll diff.
3. DB-kolumner och API (disciplin in och ut).
4. Disciplinval i UI; bara VVS kan väljas tills fas 2 och 3 är byggda.

Godkänt när golden-testerna och korpusspärren är identiska, hela sviten är grön och befintliga projekt öppnas
oförändrade.

**Skannat (C1–C3)** – C1: mottagning, förbehandling, vektorisering, OCR. C2: precision med egen gräns i
korpusspärren. C3: de andra disciplinerna.

**Fas 2 – Sprinkler och Kyla.** Systemkoder och katalog per disciplin, verifierade mot riktiga ritningar innan
något byggs. Rör mäts som i VVS. COUNT för sprinklerhuvuden, ventilstationer och kylaggregat där de kan
identifieras säkert – annars flaggas de. *Behöver:* sprinkler- och kylritningar, gärna med handmängd.

**Fas 3 – Ventilation.** Kanalbeteckningar med Ø och b×h, luftsystemen (tilluft, frånluft, uteluft, avluft) som
konfigurerbara koder, meter per system och dimension, m² plåt och m² isolering där isoleringsklass anges. COUNT
för don, spjäll, ljuddämpare och aggregat; böjar, T-stycken och reduktioner räknas om det går säkert ur
geometrin, annars flaggas de. 3D-tvärsnitt sist. *Behöver:* ventilationsritningar, gärna med handmängd.

**Senare – El och Bygg/A-K.** Symbolräkning och kabelstegar respektive areor och volymer behöver bara egna
läsare; registret och mättyperna är förberedda för dem.

Varje fas: små commits med tester, hela sviten, och en sammanfattning med vad som ändrats, testresultat, kända
begränsningar och vad nästa fas behöver.

## 7. Referenser (webbsökning – koderna verifieras ändå mot riktiga ritningar)

- Kyla – KP, KB och KM som systemkategorier: [Armatec, kunskapsguide vätskeburen kyla](https://armatec.com/sv/koncept/industriella-system/kunskap/kunskapsguide-vatskeburen-kyla/DownloadPdf); KBxxx i [Region Västerbottens beteckningssystem](https://regionvasterbotten.se/VLL\Filer\Beteckningssystem%20(bilaga).pdf); systembeteckningar i [Danderyds kommuns projekteringsanvisning](https://www.danderyd.se/contentassets/d4cf4c4f61dc47e4838d1202e3d916ad/styr-och-regler/danderyds-kommun-projekteringsanvisning--styr-och-overvakning_bilaga-2-beteckningssystem_v3.0.pdf).
- Sprinkler – [SBF 120](https://www.brandskyddsforeningen.se/webbshop/normer-och-regelverk/sbf-1208-rules-for-automatic-sprinkler-systems/) (gäller tillsammans med SS-EN 12845). Ingen svensk sprinklerritning hittades som exempel.
- Ventilation – T/F för tilluft/frånluft, TD/FD för don, TA/FA för aggregat, TF/FF för fläktar enligt ett svenskt [symbolblad](https://www.yumpu.com/sv/document/view/63511785/flik-26-ritningssymboler); märkbeteckningar i [Jönköpings kommuns anvisning](https://www.jonkoping.se/download/18.18363ea31862b16dbb8212f8/1676357560481/Bilaga%201.2%20M%C3%A4rkbeteckningar.pdf); termer i [EN 12792](https://genorma.com/en/standards/en-12792-2003/amp).
- Allmänt – [AMA VVS & Kyla 25](https://byggtjanstcms.byggtjanst.se/globalassets/bokhandeln/provlas/ama-vvs-kyla-25_6361461.pdf).

## 8. Fas 1 – genomförd: så hålls VVS stilla

- **Golden-test i CI** (`engine/tests/test_golden_readings.py`): de syntetiska bladen läses som i produktionen,
  och längder, system, dimensioner, stigare och flaggor jämförs rad för rad med `engine/tests/golden/*.json`.
  En avsiktlig ändring av läsningen skriver om filerna med `VVS_GOLDEN_UPDATE=1`, och diffen är ändringen.
- **Strikt jämförelse lokalt** (`engine/tools/golden.py`): varje JSON-artefakt på korpusens blad, läst före och
  efter en ändring, med tider, sökvägar och versionsstämplar borttagna. Klientritningarna och jämförelserna ligger
  utanför repot.

      python engine/tools/golden.py run manifest.json before   # före ändringen
      python engine/tools/golden.py run manifest.json after    # efter
      python engine/tools/golden.py digest before before.json; python engine/tools/golden.py digest after after.json
      python engine/tools/golden.py compare before.json after.json

- **Determinism:** två identiska läsningar skiljer sig bara i ordningen mellan två lika nära kontaktpunkter, och i en
  diagnosdetalj bortom en rörfront. Det beror på Pythons slumpade hash-ordning och påverkar aldrig mängden. Verktyget
  läser därför med fast `PYTHONHASHSEED`.
- **Resultat för refaktoreringen:** 19 riktiga blad och 1102 artefakter, och läsningen är identisk före och efter.

## 9. Spår C1 – genomförd: skannade blad och bilder läses ur bildpunkterna

**Vad som händer.** En handling där ingen sida har vektorgeometri avvisas inte längre. Varje skannad sida eller
bildsida läses ur sina bildpunkter (`engine/vvs_engine/raster`) och lämnas sedan till samma läsning som ett
vektorblad: grammatik, hänvisningslinjer, koppling och mätning. Stegen per sida:

1. Bladet ritas upp med skanningens egen upplösning, inom 150–300 dpi och högst 40 miljoner bildpunkter. Ojämn
   belysning jämnas ut, och bläcket skiljs från papperet med Otsus tröskel. Damm försvinner.
2. OCR (tesseract, svenska och engelska, en tråd) läser bara det bläck som är stort som bokstäver. Linjer, väggar
   och symboler tas bort först, så att linjer inte läses som bokstäver. Tesseract körs i tre omgångar: glest
   utspridd text, fristående tal (siffrorna under en skalstock och måttal) och text som är skriven uppåt. Ord som
   har lästs lyfts ur linjebilden.
3. Linjerna tunnas till en pixel och följs från knut till knut. Två armar som fortsätter rakt genom en korsning blir
   samma linje, och övriga armar slutar på den linjen, så att en ledare landar mitt på röret. En linje delas där
   strecket byter bredd, eftersom en ledare ritad mot ett rörs ände annars blir ett enda bläckdrag med röret. Varje
   rak sträcka läggs på linjen genom alla sina pixlar, med skarpa hörn, så att skannerbrus inte blir små knyckar.
4. Bredden mäts tvärs över strecket och knyts till pennor, och färgen tas ur strecket kärna i breda gråsteg. Ytor
   som är för breda för att vara streck blir fyllda ytor.
5. Bilder (PNG, JPG, TIFF) blir en PDF med bildens egna bildpunkter, i den storlek filen anger. En fil som inte
   anger upplösning läggs ut vid 200 dpi.

**Förtroende, enligt beslut:**
- Varje rör från en bildsida är flaggat `read_from_image` och har nivån granska.
- Varje rad står som `READ_FROM_IMAGE` (LÄST UR BILD), och omdömet säger `READ_FROM_IMAGE`.
- Skalan gäller bara om den är mätt på bladet: `VERIFIED`, `BAR_ONLY`, `DIMENSIONS_ONLY` eller `CONFLICT` med den
  uppmätta, eller om den anges för hand. En skaltext ensam räcker inte, eftersom en skanner kan ha krympt bladet
  och 1:50 då inte längre stämmer på papperet. Det gäller också papperformat, rörbredder och omgångens skala.

**Oförändrat för vektor-PDF:**
- En handling med en enda vektorsida läses precis som förut, och dess skannade sidor hoppas över som förut.
- Golden-testerna och den strikta jämförelsen på de 19 riktiga bladen är identiska.

**Credits:** en sida som läses ur bildpunkter kostar `raster_page` (1 credit) utöver bladpriset. Admin kan ändra det.

**Utvärdering.** De 15 facitbladen rastrerades vid 200 dpi i färg, utan påskrift. Sedan lästes de som
produktionen läser och jämfördes med facit i bladets egna koordinater:

| Facitmeter, viktat över bladen | rätt | fel DN | fel system | missad |
|---|---|---|---|---|
| Vektor (`corpus_baseline.json`) | 91,5 % | | | |
| Bild vid 200 dpi, C1 (`corpus_baseline_raster.json`) | 10,7 % | 10,5 % | 13,3 % | 65,5 % |

Per blad ligger bildläsningen mellan 0 och 54 % rätt. Den hittar rörens geometri och bladets beteckningar:
- På A0011 läser OCR 163 beteckningar, varav 109 med DN.
- Rörpennorna återfinns med ungefär rätt längd.

Det som brister är vilka pennor som tas som rör, och kopplingen från etiketterna. Stigare räknas inte alls än.
Bilden är alltså en första läsning att granska, och precisionen är arbetet i C2, mätt mot sin egen baslinje.

Skalan stod på inget av facitbladen på en skalstock, bara som text. Ingen av de rastrerade versionerna fick därför
någon skala förrän den angavs, vilket är precis vad beslutet om verifierad skala innebär. Facitjämförelsen görs i
bladets egna koordinater och påverkas inte av det.

Syntetiskt blad (två rör, skalstock): läst ur bild blir den totala längden 12,25 m vid 200 dpi och 12,07 m vid
150 dpi. Bladet lutat 1,5° ger 12,10 m. Vektorläsningen ger 12,30 m. Med brus och JPEG-artefakter hittas båda
rören, men den högra delen av T-knuten får ingen ägare.

**Kända begränsningar (C2):**
- Utan CAD-lagrens namn väljer läsningen rörpennor bara efter bredd, färg och etiketternas landningar. Tunna svarta
  streckade linjer i arkitekturen tas därför ibland som rör, och en del etiketter hamnar på fel penna.
- Ledare som slutar vid en symbol (stigarringar) kopplas sämre än i vektor. Stigare ur bild räknas inte än.
- Ritningsnumret i namnrutan kan läsas som en beteckning. Åtgärdat i C2, se avsnitt 10.
- Riktiga skanningar saknas. Lutning, brus och låg upplösning är bara provade syntetiskt.
- Upp och nedvända blad, och text skriven uppifrån och ned, läses inte.
- Fotografier med perspektiv rätas inte upp.

## 10. Spår C2 – första steget: fler rätta meter och färre falska

C2 mäter bildläsningen åt två håll. Det första är facits meter: hur många som läses rätt, med fel DN eller system,
eller inte alls. Det andra är läsningens egna meter: hur många som ligger där facit inte har något rör.
Korpusverktyget räknade tidigare bara det första. En ändring kunde därför se bättre ut samtidigt som den mätte
tusentals meter som inte finns. Därför visar verktyget nu också **utanför facit**, per blad och som andel av facits
meter. Siffran sparas med baslinjen.

Utanför facit är inte alltid fel. En mängdning tar inte alltid med allt som är ritat: vektorläsningen har 16,4 %
utanför facit, och på A0014 77,5 %. Därför jämförs varje blad bara med sig självt, och spärren nekar inte på
siffran än. Ingen vet ännu hur mycket den varierar mellan två körningar.

**Två ändringar, båda bara för sidor lästa ur bild:**

1. **En sida läst ur bild läses en gång.**
   - Vektorbladet läses en andra gång med de pennor undantagna som den första läsningens hänvisningslinjer var
     ritade med. Tanken är att vissa pennor skriver och andra ritar.
   - En skanning kan inte pröva den tanken. Där är en penna en bredd mätt i bildpunkter, och vid 200 dpi är en
     bildpunkt 0,36 pt. Hänvisningslinjernas penna kommer ut som två eller tre bredder, och husets tunna linjer
     delar dem.
   - Den andra läsningen sökte då hänvisningslinjer bara i en av bredderna. Etiketterna vars linjer mättes i de
     andra blev utan rör, och rören de pekade på mättes inte alls.
2. **Ett ritningsnummer på en sida läst ur bild namnger inget rör.**
   - Namnrutans linjer kommer ur bildpunkterna som linjer som löper vidare under numret. Bladets eget nummer, med
     ett tal där en dimension brukar stå, lästes därför som ett rör längs hela namnrutan: 5 400–5 800 pt på fem
     av bladen och 90–1 100 pt på två till.
   - Formen känns igen så som handlingsläsningen redan läser ritningsnummer (`handling.py`): en ensam
     disciplinbokstav, en tvåsiffrig grupp och minst ett led till.
   - Inget av facits 64 rörnamn har den formen. Av de 683 beteckningstexter som läsningarna av bladen hittat har
     bara ritningsnummer den: bladens egna och en hänvisning till en arkitektritning.
   - I vektorläsningarna av bladen har numret aldrig nått en linje, och den läsningen är orörd.

**Resultat.** De 15 facitbladen är rastrerade vid 200 dpi som i C1. Alla siffror är procent av bladets facitmeter.

| Blad | rätt C1 | rätt C2 | utanför facit C1 | utanför facit C2 |
|---|---|---|---|---|
| A0011 | 22,0 | 22,0 | 55,7 | 7,6 |
| A0013 | 54,0 | 54,0 | 7,5 | 7,5 |
| A0014 | 11,3 | 27,3 | 2,0 | 7,5 |
| A0111 | 7,4 | 7,4 | 15,7 | 15,7 |
| A0114 | 6,6 | 6,6 | 7,3 | 6,8 |
| A0213 | 3,6 | 21,2 | 1,9 | 6,2 |
| A0222 | 9,1 | 15,2 | 8,6 | 10,6 |
| A0223 | 10,7 | 10,4 | 1,2 | 2,1 |
| A0233 | 1,2 | 2,7 | 1,2 | 3,5 |
| A0311 | 31,9 | 31,9 | 14,9 | 14,9 |
| A0314 | 0,0 | 0,0 | 0,0 | 0,0 |
| W0023 | 0,0 | 0,0 | 0,0 | 0,0 |
| W0024 | 31,5 | 35,8 | 0,2 | 0,2 |
| W0122 | 4,3 | 11,3 | 4,3 | 9,1 |
| W0123 | 5,4 | 5,4 | 40,2 | 7,5 |

Viktat över bladen:

| Facitmeter | rätt | fel DN | fel system | missad | utanför facit |
|---|---|---|---|---|---|
| C1 | 10,7 % | 10,5 % | 13,3 % | 65,5 % | 14,2 % |
| C2 | 13,7 % | 12,4 % | 16,3 % | 57,6 % | 8,7 % |

Av det läsningen själv mäter ligger nu 27,2 % på en facitlinje med samma namn (22,4 % i C1), 55,5 % på en
facitlinje med ett annat namn (47,9 %) och 17,3 % där facit inte har något rör (29,7 %).

**Vägt mot varandra:**
- Vinsten i rätta meter kommer helt från att den andra läsningen inte görs: A0213 +17,7, A0014 +16,0, W0122
  +7,0 och A0222 +6,2 procentenheter.
- Utan regeln om ritningsnummer kostade det mer än det gav. Läsningen mätte då 38,6 % av sina meter utanför
  facit, och därför skickas ändringarna tillsammans.
- Regeln om ritningsnummer kostar inga rätta meter på något blad.
- A0223 tappar 0,3 procentenheter rätt och får 0,9 mer utanför facit. A0233 får 1,6 mer rätt och 2,3 mer utanför
  facit. Det är vanliga fel, inte en ny felklass: en ledning som läses en bit förbi facit, och en avkortad
  etikett (`S2-P5-1`) på tunna grå linjer.

**Oförändrat:** vektorläsningen. Båda ändringarna gäller bara sidor med `read_as == "raster"`, och golden-testerna
är identiska. Vektorkorpusen läser alla 15 blad precis som main gör.

Baslinjen för A0111 var äldre än main: där stod 79,98 % rätt, medan main läser 80,24 %. Det kommer av en tidigare
ändring. Baslinjen är nu uppdaterad, och varje blad har fått sin andel utanför facit.

**Kända begränsningar (kvar till nästa steg i C2):**
- Mer än hälften av läsningens meter ligger på ett rör som facit kallar något annat, med fel DN eller fel
  system. Fler etiketter når nu sina rör, men en del når grannens.
- OCR tappar en del av CAD-typsnittens ord under konfidensgränsen 60. Bladens förklaringslistor och texter som
  `CL 3196` blir skenbeteckningar.
- Tunna linjer tas fortfarande som rör på några blad (A0111 och A0311 har 15 % utanför facit).
- Stigare räknas inte ur bild.
- Riktiga skanningar saknas fortfarande. Allt här är mätt på rastrerade vektorblad.

## 11. Disciplinen "Alla" – Fas 1 genomförd: varje beteckning på bladet

"Alla" väljs när projektet skapas, som VVS. Rören läses och mäts av VVS-läsningen, oförändrad. Bredvid mängden
skrivs ett register över varje beteckning bladet skriver, oavsett disciplin, med slag, platser och mängd:
ledningar i meter, komponenter och klasser i styck och rum i m². Reglerna står i `docs/SYSTEMET.md` (5b).

**Så hålls VVS stilla.** Registret räknas fram efter läsningen och bara i läget "Alla". Det ändrar ingen rad i
mängden. En VVS-läsning skriver ingen ny fil, och dess exporter har inget nytt blad.

**Resultat på de 15 facitbladen, lästa i läget "Alla".** På varje blad är `quantities.json` och
`physical-pipes.json` byte för byte VVS-läsningens på main, och registrets meter är mängdens. Enda skillnaden är
avrundningen av A0233:s 237,005 m: 237,01 i registret och 237,00 i mängdtabellen.

| Blad | beteckningar | ledning | komponent | okänd | granskas |
|---|---|---|---|---|---|
| A0011 | 20 | 9 | 4 | 7 | 10 |
| A0013 | 24 | 11 | 6 | 7 | 13 |
| A0014 | 10 | 3 | 1 | 6 | 7 |
| A0111 | 114 | 51 | 36 | 27 | 79 |
| A0114 | 87 | 37 | 26 | 24 | 65 |
| A0213 | 49 | 14 | 17 | 18 | 37 |
| A0222 | 45 | 16 | 12 | 17 | 35 |
| A0223 | 44 | 16 | 11 | 17 | 34 |
| A0233 | 55 | 20 | 15 | 20 | 39 |
| A0311 | 42 | 18 | 5 | 19 | 29 |
| A0314 | 38 | 6 | 6 | 26 | 33 |
| W0023 | 10 | 3 | 1 | 6 | 7 |
| W0024 | 11 | 3 | 0 | 8 | 9 |
| W0122 | 67 | 26 | 18 | 23 | 51 |
| W0123 | 47 | 22 | 9 | 16 | 38 |
| **Summa** | **663** | **255** | **167** | **241** | **486** |

**Vad "okänd" är på de här bladen.** Bladen skriver sin text med streck, och 241 av 663 beteckningar är okända:
- stomlinjernas beteckningar (`A200` i en cirkel)
- radiatorer (`RAD101-11-400X1000`): varken bladens listor eller referensdatan har en kod för radiator, bara en
  symbol
- arkitektens hänvisningar (`AA1:112`)
- ord och tecken som streckläsningen läst fel

Alla står som granskas. Ingen av dem får meter.

**På en planritning med textlager** finns varje kodlik ord i textlagret i registret, med samma antal förekomster.
Två står där med dimensionen på raden under (`KV1-X32` som `KV1-X32-16`). Ett ord i textlagret ligger utanför
ritningens vyfönster och syns inte på bladet, och det räknas inte.

**Kvar till Fas 2:**
- Andra discipliners ledningar mäts i meter. Formfamiljer utan DN och koder som förklaringslistan inte nämner läses
  i en andra, vidgad läsning, och det den mäter på geometri som rörläsningen inte äger blir egna rader som granskas.
- Stomlinjernas beteckningar känns igen som stomlinjer.
- Symboler utan text räknas inte.

## 12. Disciplinen "Alla" – Fas 2 genomförd: andra discipliners ledningar i meter

Bladet läses en gång till, vidgad (`widened_runs` i `pipeline.py`), på samma förberedda sida. Värdena under `wide`
i `disciplines/data/alla.json` gäller bara i den läsningen. Den första läsningen är VVS-läsningen, oförändrad.
Reglerna står i `docs/SYSTEMET.md` (5b).

**Vad den vidgade läsningen gör annorlunda:**
- En etikett som bladets lista inte nämner namnger en ledning där den är skriven som en: med ett kanalmått (`Ø250`,
  `400x200`) eller med en systemkod ur den svenska tabellen (BRL, KB, G …).
- Ett kanalmått är en storlek, som en DN är det. En ledning ritad som sina två kanter mäts en gång, och ledningens
  eget mått avgör hur långt isär kanterna får ligga. Rörens tak gäller inte där.
- Bara en etikett som bär en storlek eller ett system namnger en ledning, och bara en sådan etikett ger en ledning
  dess namn. Taggar (`UT1`, `TD01`), det bladets lista förklarar som en sak (`TD101-Ø100`) och koder med löpnummer
  och storlek (`AVT101-32`) räknas i styck.

**Vad som behålls:** det som mäts på linjer VVS-läsningen inte tog, under namn som mängden inte har. Det blir rader
i registret, aldrig i mängden, och varje rad ska granskas. Fliken tänder ledningens linjer och zoomar dit, och den
markerade PDF:en ritar dem streckade.

**Syntetiska blad** (`engine/tests/test_alla_measures_other_disciplines_runs.py`):

| Blad | Mätt i den vidgade läsningen, granskas | Räknat i styck |
|---|---|---|
| Ventilation, två kanaler ritade som sina två kanter | `TL01-Ø250` 6,00 m, `FL01-400x200` 4,00 m | `TD01` 1 |
| El, två kabelstegar och 24 uttag | `KS1-300x60` 7,00 m, `KS2-200x60` 5,00 m | `UT1` 24 |
| Sprinklerrör bredvid en VVS-lista | `BRL1-32` 5,00 m | `SAV101-32` 1 |
| Don som listan förklarar, ritade med kanalernas penna | – | `TD101-Ø100` … 3 |
| Kanaler ritade som slutna konturer | `TL01-Ø250` 6,50 m, `FL01-400x200` 4,80 m | – |

På bladet med don och lista mäter VVS-läsningen själv kanalerna, eftersom listan kallar TL och FL system
(tilluft, frånluft). Där har den vidgade läsningen inget att lägga till.

Varje regel är prövad genom att tas bort en i taget, 22 sådana mutationer. Proven fångar alla.

**De 15 facitbladen, planritningen och sektionsbladet, lästa i läget "Alla" som i produktionen:**
- `quantities.json`, `physical-pipes.json` och `vector-designations.json` är byte för byte VVS-läsningens på 16 av
  17 blad. På planritningen skiljer sig `physical-pipes.json` bara i fältet `frontiers[].detail.beyond_state` på
  fem rör. Fältet växlar mellan körningar också i VVS-läget och i Fas 1:s körningar, så det är en äldre ojämnhet
  och inte den vidgade läsningen. Mängden är densamma.
- Den vidgade läsningen lägger till en ledning: 0,19 m `S3-P5-160` på A0311, där VVS-läsningen inte gav namnet
  några meter. Facit har 0,30 m `S3-P5-160` på samma linje, och den vidgade läsningen mätte en del av den. Raden
  står i registret som granskas, inte i mängden.
- Bladen har inga andra discipliners ledningar, och den vidgade läsningen hittade inga.
- Tid: två av bladen, lästa ett i taget, tog 298 s i VVS och 327 s i "Alla".

**Gränser:**
- Andra discipliners meter är prövade på syntetiska blad: ventilationskanaler, kabelstegar med uttag och ett
  sprinklerrör bredvid en VVS-lista. Riktiga el-, ventilations- och sprinklerblad med en mängdning saknas.
- En kanal ritad som en sluten kontur får sina ändar med i längden, alltså kanalens bredd en gång per ände.
- I läget "Alla" läses bladet två gånger. Den andra läsningen återanvänder den förberedda sidan, så analysen tar
  bara något längre tid än i VVS.

**Kvar:**
- Stomlinjernas beteckningar känns igen som stomlinjer. Nu står de som okända.
- Symboler utan text räknas inte.
- Riktiga el-, ventilations- och sprinklerblad med mängdning, så att Fas 2 får ett eget facit och en egen spärr.
