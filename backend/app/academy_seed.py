from __future__ import annotations

from sqlalchemy.orm import Session

from .academy_models import Course, Exam, Exercise, Lesson, Module, Question
from .academy_courses_2 import COURSES_2, EXERCISES_2
from .academy_plans import BAD, STAM, VARME

"""Innehållet i Dahl Academy.

Skrivet för svensk VVS-praxis och för den som ska mängda och kalkylera på riktigt. Där ett kontor kan göra på
flera sätt står det uttryckligen att det är så - en utbildning som låtsas att det finns ett svar på allt lär
ut fel sak.

Facit till varje mängdningsövning räknas ur bladets geometri i academy_plans, aldrig ur ett tal här. Ändrar
någon ett stråk följer svaret med, och en övning kan inte bli fel av att någon glömde uppdatera facit.

Seedningen är idempotent: den känner igen allt på slug och uppdaterar i stället för att skapa dubbletter.
"""

P = lambda t: {"k": "p", "t": t}                                            # noqa: E731
UL = lambda xs: {"k": "ul", "t": xs}                                        # noqa: E731
TERMS = lambda xs: {"k": "terms", "t": xs}                                  # noqa: E731
NOTE = lambda t: {"k": "note", "t": t}                                      # noqa: E731
WARN = lambda t: {"k": "warn", "t": t}                                      # noqa: E731
FORMULA = lambda t, w: {"k": "formula", "t": t, "why": w}                   # noqa: E731
PLAN = lambda slug, cap: {"k": "drawing", "plan": slug, "caption": cap}     # noqa: E731
H = lambda t: {"k": "h", "t": t}                                            # noqa: E731


# ================================================================ kurs 1: grundläggande VVS-kalkyl

