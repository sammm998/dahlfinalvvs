import { t as tr } from "../i18n";
/* Figurerna som visar vad varje funktion gör.
 *
 * Ingen av dem är en dekoration och ingen är ett fotografi. De ritar det systemet faktiskt gör, i systemets
 * eget språk: en ledarlinje som hittar sitt rör, en front med sitt skäl, en modell som reser sig, en
 * markeringslista, ett samtal, ett anbud. Det är också det ärligaste en produktsida kan visa - ett
 * skärmavbild åldras och en illustration av något annat ljuger.
 *
 * Alla ritar i samma rutnät (1200 x 760) och tar sin färg ur `accent`, så de kan ligga bredvid varandra utan
 * att se ut som sex olika hus.
 */

type P = { accent: string };

const GRID = (
  <g stroke="rgba(255,255,255,0.045)" strokeWidth="1" fill="none">
    {Array.from({ length: 15 }, (_, i) => <path key={`h${i}`} d={`M0 ${i * 54} H1200`} />)}
    {Array.from({ length: 23 }, (_, i) => <path key={`v${i}`} d={`M${i * 54} 0 V760`} />)}
  </g>
);

function Frame({ children, label }: { children: any; label?: string }) {
  return (
    <svg viewBox="0 0 1200 760" className="fa" role="img" aria-label={label ?? ""}>
      {GRID}
      {children}
    </svg>
  );
}

/* ---------- läsningen: beteckning, ledare, rör ---------- */

function Read({ accent }: P) {
  return (
    <Frame label={tr("En hänvisningslinje går från beteckningen till röret den namnger")}>
      <g stroke="#3a4049" strokeWidth="1.6" fill="none">
        <path d="M120 120 H700 V620 H120 Z M420 120 V620 M120 380 H420" />
        <path d="M760 120 H1080 V360 H760 Z M760 420 H1080 V620 H760 Z" />
      </g>
      <g fill="none" strokeWidth="4.2" strokeLinecap="butt">
        <path d="M170 520 H520 V300 H860 V200 H1040" stroke={accent} strokeDasharray="22 8 4 8" />
        <path d="M520 520 H880 V470" stroke="#60a5fa" strokeOpacity="0.75" strokeDasharray="22 8 4 8" />
      </g>
      <g fill="#07080a" stroke={accent} strokeWidth="2.4">
        <circle cx="170" cy="520" r="6" /><circle cx="1040" cy="200" r="6" />
      </g>
      <g>
        <path d="M560 200 L700 296" stroke={accent} strokeOpacity="0.55" strokeWidth="1.6" fill="none" />
        <path d="M400 176 H560" stroke={accent} strokeOpacity="0.55" strokeWidth="1.6" fill="none" />
        <text x="400" y="166" fill="#f4f5f7" fontSize="21" fontFamily="ui-monospace, monospace">S1-P5-110</text>
        <text x="400" y="196" fill="#8b929e" fontSize="18" fontFamily="ui-monospace, monospace">24,8 m</text>
      </g>
      <g>
        <path d="M660 430 L790 500" stroke="#60a5fa" strokeOpacity="0.5" strokeWidth="1.6" fill="none" />
        <path d="M500 430 H660" stroke="#60a5fa" strokeOpacity="0.5" strokeWidth="1.6" fill="none" />
        <text x="500" y="420" fill="#f4f5f7" fontSize="21" fontFamily="ui-monospace, monospace">KV1-X7-32</text>
        <text x="500" y="450" fill="#8b929e" fontSize="18" fontFamily="ui-monospace, monospace">11,4 m</text>
      </g>
      <g>
        <path d="M800 660 H1060" stroke="#565d6a" strokeWidth="3.6" strokeDasharray="20 7 3 7" fill="none" />
        <text x="800" y="644" fill="#6a7280" fontSize="16" fontFamily="ui-monospace, monospace">{tr("onämnd — redovisas, mäts inte")}</text>
      </g>
    </Frame>
  );
}

