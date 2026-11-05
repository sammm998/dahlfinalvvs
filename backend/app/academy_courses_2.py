"""Dahl Academy, del två: ventilation, entreprenadjuridik, isolering, injustering och projektledning.

Kurs 1-5 tar den som ska mängda och kalkylera VVS från första blicken på ett blad till ett anbud. De här fem
tar vid där det slutar: luften, avtalet arbetet utförs under, det som byggs in runt röret, det som ska bevisas
innan bygget lämnas över, och det som händer när något ändras efter att anbudet är lämnat.

Samma två regler som i del ett gäller här.

Facit till varje mängdningsövning räknas ur bladets geometri i academy_plans, aldrig ur ett tal skrivet här.
Ändrar någon ett stråk följer svaret med, och en övning kan inte bli fel av att någon glömde uppdatera facit.

Och där ett kontor kan göra på flera sätt står det uttryckligen att det är så. AB 04 och ABT 06 är två avtal
med olika ansvarsfördelning, inte ett rätt och ett fel; en utbildning som låtsas annat lär ut fel sak.
"""
from __future__ import annotations

from .academy_plans import MARK, UC, VENT

P = lambda t: {"k": "p", "t": t}                                            # noqa: E731
UL = lambda xs: {"k": "ul", "t": xs}                                        # noqa: E731
TERMS = lambda xs: {"k": "terms", "t": xs}                                  # noqa: E731
NOTE = lambda t: {"k": "note", "t": t}                                      # noqa: E731
WARN = lambda t: {"k": "warn", "t": t}                                      # noqa: E731
FORMULA = lambda t, w: {"k": "formula", "t": t, "why": w}                   # noqa: E731
PLAN = lambda slug, cap: {"k": "drawing", "plan": slug, "caption": cap}     # noqa: E731
H = lambda t: {"k": "h", "t": t}                                            # noqa: E731


# ================================================================ kurs 6: ventilation

KURS6 = {
    "slug": "ventilation-mangdning", "title": "Ventilation: mängdning och kalkyl", "level": "fortsattning",
    "order": 6, "hours": 7.0,
    "blurb": "Kanal, don, spjäll och aggregat — från bladets kanalstreck till en kalkyl som håller för luft.",
    "moduler": [
        {
            "slug": "kanalen", "title": "Kanalen på bladet", "xp": 150, "requires": "",
            "blurb": "Hur en kanal ritas, vad dimensionen betyder och varför luft mängdas annorlunda än vatten.",
            "lektioner": [
                {"slug": "kanal-ritas", "title": "Så ritas en kanal", "minutes": 7, "blocks": [
                    P("En ventilationskanal ritas som dubbellinje när den är grov nog att synas i skala, och som "
                      "enkel linje när den inte är det. Måttet i beteckningen är innerdiametern på en cirkulär "
                      "kanal och bredd × höjd på en rektangulär."),
                    TERMS([
                        ["Ø400", "Cirkulär kanal, innerdiameter 400 mm. Vanligast i standardsystem."],
                        ["800×400", "Rektangulär kanal, bredd × höjd. Vanlig i aggregatrum och stora stammar."],
                        ["TL / FL", "Tilluft respektive frånluft. Två separata system som ofta går parallellt."],
                        ["ÖL / AL", "Överluft och avluft. Överluft går mellan rum, avluft ut ur byggnaden."],
                    ]),
                    NOTE("Två kanaler ritade bredvid varandra är nästan alltid TL och FL, inte en kanal ritad med "
                         "två linjer. Skillnaden syns i beteckningen — varje kanal har sin egen."),
                    PLAN("vent-1", "Tilluft och frånluft med don, spjäll och brandspjäll."),
                ]},
                {"slug": "kanal-mangd", "title": "Vad som mängdas på en kanal", "minutes": 8, "blocks": [
                    P("Kanal mängdas i meter per dimension, precis som rör. Det som skiljer är att kanalens "
                      "delar är en mycket större del av kostnaden än rörets — böjar, T-stycken, dimensionsbyten "
                      "och anslutningar till don kan vara halva kanalposten."),
                    UL([
                        "Rak kanal, meter per dimension.",
                        "Böjar, per styck och dimension. Räkna dem; de ligger inte i metertalet.",
                        "T-stycken och byxor, per styck.",
                        "Dimensionsbyten (reduceringar), per styck.",
                        "Don, spjäll, brandspjäll, ljuddämpare, per styck.",
                    ]),
                    WARN("Ett vanligt kalkylfel är att mängda kanalmeter noggrant och sedan slänga in delarna "
                         "som ett påslag. På ett kontorsplan med många don blir påslaget alltid för lågt."),
                ]},
                {"slug": "kanal-isolering", "title": "Isolerad, oisolerad och brandisolerad", "minutes": 6, "blocks": [
                    P("Kanal isoleras av tre olika skäl, och de ger tre olika poster i kalkylen."),
                    TERMS([
                        ["Kondensisolering", "Kall kanal i varmt utrymme. Hindrar att det droppar."],
                        ["Värmeisolering", "Håller temperaturen på luften mellan aggregat och don."],
                        ["Brandisolering", "Gör kanalen till en brandcellsskiljande konstruktion, EI30/EI60."],
                    ]),
                    NOTE("Brandisolering och brandspjäll är två olika lösningar på samma krav. Vilken som gäller "
                         "står i brandskyddsbeskrivningen, inte på ventilationsbladet."),
                ]},
            ],
            "fragor": [
                {"slug": "q-vent-1", "kind": "single", "area": "ritning", "points": 10, "in_exam": True,
                 "prompt": "Vad betyder beteckningen 800×400 på en kanal?",
                 "options": ["Längd och bredd på systemet", "Bredd och höjd på en rektangulär kanal",
                             "Två parallella kanaler Ø800 och Ø400", "Luftflöde i l/s"],
                 "answer": {"index": 1},
                 "explain": "Rektangulär kanal anges bredd × höjd. Cirkulär anges med Ø och innerdiameter."},
                {"slug": "q-vent-2", "kind": "bool", "area": "mangdning", "points": 10, "in_exam": True,
                 "prompt": "Kanalböjar ligger med i metertalet för rak kanal.", "options": [],
                 "answer": {"value": False},
                 "explain": "Böjar räknas per styck och dimension. De är en egen post och ofta en stor sådan."},
                {"slug": "q-vent-3", "kind": "single", "area": "ritning", "points": 10, "in_exam": True,
                 "prompt": "Två kanaler ritade parallellt på ett plan är oftast:",
                 "options": ["En kanal ritad med dubbellinje", "Tilluft och frånluft",
                             "Kanal och dess isolering", "Ett ritfel"],
                 "answer": {"index": 1},
                 "explain": "TL och FL följs åt genom byggnaden. Varje kanal har sin egen beteckning — det är så du ser skillnaden."},
                {"slug": "q-vent-4", "kind": "single", "area": "kalkyl", "points": 10, "in_exam": True,
                 "prompt": "Varför blir ett schablonpåslag för kanaldelar ofta för lågt på ett kontorsplan?",
                 "options": ["Kanalen är billigare där", "Många don ger många avstick, böjar och reduceringar",
                             "Kontor har kortare kanaler", "Påslaget räknas på fel dimension"],
                 "answer": {"index": 1},
                 "explain": "Delarna följer antalet don, inte antalet meter. Ett plan med tätt mellan donen har fler delar per meter."},
            ],
        },
        {
            "slug": "don-och-flode", "title": "Don, spjäll och flöde", "xp": 150, "requires": "kanalen",
            "blurb": "Vad som sitter i kanalen, vad det kostar och vad flödet säger om dimensionen.",
            "lektioner": [
                {"slug": "donen", "title": "Donen och deras anslutning", "minutes": 6, "blocks": [
                    P("Ett don är slutpunkten: där luften lämnar eller går in i kanalsystemet. Donet i sig är en "
                      "produkt med ett pris, men anslutningen till det — avsticket, flexslangen, anslutningslådan "
                      "— är minst lika mycket arbete."),
                    TERMS([
                        ["Tilluftsdon", "Blåser in. Ofta med spridningsmönster som styr komforten."],
                        ["Frånluftsdon", "Suger ut. Enklare konstruktion, billigare."],
                        ["Överluftsdon", "Sitter i vägg eller dörr och släpper luft mellan rum."],
                        ["Anslutningslåda", "Låda bakom donet som fördelar luften. Egen post, egen montagetid."],
                    ]),
                ]},
                {"slug": "spjallen", "title": "Injusteringsspjäll och brandspjäll", "minutes": 7, "blocks": [
                    P("Två sorters spjäll, två helt olika kostnader och två helt olika skäl."),
                    TERMS([
                        ["Injusteringsspjäll", "Strypning som ger rätt flöde i varje gren. Billigt, monteras i kanal."],
                        ["Brandspjäll", "Stänger vid brand. Dyrt, kräver el, kräver funktionsprov och märkning."],
                    ]),
                    WARN("Ett brandspjäll kostar ofta mer än tio injusteringsspjäll, och det kräver dessutom en "
                         "elanslutning som kanske inte ligger i ditt kontrakt. Räkna dem alltid för sig."),
                    PLAN("vent-1", "Brandspjällen sitter i väggarna mellan brandcellerna."),
                ]},
                {"slug": "flodet", "title": "Vad flödet säger om dimensionen", "minutes": 6, "blocks": [
                    P("Luftflödet anges i l/s och står ofta vid donet. Det är inte en mängd du ska prissätta, "
                      "men det är en kontroll: en Ø100-kanal som påstås bära 200 l/s är antingen felritad eller "
                      "så har du läst fel kanal."),
                    FORMULA("v = q / A", "Hastigheten är flödet delat med kanalarean. Över ca 5 m/s i en gren "
                                          "börjar det låta, och då brukar ritningen ha en grövre kanal än du tror."),
                    NOTE("Den här kontrollen hittar inte fel i kalkylen. Den hittar fel i din läsning av bladet, "
                         "och det är oftare det som är problemet."),
                ]},
            ],
            "fragor": [
                {"slug": "q-don-1", "kind": "single", "area": "kalkyl", "points": 10, "in_exam": True,
                 "prompt": "Varför ska brandspjäll alltid räknas som egen post?",
                 "options": ["De är fler än injusteringsspjällen", "De är mycket dyrare och kräver el och funktionsprov",
                             "De sitter alltid i tak", "De ingår i kanalpriset"],
                 "answer": {"index": 1},
                 "explain": "Ett brandspjäll kan kosta mer än tio injusteringsspjäll och drar med sig el och provning."},
                {"slug": "q-don-2", "kind": "bool", "area": "mangdning", "points": 10, "in_exam": False,
                 "prompt": "Anslutningslådan bakom ett don ingår i donets pris.", "options": [],
                 "answer": {"value": False},
                 "explain": "Lådan är en egen produkt med egen montagetid. Den glöms ofta och syns inte i efterhand."},
                {"slug": "q-don-3", "kind": "numeric", "area": "kontroll", "points": 10, "in_exam": True,
                 "prompt": "En kanal Ø200 har arean 0,0314 m². Vid 100 l/s — vilken hastighet i m/s? Svara med en decimal.",
                 "options": [], "answer": {"value": 3.2}, "tolerance": 0.15,
                 "explain": "0,100 m³/s delat med 0,0314 m² ≈ 3,2 m/s — normalt för en gren."},
            ],
        },
        {
            "slug": "aggregat", "title": "Aggregat och aggregatrum", "xp": 150, "requires": "don-och-flode",
            "blurb": "Den dyraste posten på bladet, och vad som hör till den.",
            "lektioner": [
                {"slug": "vad-ingar", "title": "Vad som hör till aggregatet", "minutes": 7, "blocks": [
                    P("Aggregatet är en produkt med ett pris ur leverantörens offert. Det som gör posten dyr är "
                      "allt runt omkring, och det ligger sällan i offerten."),
                    UL([
                        "Inlyft och transport — ofta med kran, ibland innan taket är på.",
                        "Fundament och vibrationsdämpning.",
                        "Kanalanslutningar med ljuddämpare och flexibla anslutningar.",
                        "Kondensavlopp med vattenlås till golvbrunn.",
                        "Värme- och kylbatteriets rörinkoppling — det är VS-arbete i ett ventilationsrum.",
                        "El och styr, om det ligger i ditt kontrakt.",
                    ]),
                    WARN("Batteriinkopplingen är den vanligaste tvisten i gränssnittet mellan luft och rör. Läs "
                         "vem som har den innan du räknar bort den."),
                    PLAN("vent-1", "Aggregatet står nere till vänster, där båda huvudkanalerna börjar."),
                ]},
                {"slug": "aggregatrummet", "title": "Mängdning i ett aggregatrum", "minutes": 6, "blocks": [
                    P("Ett aggregatrum har korta kanallängder och väldigt många delar. Mängda per meter där och "
                      "du får fel i storleksordningen. Räkna delarna styckvis och kanalen som det lilla den är."),
                    NOTE("Samma sak gäller en undercentral på rörsidan: där ligger kostnaden i komponenterna, "
                         "inte i metrarna."),
                ]},
            ],
            "fragor": [
                {"slug": "q-agg-1", "kind": "multi", "area": "kalkyl", "points": 15, "in_exam": True,
                 "prompt": "Vilka poster hör till aggregatet men ligger sällan i leverantörens offert?",
                 "options": ["Inlyft med kran", "Aggregatets fläktmotor", "Kondensavlopp med vattenlås",
                             "Fundament och vibrationsdämpning", "Aggregatets filter"],
                 "answer": {"indices": [0, 2, 3]},
                 "explain": "Motor och filter är delar av produkten. Inlyft, avlopp och fundament är ditt arbete."},
                {"slug": "q-agg-2", "kind": "single", "area": "mangdning", "points": 10, "in_exam": True,
                 "prompt": "Varför blir mängdning per meter fel i ett aggregatrum?",
                 "options": ["Kanalerna är för grova", "Kostnaden ligger i delarna, inte i metrarna",
                             "Rummet är för litet att mäta i", "Skalan är en annan"],
                 "answer": {"index": 1},
                 "explain": "Korta längder, mycket delar. Samma sak gäller en undercentral på rörsidan."},
            ],
        },
    ],
}