KURS1 = {
    "slug": "grund-vvs-kalkyl", "title": "Grundläggande VVS-kalkyl", "level": "grund", "order": 1, "hours": 6.0,
    "blurb": "Från första blicken på ett blad till en kalkyl som håller. Kursen som allt annat bygger på.",
    "moduler": [
        {
            "slug": "intro", "title": "Introduktion till kalkylering", "xp": 100, "requires": "",
            "blurb": "Vad en kalkyl är, vem den är till för och vad som gör den fel.",
            "lektioner": [
                {"slug": "vad-ar-kalkyl", "title": "Vad en VVS-kalkyl faktiskt är", "minutes": 6, "blocks": [
                    P("En kalkyl är ett påstående om vad ett arbete kommer att kosta att utföra. Den är inte en "
                      "gissning och inte en offert — den är en uträkning med redovisade förutsättningar, och den "
                      "ska gå att granska av någon annan än den som gjorde den."),
                    H("Tre delar"),
                    TERMS([
                        ["Mängd", "Hur mycket det är. Meter rör, antal ventiler, antal apparater. Kommer ur ritningen."],
                        ["Pris", "Vad materialet kostar. Kommer ur leverantörens prislista minus rabatt."],
                        ["Tid", "Hur länge det tar att montera. Kommer ur normtid eller egen erfarenhet."],
                    ]),
                    P("Allt annat i en kalkyl — påslag, risk, UE, marginal — är justeringar av de tre. Sitter någon "
                      "av de tre fel spelar justeringarna ingen roll."),
                    NOTE("Den vanligaste orsaken till att ett jobb går back är inte fel pris. Det är fel mängd. Ett "
                         "materialpris som är tio procent fel kostar tio procent på materialdelen; en glömd stam "
                         "kostar hela stammen."),
                ]},
                {"slug": "vem-laser", "title": "Vem som läser kalkylen", "minutes": 4, "blocks": [
                    P("En kalkyl läses av fyra sorters människor, och de vill ha olika saker ur den."),
                    TERMS([
                        ["Du själv", "Om två år, när något gått fel. Då är det förutsättningarna du letar efter."],
                        ["Kollegan", "Som ska granska. Vill se att mängden går att spåra till bladet."],
                        ["Chefen", "Vill se marginalen och vad som är osäkert."],
                        ["Beställaren", "Ser bara anbudet, men frågar om en post när den sticker ut."],
                    ]),
                    P("Därför är spårbarhet inte byråkrati. En rad som säger 12,48 m utan att säga vilket rör på "
                      "vilket blad går inte att försvara när någon frågar."),
                ]},
                {"slug": "kalkylens-fel", "title": "De fem felen som kostar mest", "minutes": 7, "blocks": [
                    UL([
                        "Glömd sträcka — ett stråk som fortsätter på nästa blad och aldrig mängdades.",
                        "Dubbelräkning — samma stam mängdad både i schaktritningen och i planen.",
                        "Fel dimension — DN25 prissatt som DN20 på hela stammen.",
                        "Orimlig montagetid — 0,05 h/m på ett rör som ska klamras i betongtak.",
                        "Saknade rördelar — böjar, T-rör och kopplingar som aldrig kom med.",
                    ]),
                    WARN("Dubbelräkning är farligast av dem, eftersom den gör kalkylen för dyr och därmed osynlig: "
                         "du förlorar jobbet och får aldrig veta varför."),
                ]},
            ],
            "fragor": [
                {"slug": "q-intro-1", "kind": "single", "area": "teori", "points": 10, "in_exam": True,
                 "prompt": "Vilken del av en kalkyl kostar mest när den blir fel?",
                 "options": ["Materialpriset", "Mängden", "Påslaget", "Timkostnaden"],
                 "answer": {"index": 1},
                 "explain": "Ett pris som är tio procent fel kostar tio procent på materialet. En glömd stam kostar hela stammen."},
                {"slug": "q-intro-2", "kind": "bool", "area": "teori", "points": 10, "in_exam": True,
                 "prompt": "En kalkyl och en offert är samma sak.", "options": [],
                 "answer": {"value": False},
                 "explain": "Kalkylen är uträkningen med sina förutsättningar. Offerten är det pris du väljer att lämna ut ur den."},
                {"slug": "q-intro-3", "kind": "single", "area": "teori", "points": 10, "in_exam": True,
                 "prompt": "Varför är dubbelräkning farligare än en glömd post?",
                 "options": ["Den syns i granskningen", "Den gör anbudet för dyrt, så du förlorar jobbet utan att få veta varför",
                             "Den påverkar bara materialet", "Den är lätt att rätta i efterhand"],
                 "answer": {"index": 1},
                 "explain": "En för låg kalkyl upptäcks under produktionen. En för hög upptäcks aldrig — anbudet bara förlorar."},
            ],
        },
        {
            "slug": "ritningslasning", "title": "Ritningsläsning", "xp": 150, "requires": "intro",
            "blurb": "Bladets grammatik: linjetyper, beteckningar, hänvisningslinjer och skala.",
            "lektioner": [
                {"slug": "linjetyper", "title": "Linjetyperna berättar var röret ligger", "minutes": 6, "blocks": [
                    P("Svensk ritstandard låter linjetypen säga något om ledningen, och beteckningen säga vilket "
                      "system den tillhör. Den som bara läser färgen läser fel på ett svartvitt blad."),
                    TERMS([
                        ["Heldragen", "Ledning i det plan ritningen visar."],
                        ["Streckad", "Ledning som ligger dolt — i bjälklag, i vägg eller under golv."],
                        ["Streck-punkt", "Centrumlinje eller ledning i annat plan, beroende på kontorets nyckel."],
                        ["Dubbellinje", "Rörets två väggar, ritade var för sig. Vanligt på grova dimensioner."],
                    ]),
                    NOTE("Nyckeln står i bladets egen teckenförklaring. Två kontor kan använda streck-punkt för "
                         "olika saker, och det är teckenförklaringen som gäller — inte vanan från förra projektet."),
                ]},
                {"slug": "beteckningar", "title": "Beteckningen och dess hänvisningslinje", "minutes": 7, "blocks": [
                    P("En beteckning som KV1-X31-25 säger tre saker: system, placering i systemet och dimension. "
                      "Den hör ihop med ett rör genom sin hänvisningslinje — den tunna linjen från texten till röret."),
                    TERMS([
                        ["KV1", "Systemet. Tappkallvatten, krets 1."],
                        ["X31", "Var i systemet. Kontorets egen numrering."],
                        ["25", "Dimensionen, DN25."],
                    ]),
                    WARN("Närmaste rör är inte samma sak som rätt rör. I en bunt ligger KV, VV och VVC några "
                         "centimeter isär, och bara hänvisningslinjen kan säga vilken etikett som gäller vilket rör. "
                         "Det är därför Dahl aldrig gissar på närhet."),
                    PLAN("stam-1", "Tre stigare i samma schakt. Geometrin kan inte skilja dem åt — etiketten kan."),
                ]},
                {"slug": "skala", "title": "Skalan och varför den måste kontrolleras", "minutes": 5, "blocks": [
                    P("Skalan står oftast i namnrutan, men den gäller bara om bladet skrivits ut i rätt format. "
                      "Ett A1-blad utskrivet på A3 är i halv skala, och en mängd tagen ur det är hälften så lång."),
                    P("Skalstocken på bladet är det enda måttet som följer med utskriften. Mät den först."),
                    FORMULA("meter = uppmätt längd på bladet × skalans nämnare ÷ 1000",
                            "En sträcka på 62 mm i skala 1:50 är 62 × 50 / 1000 = 3,10 m."),
                ]},
                {"slug": "symboler", "title": "Symbolerna du måste känna igen", "minutes": 8, "blocks": [
                    P("Ventiler och apparater ritas som symboler. De flesta är gemensamma mellan kontor, men "
                      "teckenförklaringen är alltid facit."),
                    TERMS([
                        ["Kulventil", "Avstängning. Två trianglar mot varandra med ett handtag."],
                        ["Backventil", "Släpper bara igenom åt ett håll. Triangel mot ett streck."],
                        ["Injusteringsventil", "Ställs in på ett flöde. Kulventil med mätuttag."],
                        ["Golvbrunn", "Cirkel med kryss."],
                        ["Radiator", "Avlång rektangel mot vägg."],
                        ["Cirkulationspump", "Cirkel med triangel i."],
                        ["Expansionskärl", "Rundad behållare på grenledning."],
                    ]),
                    PLAN("varme-1", "En radiatorkrets med pump, backventil, avstängning och injustering."),
                ]},
            ],
            "fragor": [
                {"slug": "q-rit-1", "kind": "single", "area": "ritning", "points": 10, "in_exam": True,
                 "prompt": "En ledning är ritad streckad. Vad betyder det oftast?",
                 "options": ["Att den är riven", "Att den ligger dold, i bjälklag eller vägg",
                             "Att den är oisolerad", "Att den saknar dimension"],
                 "answer": {"index": 1},
                 "explain": "Streckad linje är dold ledning. Bladets egen teckenförklaring är alltid facit."},
                {"slug": "q-rit-2", "kind": "single", "area": "ritning", "points": 10, "in_exam": True,
                 "prompt": "I beteckningen VV1-X31-20 — vad är 20?",
                 "options": ["Antal meter", "Våningsplan", "Dimensionen DN20", "Kretsnummer"],
                 "answer": {"index": 2},
                 "explain": "Sista talet är dimensionen. Första ledet är systemet, mittenledet placeringen."},
                {"slug": "q-rit-3", "kind": "numeric", "area": "ritning", "points": 10, "in_exam": True,
                 "tolerance": 0.02,
                 "prompt": "En sträcka mäter 74 mm på ett blad i skala 1:50. Hur många meter är det?",
                 "options": [], "answer": {"value": 3.7},
                 "explain": "74 × 50 / 1000 = 3,70 m."},
                {"slug": "q-rit-4", "kind": "single", "area": "ritning", "points": 10, "in_exam": True,
                 "prompt": "Två parallella rör går i samma schakt. Det ena är märkt VV1-S1-25. Hur avgör du vilket rör etiketten gäller?",
                 "options": ["Det närmaste röret", "Det grövsta röret",
                             "Genom hänvisningslinjen från etiketten", "Genom färgen"],
                 "answer": {"index": 2},
                 "explain": "Bara hänvisningslinjen binder en etikett till ett rör. Närhet är en gissning."},
                {"slug": "q-rit-5", "kind": "bool", "area": "ritning", "points": 10, "in_exam": True,
                 "prompt": "Skalan i namnrutan gäller alltid, oavsett vilket pappersformat bladet skrivits ut på.",
                 "options": [], "answer": {"value": False},
                 "explain": "Ett A1-blad utskrivet på A3 är i halv skala. Skalstocken följer med utskriften, det gör inte texten."},
            ],
        },
        {
            "slug": "mangdning-grund", "title": "Grundläggande mängdning", "xp": 200, "requires": "ritningslasning",
            "blurb": "Att ta ut meter, antal och rördelar ur ett blad — och att kunna visa var de kom ifrån.",
            "lektioner": [
                {"slug": "ordning", "title": "Ordningen du mängdar i", "minutes": 6, "blocks": [
                    P("Mängda alltid system för system, aldrig blad för blad. Ett system som följs hela vägen "
                      "upptäcker sina egna hål; ett blad som mängdas i taget lämnar skarvarna omängdade."),
                    UL([
                        "Börja vid inkommande servis eller värmekälla.",
                        "Följ stammen uppåt eller utåt tills den delar sig.",
                        "Ta varje gren till sin sista apparat innan du går tillbaka.",
                        "Markera det du mängdat på bladet — annars mängdar du det igen.",
                    ]),
                ]},
                {"slug": "rordelar", "title": "Rördelar, klamring och det som inte syns", "minutes": 7, "blocks": [
                    P("Böjar, T-rör, muffar och reduceringar ritas sällan ut. De räknas som påslag på rörlängden "
                      "eller som poster ur erfarenhet."),
                    TERMS([
                        ["Böjar", "Räknas ur ritningen där de syns, annars som procentpåslag på rörmängden."],
                        ["T-rör", "En per avstick. De syns i geometrin — varje gren börjar i ett T."],
                        ["Klammer", "Ett per c/c-avstånd enligt monteringsanvisning, typiskt 1,5–2,5 m."],
                        ["Isolering", "Mäts som rörlängd, men bara på de system som ska isoleras."],
                    ]),
                    NOTE("Dahl räknar rörlängd ur bladets geometri. Rördelar är en kalkylpost, inte en "
                         "mängdpost — det är en viktig skillnad när du granskar en maskinmängd."),
                ]},
                {"slug": "kontroll", "title": "Kontrollen som tar två minuter", "minutes": 5, "blocks": [
                    P("Tre kontroller fångar de flesta felen och tar tillsammans ett par minuter."),
                    UL([
                        "Summera per system och jämför med en grov överslagsräkning av husets storlek.",
                        "Kontrollera att varje apparat har både tillopp och avlopp där det behövs.",
                        "Leta efter stråk som slutar mitt i luften — de fortsätter oftast på ett annat blad.",
                    ]),
                ]},
            ],
            "fragor": [
                {"slug": "q-mangd-1", "kind": "single", "area": "mangdning", "points": 10, "in_exam": True,
                 "prompt": "Varför mängdar man system för system i stället för blad för blad?",
                 "options": ["Det går fortare", "Systemet upptäcker sina egna hål vid skarvarna",
                             "Bladen är olika stora", "Det krävs enligt AMA"],
                 "answer": {"index": 1},
                 "explain": "Ett stråk som fortsätter på nästa blad syns bara om du följer systemet, inte bladet."},
                {"slug": "q-mangd-2", "kind": "single", "area": "mangdning", "points": 10, "in_exam": True,
                 "prompt": "Ett stråk slutar mitt på bladet utan apparat. Vad är den troligaste förklaringen?",
                 "options": ["Det är ett ritfel", "Det fortsätter på ett annat blad",
                             "Det är en proppad ände", "Det är isolerat"],
                 "answer": {"index": 1},
                 "explain": "Bladgränser klipper stråk. Kontrollera anslutande blad innan du antar något annat."},
                {"slug": "q-mangd-3", "kind": "single", "area": "mangdning", "points": 10, "in_exam": True,
                 "prompt": "Var hör klammer hemma i en kalkyl?",
                 "options": ["Som rörlängd", "Som antal ur c/c-avståndet", "Som isolering", "De räknas inte"],
                 "answer": {"index": 1},
                 "explain": "Klammer räknas som antal, ur rörlängden delat med c/c-avståndet enligt monteringsanvisningen."},
            ],
        },
        {
            "slug": "kalkyl-grund", "title": "Kalkyl", "xp": 200, "requires": "mangdning-grund",
            "blurb": "Material, tid, timkostnad och påslag — och hur de blir ett pris.",
            "lektioner": [
                {"slug": "material", "title": "Materialkostnad och rabatt", "minutes": 6, "blocks": [
                    P("Materialpriset kommer ur leverantörens bruttoprislista, minskat med din rabattsats för den "
                      "varugruppen. Rabatten är sällan densamma för rör som för ventiler."),
                    FORMULA("nettopris = bruttopris × (1 − rabatt)",
                            "Ett rör på 118 kr/m med 28 % rabatt kostar 118 × 0,72 = 84,96 kr/m."),
                    NOTE("Ange alltid vilken prislista och vilket datum kalkylen bygger på. En kalkyl utan "
                         "prisdatum går inte att försvara ett halvår senare."),
                ]},
                {"slug": "tid", "title": "Montagetid och timkostnad", "minutes": 7, "blocks": [
                    P("Montagetiden anges i timmar per enhet — h/m för rör, h/st för apparater. Den kommer ur "
                      "normtidslistor eller ur egen uppföljning."),
                    FORMULA("arbetskostnad = mängd × montagetid × timkostnad",
                            "120 m rör × 0,18 h/m × 520 kr/h = 11 232 kr."),
                    P("Timkostnaden är inte lönen. Den är lön plus sociala avgifter, plus overhead, plus "
                      "restid och bodar, delat på debiterbara timmar."),
                    WARN("Montagetid är den post som skiljer mest mellan kontor. Använd egna siffror när du har "
                         "dem, och skriv ut vilken källa du använt när du inte har det."),
                ]},
                {"slug": "paslag", "title": "Påslag, risk och marginal", "minutes": 6, "blocks": [
                    TERMS([
                        ["Materialpåslag", "Täcker hantering, spill och kapitalbindning. Ofta 8–15 %."],
                        ["Risk", "Täcker det du vet att du inte vet. Sätts per projekt, inte per rad."],
                        ["TB", "Täckningsbidrag: intäkt minus rörlig kostnad. Det som ska bära företaget."],
                        ["Marginal", "TB delat med priset. Det du faktiskt tjänar."],
                    ]),
                    FORMULA("pris = (material × (1 + påslag) + arbete) × (1 + risk) / (1 − marginal)",
                            "Ordningen spelar roll: marginal räknas på priset, påslag på kostnaden."),
                ]},
            ],
            "fragor": [
                {"slug": "q-kalk-1", "kind": "numeric", "area": "kalkyl", "points": 10, "in_exam": True,
                 "tolerance": 0.01,
                 "prompt": "240 m rör, 0,16 h/m. Hur många timmar?", "options": [],
                 "answer": {"value": 38.4}, "explain": "240 × 0,16 = 38,4 timmar."},
                {"slug": "q-kalk-2", "kind": "numeric", "area": "kalkyl", "points": 10, "in_exam": True,
                 "tolerance": 0.01,
                 "prompt": "Bruttopris 118 kr/m, rabatt 28 %. Vad är nettopriset per meter?", "options": [],
                 "answer": {"value": 84.96}, "explain": "118 × (1 − 0,28) = 84,96 kr/m."},
                {"slug": "q-kalk-3", "kind": "single", "area": "kalkyl", "points": 10, "in_exam": True,
                 "prompt": "Vad ingår i en timkostnad utöver lönen?",
                 "options": ["Ingenting", "Sociala avgifter, overhead, restid och bodar",
                             "Bara sociala avgifter", "Materialpåslaget"],
                 "answer": {"index": 1},
                 "explain": "Timkostnaden är hela kostnaden för en debiterbar timme, inte utbetald lön."},
                {"slug": "q-kalk-4", "kind": "single", "area": "kalkyl", "points": 10, "in_exam": True,
                 "prompt": "Vad är skillnaden mellan påslag och marginal?",
                 "options": ["Ingen", "Påslag räknas på kostnaden, marginal på priset",
                             "Marginal räknas på kostnaden", "Påslag gäller bara arbete"],
                 "answer": {"index": 1},
                 "explain": "Ett påslag på 20 % ger inte 20 % marginal. Marginalen räknas på försäljningspriset."},
            ],
        },
        {
            "slug": "praktiskt", "title": "Praktiskt projekt", "xp": 300, "requires": "kalkyl-grund",
            "blurb": "Ett litet badrum från blad till slutpris. Allt du lärt dig, i ett svep.",
            "lektioner": [
                {"slug": "uppgiften", "title": "Uppgiften", "minutes": 4, "blocks": [
                    P("Ett badrum ska byggas om. Ritningen visar tappvatten, spillvatten och de apparater som ska "
                      "sitta. Din uppgift är att mängda, prissätta och lämna ett pris."),
                    PLAN("badrum-1", "Badrummet du ska mängda. KV i blått, VV i rött, spillvatten i grönt."),
                    UL([
                        "Mängda KV, VV och spillvatten var för sig.",
                        "Räkna apparater och ventiler.",
                        "Sätt material- och tidsposter.",
                        "Lägg påslag och lämna ett slutpris.",
                    ]),
                ]},
            ],
            "fragor": [],
        },
    ],
}