function Leader({ accent }: P) {
  return (
    <Frame label={tr("Den närmaste linjen är inte den som namnger")}>
      <g fill="none" strokeWidth="4" strokeLinecap="round">
        <path d="M200 300 H1000" stroke={accent} />
        <path d="M200 470 H1000" stroke="#565d6a" strokeDasharray="18 10" />
      </g>
      <path d="M430 210 H560 L640 296" stroke={accent} strokeOpacity="0.6" strokeWidth="1.8" fill="none" />
      <path d="M636 292 L644 300" stroke={accent} strokeWidth="3" />
      <text x="430" y="198" fill="#f4f5f7" fontSize="22" fontFamily="ui-monospace, monospace">VS21-S13-15</text>
      <g opacity="0.75">
        <path d="M700 430 L700 466" stroke="#f6a5a5" strokeWidth="1.8" strokeDasharray="5 5" fill="none" />
        <text x="716" y="446" fill="#f6a5a5" fontSize="17" fontFamily="ui-monospace, monospace">{tr("närmast — men ingen linje går hit")}</text>
      </g>
      <text x="200" y="560" fill="#6a7280" fontSize="17" fontFamily="ui-monospace, monospace">
        identitet kommer ur linjen, inte ur avståndet
      </text>
    </Frame>
  );
}

function Frontier({ accent }: P) {
  const stops: [number, string][] = [
    [330, "REAL_DN_BOUNDARY"],
    [560, "AMBIGUOUS_JUNCTION"],
    [790, "SYMBOL"],
  ];
  return (
    <Frame label={tr("Varje ställe ett rör slutar har ett skäl")}>
      <path d="M150 380 H1050" stroke={accent} strokeWidth="4.5" fill="none" />
      {stops.map(([x, t], i) => (
        <g key={t}>
          <path d={`M${x} 330 V430`} stroke="#f4f5f7" strokeWidth="2" strokeOpacity="0.5" />
          <circle cx={x} cy="380" r="8" fill="#07080a" stroke={accent} strokeWidth="2.4" />
          <text x={x} y={i % 2 ? 470 : 300} fill="#8b929e" fontSize="16"
            textAnchor="middle" fontFamily="ui-monospace, monospace">{t}</text>
        </g>
      ))}
      <text x="150" y="580" fill="#6a7280" fontSize="17" fontFamily="ui-monospace, monospace">
        sexton skäl — och inget rör lämnar läsningen utan ett
      </text>
    </Frame>
  );
}

function Scale({ accent }: P) {
  return (
    <Frame label={tr("Skalan tas ur bladets egen skalstock")}>
      <g stroke="#3a4049" strokeWidth="1.6" fill="none">
        <path d="M140 150 H700 V560 H140 Z" />
      </g>
      {/* skrafferad vägg */}
      <g stroke="#4a5058" strokeWidth="1.5">
        {Array.from({ length: 22 }, (_, i) => <path key={i} d={`M${560 + i * 9} 150 L${600 + i * 9} 560`} />)}
      </g>
      <path d="M180 360 H1020" stroke={accent} strokeWidth="4.5" fill="none" />
      <text x="620" y="620" fill="#6a7280" fontSize="16" fontFamily="ui-monospace, monospace">{tr("rör i vägg — redovisas för sig")}</text>
      <g>
        <path d="M760 200 H1060" stroke="#f4f5f7" strokeWidth="2.4" />
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <g key={i}>
            <path d={`M${760 + i * 60} 190 V210`} stroke="#f4f5f7" strokeWidth="2" />
            <text x={760 + i * 60} y="178" fill="#8b929e" fontSize="15" textAnchor="middle"
              fontFamily="ui-monospace, monospace">{i}</text>
          </g>
        ))}
        <text x="760" y="248" fill={accent} fontSize="17" fontFamily="ui-monospace, monospace">SKALA 1:50 · skalstock och stämpel överens</text>
      </g>
    </Frame>
  );
}

/* ---------- CAD ---------- */

