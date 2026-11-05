# Dahls produktkatalog 2026 som artikelfil

Resultat: `backend/app/data/dahl_catalog.json.gz` (27 067 artiklar), skapad av `tools/import_dahl_catalog.py`.

## 1. Varifrån texten kommer: sidtexterna, inte PDF:en

- Bläddringsvy: https://katalog.dahl.se/dahl-sverige-ab/dahl-produktkatalog-2026pdf/ (iPaper, paperId 3032465).
- PDF:en: `https://katalog.dahl.se/dahl-sverige-ab/dahl-produktkatalog-2026pdf/GetPDF.ashx` svarar 302 och
  omdirigerar till `https://cdn.ipaper.io/iPaper/Papers/37f47050-0b95-4655-81db-321b4069e6b9/Download.pdf?...`
  (filnamn `Dahl-Produktkatalog-2026pdf.pdf`).
- **Blockerad värd: `cdn.ipaper.io`.** Miljöns proxy svarar 403 på CONNECT. Samma gäller `files.cdn.ipaper.io`,
  `viewer.ipaper.io` och `embeds.ipaper.io`. PDF:en kunde alltså inte hämtas, och inte heller sidbilderna.
- I stället används vyns egna sidtexter. Vyns HTML (3,9 MB, hämtad från katalog.dahl.se) innehåller
  `window.staticSettings.pageTexts`: en textsträng per sida.
- Sidantal: vyn har **1248 sidor**, och `pageTexts` har 1247 texter. Sidnummer i filen = textens index + 1.
  Det bör stämma med PDF:ens sidnummer, men det har inte gått att kontrollera mot PDF:en.
- Därför gick det inte att använda ordpositioner (pymupdf `get_text("words"/"dict")`). Tabellerna tolkas ur den
  platta texten. Skriptet har ett läge `--pdf katalog.pdf` som läser sidtexten med pymupdf och kör samma
  tolkning. Det läget är **inte testat**, eftersom PDF:en inte gick att hämta.

Så här tillåts värden i miljön: lägg till `cdn.ipaper.io` under Allowed domains i miljöns nätverksinställningar.
Kör sedan om skriptet med `--pdf`, så blir resultatet bättre (se avsnitt 5).

## 2. Hur en artikel står i katalogen

Katalogen har 26 flikar, med en flik:sida-numrering i sidfoten (t.ex. `3:5`). Det finns tre typer av sidor:

1. **Artikelnummerregistret** (vyns sidor 11–102). Varje artikel har tre kolumner: `Art.nr`, `Kalkylgrupp`
   (t.ex. `CB2010`) och `Flik/sida` (t.ex. `19:4`). Det här är källan till vilka artiklar som finns.
2. **Flikarnas innehållsförteckningar**, med produktgrupp och flik:sida (`Badkar akryl Alterna .18:5`).
3. **Produktsidor.** Där står en rubrik, en beskrivning och en tabell, antingen kolumnvis
   (`Art.nr A1 A2 … Dim D1 D2 …`) eller radvis (`Art.nr Dim A1 D1 A2 D2 …`). Ibland finns fler kolumner
   (`Längd m`, `Mått mm`, `Passar` …). Sidfoten säger "Grundenheten är styck, om inget annat anges". Undantag
   står i texten, t.ex. "Enhet: Meter".

Katalogen anger inga priser ("Dagspris gäller"), så `p` är alltid `null`. Katalogen har ingen egen RSK-kolumn,
utan kallar numret "Art.nr". De 7-siffriga numren är RSK-nummer. Texten hänvisar till dem som RSK, t.ex.
"RSK 3131139" för vakuumventilsatsen med art.nr 3131139, och dahl.se använder samma nummer. Därför gäller
`rsk = art.nr` när numret har 7 siffror. Kortare nummer (2 815 st, t.ex. `870126`) och nummer med prefix K
(63 st) är Dahls egna. För dem är `rsk` tom.

### Tre exempel