# ================================================================ kurs 2-5

KURS2 = {
    "slug": "mangdning-vs", "title": "Mängdning VS", "level": "fortsattning", "order": 2, "hours": 8.0,
    "blurb": "Systemvis mängdning av tappvatten, värme, spill, dag, isolering, rördelar, ventiler och apparater.",
    "moduler": [
        {"slug": "tappvatten", "title": "Tappvatten", "xp": 100, "requires": "", "blurb": "KV, VV och VVC — och varför de alltid går tillsammans.",
         "lektioner": [
             {"slug": "kv-vv-vvc", "title": "KV, VV och VVC", "minutes": 6, "blocks": [
                 P("Tappvattnet delas i tre ledningar som nästan alltid går i bunt, och som därför är lätta att "
                   "blanda ihop."),
                 TERMS([
                     ["KV", "Tappkallvatten. Från servis ut till varje tappställe."],
                     ["VV", "Tappvarmvatten. Från beredare eller växlare ut till tappstället."],
                     ["VVC", "Varmvattencirkulation. Tillbaka från yttersta tappstället så vattnet inte kallnar."],
                 ]),
                 P("VVC är klenare än VV, ofta en dimension mindre, och finns bara där sträckan är lång nog att "
                   "väntetiden annars blir för lång."),
                 PLAN("stam-1", "KV, VV och VVC i samma schakt genom tre plan."),
             ]},
             {"slug": "tappvatten-mangd", "title": "Att mängda en tappvattenstam", "minutes": 6, "blocks": [
                 P("En stam mängdas i höjdled först, sedan gren för gren på varje plan. Höjden tas ur "
                   "sektionsritning eller våningshöjd, inte ur planen — planen visar ingen höjd."),
                 WARN("Stigare glöms oftast. En stam genom fem plan med 3,0 m våningshöjd är 15 meter rör som "
                      "inte syns som längd på någon plan."),
             ]},
         ],
         "fragor": [
             {"slug": "q-tv-1", "kind": "single", "area": "mangdning", "points": 10, "in_exam": True,
              "prompt": "Vilken ledning är normalt klenast av KV, VV och VVC?",
              "options": ["KV", "VV", "VVC", "De är lika"], "answer": {"index": 2},
              "explain": "VVC bär bara cirkulationsflödet och är ofta en dimension mindre än VV."},
             {"slug": "q-tv-2", "kind": "bool", "area": "mangdning", "points": 10, "in_exam": True,
              "prompt": "Stigarnas längd går att läsa direkt ur en planritning.", "options": [],
              "answer": {"value": False},
              "explain": "En plan visar inga höjder. Stigarlängden kommer ur sektion eller våningshöjd."},
         ]},
        {"slug": "varme", "title": "Värme", "xp": 100, "requires": "tappvatten", "blurb": "Fram och retur, radiatorer, injustering och pump.",
         "lektioner": [
             {"slug": "krets", "title": "Kretsen och dess delar", "minutes": 6, "blocks": [
                 P("En värmekrets går alltid i par: framledning ut till radiatorerna och returledning tillbaka. "
                   "Mängdar du bara den ena har du halva kretsen."),
                 PLAN("varme-1", "Fram och retur i par, tre radiatorer med injusteringsventiler."),
                 TERMS([
                     ["Framledning", "Varmt vatten ut till radiatorerna."],
                     ["Returledning", "Avkylt vatten tillbaka till värmekällan."],
                     ["Injusteringsventil", "Ställer flödet så varje radiator får sin del."],
                     ["Cirkulationspump", "Driver flödet runt kretsen."],
                 ]),
             ]},
         ],
         "fragor": [
             {"slug": "q-va-1", "kind": "single", "area": "mangdning", "points": 10, "in_exam": True,
              "prompt": "Vad är det vanligaste mängdningsfelet på en värmekrets?",
              "options": ["Fel radiatorstorlek", "Att bara mängda framledningen",
                          "Fel pump", "För många ventiler"],
              "answer": {"index": 1},
              "explain": "Kretsen går i par. Bara framledningen är halva mängden."},
         ]},
        {"slug": "spill-dag", "title": "Spillvatten och dagvatten", "xp": 100, "requires": "varme", "blurb": "Självfall, lutning och luftning.",
         "lektioner": [
             {"slug": "sjalvfall", "title": "Självfall bestämmer allt annat", "minutes": 6, "blocks": [
                 P("En självfallsledning måste luta hela vägen, och lutningen är typiskt 1:100 till 1:50 beroende "
                   "på dimension. Det betyder att spillvattnet bestämmer var allt annat får plats."),
                 FORMULA("höjdskillnad = längd × lutning",
                         "20 m ledning med lutning 1:100 sjunker 0,20 m på vägen."),
                 NOTE("Spillvattnet ritas i planen, men dess verkliga längd är något längre än den plana längden "
                      "eftersom den lutar. På normala lutningar är skillnaden under en procent och ryms i påslaget."),
             ]},
         ],
         "fragor": [
             {"slug": "q-sp-1", "kind": "numeric", "area": "mangdning", "points": 10, "in_exam": True,
              "tolerance": 0.02,
              "prompt": "En spillvattenledning är 24 m lång och har lutning 1:100. Hur många meter sjunker den?",
              "options": [], "answer": {"value": 0.24}, "explain": "24 × 1/100 = 0,24 m."},
             {"slug": "q-sp-2", "kind": "single", "area": "teori", "points": 10, "in_exam": True,
              "prompt": "En ledning stiger tre våningar utan lutning. Vilket system kan den inte tillhöra?",
              "options": ["Tappkallvatten", "Spillvatten", "Värme framledning", "Komfortkyla"],
              "answer": {"index": 1},
              "explain": "Spillvatten går med självfall. En stigande spillvattenledning finns bara som stigare med luftning."},
         ]},
        {"slug": "isolering-delar", "title": "Isolering, rördelar och ventiler", "xp": 100, "requires": "spill-dag",
         "blurb": "Det som inte är rör men ändå kostar.",
         "lektioner": [
             {"slug": "isolering", "title": "Vad som isoleras och varför", "minutes": 6, "blocks": [
                 TERMS([
                     ["VV och VVC", "Isoleras för att hålla värmen och spara energi."],
                     ["KV", "Isoleras mot kondens där det är varmt och fuktigt."],
                     ["Värme", "Isoleras i ouppvärmda utrymmen."],
                     ["Kyla", "Isoleras alltid — kondens annars droppar i taket."],
                 ]),
                 P("Isolering mängdas som rörlängd per system och tjocklek, inte som en klumpsumma."),
             ]},
         ],
         "fragor": [
             {"slug": "q-iso-1", "kind": "single", "area": "teori", "points": 10, "in_exam": True,
              "prompt": "Varför isoleras kylledningar alltid?",
              "options": ["Energiskäl", "Kondens droppar annars", "Ljudskäl", "Brandskäl"],
              "answer": {"index": 1},
              "explain": "En kall yta i varm luft drar kondens. Utan isolering droppar det i taket."},
         ]},
    ],
}