function Cad({ accent }: P) {
  return (
    <Frame label={tr("Väggar, stomme och installationer i en modell")}>
      <g stroke="#3a4049" strokeWidth="2.2" fill="none">
        <path d="M160 180 H1040 V600 H160 Z" />
        <path d="M520 180 V600 M160 400 H520 M760 400 H1040" />
      </g>
      <g stroke="#565d6a" strokeWidth="9" strokeLinecap="square" fill="none" opacity="0.5">
        <path d="M160 180 H1040 M160 600 H1040 M160 180 V600 M1040 180 V600" />
      </g>
      <g fill="none" strokeWidth="3.6">
        <path d="M230 300 H470 V520" stroke={accent} />
        <path d="M600 260 H980" stroke="#00b5e2" strokeOpacity="0.8" />
        <path d="M600 470 H980 V560" stroke="#fbbf24" strokeOpacity="0.8" />
      </g>
      {[[230, 300], [470, 520], [980, 260], [980, 560]].map(([x, y]) => (
        <circle key={`${x}-${y}`} cx={x} cy={y} r="7" fill="#07080a" stroke={accent} strokeWidth="2.4" />
      ))}
      <g fill="#8b929e" fontSize="16" fontFamily="ui-monospace, monospace">
        <text x="240" y="284">KV1-X7-32</text>
        <text x="610" y="244">VS1-S13-22</text>
        <text x="610" y="454">S2-P5-110</text>
      </g>
      <text x="160" y="670" fill="#6a7280" fontSize="17" fontFamily="ui-monospace, monospace">
        nivåer · rutnät · lager · ångra och gör om · revisioner
      </text>
    </Frame>
  );
}

function CadModel({ accent }: P) {
  return (
    <Frame label={tr("En vägg vet att den är en vägg")}>
      {[0, 1, 2].map((i) => (
        <g key={i} transform={`translate(${i * 40} ${i * 120})`} opacity={1 - i * 0.22}>
          <path d="M240 200 L760 120 L960 240 L440 330 Z" fill="rgba(255,255,255,0.03)"
            stroke={i === 0 ? accent : "#3a4049"} strokeWidth="2.2" />
        </g>
      ))}
      <g fill="#8b929e" fontSize="17" fontFamily="ui-monospace, monospace">
        <text x="1000" y="200">{tr("plan 3")}</text>
        <text x="1000" y="320">{tr("plan 2")}</text>
        <text x="1000" y="440">{tr("plan 1")}</text>
      </g>
      <text x="240" y="660" fill="#6a7280" fontSize="17" fontFamily="ui-monospace, monospace">
        mängderna räknas ur modellen, inte av den
      </text>
    </Frame>
  );
}

function Views({ accent }: P) {
  const boxes = [["PLAN", 150], ["SEKTION", 420], ["FASAD", 690], ["3D", 960]];
  return (
    <Frame label={tr("Plan, sektion, fasad och 3D ur samma modell")}>
      {boxes.map(([t, x], i) => (
        <g key={t as string}>
          <rect x={x as number} y="230" width="200" height="300" rx="10"
            fill="rgba(255,255,255,0.025)" stroke={i === 0 ? accent : "#3a4049"} strokeWidth="2" />
          <text x={(x as number) + 100} y="200" fill={i === 0 ? accent : "#8b929e"} fontSize="17"
            textAnchor="middle" fontFamily="ui-monospace, monospace">{t}</text>
          <g stroke={i === 0 ? accent : "#565d6a"} strokeWidth="2.4" fill="none" opacity="0.8">
            <path d={`M${(x as number) + 30} 300 H${(x as number) + 170}`} />
            <path d={`M${(x as number) + 30} 380 H${(x as number) + 120}`} />
            <path d={`M${(x as number) + 30} 460 H${(x as number) + 150}`} />
          </g>
        </g>
      ))}
      <text x="150" y="620" fill="#6a7280" fontSize="17" fontFamily="ui-monospace, monospace">
        ändra i en — de andra följer med
      </text>
    </Frame>
  );
}