# ================================================================ kurs 7: AB 04 och ABT 06

KURS7 = {
    "slug": "ab04-abt06", "title": "Entreprenadjuridik: AB 04 och ABT 06", "level": "fortsattning",
    "order": 7, "hours": 8.0,
    "blurb": "Vilket avtal som gäller, vem som bär ansvaret för vad, och hur det syns i kalkylen.",
    "moduler": [
        {
            "slug": "tva-avtal", "title": "Två avtal, två ansvarsfördelningar", "xp": 200, "requires": "",
            "blurb": "Skillnaden mellan utförandeentreprenad och totalentreprenad, i praktiken.",
            "lektioner": [
                {"slug": "vem-projekterar", "title": "Vem som har projekterat", "minutes": 8, "blocks": [
                    P("Hela skillnaden mellan AB 04 och ABT 06 går att sammanfatta i en fråga: vem ritade? "
                      "Svaret avgör vem som bär felet när ritningen är fel."),
                    TERMS([
                        ["AB 04 — utförandeentreprenad", "Beställaren projekterar. Du utför det som är ritat. "
                                                          "Är ritningen fel är det beställarens fel, och rättelsen är ÄTA."],
                        ["ABT 06 — totalentreprenad", "Du projekterar och utför. Du svarar för att lösningen "
                                                       "uppfyller den funktion som är beställd."],
                    ]),
                    NOTE("Det finns mellanformer, och de är vanliga: en styrd totalentreprenad där beställaren "
                         "ritat det mesta men du svarar för funktionen. Vad som gäller står i de administrativa "
                         "föreskrifterna (AF), inte i avtalets namn."),
                ]},
                {"slug": "vad-det-kostar", "title": "Vad skillnaden kostar i kalkylen", "minutes": 8, "blocks": [
                    P("Två anbud på samma byggnad, ett under AB 04 och ett under ABT 06, ska inte vara lika "
                      "stora. Under ABT 06 köper beställaren en funktion, och du bär risken för hur mycket "
                      "material det krävs för att nå den."),
                    UL([
                        "AB 04: mängden kommer ur handlingen. Blir det mer är det ÄTA.",
                        "ABT 06: mängden kommer ur din egen projektering. Blir det mer är det ditt.",
                        "ABT 06 kräver därför ett riskpåslag som AB 04 inte kräver — och projekteringskostnad.",
                        "AB 04 kräver noggrannare granskning av handlingen: det du missar i den blir inte ÄTA.",
                    ]),
                    WARN("Att lämna ett ABT-anbud räknat som ett AB-anbud är ett av de dyraste misstagen som "
                         "finns i branschen. Hela mängdrisken ligger då hos dig, oprisad."),
                ]},
                {"slug": "funktionsansvar", "title": "Funktionsansvar i praktiken", "minutes": 7, "blocks": [
                    P("Under ABT 06 räcker det inte att installationen är utförd fackmässigt. Den ska fungera "
                      "som beställaren beskrivit — och beskrivningen är ofta en mening i ett rumsfunktionsprogram."),
                    TERMS([
                        ['"Tappvarmvatten 55 °C vid tappställe"', "Din sak att dimensionera VVC så det uppnås."],
                        ['"Ljudnivå högst 30 dB(A)"', "Din sak att välja don, ljuddämpare och hastigheter."],
                        ['"Radiatorer ska klara -18 °C ute"', "Din sak att dimensionera efter det."],
                    ]),
                    P("Varje sådan mening är en dimensioneringsuppgift, och den ska prissättas som projektering "
                      "plus den marginal du behöver för att lösningen kan bli dyrare än du tror."),
                ]},
            ],
            "fragor": [
                {"slug": "q-ab-1", "kind": "single", "area": "teori", "points": 10, "in_exam": True,
                 "prompt": "Vad är den avgörande skillnaden mellan AB 04 och ABT 06?",
                 "options": ["Vilken bransch de gäller", "Vem som har projekterat och därmed bär felet i handlingen",
                             "Hur lång garantitiden är", "Om moms ingår"],
                 "answer": {"index": 1},
                 "explain": "AB 04: beställaren projekterar. ABT 06: entreprenören projekterar och svarar för funktionen."},
                {"slug": "q-ab-2", "kind": "bool", "area": "teori", "points": 10, "in_exam": True,
                 "prompt": "Under ABT 06 blir en ökad mängd normalt ett ÄTA-arbete.", "options": [],
                 "answer": {"value": False},
                 "explain": "Under ABT 06 kommer mängden ur din egen projektering. Blir det mer är det ditt — det är därför riskpåslaget finns."},
                {"slug": "q-ab-3", "kind": "single", "area": "kalkyl", "points": 10, "in_exam": True,
                 "prompt": "Vad krävs i ett ABT 06-anbud som inte krävs i ett AB 04-anbud?",
                 "options": ["Lägre påslag", "Projekteringskostnad och riskpåslag för mängden",
                             "Fler leverantörsofferter", "Kortare tidplan"],
                 "answer": {"index": 1},
                 "explain": "Du köper både ritandet och risken för att din lösning kräver mer material än du trodde."},
                {"slug": "q-ab-4", "kind": "single", "area": "teori", "points": 10, "in_exam": True,
                 "prompt": "Var står det vilken ansvarsfördelning som faktiskt gäller i ett projekt?",
                 "options": ["I avtalets namn", "I de administrativa föreskrifterna (AF)",
                             "På ritningens namnruta", "I mängdförteckningen"],
                 "answer": {"index": 1},
                 "explain": "Mellanformer är vanliga. AF säger vad som gäller; namnet på avtalet räcker inte."},
            ],
        },
        {
            "slug": "ata", "title": "ÄTA-arbeten", "xp": 200, "requires": "tva-avtal",
            "blurb": "Ändring, tillägg och avgående — vad som är ÄTA, och hur det ska hanteras för att bli betalt.",
            "lektioner": [
                {"slug": "vad-ar-ata", "title": "Vad ÄTA faktiskt betyder", "minutes": 7, "blocks": [
                    P("ÄTA står för Ändrings-, Tilläggs- och Avgående arbeten. Det är arbete som skiljer sig "
                      "från kontraktsarbetet, och det är den vanligaste orsaken till tvist i en entreprenad."),
                    TERMS([
                        ["Ändring", "Samma sak, utförd på annat sätt än kontraktet säger."],
                        ["Tillägg", "Något som inte fanns i kontraktet alls."],
                        ["Avgående", "Något i kontraktet som utgår. Ger avdrag — och det ska också räknas."],
                    ]),
                    NOTE("Avgående arbeten glöms nästan alltid av entreprenören och nästan aldrig av beställaren. "
                         "Räkna dem själv, innan någon annan gör det åt dig."),
                ]},
                {"slug": "bestallning", "title": "Beställning och underrättelse", "minutes": 8, "blocks": [
                    P("Ett ÄTA-arbete ska vara beställt för att betalas. Både AB 04 och ABT 06 ställer krav på "
                      "form och på tid, och det är där de flesta ÄTA-krav faller."),
                    UL([
                        "En beställning ska vara skriftlig. Ett samtal på bygget är inte en beställning.",
                        "Upptäcker du något som gör kontraktsarbetet dyrare ska du underrätta beställaren utan dröjsmål.",
                        "Utför du ett ÄTA-arbete utan beställning har du gjort det på egen risk.",
                        "Kostnaden ska specificeras: material, tid, påslag — inte ett klumpbelopp.",
                    ]),
                    WARN("Det vanligaste skälet till att ett berättigat ÄTA-krav inte betalas är inte att det var "
                         "fel. Det är att det kom för sent eller utan underlag."),
                ]},
                {"slug": "prissattning", "title": "Att prissätta en ÄTA", "minutes": 7, "blocks": [
                    P("En ÄTA prissätts som en liten kalkyl, med samma delar som den stora: mängd, pris, tid. "
                      "Skillnaden är att omkostnaderna sällan blir mindre bara för att jobbet är litet."),
                    FORMULA("ÄTA = material + tid + påslag + störning",
                            "Störningen — att arbetet bryter en planerad ordning — är verklig kostnad och den "
                            "posten är den som oftast saknas."),
                    NOTE("Finns à-priser i kontraktet gäller de. Läs dem innan du räknar fritt; ett à-pris du "
                         "glömt kan vara lägre än din kalkyl."),
                ]},
            ],
            "fragor": [
                {"slug": "q-ata-1", "kind": "single", "area": "teori", "points": 10, "in_exam": True,
                 "prompt": "Vad står A:et i ÄTA för?",
                 "options": ["Ackord", "Avgående arbeten", "Avtal", "Avstämning"],
                 "answer": {"index": 1},
                 "explain": "Ändrings-, Tilläggs- och Avgående arbeten. Avgående ger avdrag och räknas också."},
                {"slug": "q-ata-2", "kind": "single", "area": "teori", "points": 10, "in_exam": True,
                 "prompt": "Varför faller berättigade ÄTA-krav oftast?",
                 "options": ["De är för dyra", "De kom för sent eller utan underlag",
                             "Beställaren saknar pengar", "De rör fel entreprenad"],
                 "answer": {"index": 1},
                 "explain": "Form och tid är krav i både AB 04 och ABT 06. Ett muntligt besked på bygget bär inte."},
                {"slug": "q-ata-3", "kind": "bool", "area": "kalkyl", "points": 10, "in_exam": False,
                 "prompt": "Ett avgående arbete ska räknas och redovisas precis som ett tilläggsarbete.", "options": [],
                 "answer": {"value": True},
                 "explain": "Det ger avdrag. Räknar du det inte själv gör beställaren det, och sällan till din fördel."},
                {"slug": "q-ata-4", "kind": "multi", "area": "kalkyl", "points": 15, "in_exam": True,
                 "prompt": "Vad ingår i en korrekt prissatt ÄTA?",
                 "options": ["Material", "Tid", "Påslag", "Störning av planerad ordning", "Beställarens vinst"],
                 "answer": {"indices": [0, 1, 2, 3]},
                 "explain": "Störningsposten är den som oftast saknas — ett litet jobb som bryter en ordning kostar mer än sitt material."},
            ],
        },
        {
            "slug": "tid-och-fel", "title": "Tid, besiktning och ansvar efteråt", "xp": 200, "requires": "ata",
            "blurb": "Vad som händer vid förseningar, vid besiktning och under garantitiden.",
            "lektioner": [
                {"slug": "tiden", "title": "Tidplan, försening och vite", "minutes": 7, "blocks": [
                    P("Kontraktstiden är ett åtagande med pengar bakom sig. Blir entreprenaden försenad av något "
                      "du svarar för löper vite; blir den försenad av något beställaren svarar för har du rätt "
                      "till tidsförlängning — men du måste begära den."),
                    UL([
                        "Vite räknas oftast per påbörjad vecka på kontraktssumman.",
                        "Rätt till tidsförlängning kräver att du underrättar, i tid.",
                        "Hinder du inte underrättar om blir i praktiken ditt.",
                    ]),
                ]},
                {"slug": "besiktning", "title": "Besiktningen", "minutes": 7, "blocks": [
                    P("Slutbesiktningen avgör om entreprenaden är godkänd, och den startar garantitiden. Det som "
                      "antecknas som fel ska avhjälpas; det som inte antecknas är i regel inte fel."),
                    TERMS([
                        ["Förbesiktning", "En del besiktigas i förväg, ofta det som byggs in."],
                        ["Slutbesiktning", "Hela entreprenaden. Godkännande startar garantitiden."],
                        ["Garantibesiktning", "Efter garantitiden, normalt fem år för entreprenaden."],
                        ["Efterbesiktning", "Kontroll av att antecknade fel är avhjälpta."],
                    ]),
                    NOTE("Det som byggs in — rör i vägg, i bjälklag, under mark — måste besiktigas eller "
                         "dokumenteras innan det täcks. Efteråt går det inte att visa, och då är det ditt."),
                ]},
                {"slug": "garantin", "title": "Garantitid och ansvarstid", "minutes": 6, "blocks": [
                    P("Två perioder som blandas ihop: garantitiden och ansvarstiden."),
                    TERMS([
                        ["Garantitid", "Normalt fem år för entreprenaden, två för det beställaren föreskrivit. "
                                       "Fel under den tiden antas vara ditt om du inte visar annat."],
                        ["Ansvarstid", "Tio år. Efter garantitiden svarar du bara för väsentliga fel du orsakat "
                                       "genom vårdslöshet — och nu är det beställaren som ska visa det."],
                    ]),
                    P("Bevisbördan vänder alltså när garantitiden går ut. Det är hela skillnaden mellan dem."),
                ]},
            ],
            "fragor": [
                {"slug": "q-tid-1", "kind": "single", "area": "teori", "points": 10, "in_exam": True,
                 "prompt": "Vad är den viktigaste skillnaden mellan garantitid och ansvarstid?",
                 "options": ["Garantitiden är längre", "Bevisbördan vänder när garantitiden går ut",
                             "Ansvarstiden gäller bara material", "De gäller olika entreprenörer"],
                 "answer": {"index": 1},
                 "explain": "Under garantitiden antas felet vara ditt. Efteråt ska beställaren visa att det är det."},
                {"slug": "q-tid-2", "kind": "bool", "area": "teori", "points": 10, "in_exam": True,
                 "prompt": "Rör som byggs in i vägg bör besiktigas eller dokumenteras innan de täcks.", "options": [],
                 "answer": {"value": True},
                 "explain": "Efteråt går det inte att visa hur det var utfört, och då blir tvisten din."},
                {"slug": "q-tid-3", "kind": "single", "area": "teori", "points": 10, "in_exam": False,
                 "prompt": "Vad krävs för att få tidsförlängning för ett hinder beställaren svarar för?",
                 "options": ["Ingenting, den ges automatiskt", "Att du underrättar beställaren i tid",
                             "Att besiktningsmannen noterar det", "Att vitet redan löpt"],
                 "answer": {"index": 1},
                 "explain": "Ett hinder du inte underrättar om blir i praktiken ditt, hur berättigat det än var."},
            ],
        },
    ],
}