KURS3 = {
    "slug": "avancerad-kalkyl", "title": "Avancerad VVS-kalkyl", "level": "avancerad", "order": 3, "hours": 7.0,
    "blurb": "Kalkylstrategi, anbud, leverantörspriser, UE, risk, påslag, TB, marginal och ÄTA.",
    "moduler": [
        {"slug": "strategi", "title": "Kalkylstrategi", "xp": 120, "requires": "", "blurb": "Vad du räknar på, och vad du väljer att inte räkna på.",
         "lektioner": [
             {"slug": "produktionskalkyl", "title": "Anbudskalkyl mot produktionskalkyl", "minutes": 7, "blocks": [
                 P("Anbudskalkylen är den du lämnar pris på. Produktionskalkylen är den du styr arbetet mot. De är "
                   "sällan identiska, och det är avsiktligt."),
                 TERMS([
                     ["Anbudskalkyl", "Innehåller risk och marginal. Är ett pris."],
                     ["Produktionskalkyl", "Är en budget. Risken ligger utanför, marginalen är målet."],
                 ]),
                 NOTE("Blandar man ihop dem ser produktionen ut att gå med vinst medan risken äts upp i tysthet."),
             ]},
             {"slug": "ue", "title": "UE, risk och ÄTA", "minutes": 7, "blocks": [
                 TERMS([
                     ["UE", "Underentreprenör. Deras pris är din kostnad — lägg eget påslag på det."],
                     ["Risk", "Det du vet att du inte vet. Sätts per projekt efter vad handlingen faktiskt säger."],
                     ["ÄTA", "Ändring, tillägg, avgående. Regleras i AB 04 och ABT 06."],
                 ]),
                 P("En handling med många oklarheter motiverar högre risk, inte fler gissningar i kalkylen. "
                   "Skriv ned oklarheterna som reservationer i anbudet."),
             ]},
         ],
         "fragor": [
             {"slug": "q-str-1", "kind": "single", "area": "kalkyl", "points": 10, "in_exam": True,
              "prompt": "Var hör risken hemma?",
              "options": ["I produktionskalkylen", "I anbudskalkylen", "I materialpriset", "I timkostnaden"],
              "answer": {"index": 1},
              "explain": "Anbudskalkylen bär risken. Produktionskalkylen är budgeten som ska hållas utan den."},
             {"slug": "q-str-2", "kind": "single", "area": "teori", "points": 10, "in_exam": True,
              "prompt": "Vad står ÄTA för?",
              "options": ["Ändring, tillägg, avgående", "Årlig teknisk avstämning",
                          "Överenskommen tidsplan", "Ändrad teknisk anvisning"],
              "answer": {"index": 0},
              "explain": "ÄTA-arbeten regleras i AB 04 och ABT 06."},
         ]},
        {"slug": "kontroll", "title": "Kalkylkontroll", "xp": 150, "requires": "strategi",
         "blurb": "Att granska någon annans kalkyl — eller maskinens.",
         "lektioner": [
             {"slug": "granska", "title": "Vad du letar efter", "minutes": 8, "blocks": [
                 UL([
                     "Poster med orimlig enhetstid — för snabbt är farligare än för långsamt.",
                     "Mängder som inte går att spåra till ett blad.",
                     "Dimensioner som byter mitt i ett stråk utan att något händer på ritningen.",
                     "Dubbla poster med olika namn för samma sak.",
                     "Apparater utan anslutande ledning, och ledningar utan apparat.",
                 ]),
                 NOTE("När du granskar en maskinmängd: be om bevisningen. Dahl kan visa vilket bläck varje "
                      "meter kom ur. En mängd utan bevis är en siffra, inte en mängd."),
             ]},
         ],
         "fragor": [
             {"slug": "q-kon-1", "kind": "single", "area": "kontroll", "points": 10, "in_exam": True,
              "prompt": "Vilket är det farligaste fyndet i en kalkylgranskning?",
              "options": ["För hög montagetid", "För låg montagetid", "Ett stavfel", "För många poster"],
              "answer": {"index": 1},
              "explain": "För låg tid ser bra ut i anbudet och äts upp i produktionen."},
             {"slug": "q-kon-2", "kind": "single", "area": "kontroll", "points": 10, "in_exam": True,
              "prompt": "En dimension byter från DN25 till DN20 mitt på ett rakt stråk utan T-rör. Vad betyder det troligen?",
              "options": ["Normalt", "En läsning som tagit fel etikett till en del av stråket",
                          "En reducering som glömts ritas", "Isolering"],
              "answer": {"index": 1},
              "explain": "En dimensionsändring kräver en reducering. Utan den på ritningen är det oftast läsningen som delat stråket fel."},
         ]},
    ],
}