/* ---------- 3D ---------- */

function Three({ accent }: P) {
  return (
    <Frame label={tr("Planen reser sig till en modell")}>
      <g opacity="0.35">
        <path d="M200 520 L740 400 L1000 520 L460 650 Z" fill="none" stroke="#3a4049" strokeWidth="2" />
      </g>
      <g fill="none" strokeWidth="4">
        <path d="M300 540 L720 446 L900 530" stroke={accent} />
        <path d="M420 566 L840 470" stroke="#00b5e2" strokeOpacity="0.7" />
      </g>
      {/* stigare genom bjälklaget */}
      {[[560, 480], [790, 500]].map(([x, y], i) => (
        <g key={i}>
          <path d={`M${x} ${y} V${y - 210}`} stroke="#fbbf24" strokeWidth="4" fill="none" strokeDasharray="10 7" />
          <circle cx={x} cy={y - 210} r="7" fill="#07080a" stroke="#fbbf24" strokeWidth="2.4" />
        </g>
      ))}
      <path d="M200 300 L740 180 L1000 300 L460 430 Z" fill="none" stroke="#3a4049" strokeWidth="2" opacity="0.6" />
      <g fill="#8b929e" fontSize="16" fontFamily="ui-monospace, monospace">
        <text x="580" y="250">{tr("stigare · 2 st")}</text>
        <text x="300" y="594">{tr("VS1-S13-22 · 61,9 m")}</text>
      </g>
    </Frame>
  );
}

function Link3d({ accent }: P) {
  return (
    <Frame label={tr("Samma rör i tabellen och i modellen")}>
      <g>
        {["KV1-X31-16", "VV1-X31-16", "S3-R8-110", "VS1-S13-22"].map((t, i) => (
          <g key={t}>
            <rect x="120" y={220 + i * 72} width="420" height="56" rx="8"
              fill={i === 3 ? "rgba(0, 181, 226,0.1)" : "rgba(255,255,255,0.025)"}
              stroke={i === 3 ? accent : "#2a2f37"} strokeWidth="1.6" />
            <text x="148" y={256 + i * 72} fill="#e8ecf1" fontSize="19" fontFamily="ui-monospace, monospace">{t}</text>
            <text x="500" y={256 + i * 72} fill="#8b929e" fontSize="18" textAnchor="end"
              fontFamily="ui-monospace, monospace">{["17,1", "33,9", "56,7", "61,9"][i]} m</text>
          </g>
        ))}
      </g>
      <path d="M560 470 C 660 470, 660 400, 760 400" stroke={accent} strokeWidth="2" fill="none" strokeDasharray="6 6" />
      <g opacity="0.9">
        <path d="M700 520 L1080 430" stroke="#3a4049" strokeWidth="2" fill="none" />
        <path d="M760 400 L1040 340" stroke={accent} strokeWidth="5" fill="none" />
        <circle cx="760" cy="400" r="8" fill="#07080a" stroke={accent} strokeWidth="2.6" />
      </g>
    </Frame>
  );
}

/* ---------- mängda för hand ---------- */