| Som det står (vyns sidtext) | Som det tolkades |
|---|---|
| s. 225: `Klämringskopplingar Altech Ventilfäste Klämring x invändig gänga. Förkromad. Art.nr 1965604 1965605 1965606 1965607 Dim 10xG15 12xG10 12xG15 15xG15` | `a=1965604`, `n="Rak koppling Vinkelkoppling Klämringskopplingar Altech Ventilfäste Klämring x invändig gänga 10xG15"`, `e=st`, `gr="Kopparrör och Koppardelar – Klämringskopplingar Altech"`, `page=225` |
| s. 225: `Vinkelkoppling 2 x klämring. Förkromad. Art.nr Dim 1966438 10 1966439 12 …` (radvis) | `a=1966438`, `n="Vinkelkoppling 2 x klämring 10"`, `e=st`, samma `gr`, `page=225` |
| s. 223: `… Längd: 2,5 m. Enhet: Meter. Dagspris gäller. Art.nr 4816000 4816001 … Dim mm 10 12 15 … Gods tjlek. mm …` | `a=4816000`, `n="Kopparrör hårda raka … 10 mm, Gods tjlek. mm 0,8, Max tryck bar 99"`, `e=m`, `page=223` |

Det första exemplet visar en typisk svaghet. Rubrikerna för flera produkter på sidan står samlade i texten
("Rak koppling Vinkelkoppling …"), så benämningen tar med mer än den egna rubriken.

## 3. Tolkningen

1. Registret läses sida för sida. På 90 av 92 registersidor har de tre kolumnerna lika många värden, och
   art.nr står i stigande ordning. Där paras de ihop i ordning. På registersida 85 saknas en flik:sida.
   Där behålls flik:sida bara för de rader där parning framifrån och bakifrån ger samma svar. På registersida
   102 saknas 35 art.nr i texten. Där tas de 255 synliga art.nr med utan registrets flik:sida.
2. flik:sida översätts till vyns sidnummer via sidfötterna (672 sidor har en läsbar sidfot, och inga av dem
   motsäger varandra). Kontroll: för 24 564 av 26 954 registerrader (91 %) står art.nr i klartext på den
   sida som kopplingen pekar ut. Saknas flik:sida letas art.nr upp på produktsidorna. Om det står på exakt en
   sida används den.
3. På sidan letas tabellen med art.nr upp. Benämningen (`n`) blir första meningen i texten före tabellen
   (högst tio ord), plus dimensionen/kolumnvärdena. Om art.nr inte står i klartext på sidan blir `n`
   produktgruppens rubrik ur innehållsförteckningen. Det gäller 5 668 rader.
4. `gr` = flikens namn + produktgrupp ur flikens innehållsförteckning (rubriken som pekar på sidan), t.ex.
   `Kopparrör och Koppardelar – Klämringskopplingar Altech`.
5. Delar av texten har ett typsnitt med förskjuten teckenkodning (`EO\IULDY]LQNQLQJ` = "blyfriavzinkning").
   Sådana ord avkodas: tecken 33–93 får +29 och tecken 94–193 får +62. Ligaturerna ȴ/ȵ/΍ blir fi/fl/ff.
   **I de partierna har mellanslag och siffror fallit bort i sidtexten** och kan inte återställas. Därför syns
   ihopskrivna ord ("Konsolmontageellervägghake") och mått utan siffror (`[*[*` för t.ex. "16xG½xG½").
6. Dubbletter: 441 art.nr står två gånger i registret, på olika sidor. Raden med första förekomsten behålls.
7. Kalkylgrupp och flik:sida finns inte bland nycklarna. De går att få ur registret med skriptet.

## 4. Kontroll

| | |
|---|---|
| Artiklar (rader) | **27 067** |
| med RSK (7 siffror) | **24 189** |
| Dahl-egna nummer | 2 878 |
| Kapitel (flikar) | **26**, med 663 olika kapitel+produktgrupp |
| benämning ur produktsidans tabell | 21 399, varav 14 338 med dimension/kolumnvärde |
| utan sida (bara i registret) | 128 |
| Enhet | st 26 616, m 422, par 29 |
| `material.json.gz` | 55 161 rader. **9 021** av katalogens artikelnummer (`a`) finns även där |

Kapitlen: 1 Tryckrör Avloppsystem, 2 Stålrör och Ståldelar, 3 Kopparrör och Koppardelar, 4 Slangar,
5 PVCrör och PPrör, 6 Övriga plaströr, 7 Fästdetaljer Isolering, 8 Armaturer, Stängventiler, 9 Regler och
Backventiler Filter, 10 Mätinstrument, 11 Betäckningar och Brunnar, 12 Automatik, 13 Kärl och Cisterner,
14 Pumpar, 15 Pannor, Oljebrännare och Tillbehör, 16 Radiatorer, 17 Vattenvärmare, Värmepumpar, 18 Badkar
Duschkabiner och Duschväggar, 19 Tvättställ Dricksfontäner, 20 WCstolar Bidéer Urinaler, 21 Disk och
Tvättbänkar Minikök, 22 Vattenlås Fixturer, 23 Blandare, 24 Sanitetsarmatur Duschtillbehör,
25 Badrumsinredningar, 26 Verktyg Förnödenheter och Städ. Namnen står som de avkodas; skiljetecknen saknas i
sidtexten.