# ================================================================ kurs 8: isolering och brandtätning

KURS8 = {
    "slug": "isolering-brandtatning", "title": "Isolering, brandtätning och genomföringar",
    "level": "fortsattning", "order": 8, "hours": 5.0,
    "blurb": "Det som byggs runt röret: isolering per meter, brandtätning per hål, och vem som äger hålet.",
    "moduler": [
        {
            "slug": "isoleringen", "title": "Isolering", "xp": 150, "requires": "",
            "blurb": "Fyra skäl att isolera, fyra olika poster.",
            "lektioner": [
                {"slug": "fyra-skal", "title": "Fyra skäl att isolera", "minutes": 7, "blocks": [
                    TERMS([
                        ["Värmeisolering", "VS- och VV-ledningar. Håller energin i röret. Tjocklek ur beskrivningen."],
                        ["Kondensisolering", "KV och kyla. Hindrar att det droppar på det som står under."],
                        ["Brandisolering", "Rör genom brandcellsgräns, där brandtätning inte räcker."],
                        ["Ljudisolering", "Spillvattenstammar i lägenhet. Ofta ett eget fabrikat, ofta dyrt."],
                    ]),
                    NOTE("Samma rör kan behöva två av dem på olika sträckor. Isoleringen mängdas därför per "
                         "sträcka och sort, inte per rör."),
                ]},
                {"slug": "isolering-mangd", "title": "Hur isolering mängdas", "minutes": 7, "blocks": [
                    P("Isolering mängdas i meter per rördimension och isolertjocklek. Böjar, ventiler och "
                      "flänsar isoleras också, och de räknas per styck — en isolerad ventil tar ofta lika lång "
                      "tid som fem meter rak isolering."),
                    UL([
                        "Rak isolering: meter per dimension och tjocklek.",
                        "Böjar: styck. Ofta prefabricerade, ibland gjorda på plats.",
                        "Ventilkåpor: styck. Ska gå att öppna, så de kostar mer än de ser ut att göra.",
                        "Ytbeklädnad: plåt, folie eller ingen alls. Stor prisskillnad.",
                    ]),
                    WARN("Isolering som mängdas som en procentsats av rörposten blir alltid fel på ett blad med "
                         "många ventiler, och alltid för lågt."),
                ]},
            ],
            "fragor": [
                {"slug": "q-iso-1", "kind": "single", "area": "mangdning", "points": 10, "in_exam": True,
                 "prompt": "Varför mängdas isolering per sträcka och inte per rör?",
                 "options": ["Rören är olika långa", "Samma rör kan behöva olika isolering på olika sträckor",
                             "Isolering säljs per sträcka", "Det står så i AMA"],
                 "answer": {"index": 1},
                 "explain": "Ett rör kan gå värmeisolerat genom ett schakt och brandisolerat genom en vägg."},
                {"slug": "q-iso-2", "kind": "bool", "area": "kalkyl", "points": 10, "in_exam": True,
                 "prompt": "En isolerad ventil kan ta lika lång tid som flera meter rak isolering.", "options": [],
                 "answer": {"value": True},
                 "explain": "Ventilkåpan ska dessutom gå att öppna. Räkna dem styckvis."},
                {"slug": "q-iso-3", "kind": "single", "area": "teori", "points": 10, "in_exam": False,
                 "prompt": "Vilket skäl att isolera gäller en kallvattenledning i ett varmt schakt?",
                 "options": ["Värmeisolering", "Kondensisolering", "Brandisolering", "Ljudisolering"],
                 "answer": {"index": 1},
                 "explain": "Kallt rör i varm luft ger kondens, och kondensen droppar på det som står under."},
            ],
        },
        {
            "slug": "brandtatning", "title": "Brandtätning och genomföringar", "xp": 150, "requires": "isoleringen",
            "blurb": "Varje hål genom en brandcellsgräns är en post — och en ansvarsfråga.",
            "lektioner": [
                {"slug": "hallet", "title": "Hålet, tätningen och ansvaret", "minutes": 8, "blocks": [
                    P("Ett rör som går genom en brandcellsskiljande vägg eller ett bjälklag måste tätas så att "
                      "väggens brandklass återställs. Det är en produkt, ett montage och en dokumenterad kontroll."),
                    UL([
                        "Brandtätning räknas per genomföring, inte per meter rör.",
                        "Priset beror på rörets dimension, väggens klass och materialet i röret.",
                        "Plaströr kräver brandmanschett; stålrör räcker det ofta med massa runt.",
                        "Varje tätning ska märkas och dokumenteras — det är en egen arbetsinsats.",
                    ]),
                    WARN("Vem som borrar hålet och vem som tätar det är en av de vanligaste gränssnittsfrågorna "
                         "i en entreprenad. Står det inte i AF står det ingenstans, och då får du räkna med att "
                         "det är ditt."),
                ]},
                {"slug": "rakna-hal", "title": "Att räkna hålen ur ritningen", "minutes": 7, "blocks": [
                    P("Antalet genomföringar går att räkna ur planen: varje gång ett rörstråk korsar en vägg som "
                      "är brandcellsgräns är det en genomföring. Vilka väggar det är står i brandskyddsplanen, "
                      "inte på VVS-bladet."),
                    NOTE("Ett schakt genom alla plan ger en genomföring per bjälklag, per rör. En stam med tre "
                         "rör genom sex plan är arton tätningar — och ingen av dem syns på planritningen."),
                    PLAN("stam-1", "Tre stigare genom tre plan: nio bjälklagsgenomföringar."),
                ]},
            ],
            "fragor": [
                {"slug": "q-bt-1", "kind": "single", "area": "mangdning", "points": 10, "in_exam": True,
                 "prompt": "Hur räknas brandtätning?",
                 "options": ["Per meter rör", "Per genomföring", "Per kvadratmeter vägg", "Som påslag på röret"],
                 "answer": {"index": 1},
                 "explain": "Varje hål genom en brandcellsgräns är en post, med produkt, montage och dokumentation."},
                {"slug": "q-bt-2", "kind": "numeric", "area": "mangdning", "points": 15, "in_exam": True,
                 "prompt": "En stam med tre rör går genom sex bjälklag. Hur många genomföringar?",
                 "options": [], "answer": {"value": 18}, "tolerance": 0,
                 "explain": "Tre rör × sex bjälklag. Ingen av dem syns på planritningen — de måste räknas ur sektionen eller ur antalet plan."},
                {"slug": "q-bt-3", "kind": "single", "area": "teori", "points": 10, "in_exam": True,
                 "prompt": "Var står det vilka väggar som är brandcellsgräns?",
                 "options": ["På VVS-bladet", "I brandskyddsbeskrivningen eller brandskyddsplanen",
                             "I mängdförteckningen", "I leverantörens katalog"],
                 "answer": {"index": 1},
                 "explain": "VVS-bladet visar röret. Vilken vägg som är en gräns är en annan handling."},
            ],
        },
    ],
}