function Measure({ accent }: P) {
  return (
    <Frame label={tr("Mätverktyget: kalibrering, fångst och avdrag")}>
      <g stroke="#3a4049" strokeWidth="1.6" fill="none">
        <path d="M140 160 H820 V600 H140 Z M480 160 V600" />
      </g>
      <path d="M200 520 H760" stroke={accent} strokeWidth="4" fill="none" />
      {[200, 760].map((x) => (
        <g key={x}>
          <path d={`M${x} 496 V544`} stroke={accent} strokeWidth="2.4" />
          <circle cx={x} cy="520" r="7" fill="#07080a" stroke={accent} strokeWidth="2.4" />
        </g>
      ))}
      <text x="480" y="486" fill={accent} fontSize="19" textAnchor="middle" fontFamily="ui-monospace, monospace">14,62 m</text>
      <g opacity="0.85">
        <rect x="300" y="240" width="220" height="150" rx="6" fill="rgba(251,191,36,0.08)"
          stroke="#fbbf24" strokeWidth="2.2" strokeDasharray="8 6" />
        <text x="410" y="322" fill="#fbbf24" fontSize="18" textAnchor="middle" fontFamily="ui-monospace, monospace">avdrag</text>
      </g>
      <g>
        <rect x="880" y="200" width="280" height="360" rx="10" fill="rgba(255,255,255,0.025)" stroke="#2a2f37" />
        <text x="906" y="240" fill="#6a7280" fontSize="15" fontFamily="ui-monospace, monospace">MARKERINGAR</text>
        {["längd 14,62", "längd 8,04", "area 12,1", "antal 6"].map((t, i) => (
          <text key={t} x="906" y={286 + i * 42} fill="#c7cdd7" fontSize="18" fontFamily="ui-monospace, monospace">{t}</text>
        ))}
      </g>
    </Frame>
  );
}

function Bench({ accent }: P) {
  return (
    <Frame label={tr("Ritningen är sidan, verktygen i kanten")}>
      <rect x="120" y="150" width="760" height="470" rx="12" fill="rgba(255,255,255,0.02)" stroke="#2a2f37" />
      <g stroke="#3a4049" strokeWidth="1.6" fill="none">
        <path d="M180 220 H820 V560 H180 Z M480 220 V560" />
      </g>
      <path d="M240 480 H760" stroke={accent} strokeWidth="4" fill="none" />
      <g>
        {[0, 1, 2, 3, 4].map((i) => (
          <rect key={i} x="930" y={170 + i * 68} width="56" height="56" rx="10"
            fill={i === 1 ? "rgba(255,255,255,0.1)" : "rgba(255,255,255,0.03)"} stroke="#2a2f37" />
        ))}
      </g>
      <text x="1020" y="238" fill={accent} fontSize="17" fontFamily="ui-monospace, monospace">{tr("längd")}</text>
    </Frame>
  );
}

/* ---------- agenten ---------- */

function Agent({ accent }: P) {
  return (
    <Frame label={tr("Ett samtal om ritningen")}>
      <g>
        <rect x="560" y="170" width="520" height="86" rx="16" fill="rgba(255,255,255,0.07)" stroke="#2a2f37" />
        <text x="588" y="222" fill="#f4f5f7" fontSize="20" fontFamily="ui-monospace, monospace">Vad kunde inte avgöras?</text>
      </g>
      <g>
        <rect x="120" y="300" width="760" height="180" rx="16" fill="rgba(255,255,255,0.025)" stroke="#2a2f37" />
        <text x="150" y="350" fill="#e8ecf1" fontSize="20" fontFamily="ui-monospace, monospace">Två sträckor står som tvetydiga:</text>
        <text x="150" y="392" fill={accent} fontSize="19" fontFamily="ui-monospace, monospace">{tr("S1-P2 · DN110 eller DN160 · 1,7 m")}</text>
        <text x="150" y="434" fill="#8b929e" fontSize="18" fontFamily="ui-monospace, monospace">Skäl: AMBIGUOUS_BRANCH</text>
      </g>
      <g opacity="0.85">
        <rect x="120" y="520" width="420" height="64" rx="10" fill="rgba(255,255,255,0.02)" stroke="#2a2f37" strokeDasharray="6 6" />
        <text x="148" y="560" fill="#6a7280" fontSize="17" fontFamily="ui-monospace, monospace">{tr("3 verktygsanrop ▸")}</text>
      </g>
    </Frame>
  );
}