### Uppslag

| Sökt | Resultat |
|---|---|
| RSK 7606418 | s. 838, `Tvättställ Dricksfontäner – Tvättställ IFÖ`. På sidan står det "Sjukhustvättställ Spira 15162 Konsolmontage … Art.nr 7606418". Benämningen i filen blev rörig: "Tvättställ IFÖ … Cera 2322 … Spira 15017 …" |
| RSK 7811054 | s. 849, `WCstolar Bidéer Urinaler – WC-stolar IFÖ`, "… WC-stol Spira 6260, Rimfree, S-lås Ifö Spira … Spolning l 2/4" |
| RSK 8036222 | s. 889, "Utslagsbackar Intra Bottenventil för utslagsback", `Disk och Tvättbänkar Minikök` |
| RSK 8560167 | **finns inte** i katalogen, varken i registret eller på någon sida |
| RSK 8188682 | s. 1022, "För utanpåliggande rördragning Ansl M26x1,5xG15, Blandarfäste 40-160", `Sanitetsarmatur Duschtillbehör – Nipplar, anslutn-kpl, Ezze`. Sidan hittades via produktsidan, eftersom registret saknar flik:sida för numret |
| RSK 4316698 | s. 988, "Spindelförlängare Nyckel till vattenutkastare … Väggtj max mm 600", `… Vattenutkastare Alterna / FMM` |
| "Furo 142", "Furo 152" | 0 träffar. Ordet "Furo" finns inte någonstans i sidtexten, inte heller avkodat |
| "AT 3700", "AT 4003" | 0 träffar, finns inte i sidtexten |
| "Ballofix" | 98 i benämning och 59 till i produktgrupp, t.ex. 1934316 "Förminskningsset Ballofix … 10x8" (s. 241). Ordet står bara i det förskjutna typsnittet |
| "Brage" | 7, t.ex. 7103439 "Golvbrunn S-Serie Brage …" (s. 630), 7102837 "Golvbrunn Minibrage …" |
| "Mapress" | 250 i benämning och 366 till i produktgrupp (`Pressrör Rostfria Mapress …`) |
| "Wafix" | 0 i filen. Ordet står i katalogen, avkodat ("PP-rör med muff Wafix", "Rör utan muff Wafix", s. 290), men på den sidan saknas art.nr i sidtexten. Artiklarna där fick därför produktgruppens namn ("… PP Avloppsrör Wavin …") |
| "Eminent" | 8, t.ex. 6229114 "Varmvattenberedare Eminent E35 …" (s. 788) |

## 5. Vad som är osäkert

- **Källan är sidtexterna och inte PDF:en.** I det förskjutna typsnittet saknas siffror och mellanslag, och på
  en del sidor saknas art.nr helt i tabellerna (t.ex. s. 290 och 301). Med PDF:en och ordpositioner skulle
  både benämningar och mått bli bättre.
- **Benämningarna är heuristiska.** De är ungefär "texten före tabellen". Ungefär hälften av ett stickprov
  på 40 rader var bra benämningar. De övriga innehåller andra produkters rubriker, beskrivningstext eller
  rubriker utan värden ("Gods Max tjlek 10 mm"). För 5 668 rader är `n` bara produktgruppen.
- **Dimensionen** tas bara med när kolumnen går att para ihop exakt med artiklarna (lika många värden, eller en
  jämn multipel). Annars utelämnas den i stället för att gissas.
- **RSK = 7-siffrigt art.nr.** Det bygger på att katalogtexten och dahl.se använder samma nummer som RSK. Det
  är inte kontrollerat mot RSK-databasen.
- **Enheten** är "st" om inget "Enhet: …" står i texten närmast före tabellen. Ett "Enhet: Meter" längre bort på
  sidan missas (t.ex. 1760653, kopparrör i ring, som fick "st").
- Produktgruppen väljs ur innehållsförteckningen. Flera rubriker kan peka på samma sida, och då slås de ihop
  med " / ".
- Flikregistrets namn har tolkats ur en sidtext där radbrytningarna har försvunnit. För flik 15/16 delas
  namnen efter flikarnas innehåll: 15 = Pannor, Oljebrännare och Tillbehör, 16 = Radiatorer.