# ================================================================ kurs 9: injustering och överlämnande

KURS9 = {
    "slug": "injustering-overlamnande", "title": "Injustering, provning och överlämnande",
    "level": "avancerad", "order": 9, "hours": 5.0,
    "blurb": "Det som ska bevisas innan bygget lämnas över — och vad det kostar att bevisa det.",
    "moduler": [
        {
            "slug": "provning", "title": "Provning och täthet", "xp": 150, "requires": "",
            "blurb": "Tryckprov, spolning och desinfektion: arbete som måste rymmas i tidplanen.",
            "lektioner": [
                {"slug": "tryckprov", "title": "Tryckprovning", "minutes": 7, "blocks": [
                    P("Varje tryckledning ska tryckprovas innan den byggs in. Provet är enkelt i sig; det som "
                      "kostar är att systemet måste vara färdigt, avstängt i sektioner, och att någon står där."),
                    UL([
                        "Provtryck och provtid står i beskrivningen eller i AMA.",
                        "Provet dokumenteras med protokoll — det är en handling, inte en anteckning.",
                        "Ett underkänt prov betyder felsökning, och felsökningstid är sällan kalkylerad.",
                    ]),
                ]},
                {"slug": "spolning", "title": "Spolning och desinfektion", "minutes": 6, "blocks": [
                    P("Tappvattensystem spolas rent och desinficeras innan de tas i bruk. Vattnet ska ut "
                      "någonstans, och på ett bygge utan färdigt avlopp är det en egen logistikfråga."),
                    NOTE("Legionellaprovtagning kan krävas i beskrivningen. Det är en extern kostnad med en "
                         "ledtid som kan ligga på den kritiska linjen."),
                ]},
            ],
            "fragor": [
                {"slug": "q-prov-1", "kind": "single", "area": "kalkyl", "points": 10, "in_exam": True,
                 "prompt": "Vad kostar mest i en tryckprovning?",
                 "options": ["Pumpen", "Att systemet måste vara färdigt och att någon står där under provtiden",
                             "Vattnet", "Protokollet"],
                 "answer": {"index": 1},
                 "explain": "Provet i sig är enkelt. Tiden, sektioneringen och risken för underkänt prov är kostnaden."},
                {"slug": "q-prov-2", "kind": "bool", "area": "kontroll", "points": 10, "in_exam": True,
                 "prompt": "Ett tryckprov ska dokumenteras med protokoll.", "options": [],
                 "answer": {"value": True},
                 "explain": "Det är en handling som lämnas över. En anteckning i telefonen är inte ett protokoll."},
            ],
        },
        {
            "slug": "injusteringen", "title": "Injustering", "xp": 150, "requires": "provning",
            "blurb": "Att få rätt flöde i varje gren — och att kunna visa att du fick det.",
            "lektioner": [
                {"slug": "vatten", "title": "Injustering av vattensystem", "minutes": 8, "blocks": [
                    P("Ett värmesystem med rätt total effekt men fel fördelning värmer ett rum för mycket och "
                      "ett för lite. Injusteringen fördelar flödet, ventil för ventil, efter ett protokoll."),
                    UL([
                        "Varje injusteringsventil ställs in mot ett beräknat flöde.",
                        "Mätningen görs med instrument över ventilen.",
                        "Resultatet skrivs i ett protokoll per ventil — det är leveransen.",
                        "Tiden är ungefär proportionell mot antalet ventiler, inte mot antalet meter rör.",
                    ]),
                    PLAN("varme-1", "Två injusteringsventiler i kretsen, en på varje radiatorretur."),
                    WARN("Injustering kalkylerad som en klumpsumma blir alltid fel på ett stort system. Räkna "
                         "ventiler, inte kvadratmeter."),
                ]},
                {"slug": "luft", "title": "Injustering av luftsystem", "minutes": 7, "blocks": [
                    P("Samma princip för luft: varje don ska ge sitt projekterade flöde, mätt och protokollfört. "
                      "Skillnaden är att luftsystem påverkas av allt annat som händer i huset — en stängd dörr, "
                      "ett igensatt filter, ett spjäll någon rört."),
                    NOTE("Därför görs luftinjustering sent, och därför hamnar den ofta i tidsklämman. Lägg den i "
                         "tidplanen där den hör hemma, inte där det råkar finnas plats."),
                    PLAN("vent-1", "Injusteringsspjäll på tilluftsgrenarna, ett per gren."),
                ]},
            ],
            "fragor": [
                {"slug": "q-inj-1", "kind": "single", "area": "kalkyl", "points": 10, "in_exam": True,
                 "prompt": "Vad är injusteringstiden ungefär proportionell mot?",
                 "options": ["Antal meter rör", "Antal ventiler eller don", "Byggnadens yta", "Antal plan"],
                 "answer": {"index": 1},
                 "explain": "Varje ventil eller don ställs in och mäts var för sig. Metrarna spelar ingen roll."},
                {"slug": "q-inj-2", "kind": "single", "area": "teori", "points": 10, "in_exam": True,
                 "prompt": "Varför hamnar luftinjustering ofta i tidsklämman?",
                 "options": ["Den kräver specialverktyg", "Den måste göras sent, när huset i övrigt är färdigt",
                             "Den kräver två personer", "Den kan bara göras på sommaren"],
                 "answer": {"index": 1},
                 "explain": "Luftsystemet påverkas av allt annat i huset, så mätningen blir giltig först på slutet."},
                {"slug": "q-inj-3", "kind": "bool", "area": "kontroll", "points": 10, "in_exam": False,
                 "prompt": "Ett värmesystem med rätt total effekt är rätt injusterat.", "options": [],
                 "answer": {"value": False},
                 "explain": "Fel fördelning ger ett kallt och ett varmt rum, med rätt totaleffekt."},
            ],
        },
        {
            "slug": "overlamnande", "title": "Överlämnande och relationshandling", "xp": 150,
            "requires": "injusteringen",
            "blurb": "Dokumentationen är en leverans med en kostnad, inte en efterhandsuppgift.",
            "lektioner": [
                {"slug": "vad-lamnas", "title": "Vad som ska lämnas över", "minutes": 7, "blocks": [
                    UL([
                        "Relationshandlingar: ritningar som visar hur det blev, inte hur det var tänkt.",
                        "Drift- och underhållsinstruktioner, per komponent.",
                        "Protokoll: tryckprov, spolning, injustering, funktionsprov.",
                        "Märkning på plats: ventiler, schakt, brandtätningar.",
                        "Utbildning av driftpersonal, om det står i beskrivningen.",
                    ]),
                    NOTE("Relationshandlingen kräver att någon följt bygget och antecknat ändringarna medan de "
                         "gjordes. Görs det i efterhand blir den en gissning, och den gissningen står kvar i "
                         "huset i trettio år."),
                ]},
                {"slug": "kostnaden", "title": "Vad dokumentationen kostar", "minutes": 6, "blocks": [
                    P("På en normal VVS-entreprenad ligger överlämnandet på några procent av entreprenadsumman. "
                      "Det är en av de poster som oftast sätts till noll i en kalkyl — och den enda som säkert "
                      "kommer att krävas in."),
                    FORMULA("Överlämnande ≈ dokumentation + märkning + utbildning + slutstädning",
                            "Fyra poster, alla med en timkostnad, ingen av dem synlig på ritningen."),
                ]},
            ],
            "fragor": [
                {"slug": "q-ovl-1", "kind": "single", "area": "teori", "points": 10, "in_exam": True,
                 "prompt": "Vad är en relationshandling?",
                 "options": ["Kontraktet mellan parterna", "Ritningar som visar hur det faktiskt blev utfört",
                             "Leverantörens produktblad", "Besiktningsprotokollet"],
                 "answer": {"index": 1},
                 "explain": "Hur det blev, inte hur det var tänkt. Den kräver att någon antecknat under bygget."},
                {"slug": "q-ovl-2", "kind": "multi", "area": "kalkyl", "points": 15, "in_exam": True,
                 "prompt": "Vad ingår i posten överlämnande?",
                 "options": ["Relationshandlingar", "Märkning på plats", "Utbildning av driftpersonal",
                             "Tryckprovning av systemet", "Drift- och underhållsinstruktioner"],
                 "answer": {"indices": [0, 1, 2, 4]},
                 "explain": "Tryckprovningen hör till utförandet. De övriga fyra är överlämnandet."},
            ],
        },
    ],
}