KURS4 = {
    "slug": "ritningslasning-vvs", "title": "Ritningsläsning VVS", "level": "grund", "order": 4, "hours": 5.0,
    "blurb": "Bladet i detalj: teckenförklaring, namnruta, revideringar, sektioner och schakt.",
    "moduler": [
        {"slug": "bladet", "title": "Bladet och dess delar", "xp": 100, "requires": "",
         "blurb": "Namnruta, teckenförklaring, revidering och vad som gäller när de säger emot varandra.",
         "lektioner": [
             {"slug": "namnruta", "title": "Namnrutan", "minutes": 5, "blocks": [
                 P("Namnrutan säger vad bladet är, vem som ritat det, vilken skala det har och vilken revidering "
                   "som gäller. Den är det första du läser och det sista du kontrollerar."),
                 UL(["Ritningsnummer och innehåll", "Skala", "Datum och revideringsbokstav",
                     "Konstruktör och granskare", "Projektnummer"]),
                 WARN("Mängdar du på en gammal revidering mängdar du ett hus som inte ska byggas."),
             ]},
             {"slug": "teckenforklaring", "title": "Teckenförklaringen är facit", "minutes": 5, "blocks": [
                 P("Varje kontor har sin egen nyckel. Teckenförklaringen på bladet gäller före allt du lärt dig "
                   "på ett annat projekt."),
             ]},
             {"slug": "schakt", "title": "Schakt och sektioner", "minutes": 6, "blocks": [
                 P("Ett schakt visas i plan som en liten ruta med många ledningar i. Det som händer i höjdled "
                   "syns bara i sektionen."),
                 PLAN("stam-1", "Ett schakt sett över tre plan."),
             ]},
         ],
         "fragor": [
             {"slug": "q-bl-1", "kind": "single", "area": "ritning", "points": 10, "in_exam": True,
              "prompt": "Bladets teckenförklaring säger en sak, och ditt förra projekt en annan. Vad gäller?",
              "options": ["Förra projektet", "Bladets teckenförklaring", "AMA", "Beställarens önskemål"],
              "answer": {"index": 1},
              "explain": "Teckenförklaringen på bladet är alltid facit för just det bladet."},
         ]},
    ],
}

KURS5 = {
    "slug": "futurecalc-vpr", "title": "Dahl & VPR", "level": "grund", "order": 5, "hours": 4.0,
    "blurb": "Verktyget: projekt, läsning, mängdning, material, kalkyl, rapport och anbud.",
    "moduler": [
        {"slug": "kom-igang", "title": "Kom igång", "xp": 100, "requires": "",
         "blurb": "Skapa projekt, ladda upp ritning, läsa av resultatet.",
         "lektioner": [
             {"slug": "projekt", "title": "Projekt och ritningar", "minutes": 5, "blocks": [
                 P("Allt i Dahl hänger under ett projekt. Ett projekt är en handling: alla blad som hör "
                   "ihop, med sina revideringar."),
                 UL(["Skapa projekt", "Ladda upp ritningar som PDF", "Starta läsning per blad",
                     "Granska mängden mot bladet", "Ta ut kalkyl och anbud"]),
             ]},
             {"slug": "granska-lasning", "title": "Att granska en läsning", "minutes": 7, "blocks": [
                 P("Läsningen redovisar tre tillstånd per beteckning, och alla tre är svar."),
                 TERMS([
                     ["Verifierad", "Beteckningen har en hänvisningslinje som når ett rör. Mängden är mätt."],
                     ["Tvetydig", "Hänvisningslinjen når flera möjliga rör. Läsningen vägrar gissa."],
                     ["Utan fäste", "Ingen hänvisningslinje når något rör alls."],
                 ]),
                 NOTE("Tvetydigt är ett giltigt svar. Fel säkerhet är det inte. Där ritningen inte säger vilket "
                      "rör en etikett menar får du frågan i stället för en siffra som ser rätt ut."),
             ]},
         ],
         "fragor": [
             {"slug": "q-vpr-1", "kind": "single", "area": "teori", "points": 10, "in_exam": True,
              "prompt": "Vad betyder det att en beteckning är tvetydig i Dahl?",
              "options": ["Läsningen misslyckades", "Hänvisningslinjen når flera möjliga rör och läsningen vägrar gissa",
                          "Beteckningen är felstavad", "Röret saknar dimension"],
              "answer": {"index": 1},
              "explain": "Tvetydigt är ett svar. Det säger att bladet inte avgör saken, och lämnar valet till dig."},
         ]},
    ],
}

COURSES = [KURS1, KURS2, KURS3, KURS4, KURS5] + COURSES_2


# ================================================================ övningarna

def _ex(slug, kind, title, instructions, course, module, lesson, data, answer, **kw) -> dict:
    return {"slug": slug, "kind": kind, "title": title, "instructions": instructions,
            "course": course, "module": module, "lesson": lesson,
            "data": data, "answer": answer, **kw}