function Chat({ accent }: P) {
  return (
    <Frame label={tr("Modellen väljer frågan, ritningen ger svaret")}>
      <g fill="none" stroke="#2a2f37" strokeWidth="2">
        <rect x="140" y="250" width="280" height="260" rx="14" />
        <rect x="470" y="250" width="280" height="260" rx="14" />
        <rect x="800" y="250" width="280" height="260" rx="14" />
      </g>
      <g fill="#8b929e" fontSize="18" fontFamily="ui-monospace, monospace" textAnchor="middle">
        <text x="280" y="310">{tr("fråga")}</text>
        <text x="610" y="310">verktyg</text>
        <text x="940" y="310">svar</text>
      </g>
      <g fill="#e8ecf1" fontSize="17" fontFamily="ui-monospace, monospace" textAnchor="middle">
        <text x="280" y="390">modellen</text>
        <text x="280" y="420">formulerar</text>
        <text x="610" y="390">{tr("läsningen")}</text>
        <text x="610" y="420">svarar</text>
        <text x="940" y="390">{tr("med belägg")}</text>
        <text x="940" y="420">{tr("eller inte alls")}</text>
      </g>
      <g stroke={accent} strokeWidth="2.4" fill="none">
        <path d="M420 380 H470" /><path d="M750 380 H800" />
        <path d="M455 372 L470 380 L455 388" /><path d="M785 372 L800 380 L785 388" />
      </g>
      <text x="610" y="600" fill="#6a7280" fontSize="17" textAnchor="middle" fontFamily="ui-monospace, monospace">
        en siffra utan belägg blir «det står inte i handlingen»
      </text>
    </Frame>
  );
}

/* ---------- kalkyl ---------- */

function Calc({ accent }: P) {
  const rows: [string, string, string][] = [
    ["KV1-X31-16", "17,1 m", "2 940 kr"],
    ["VV1-X31-16", "33,9 m", "5 830 kr"],
    ["S3-R8-110", "56,7 m", "14 180 kr"],
    ["VS1-S13-22", "61,9 m", "11 420 kr"],
  ];
  return (
    <Frame label={tr("Mängden blir ett anbud")}>
      {rows.map(([a, b, c], i) => (
        <g key={a}>
          <path d={`M140 ${290 + i * 70} H1060`} stroke="#22262d" strokeWidth="1.4" />
          <text x="150" y={270 + i * 70} fill="#e8ecf1" fontSize="20" fontFamily="ui-monospace, monospace">{a}</text>
          <text x="700" y={270 + i * 70} fill="#8b929e" fontSize="19" textAnchor="end" fontFamily="ui-monospace, monospace">{b}</text>
          <text x="1050" y={270 + i * 70} fill={accent} fontSize="19" textAnchor="end" fontFamily="ui-monospace, monospace">{c}</text>
        </g>
      ))}
      <text x="150" y="200" fill="#6a7280" fontSize="16" fontFamily="ui-monospace, monospace">BETECKNING</text>
      <text x="700" y="200" fill="#6a7280" fontSize="16" textAnchor="end" fontFamily="ui-monospace, monospace">{tr("MÄNGD")}</text>
      <text x="1050" y="200" fill="#6a7280" fontSize="16" textAnchor="end" fontFamily="ui-monospace, monospace">MATERIAL</text>
      <text x="1050" y="640" fill="#fff" fontSize="26" textAnchor="end" fontFamily="ui-monospace, monospace">{tr("34 370 kr")}</text>
    </Frame>
  );
}

function Tender({ accent }: P) {
  return (
    <Frame label={tr("Anbudet granskas på skärmen innan det lämnar huset")}>
      {[0, 1, 2].map((i) => (
        <g key={i} transform={`translate(${i * 60} ${i * 26})`}>
          <rect x="260" y="150" width="440" height="520" rx="10"
            fill="rgba(255,255,255,0.03)" stroke={i === 2 ? accent : "#2a2f37"} strokeWidth="2" />
        </g>
      ))}
      <g fill="#8b929e" fontSize="17" fontFamily="ui-monospace, monospace">
        <text x="820" y="300">{tr("sida 1 · sammanställning")}</text>
        <text x="820" y="350">{tr("sida 2 · mängdförteckning")}</text>
        <text x="820" y="400">{tr("sida 3 · villkor")}</text>
      </g>
      <text x="380" y="720" fill="#6a7280" fontSize="17" fontFamily="ui-monospace, monospace">
        AB 04 och ABT 06 — men aldrig i geometrin
      </text>
    </Frame>
  );
}

