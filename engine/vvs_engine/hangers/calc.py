"""Lönsamhetskalkylen: traditionell upphängning mot SmartHangers.

Alla antaganden är inmatningar som syns och kan ändras. Standardvärdena är ett RÄKNEEXEMPEL, inte Dahls eller
någon kunds siffror, och står märkta så.

Traditionellt:   montören mäter, kapar och monterar på plats: antal x normtid x montörens timkostnad + material
SmartHangers:    lärlingen (eller verkstaden) förtillverkar: antal x produktionstid x lärlingens timkostnad,
                 montören monterar en färdig hängare: antal x montagetid x montörens timkostnad,
                 + material + uppstart + styckpris + frakt, med påslag
"""
from __future__ import annotations

from typing import Any

EXAMPLE: dict[str, Any] = {
    "label": "RÄKNEEXEMPEL - ersätt med egna värden",
    "antal": 500,
    "normtid_trad_h": 0.60,          # montörens tid per hängare på plats, traditionellt (mät, kapa, montera)
    "normtid_montage_h": 0.20,       # montörens tid per färdig SmartHanger
    "produktion_h": 0.15,            # lärlingens/verkstadens tid per hängare i produktionen
    "montor_kr_h": 650.0,
    "larling_kr_h": 380.0,
    "material_trad_kr": 140.0,       # material per hängare traditionellt (med spill)
    "material_prefab_kr": 125.0,     # material per hängare förtillverkad (kapoptimerad)
    "uppstart_kr": 15000.0,          # modell, regler, granskning per projekt
    "styckpris_kr": 0.0,             # extern prefab: pris per hängare
    "frakt_kr": 3000.0,
    "paslag_pct": 0.0,
}


def compute(inp: dict[str, Any] | None = None) -> dict[str, Any]:
    a = {**EXAMPLE, **{k: v for k, v in (inp or {}).items() if v is not None}}
    n = float(a["antal"])
    trad_arbete = n * a["normtid_trad_h"] * a["montor_kr_h"]
    trad = trad_arbete + n * a["material_trad_kr"]
    montage = n * a["normtid_montage_h"] * a["montor_kr_h"]
    produktion = n * a["produktion_h"] * a["larling_kr_h"]
    fast = n * (a["material_prefab_kr"] + a["styckpris_kr"]) + produktion + a["uppstart_kr"] + a["frakt_kr"]
    smart = (fast + montage) * (1 + a["paslag_pct"] / 100.0)
    per_st = (a["normtid_trad_h"] - a["normtid_montage_h"]) * a["montor_kr_h"] + a["material_trad_kr"] \
        - (a["material_prefab_kr"] + a["styckpris_kr"] + a["produktion_h"] * a["larling_kr_h"])
    breakeven = None
    if per_st > 0:
        breakeven = int(-(-(a["uppstart_kr"] + a["frakt_kr"]) // per_st))
    out = {
        "assumptions": a,
        "traditionell_kr": round(trad, 0),
        "smarthangers_kr": round(smart, 0),
        "besparing_kr": round(trad - smart, 0),
        "besparing_pct": round(100 * (trad - smart) / trad, 1) if trad else None,
        "frigjorda_montorstimmar": round(n * (a["normtid_trad_h"] - a["normtid_montage_h"]), 1),
        "larlingstimmar": round(n * a["produktion_h"], 1),
        "fastprisandel_pct": round(100 * fast * (1 + a["paslag_pct"] / 100.0) / smart, 1) if smart else None,
        "lonsamhetsgrans_antal": breakeven,
        "besparing_per_hangare_kr": round(per_st, 2),
    }
    sens = []
    for key, label in (("normtid_trad_h", "Normtid traditionellt"), ("normtid_montage_h", "Montagetid SmartHanger"),
                       ("montor_kr_h", "Montörens timkostnad"), ("antal", "Antal hängare")):
        for f in (0.8, 1.2):
            b = dict(a, **{key: a[key] * f})
            r = _quick(b)
            sens.append({"variabel": label, "andring_pct": round((f - 1) * 100), "besparing_kr": round(r, 0)})
    out["kanslighet"] = sens
    return out


def _quick(a: dict[str, Any]) -> float:
    n = a["antal"]
    trad = n * (a["normtid_trad_h"] * a["montor_kr_h"] + a["material_trad_kr"])
    smart = (n * (a["material_prefab_kr"] + a["styckpris_kr"] + a["produktion_h"] * a["larling_kr_h"]
                  + a["normtid_montage_h"] * a["montor_kr_h"]) + a["uppstart_kr"] + a["frakt_kr"]) * (1 + a["paslag_pct"] / 100)
    return trad - smart