# ================================================================ kurs 10: mark, spill och dagvatten

KURS10 = {
    "slug": "mark-spill-dag", "title": "Mark, spillvatten och dagvatten", "level": "fortsattning",
    "order": 10, "hours": 6.0,
    "blurb": "Ledningar under mark: självfall, brunnar, schakt och det som inte syns på planen.",
    "moduler": [
        {
            "slug": "sjalvfall", "title": "Självfall och fall", "xp": 150, "requires": "",
            "blurb": "En ledning utan tryck styrs av lutningen, och lutningen styr djupet.",
            "lektioner": [
                {"slug": "vad-ar-fall", "title": "Vad fall betyder", "minutes": 7, "blocks": [
                    P("En självfallsledning drivs av tyngdkraften. Fallet anges i promille eller som ett "
                      "förhållande, och det avgör hur djupt ledningen ligger i sin andra ände."),
                    FORMULA("djup = startdjup + längd × fall",
                            "En 40 m lång ledning med 10 ‰ fall ligger 0,4 m djupare i slutänden än i början."),
                    TERMS([
                        ["Fall 10 ‰", "En centimeter per meter. Vanligt för grövre spillvattenledningar."],
                        ["Fall 1:60", "Samma sak uttryckt som förhållande — knappt 17 ‰."],
                        ["Vattengång (VG)", "Höjden på ledningens botten. Det är den som styr, inte marknivån."],
                    ]),
                    WARN("Fallet syns inte på en planritning. Det står i profilen eller i en tabell, och utan "
                         "det går schaktdjupet inte att räkna."),
                    PLAN("mark-1", "Spill- och dagvatten med brunnar. Planen visar sträckningen; djupet står i profilen."),
                ]},
                {"slug": "schakt", "title": "Schakt, fyllning och återställning", "minutes": 8, "blocks": [
                    P("Under mark är ledningen sällan den dyraste posten. Schaktet är det, och schaktet räknas "
                      "i kubikmeter som beror på djupet, bredden och släntlutningen."),
                    UL([
                        "Schaktvolym: längd × bredd × medeldjup, plus slänt eller spont.",
                        "Kringfyllning: sand runt röret, i regel en egen produkt.",
                        "Återfyllning: massorna tillbaka, eller nya om de gamla inte duger.",
                        "Återställning av ytan: asfalt, plattor eller gräs — stor prisskillnad.",
                    ]),
                    NOTE("Vem som schaktar är ofta markentreprenören, inte du. Men vem som gör kringfyllningen "
                         "runt ditt rör är en gränssnittsfråga du måste läsa dig till."),
                ]},
                {"slug": "brunnar", "title": "Brunnar och rensmöjlighet", "minutes": 6, "blocks": [
                    TERMS([
                        ["Spolbrunn", "Där ledningen kan spolas. Sitter vid riktningsändringar och med jämna mellanrum."],
                        ["Rensbrunn", "Rensning med större öppning, ofta där flera ledningar möts."],
                        ["Dagvattenbrunn", "Tar emot ytvatten. Har sandfång som ska gå att tömma."],
                        ["Fettavskiljare", "Där matfett förekommer. Stor, tung och med eget krav på placering."],
                    ]),
                    P("Varje brunn är en post med produkt, montage, anslutningar och en betäckning i marknivå. "
                      "Betäckningen glöms ofta och är dyrare än den ser ut."),
                ]},
            ],
            "fragor": [
                {"slug": "q-mark-1", "kind": "numeric", "area": "mangdning", "points": 15, "in_exam": True,
                 "prompt": "En 40 m ledning har fall 10 ‰ och startar på djup 0,8 m. Vilket djup i slutänden? Svara i meter med en decimal.",
                 "options": [], "answer": {"value": 1.2}, "tolerance": 0.05,
                 "explain": "40 m × 10 ‰ = 0,4 m. 0,8 + 0,4 = 1,2 m."},
                {"slug": "q-mark-2", "kind": "single", "area": "ritning", "points": 10, "in_exam": True,
                 "prompt": "Var står en självfallsledningss fall?",
                 "options": ["I beteckningen på planen", "I profilritningen eller en tabell",
                             "I teckenförklaringen", "Det går att mäta på planen"],
                 "answer": {"index": 1},
                 "explain": "Planen visar sträckningen i plan. Höjden och fallet är en annan handling."},
                {"slug": "q-mark-3", "kind": "single", "area": "kalkyl", "points": 10, "in_exam": True,
                 "prompt": "Vilken post är oftast störst i en markförlagd ledning?",
                 "options": ["Röret", "Schaktet", "Brunnarna", "Kringfyllningen"],
                 "answer": {"index": 1},
                 "explain": "Schaktvolymen växer med djupet, och djupet växer med längden gånger fallet."},
                {"slug": "q-mark-4", "kind": "bool", "area": "mangdning", "points": 10, "in_exam": False,
                 "prompt": "Betäckningen ovanpå en brunn ingår normalt i brunnens pris.", "options": [],
                 "answer": {"value": False},
                 "explain": "Betäckningen är en egen produkt, ofta dyrare än den ser ut, och den glöms ofta."},
            ],
        },
        {
            "slug": "spill-inne", "title": "Spillvatten inomhus", "xp": 150, "requires": "sjalvfall",
            "blurb": "Stammar, luftning och anslutningar — och varför spill mängdas nedifrån.",
            "lektioner": [
                {"slug": "stammen", "title": "Stammen och dess luftning", "minutes": 7, "blocks": [
                    P("En spillvattenstam måste luftas, annars suger den vattenlåsen tomma. Luftningen går "
                      "antingen upp över tak eller sker med vakuumventil inomhus."),
                    TERMS([
                        ["Luftad stam över tak", "Ritas som en fortsättning upp genom taket. Kräver takgenomföring."],
                        ["Vakuumventil", "Sitter inomhus, ofta högst upp i stammen. Billigare, men inte alltid tillåten."],
                    ]),
                    NOTE("Takgenomföringen är en egen post med tätning mot yttertaket, och den ligger ofta i "
                         "gränssnittet mot takentreprenören."),
                ]},
                {"slug": "mangda-spill", "title": "Att mängda spillvatten", "minutes": 7, "blocks": [
                    P("Spillvatten mängdas enklast nedifrån och upp: börja i den grövsta samlingsledningen och "
                      "följ varje gren uppåt. Dimensionen minskar utåt i systemet, och det gör det svårt att "
                      "missa en gren."),
                    UL([
                        "Grövsta dimensionen först — den är stammen eller samlingsledningen.",
                        "Följ varje gren till sin apparat.",
                        "Varje apparat har ett vattenlås, och vattenlåset är en egen post.",
                        "Rensanordningar sitter vid riktningsändringar och räknas styckvis.",
                    ]),
                    PLAN("badrum-1", "Spillvattnet i badrummet: golvbrunn, WC och tvättställ till samma samlingsledning."),
                ]},
            ],
            "fragor": [
                {"slug": "q-spill-1", "kind": "single", "area": "teori", "points": 10, "in_exam": True,
                 "prompt": "Varför måste en spillvattenstam luftas?",
                 "options": ["För att undvika lukt i röret", "För att vattenlåsen annars sugs tomma",
                             "För att röret ska hålla trycket", "För att brandkraven kräver det"],
                 "answer": {"index": 1},
                 "explain": "Utan luftning skapar vattenpelaren undertryck som drar ut vattenlåsen — och då kommer lukten."},
                {"slug": "q-spill-2", "kind": "single", "area": "mangdning", "points": 10, "in_exam": True,
                 "prompt": "Varför är det lättare att mängda spillvatten nedifrån och upp?",
                 "options": ["Ritningen är ritad så", "Dimensionen minskar utåt, så en missad gren syns",
                             "Fallet räknas nedifrån", "Det går fortare"],
                 "answer": {"index": 1},
                 "explain": "Börja i det grövsta och följ varje gren utåt — då finns det ingen gren som inte har en början."},
            ],
        },
    ],
}