/* ---------- utbildning ---------- */

function Learn({ accent }: P) {
  return (
    <Frame label={tr("Kurserna i akademin")}>
      {[0, 1, 2, 3, 4, 5].map((i) => {
        const x = 140 + (i % 3) * 320;
        const y = 200 + Math.floor(i / 3) * 250;
        const done = i < 2;
        return (
          <g key={i}>
            <rect x={x} y={y} width="280" height="200" rx="14"
              fill="rgba(255,255,255,0.025)" stroke={done ? accent : "#2a2f37"} strokeWidth="2" />
            <text x={x + 24} y={y + 48} fill={done ? accent : "#8b929e"} fontSize="17"
              fontFamily="ui-monospace, monospace">{String(i + 1).padStart(2, "0")}</text>
            <text x={x + 24} y={y + 96} fill="#e8ecf1" fontSize="20" fontFamily="ui-monospace, monospace">
              {["Systemen", "Beteckningen", "Bladet", "Att rita", "Att mängda", "Komponenter"][i]}
            </text>
            <path d={`M${x + 24} ${y + 150} H${x + 256}`} stroke="#22262d" strokeWidth="5" strokeLinecap="round" />
            <path d={`M${x + 24} ${y + 150} H${x + 24 + (done ? 232 : 70)}`} stroke={accent} strokeWidth="5" strokeLinecap="round" />
          </g>
        );
      })}
    </Frame>
  );
}

function Academy({ accent }: P) {
  return (
    <Frame label={tr("En föreläsning med sin figur och sin kontrollfråga")}>
      <rect x="140" y="170" width="520" height="440" rx="14" fill="rgba(255,255,255,0.02)" stroke="#2a2f37" />
      <g fill="#c7cdd7" fontSize="19" fontFamily="ui-monospace, monospace">
        <text x="172" y="230">{tr("KV, VV och VVC")}</text>
      </g>
      <g stroke="#22262d" strokeWidth="6" strokeLinecap="round">
        {[0, 1, 2, 3, 4].map((i) => <path key={i} d={`M172 ${280 + i * 44} H${560 - (i % 2) * 90}`} />)}
      </g>
      <rect x="700" y="170" width="380" height="240" rx="14" fill="rgba(255,255,255,0.03)" stroke={accent} strokeWidth="2" />
      <g fill="none" strokeWidth="4">
        <path d="M740 250 H1040" stroke="#60a5fa" strokeDasharray="14 8" />
        <path d="M740 300 H1040" stroke="#fb923c" strokeDasharray="14 8" />
        <path d="M1040 350 H740" stroke={accent} strokeDasharray="14 8" />
      </g>
      <g fill="#8b929e" fontSize="16" fontFamily="ui-monospace, monospace">
        <text x="700" y="470">{tr("KONTROLLFRÅGA")}</text>
      </g>
      {[0, 1, 2].map((i) => (
        <rect key={i} x="700" y={496 + i * 52} width="380" height="42" rx="8"
          fill={i === 1 ? "rgba(0, 181, 226,0.12)" : "rgba(255,255,255,0.02)"}
          stroke={i === 1 ? accent : "#2a2f37"} strokeWidth="1.6" />
      ))}
    </Frame>
  );
}

const ART: Record<string, (p: P) => any> = {
  read: Read, leader: Leader, frontier: Frontier, scale: Scale,
  cad: Cad, cadmodel: CadModel, views: Views,
  three: Three, link3d: Link3d,
  measure: Measure, bench: Bench,
  agent: Agent, chat: Chat,
  calc: Calc, tender: Tender,
  learn: Learn, academy: Academy,
};

export default function FeatureArt({ id, accent }: { id: string; accent: string }) {
  const F = ART[id];
  return F ? F({ accent }) : null;
}