EXERCISES = [
    # ---- mängda rör på ritning -------------------------------------------------------------------
    _ex("ov-mangda-kv", "mangda", "Mängda allt tappkallvatten",
        "Följ varje KV-ledning i badrummet och mät den. Klicka en startpunkt, sedan varje brytpunkt, "
        "och avsluta stråket. Toleransen är ±3 %.",
        "grund-vvs-kalkyl", "mangdning-grund", "ordning",
        {**BAD.data(), "highlight_sys": "KV", "exam_area": "mangdning"},
        {"metres": BAD.metres_where(sys="KV"),
         "miss_hint": "Glöm inte grenen till WC — den går längst upp, ovanför tvättstället.",
         "solution": f"Rätt mängd är {BAD.metres_where(sys='KV')} m: stammen, tvättställsgrenen, duschgrenen och WC-grenen."},
        tolerance=0.03, points=25, difficulty=2,
        hints=["Börja vid stammen längst ned till vänster.",
               "Fyra KV-stråk finns: stam, tvättställ, dusch och WC."]),

    _ex("ov-mangda-vs20", "mangda", "Mängda alla DN20-rör i värmekretsen",
        "Mät samtliga radiatorgrenar i DN20. Fram- och returledningen i DN32 ska inte vara med. Tolerans ±2 %.",
        "mangdning-vs", "varme", "krets",
        {**VARME.data(), "highlight_dn": 20, "exam_area": "mangdning"},
        {"metres": VARME.metres_where(sys="VS", dn=20),
         "miss_hint": "Kom ihåg att varje radiator har både en framgren och en returgren.",
         "solution": f"Rätt mängd är {VARME.metres_where(sys='VS', dn=20)} m fördelat på fem grenar."},
        tolerance=0.02, points=25, difficulty=2,
        hints=["Grenarna går lodrätt ned från de vågräta huvudledningarna.",
               "Radiator 3 i korridoren har bara en gren ritad."]),

    _ex("ov-mangda-vvc", "mangda", "Mängda VVC-stigaren",
        "Mät varmvattencirkulationen genom alla tre planen. Tolerans ±2 %.",
        "mangdning-vs", "tappvatten", "tappvatten-mangd",
        {**STAM.data(), "highlight_sys": "VVC", "exam_area": "mangdning"},
        {"metres": STAM.metres_where(sys="VVC"),
         "solution": f"VVC-stigaren är {STAM.metres_where(sys='VVC')} m — ett enda stråk hela vägen upp."},
        tolerance=0.02, points=20, difficulty=1,
        hints=["VVC är den klenaste av de tre stigarna."]),

    _ex("ov-mangda-spill", "mangda", "Mängda spillvattnet i badrummet",
        "Mät all spillvattenledning, oavsett dimension. Tolerans ±3 %.",
        "mangdning-vs", "spill-dag", "sjalvfall",
        {**BAD.data(), "highlight_sys": "S", "exam_area": "mangdning"},
        {"metres": BAD.metres_where(sys="S"),
         "miss_hint": "Tvättställets avlopp går ned till samma samlingsledning som golvbrunnen.",
         "solution": f"Rätt mängd är {BAD.metres_where(sys='S')} m: golvbrunn, WC och tvättställ."},
        tolerance=0.03, points=20, difficulty=2),

    # ---- markera komponenter ---------------------------------------------------------------------
    _ex("ov-markera-ventiler", "markera", "Markera samtliga avstängningsventiler",
        "Klicka på varje kulventil i badrummet. Markera inte injusteringsventiler eller backventiler.",
        "grund-vvs-kalkyl", "ritningslasning", "symboler",
        {**BAD.data(), "pick": "symbols", "exam_area": "ritning"},
        {"picked": BAD.ids_of_kind("kulventil"), "pass": 1.0,
         "solution": "Fyra kulventiler: två vid stammen, en vid tvättstället och en vid WC."},
        points=20, difficulty=1,
        hints=["Kulventilen ritas som två trianglar mot varandra."]),

    _ex("ov-markera-varme", "markera", "Markera alla injusteringsventiler",
        "Klicka på injusteringsventilerna i värmekretsen. Avstängning och backventil ska inte markeras.",
        "mangdning-vs", "varme", "krets",
        {**VARME.data(), "pick": "symbols", "exam_area": "ritning"},
        {"picked": VARME.ids_of_kind("injustering"), "pass": 1.0,
         "solution": "Två injusteringsventiler, en på varje radiatorretur i kontoren."},
        points=15, difficulty=2),

    _ex("ov-markera-apparater", "markera", "Markera badrummets sanitetsporslin",
        "Klicka på WC-stol och tvättställ. Blandare och golvbrunn räknas inte som porslin.",
        "mangdning-vs", "isolering-delar", "isolering",
        {**BAD.data(), "pick": "symbols", "exam_area": "ritning"},
        {"picked": BAD.ids_of_kind("wc", "tvattstall"), "pass": 1.0,
         "solution": "WC-stol och tvättställ. Golvbrunn är avlopp, blandare är armatur."},
        points=15, difficulty=1),

    # ---- dimension och symbol --------------------------------------------------------------------
    _ex("ov-dim-stam", "dimension", "Vilken dimension matar stammen?",
        "Stigaren för tappkallvatten är markerad på bladet. Vilken dimension har den?",
        "grund-vvs-kalkyl", "ritningslasning", "beteckningar",
        {**STAM.data(), "focus": "kv-stig", "options": ["DN15", "DN20", "DN25", "DN32"],
         "exam_area": "ritning"},
        {"index": 3, "why": "Stammen är DN32 och grenarna på varje plan är DN20."},
        points=10, difficulty=1),

    _ex("ov-dim-gren", "dimension", "Vilken dimension har radiatorgrenen?",
        "Grenen från framledningen ned till radiator 1 är markerad. Vilken dimension?",
        "mangdning-vs", "varme", "krets",
        {**VARME.data(), "focus": "vs-gren1", "options": ["DN15", "DN20", "DN25", "DN32"],
         "exam_area": "ritning"},
        {"index": 1, "why": "Huvudledningen är DN32, grenarna DN20."},
        points=10, difficulty=1),

    _ex("ov-symbol-1", "symbol", "Vilken symbol är pumpen?",
        "Peka ut cirkulationspumpen bland alternativen.",
        "grund-vvs-kalkyl", "ritningslasning", "symboler",
        {"options": ["Kulventil", "Cirkulationspump", "Expansionskärl", "Backventil"],
         "figure": "pump", "exam_area": "ritning"},
        {"index": 1, "why": "Pumpen ritas som en cirkel med en triangel i, som visar flödesriktningen."},
        points=10, difficulty=1),

    # ---- matchning -------------------------------------------------------------------------------
    _ex("ov-matcha-symboler", "matcha", "Matcha symbol mot namn",
        "Dra varje symbol till rätt namn.",
        "grund-vvs-kalkyl", "ritningslasning", "symboler",
        {"left": [{"id": "s1", "figure": "kulventil"}, {"id": "s2", "figure": "backventil"},
                  {"id": "s3", "figure": "golvbrunn"}, {"id": "s4", "figure": "radiator"},
                  {"id": "s5", "figure": "pump"}, {"id": "s6", "figure": "expansionskarl"}],
         "right": [{"id": "n1", "text": "Kulventil"}, {"id": "n2", "text": "Backventil"},
                   {"id": "n3", "text": "Golvbrunn"}, {"id": "n4", "text": "Radiator"},
                   {"id": "n5", "text": "Cirkulationspump"}, {"id": "n6", "text": "Expansionskärl"}],
         "names": {"s1": "kulventilen", "s2": "backventilen", "s3": "golvbrunnen", "s4": "radiatorn",
                   "s5": "pumpen", "s6": "expansionskärlet"},
         "exam_area": "ritning"},
        {"pairs": {"s1": "n1", "s2": "n2", "s3": "n3", "s4": "n4", "s5": "n5", "s6": "n6"}},
        points=20, difficulty=2),

    # ---- bygg rörsystem --------------------------------------------------------------------------
    _ex("ov-bygg-krets", "bygg", "Bygg värmekretsen i rätt ordning",
        "Dra komponenterna så att de står i den ordning vattnet passerar dem, från värmekällan och tillbaka.",
        "mangdning-vs", "varme", "krets",
        {"items": [{"id": "kalla", "text": "Värmekälla"}, {"id": "pump", "text": "Cirkulationspump"},
                   {"id": "avst", "text": "Avstängningsventil"}, {"id": "inj", "text": "Injusteringsventil"},
                   {"id": "rad", "text": "Radiator"}, {"id": "retur", "text": "Returledning"}],
         "names": {"kalla": "Värmekälla", "pump": "Cirkulationspump", "avst": "Avstängningsventil",
                   "inj": "Injusteringsventil", "rad": "Radiator", "retur": "Returledning"},
         "exam_area": "teori"},
        {"order": ["kalla", "pump", "avst", "inj", "rad", "retur"],
         "solution": "Värmekälla → pump → avstängning → injustering → radiator → retur."},
        points=20, difficulty=2),

    # ---- kalkyl ----------------------------------------------------------------------------------
    _ex("ov-kalkyl-1", "kalkyl", "Räkna fram kostnaden för ett rörstråk",
        "120 meter rör. Material 85 kr/m. Montagetid 0,18 h/m. Timkostnad 520 kr/h. Materialpåslag 12 %. "
        "Räkna ut varje steg.",
        "grund-vvs-kalkyl", "kalkyl-grund", "tid",
        {"givna": [["Rörmängd", "120 m"], ["Materialpris", "85 kr/m"], ["Montagetid", "0,18 h/m"],
                   ["Timkostnad", "520 kr/h"], ["Materialpåslag", "12 %"]],
         "steps": [
             {"key": "material", "label": "Materialkostnad", "unit": "kr", "hint": "mängd × pris"},
             {"key": "timmar", "label": "Timmar", "unit": "h", "hint": "mängd × montagetid"},
             {"key": "arbete", "label": "Arbetskostnad", "unit": "kr", "hint": "timmar × timkostnad"},
             {"key": "paslag", "label": "Materialpåslag", "unit": "kr", "hint": "material × påslag"},
             {"key": "total", "label": "Total kostnad", "unit": "kr", "hint": "allt ovan"},
         ], "exam_area": "kalkyl"},
        {"steps": {"material": 10200, "timmar": 21.6, "arbete": 11232, "paslag": 1224, "total": 22656},
         "solution": "Material 120 × 85 = 10 200 kr. Timmar 120 × 0,18 = 21,6 h. Arbete 21,6 × 520 = 11 232 kr. "
                     "Påslag 10 200 × 0,12 = 1 224 kr. Totalt 22 656 kr."},
        tolerance=0.01, points=30, difficulty=3,
        hints=["Ta ett steg i taget. Materialkostnaden först.",
               "Arbetskostnaden är timmar gånger timkostnad, inte meter gånger timkostnad."]),

    _ex("ov-kalkyl-marginal", "kalkyl", "Från kostnad till pris",
        "Självkostnaden är 84 000 kr. Risk 4 %. Önskad marginal 12 %. Räkna fram priset.",
        "avancerad-kalkyl", "strategi", "produktionskalkyl",
        {"givna": [["Självkostnad", "84 000 kr"], ["Risk", "4 %"], ["Marginal", "12 %"]],
         "steps": [
             {"key": "risk", "label": "Risktillägg", "unit": "kr", "hint": "självkostnad × risk"},
             {"key": "med_risk", "label": "Kostnad med risk", "unit": "kr", "hint": "summan"},
             {"key": "pris", "label": "Pris", "unit": "kr", "hint": "kostnad / (1 − marginal)"},
         ], "exam_area": "kalkyl"},
        {"steps": {"risk": 3360, "med_risk": 87360, "pris": 99272.73},
         "solution": "Risk 84 000 × 0,04 = 3 360 kr. Med risk 87 360 kr. Pris 87 360 / 0,88 = 99 272,73 kr. "
                     "Observera att marginalen räknas på priset, inte på kostnaden."},
        tolerance=0.01, points=30, difficulty=3,
        hints=["Marginalen räknas på priset. Dela med (1 − marginal), multiplicera inte med (1 + marginal)."]),

    # ---- numerisk --------------------------------------------------------------------------------
    _ex("ov-num-timmar", "numerisk", "Hur många timmar?",
        "240 meter rör ska monteras med 0,16 h/m. Hur många timmar tar det?",
        "grund-vvs-kalkyl", "kalkyl-grund", "tid",
        {"unit": "h", "exam_area": "kalkyl"},
        {"value": 38.4, "why": "240 × 0,16 = 38,4 timmar."},
        tolerance=0.01, points=10, difficulty=1),

    _ex("ov-num-klammer", "numerisk", "Hur många klammer?",
        "Ett stråk på 46 meter ska klamras med c/c 2,0 m. Hur många klammer behövs, om första sitter vid start?",
        "mangdning-vs", "isolering-delar", "isolering",
        {"unit": "st", "exam_area": "mangdning"},
        {"value": 24, "why": "46 / 2,0 = 23 mellanrum, plus en klammer vid start = 24 stycken."},
        tolerance=0.001, points=15, difficulty=2,
        hints=["Antal mellanrum är inte samma sak som antal klammer."]),

    # ---- hitta fel -------------------------------------------------------------------------------
    _ex("ov-hitta-fel", "hitta-fel", "Hitta felen i kalkylen",
        "Här är en färdig kalkyl för en tappvattenstam. Fyra rader är fel. Markera dem.",
        "avancerad-kalkyl", "kontroll", "granska",
        {"rows": [
            {"id": "r1", "text": "KV1-S1-32 stigare", "qty": "18,0 m", "price": "112 kr/m", "time": "0,22 h/m"},
            {"id": "r2", "text": "KV1-S1-20 grenar plan 1-3", "qty": "30,0 m", "price": "84 kr/m", "time": "0,18 h/m"},
            {"id": "r3", "text": "VV1-S1-25 stigare", "qty": "18,0 m", "price": "98 kr/m", "time": "0,04 h/m"},
            {"id": "r4", "text": "VVC1-S1-15 stigare", "qty": "18,0 m", "price": "76 kr/m", "time": "0,20 h/m"},
            {"id": "r5", "text": "KV1-S1-20 grenar plan 1-3", "qty": "30,0 m", "price": "84 kr/m", "time": "0,18 h/m"},
            {"id": "r6", "text": "Kulventil DN32", "qty": "3 st", "price": "890 kr/st", "time": "0,8 h/st"},
            {"id": "r7", "text": "Isolering VV DN25", "qty": "18,0 m", "price": "64 kr/m", "time": "0,10 h/m"},
            {"id": "r8", "text": "Isolering KV DN32", "qty": "180,0 m", "price": "58 kr/m", "time": "0,10 h/m"},
        ],
         "names": {"r1": "rad 1, stigaren", "r2": "rad 2, grenarna", "r3": "rad 3, VV-stigaren",
                   "r4": "rad 4, VVC", "r5": "rad 5, grenarna igen", "r6": "rad 6, ventilerna",
                   "r7": "rad 7, isolering VV", "r8": "rad 8, isolering KV"},
         "exam_area": "kontroll"},
        {"picked": ["r3", "r5", "r8"], "pass": 1.0,
         "solution": "Rad 3 har orimligt låg montagetid (0,04 h/m mot 0,22 på samma sorts stigare). Rad 5 är en "
                     "dubblett av rad 2. Rad 8 har tio gånger för stor mängd — 180 m isolering på en 18 m stigare."},
        points=30, difficulty=3,
        hints=["Jämför montagetiderna mellan rader som gör samma sorts arbete.",
               "Läs raderna två gånger — en av dem står där redan."]),

    # ---- kategorisering --------------------------------------------------------------------------
    _ex("ov-kategorisera", "kategorisera", "Sortera komponenterna",
        "Dra varje objekt till rätt kategori.",
        "grund-vvs-kalkyl", "ritningslasning", "symboler",
        {"items": [{"id": "wc", "text": "WC"}, {"id": "tv", "text": "Tvättställ"},
                   {"id": "rad", "text": "Radiator"}, {"id": "kv", "text": "Kulventil"},
                   {"id": "gb", "text": "Golvbrunn"}, {"id": "cp", "text": "Cirkulationspump"},
                   {"id": "bv", "text": "Backventil"}, {"id": "ek", "text": "Expansionskärl"}],
         "buckets": [{"id": "sanitet", "text": "Sanitet"}, {"id": "ventiler", "text": "Ventiler"},
                     {"id": "varme", "text": "Värme"}, {"id": "avlopp", "text": "Avlopp"},
                     {"id": "pumpar", "text": "Pumpar"}],
         "names": {"wc": "WC", "tv": "Tvättställ", "rad": "Radiator", "kv": "Kulventil",
                   "gb": "Golvbrunn", "cp": "Cirkulationspump", "bv": "Backventil", "ek": "Expansionskärl"},
         "exam_area": "teori"},
        {"buckets": {"wc": "sanitet", "tv": "sanitet", "rad": "varme", "kv": "ventiler",
                     "gb": "avlopp", "cp": "pumpar", "bv": "ventiler", "ek": "varme"}},
        points=20, difficulty=2),

    # ---- ritningsquiz ----------------------------------------------------------------------------
    _ex("ov-ritningsquiz", "ritningsquiz", "Läs av värmeritningen",
        "Markera alla radiatorer på bladet. Det är tre stycken.",
        "ritningslasning-vvs", "bladet", "schakt",
        {**VARME.data(), "pick": "symbols", "exam_area": "ritning"},
        {"picked": VARME.ids_of_kind("radiator"), "pass": 1.0,
         "solution": "Tre radiatorer: två i kontoren och en i korridoren."},
        points=15, difficulty=1),

    # ---- helt rum --------------------------------------------------------------------------------
    _ex("ov-rum-badrum", "rum", "Mängda hela badrummet",
        "Mät varje system för sig och fyll i mängden. Tolerans ±4 % per post.",
        "grund-vvs-kalkyl", "praktiskt", "uppgiften",
        {**BAD.data(),
         "poster": [
             {"key": "kv", "label": "Tappkallvatten, totalt", "unit": "m"},
             {"key": "vv", "label": "Tappvarmvatten, totalt", "unit": "m"},
             {"key": "spill", "label": "Spillvatten, totalt", "unit": "m"},
             {"key": "ventiler", "label": "Kulventiler", "unit": "st"},
             {"key": "porslin", "label": "Sanitetsporslin", "unit": "st"},
         ], "exam_area": "mangdning"},
        {"items": {"kv": BAD.metres_where(sys="KV"), "vv": BAD.metres_where(sys="VV"),
                   "spill": BAD.metres_where(sys="S"), "ventiler": BAD.count_of("kulventil"),
                   "porslin": BAD.count_of("wc", "tvattstall")},
         "solution": (f"KV {BAD.metres_where(sys='KV')} m, VV {BAD.metres_where(sys='VV')} m, "
                      f"spillvatten {BAD.metres_where(sys='S')} m, "
                      f"{BAD.count_of('kulventil')} kulventiler och {BAD.count_of('wc', 'tvattstall')} porslin.")},
        tolerance=0.04, points=40, difficulty=3,
        hints=["Ta ett system i taget och markera det du mätt.",
               "Antalsposterna har ingen tolerans — de är rätt eller fel."]),
] + EXERCISES_2