COURSES_2 = [KURS6, KURS7, KURS8, KURS9, KURS10]


# ================================================================ övningarna till kurs 6-10

def _ex(slug, kind, title, instructions, course, module, lesson, data, answer, **kw) -> dict:
    return {"slug": slug, "kind": kind, "title": title, "instructions": instructions,
            "course": course, "module": module, "lesson": lesson,
            "data": data, "answer": answer, **kw}


EXERCISES_2 = [
    # ---- ventilation -----------------------------------------------------------------------------
    _ex("ov-mangda-tilluft", "mangda", "Mängda all tilluftskanal",
        "Följ tilluftssystemet från aggregatet och mät varje kanal, huvudkanal och grenar. "
        "Frånluften ska inte vara med. Tolerans ±3 %.",
        "ventilation-mangdning", "kanalen", "kanal-mangd",
        {**VENT.data(), "highlight_sys": "TL", "exam_area": "mangdning"},
        {"metres": VENT.metres_where(sys="TL"),
         "miss_hint": "Tre grenar går av från huvudkanalen — en till varje rum.",
         "solution": f"Rätt mängd är {VENT.metres_where(sys='TL')} m: huvudkanalen Ø400 plus tre grenar."},
        tolerance=0.03, points=25, difficulty=2,
        hints=["Börja vid aggregatet nere till vänster.",
               "Huvudkanalen går upp och sedan rakt åt höger genom hela planet."]),

    _ex("ov-mangda-franluft", "mangda", "Mängda all frånluftskanal",
        "Mät frånluftssystemet. Tilluften ska inte vara med. Tolerans ±3 %.",
        "ventilation-mangdning", "kanalen", "kanal-mangd",
        {**VENT.data(), "highlight_sys": "FL", "exam_area": "mangdning"},
        {"metres": VENT.metres_where(sys="FL"),
         "solution": f"Rätt mängd är {VENT.metres_where(sys='FL')} m. Frånluften går parallellt med tilluften men har egna grenar."},
        tolerance=0.03, points=25, difficulty=2,
        hints=["Frånluftens huvudkanal ligger strax under tilluftens."]),

    _ex("ov-markera-brandspjall", "markera", "Markera brandspjällen",
        "Klicka på varje brandspjäll. Injusteringsspjällen ska inte markeras — de är en helt annan post.",
        "ventilation-mangdning", "don-och-flode", "spjallen",
        {**VENT.data(), "pick": "symbols", "exam_area": "ritning"},
        {"picked": VENT.ids_of_kind("brandspjall"), "pass": 1.0,
         "solution": "Två brandspjäll, ett i varje vägg mellan brandcellerna."},
        points=20, difficulty=2,
        hints=["Brandspjällen sitter där en kanal passerar en vägg."]),

    _ex("ov-markera-don", "markera", "Markera samtliga tilluftsdon",
        "Klicka på varje tilluftsdon. Frånluftsdon och spjäll ska inte markeras.",
        "ventilation-mangdning", "don-och-flode", "donen",
        {**VENT.data(), "pick": "symbols", "exam_area": "ritning"},
        {"picked": VENT.ids_of_kind("tilluftsdon"), "pass": 1.0,
         "solution": "Tre tilluftsdon: kontorslandskap, mötesrum och pentry."},
        points=15, difficulty=1),

    _ex("ov-vent-kategorier", "kategorisera", "Sortera ventilationsposterna",
        "Varje post mängdas antingen i meter eller i styck. Dra dem rätt.",
        "ventilation-mangdning", "kanalen", "kanal-mangd",
        {"buckets": [{"id": "meter", "label": "Mängdas i meter"}, {"id": "styck", "label": "Mängdas i styck"}],
         "items": [{"id": "rak", "text": "Rak kanal Ø400"}, {"id": "boj", "text": "Kanalböj 90°"},
                   {"id": "tstycke", "text": "T-stycke"}, {"id": "isol", "text": "Kondensisolering på kanal"},
                   {"id": "don", "text": "Tilluftsdon"}, {"id": "bsp", "text": "Brandspjäll"},
                   {"id": "red", "text": "Reducering Ø400/Ø250"}],
         "exam_area": "mangdning"},
        {"buckets": {"meter": ["rak", "isol"], "styck": ["boj", "tstycke", "don", "bsp", "red"]},
         "solution": "Bara rak kanal och isolering mäts i meter. Allt som är en del räknas styckvis."},
        points=20, difficulty=2),

    # ---- AB 04 / ABT 06 --------------------------------------------------------------------------
    _ex("ov-avtal-matcha", "matcha", "Vem bär vad under vilket avtal",
        "Para ihop varje situation med det avtal där ansvaret ligger hos entreprenören.",
        "ab04-abt06", "tva-avtal", "vem-projekterar",
        {"left": [{"id": "l1", "text": "Ritningen visar för få radiatorer för att nå 21 °C"},
                  {"id": "l2", "text": "Beställarens ritning har fel dimension på en stam"},
                  {"id": "l3", "text": "Din egen projektering ger för lite VVC-flöde"},
                  {"id": "l4", "text": "Handlingen saknar en hel våningsplansritning"}],
         "right": [{"id": "r1", "text": "Entreprenörens ansvar (ABT 06)"},
                   {"id": "r2", "text": "Beställarens ansvar (AB 04)"}],
         "exam_area": "teori"},
        {"pairs": {"l1": "r1", "l2": "r2", "l3": "r1", "l4": "r2"},
         "solution": "Under ABT 06 svarar du för funktionen och därmed för din egen dimensionering. "
                     "Under AB 04 svarar beställaren för sin handling."},
        points=25, difficulty=3),

    _ex("ov-ata-ordning", "bygg", "Ordningen för ett ÄTA-arbete",
        "Lägg stegen i den ordning som gör att ÄTA-arbetet faktiskt blir betalt.",
        "ab04-abt06", "ata", "bestallning",
        {"items": [{"id": "s1", "text": "Upptäck avvikelsen mot kontraktshandlingen"},
                   {"id": "s2", "text": "Underrätta beställaren utan dröjsmål"},
                   {"id": "s3", "text": "Lämna specificerat pris: material, tid, påslag"},
                   {"id": "s4", "text": "Få skriftlig beställning"},
                   {"id": "s5", "text": "Utför arbetet"},
                   {"id": "s6", "text": "Fakturera med hänvisning till beställningen"}],
         "exam_area": "teori"},
        {"order": ["s1", "s2", "s3", "s4", "s5", "s6"],
         "solution": "Utförande före beställning är arbete på egen risk — det är där de flesta ÄTA-krav faller."},
        points=25, difficulty=2),

    _ex("ov-ata-kalkyl", "kalkyl", "Räkna en ÄTA",
        "En vägg har flyttats. Sex meter DN20 ska rivas och åtta meter dras om. "
        "Räkna fram vad som ska faktureras.",
        "ab04-abt06", "ata", "prissattning",
        {"givna": [["Rivning", "6 m DN20"], ["Nydragning", "8 m DN20"], ["Materialpris", "95 kr/m"],
                   ["Rivningstid", "0,25 h/m"], ["Montagetid", "0,55 h/m"], ["Timkostnad", "650 kr/h"],
                   ["Påslag på arbete", "10 %"]],
         "steps": [{"key": "mtrl", "label": "Materialkostnad nytt rör", "unit": "kr", "hint": "8 m × 95 kr/m"},
                   {"key": "tid", "label": "Arbetstid, rivning och nydragning", "unit": "h", "hint": "6 × 0,25 + 8 × 0,55"},
                   {"key": "arb", "label": "Arbetskostnad", "unit": "kr", "hint": "timmar × 650"},
                   {"key": "pas", "label": "Påslag 10 % på arbete", "unit": "kr"},
                   {"key": "summa", "label": "Att fakturera, exkl. moms", "unit": "kr"}],
         "exam_area": "kalkyl"},
        {"steps": {"mtrl": 760.0, "tid": 5.9, "arb": 3835.0, "pas": 383.5, "summa": 4978.5},
         "solution": "8 × 95 = 760 kr material. 6 × 0,25 + 8 × 0,55 = 1,5 + 4,4 = 5,9 h. "
                     "5,9 × 650 = 3 835 kr. Påslag 383,50 kr. Summa 4 978,50 kr."},
        tolerance=0.02, points=30, difficulty=3,
        hints=["Rivningen är också arbete och ska med.",
               "Påslaget läggs på arbetet, inte på materialet, i det här exemplet."]),

    # ---- isolering och brandtätning --------------------------------------------------------------
    _ex("ov-brandtatning-rakna", "numerisk", "Räkna genomföringarna",
        "Tappvattenstammen går genom tre plan med KV, VV och VVC. Hur många bjälklagsgenomföringar "
        "ska brandtätas? Räkna bjälklagen mellan planen.",
        "isolering-brandtatning", "brandtatning", "rakna-hal",
        {"plan": "stam-1", "exam_area": "mangdning"},
        {"value": 6, "tolerance": 0,
         "solution": "Tre rör genom två bjälklag mellan tre plan = sex genomföringar."},
        points=20, difficulty=2,
        hints=["Tre plan har två bjälklag mellan sig."]),

    _ex("ov-isolering-kategorier", "kategorisera", "Vilket skäl att isolera",
        "Sortera varje ledning efter vilket skäl som styr isoleringen.",
        "isolering-brandtatning", "isoleringen", "fyra-skal",
        {"buckets": [{"id": "varme", "label": "Värmeisolering"}, {"id": "kondens", "label": "Kondensisolering"},
                     {"id": "ljud", "label": "Ljudisolering"}],
         "items": [{"id": "i1", "text": "VS-framledning i kallt schakt"},
                   {"id": "i2", "text": "KV-ledning i varmt undertak"},
                   {"id": "i3", "text": "Spillvattenstam i lägenhetsvägg"},
                   {"id": "i4", "text": "VV-ledning till tappställe"},
                   {"id": "i5", "text": "Kylledning i kontorstak"}],
         "exam_area": "teori"},
        {"buckets": {"varme": ["i1", "i4"], "kondens": ["i2", "i5"], "ljud": ["i3"]},
         "solution": "Kallt rör i varm luft ger kondens. Varmt rör i kallt utrymme tappar energi. "
                     "Spillvatten i en lägenhetsvägg hörs."},
        points=20, difficulty=2),

    # ---- injustering ------------------------------------------------------------------------------
    _ex("ov-markera-injustering-uc", "markera", "Markera styrventilerna i undercentralen",
        "Klicka på de två styrventilerna. Avstängningsventiler och smutsfilter ska inte markeras.",
        "injustering-overlamnande", "injusteringen", "vatten",
        {**UC.data(), "pick": "symbols", "exam_area": "ritning"},
        {"picked": UC.ids_of_kind("styrventil"), "pass": 1.0,
         "solution": "Två styrventiler på primärsidan: en för värme, en för tappvarmvatten."},
        points=20, difficulty=2,
        hints=["Styrventilerna sitter på fjärrvärmesidan, före växlarna."]),

    _ex("ov-mangda-fjarrvarme", "mangda", "Mängda fjärrvärmeledningarna i undercentralen",
        "Mät FV-fram och FV-retur fram till växlarna. Sekundärsidan ska inte vara med. Tolerans ±3 %.",
        "injustering-overlamnande", "provning", "tryckprov",
        {**UC.data(), "highlight_sys": "FV", "exam_area": "mangdning"},
        {"metres": UC.metres_where(sys="FV"),
         "solution": f"Rätt mängd är {UC.metres_where(sys='FV')} m: fram och retur från inkommande till växlare."},
        tolerance=0.03, points=20, difficulty=2),

    _ex("ov-overlamnande-kategorier", "kategorisera", "Utförande eller överlämnande",
        "Sortera posterna efter om de hör till utförandet eller till överlämnandet.",
        "injustering-overlamnande", "overlamnande", "vad-lamnas",
        {"buckets": [{"id": "utf", "label": "Utförande"}, {"id": "ovl", "label": "Överlämnande"}],
         "items": [{"id": "o1", "text": "Tryckprovning av stammen"},
                   {"id": "o2", "text": "Relationshandling"},
                   {"id": "o3", "text": "Märkning av ventiler"},
                   {"id": "o4", "text": "Montage av radiatorer"},
                   {"id": "o5", "text": "Drift- och underhållsinstruktion"},
                   {"id": "o6", "text": "Utbildning av driftpersonal"}],
         "exam_area": "kontroll"},
        {"buckets": {"utf": ["o1", "o4"], "ovl": ["o2", "o3", "o5", "o6"]},
         "solution": "Provningen hör till utförandet. Dokumentation, märkning och utbildning är leveransen efteråt."},
        points=20, difficulty=2),

    # ---- mark, spill och dag ---------------------------------------------------------------------
    _ex("ov-mangda-spillmark", "mangda", "Mängda spillvattnet under mark",
        "Mät all spillvattenledning i markplanen, samlingsledning och grenar. Dagvattnet ska inte vara med. "
        "Tolerans ±3 %.",
        "mark-spill-dag", "sjalvfall", "schakt",
        {**MARK.data(), "highlight_sys": "S", "exam_area": "mangdning"},
        {"metres": MARK.metres_where(sys="S"),
         "miss_hint": "Tre grenar går ned från samlingsledningen in i byggnaden.",
         "solution": f"Rätt mängd är {MARK.metres_where(sys='S')} m: samlingsledningen Ø160 plus tre grenar."},
        tolerance=0.03, points=25, difficulty=2,
        hints=["Samlingsledningen är den grövsta — börja där."]),

    _ex("ov-mangda-dagvatten", "mangda", "Mängda dagvattnet",
        "Mät dagvattensystemet på gården. Spillvattnet ska inte vara med. Tolerans ±3 %.",
        "mark-spill-dag", "sjalvfall", "brunnar",
        {**MARK.data(), "highlight_sys": "D", "exam_area": "mangdning"},
        {"metres": MARK.metres_where(sys="D"),
         "solution": f"Rätt mängd är {MARK.metres_where(sys='D')} m."},
        tolerance=0.03, points=20, difficulty=1),

    _ex("ov-markera-brunnar", "markera", "Markera dagvattenbrunnarna",
        "Klicka på dagvattenbrunnarna. Spol- och rensbrunnar hör till spillvattnet och ska inte markeras.",
        "mark-spill-dag", "sjalvfall", "brunnar",
        {**MARK.data(), "pick": "symbols", "exam_area": "ritning"},
        {"picked": MARK.ids_of_kind("dagvattenbrunn"), "pass": 1.0,
         "solution": "Två dagvattenbrunnar, båda på gårdssidan."},
        points=15, difficulty=1),

    _ex("ov-schakt-kalkyl", "kalkyl", "Räkna schaktvolymen",
        "En 40 m lång ledning läggs med schaktbredd 0,9 m. Startdjupet är 0,8 m och fallet 10 ‰. "
        "Räkna fram schaktvolymen med medeldjup.",
        "mark-spill-dag", "sjalvfall", "schakt",
        {"givna": [["Ledningslängd", "40 m"], ["Schaktbredd", "0,9 m"], ["Startdjup", "0,8 m"],
                   ["Fall", "10 ‰"]],
         "steps": [{"key": "slutdjup", "label": "Djup i slutänden", "unit": "m", "hint": "startdjup + längd × fall"},
                   {"key": "medeldjup", "label": "Medeldjup", "unit": "m", "hint": "(start + slut) / 2"},
                   {"key": "volym", "label": "Schaktvolym", "unit": "m³", "hint": "40 × 0,9 × medeldjup"}],
         "exam_area": "kalkyl"},
        {"steps": {"slutdjup": 1.2, "medeldjup": 1.0, "volym": 36.0},
         "solution": "40 × 10 ‰ = 0,4 m. Slutdjup 1,2 m, medeldjup (0,8+1,2)/2 = 1,0 m. "
                     "40 × 0,9 × 1,0 = 36 m³."},
        tolerance=0.02, points=30, difficulty=3,
        hints=["Medeldjupet är genomsnittet av start och slut när fallet är jämnt."]),

    _ex("ov-spill-dimension", "dimension", "Vilken dimension har samlingsledningen?",
        "Spillvattnets samlingsledning under byggnaden är markerad. Vilken dimension har den?",
        "mark-spill-dag", "spill-inne", "mangda-spill",
        {**MARK.data(), "focus": "s-samling", "options": ["Ø75", "Ø110", "Ø160", "Ø200"],
         "exam_area": "ritning"},
        {"index": 2, "why": "Samlingsledningen är Ø160; grenarna är Ø110 och Ø75."},
        points=10, difficulty=1),
]