# ================================================================ sluttentan

# Tentan ska mäta hela utbildningen, inte den kurs den hänger under. Med tio kurser i akademin drar den
# frågor ur samtliga: teorin bakom en kalkyl, bladets grammatik, mängdning av både rör och luft, prissättning,
# avtalet arbetet utförs under, och förmågan att se när en färdig kalkyl är fel. Delarnas vikt säger vad som
# kostar mest när det blir fel; section_min_pct att ingen del får lämnas tom och räknas upp av de andra.
EXAM = {
    "slug": "fc-certified-vvs", "title": "Dahl Certified — VVS Kalkyl & Mängdning",
    "course": "grund-vvs-kalkyl", "pass_pct": 80, "section_min_pct": 60, "minutes": 0,
    "sections": [
        {"area": "teori", "title": "Del 1 — Kalkylens grunder och entreprenadformer", "weight": 20, "n": 8},
        {"area": "ritning", "title": "Del 2 — Ritningsläsning", "weight": 20, "n": 8},
        {"area": "mangdning", "title": "Del 3 — Mängdning: rör, luft och mark", "weight": 25, "n": 10},
        {"area": "kalkyl", "title": "Del 4 — Kalkyl, pris och anbud", "weight": 25, "n": 10},
        {"area": "kontroll", "title": "Del 5 — Kalkylkontroll och överlämnande", "weight": 10, "n": 4},
    ],
}


# ================================================================ seedningen

def seed(db: Session) -> dict:
    """Lägg in eller uppdatera allt. Känner igen på slug, så den går att köra om utan att skapa dubbletter."""
    n = {"kurser": 0, "moduler": 0, "lektioner": 0, "ovningar": 0, "fragor": 0, "tentor": 0}

    def upsert(model, slug_field, slug, **fields):
        row = db.query(model).filter(getattr(model, slug_field) == slug).first()
        if not row:
            row = model(**{slug_field: slug}, **fields)
            db.add(row)
            db.flush()
            return row, True
        for k, v in fields.items():
            setattr(row, k, v)
        return row, False

    by_module: dict[tuple[str, str], Module] = {}
    by_lesson: dict[tuple[str, str, str], Lesson] = {}

    for ci, c in enumerate(COURSES):
        course, made = upsert(Course, "slug", c["slug"], title=c["title"], blurb=c["blurb"],
                              level=c["level"], order=c.get("order", ci), hours=c.get("hours", 0.0),
                              published=True)
        n["kurser"] += 1 if made else 0
        for mi, m in enumerate(c["moduler"]):
            mod = db.query(Module).filter(Module.course_id == course.id, Module.slug == m["slug"]).first()
            if not mod:
                mod = Module(course_id=course.id, slug=m["slug"])
                db.add(mod)
                n["moduler"] += 1
            mod.title, mod.blurb, mod.order = m["title"], m["blurb"], mi
            mod.requires, mod.xp, mod.published = m.get("requires", ""), m.get("xp", 100), True
            db.flush()
            by_module[(c["slug"], m["slug"])] = mod

            for li, l in enumerate(m["lektioner"]):
                les = db.query(Lesson).filter(Lesson.module_id == mod.id, Lesson.slug == l["slug"]).first()
                if not les:
                    les = Lesson(module_id=mod.id, slug=l["slug"])
                    db.add(les)
                    n["lektioner"] += 1
                les.title, les.minutes, les.order = l["title"], l["minutes"], li
                les.blocks, les.xp, les.published = l["blocks"], l.get("xp", 10), True
                db.flush()
                by_lesson[(c["slug"], m["slug"], l["slug"])] = les

            for q in m.get("fragor", []):
                row, made = upsert(Question, "slug", q["slug"], module_id=mod.id, kind=q["kind"],
                                   prompt=q["prompt"], options=q.get("options", []), answer=q["answer"],
                                   tolerance=q.get("tolerance", 0.0), explain=q.get("explain", ""),
                                   points=q.get("points", 10), in_exam=q.get("in_exam", False),
                                   area=q.get("area", "teori"), published=True)
                n["fragor"] += 1 if made else 0

    for ei, e in enumerate(EXERCISES):
        mod = by_module.get((e["course"], e["module"]))
        les = by_lesson.get((e["course"], e["module"], e["lesson"]))
        row, made = upsert(
            Exercise, "slug", e["slug"],
            module_id=mod.id if mod else "", lesson_id=les.id if les else "",
            kind=e["kind"], title=e["title"], instructions=e["instructions"],
            difficulty=e.get("difficulty", 1), order=ei, data=e["data"], answer=e["answer"],
            tolerance=e.get("tolerance", 0.0), points=e.get("points", 10), hints=e.get("hints", []),
            max_attempts=e.get("max_attempts", 0), reveal_after=e.get("reveal_after", 3), published=True)
        n["ovningar"] += 1 if made else 0

    course = db.query(Course).filter(Course.slug == EXAM["course"]).first()
    row, made = upsert(Exam, "slug", EXAM["slug"], title=EXAM["title"],
                       course_id=course.id if course else "", sections=EXAM["sections"],
                       pass_pct=EXAM["pass_pct"], section_min_pct=EXAM["section_min_pct"],
                       minutes=EXAM["minutes"], requires_modules=False, published=True)
    n["tentor"] += 1 if made else 0

    db.commit()
    return n
