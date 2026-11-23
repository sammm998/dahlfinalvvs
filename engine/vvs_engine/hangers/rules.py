"""Regelmotorn: klamringsavstånd, placering, last, hängarens geometri, infästning, miljö och tolerans.

Reglerna är data, inte kod. De ligger i en versionerad regeluppsättning som en tekniskt ansvarig redigerar och
verifierar i tjänsten. Värdena nedan är EXEMPEL för att kunna köra systemet - de är inte verifierade och ska
ersättas med tillverkarens (Bevego/Novipro, Walraven, Sikla, rörtillverkaren) och projektets egna värden innan
något frisläpps till produktion. Tjänsten släpper inte en hängare till produktion på en overifierad uppsättning.
"""
from __future__ import annotations

import copy
import math
from typing import Any

DEFAULT: dict[str, Any] = {
    "version": 1,
    "name": "Exempelregler (ej verifierade)",
    "verified": False,
    "verified_by": None,
    "verified_at": None,
    "note": "EXEMPEL - värdena är inte verifierade. Ersätt med tillverkarens och projektets värden och verifiera.",
    # klamringsavstånd: största avstånd mellan upphängningar, horisontellt rör, mm. [största DN, avstånd]
    "spacing": {
        "koppar": [[15, 1200], [22, 1800], [35, 2400], [54, 2700], [999, 3000]],
        "stål": [[20, 2000], [32, 2500], [50, 3000], [80, 3500], [999, 4000]],
        "rostfritt": [[22, 1800], [35, 2400], [54, 2700], [999, 3000]],
        "plast": [[16, 500], [20, 600], [32, 750], [50, 900], [75, 1100], [110, 1400], [999, 1600]],
        # Walraven, "Klammeravstånd för plaströr (enligt DIN EN 806-4:2010-06)", bild A (glidklammer, utan
        # rörförstärkning), per ytterdiameter: kallvatten och varmvatten. Källa i "sources".
        "plast_kv": [[16, 750], [20, 800], [25, 850], [32, 1000], [40, 1100], [50, 1250], [63, 1400], [75, 1500],
                     [90, 1650], [110, 1900]],
        "plast_vv": [[16, 400], [20, 500], [25, 600], [32, 650], [40, 800], [50, 1000], [63, 1200], [75, 1300],
                     [90, 1450], [110, 1600]],
        "gjutjärn": [[999, 3000]],
        "okänt": [[999, 1200]],
    },
    "placement": {
        "end_max": 500,                 # mm från rörets ände till första upphängningen
        "fitting_max": 300,             # mm från en ventil eller rördel till närmaste upphängning
        "vertical_ratio": 0.15,         # |dz|/längd över detta: stigare, ingen takhängare
        "min_pipe_length": 300,         # kortare rör hängs inte för sig
        "parallel_angle_deg": 5,        # rör i samma stråk är parallella inom detta
        "run_max_width": 1200,          # största avstånd i sidled mellan rören på ett takjärn
        "level_tolerance": 150,         # rör vars höjd skiljer mer än så hamnar på var sin nivå
    },
    "geometry": {
        "profile": "Takjärn 41x41 (U-profil)",
        "profile_height": 41,
        "overhang": 50,                 # takjärnet sticker ut så här mycket utanför yttersta röret
        "hole_step": 25,                # hålbilden i takjärnet
        "length_step": 50,              # kaplängden avrundas uppåt till detta
        "clamp_base": 30,               # klammerns höjd under rörets underkant (montageplatta + mutter)
        "rod_allowance": 40,            # gängstången sticker ut under takjärnet (mutter, bricka)
        "rod_step": 10,                 # gängstångens kaplängd avrundas uppåt till detta
        "min_rod": 50,
        "max_rod": 2500,
    },
    "load": {
        # bärförmåga per gängstång (kN) - EXEMPEL
        "rod_capacity_kn": {"M8": 0.6, "M10": 1.0, "M12": 1.5, "M16": 3.0},
        "profile_capacity_kn": 2.0,     # takjärnets bärförmåga mitt på för spännvidden ovan - EXEMPEL
        "safety_factor": 1.5,
        "wall_mm": {"koppar": 1.2, "stål": 2.9, "rostfritt": 1.2, "plast": 3.0, "gjutjärn": 4.0, "okänt": 2.0},
        "density": {"koppar": 8.9, "stål": 7.85, "rostfritt": 7.9, "plast": 1.0, "gjutjärn": 7.2, "okänt": 7.85},
        "insulation_kg_m": 0.3,         # isolering per meter (för system som isoleras)
        "insulated_systems": ["VV", "VVC", "KV", "KB", "VS", "VÄRME"],
    },
    "fixing": {
        "ceiling": "Betong",            # betong / stål / trä / håldäck
        "anchor": {"Betong": "Expanderankare M10", "Håldäck": "Håldäcksankare M10",
                   "Stål": "Balkklammer M10", "Trä": "Träskruv med gängad hylsa M10"},
        "slab_thickness": 250,          # mm: bjälklagets tjocklek när takhöjden räknas ur nästa våning
    },
    "environment": {"default": "Inne torrt", "finish": {"Inne torrt": "Elförzinkat", "Inne fuktigt": "Varmförzinkat",
                                                          "Ute": "Varmförzinkat / rostfritt"}},
    "tolerance": {"position_mm": 10, "height_mm": 10},
    "stock": {"profile_mm": 3000, "rod_mm": 2000, "kerf_mm": 3},
    # kravunderlaget: gränsvärdena för V1 och V2 är förslag som stäms av med en BIM-samordnare
    "validation": {"origin_mm": 10, "storey_mm": 5, "zone_model_share": 0.6, "zone_model_min_run": 20},
    # gängstångens formel: L = Z_UK - Z_CL - D/2 - t_iso - h_klammer - h_ankare, kapad till L + justermarginal
    "formula": {
        "clamp_height": [[22, 30], [54, 40], [110, 55], [200, 70], [9999, 90]],   # [största ytterdiameter, mm]
        "adjust_margin_mm": 20,
        "max_rod_by_size": {"M8": 1500, "M10": 2000, "M12": 2500, "M16": 3000},
        "konsol_text": "Väggkonsol/profil i stället för gängstång",
    },
    # ankare per bjälklagstyp (K-modellen eller valt per zon): artikel, bärförmåga och höjd - EXEMPEL
    "anchors": {
        "Platsgjutet": {"text": "Expanderankare {size} för betong", "capacity_kn": 2.0, "height_mm": 15},
        "HD/F": {"text": "HD/F-ankare {size} (borras mellan kanaler)", "capacity_kn": 1.5, "height_mm": 15,
                 "note": "HD/F: borra endast mellan kanalerna - kontrollera läget mot elementritningen"},
        "KL-trä": {"text": "Träskruv med gängad hylsa {size}", "capacity_kn": 1.2, "height_mm": 20},
        "Trapetsplåt": {"text": "Trapetsplåtfäste {size}", "capacity_kn": 0.8, "height_mm": 25},
        "Stålbalk": {"text": "Balkklammer {size}", "capacity_kn": 1.5, "height_mm": 30},
    },
    "default_slab_type": "Platsgjutet",
    # punktlaster (kg) från ventiler och armaturer per dimension, när modellen inte anger vikt - EXEMPEL
    "point_loads": {"ventil": [[25, 1.5], [50, 5.0], [80, 12.0], [150, 30.0], [9999, 60.0]]},
    "clearances": {"opening_mm": 100, "beam_edge_mm": 100, "channel_snap_mm": 300, "collision_mm": 10},
    "sources": {
        "plast_kv": "Walraven datablad Klammeravstånd för plaströr enligt DIN EN 806-4:2010-06, bild A, kallvatten "
                    "(https://files.walraven.com/repository/rnd/documents/Fixing-Distances-Plastic-Pipes-Datasheet-SE.pdf)",
        "plast_vv": "Walraven datablad Klammeravstånd för plaströr enligt DIN EN 806-4:2010-06, bild A, varmvatten "
                    "(https://files.walraven.com/repository/rnd/documents/Fixing-Distances-Plastic-Pipes-Datasheet-SE.pdf)",
        "koppar": "EXEMPEL - ej från källa", "stål": "EXEMPEL - ej från källa", "rostfritt": "EXEMPEL - ej från källa",
        "load": "EXEMPEL - Bevegos bärförmåga gick inte att hämta",
    },
    # artikelnummer som delarna får på materiallistan; nyckel "del storlek längd"
    "articles": {
        "gängstång M10 2000": {"art": "51721010", "supplier": "Bevego",
                               "source": "Bevego Upphängningssystem NP-101-2024 (enligt sökresultat - kontrollera mot katalogen)"},
        "gängstång M8 2000": {"art": "51721008", "supplier": "Bevego",
                              "source": "Bevego Upphängningssystem NP-101-2024 (enligt sökresultat - kontrollera mot katalogen)"},
    },
    "hot_systems": ["VV", "VVC", "VS", "VP", "VÄRME", "KYL"],
    "packing": {"max_per_kolli": 20, "max_kg_per_kolli": 25.0, "max_volume_l_per_kolli": 60.0},
}


def default() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT)


def merged(rules: dict[str, Any] | None) -> dict[str, Any]:
    """Uppsättningen med standardvärden där den saknar något (en äldre version)."""
    out = default()
    for k, v in (rules or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def material_key(text: str | None) -> str:
    t = (text or "").lower()
    for key, words in (("rostfritt", ("rostfri", "inox", "syrafast", "rf ", "1.4301", "1.4306", "1.4401", "1.4404", "316l", "304l")),
                       ("koppar", ("koppar", "copper", "cu ", "en 1057", "en1057", "r290", "r250", "r220")),
                       ("plast", ("pex", "pp", "pe ", "pe-", "pvc", "plast", "abs", "pb ", "alupex", "polyeten", "lk pal",
                                  " pal ", "rir", "universalrör", "markavlopp", "pe-xa", "pe100", "pe80")),
                       ("gjutjärn", ("gjutjärn", "sml", "cast iron", "ma,", "ma-rör")),
                       ("stål", ("stål", "steel", "galv", "förzinkat", "svart", "press", "tuber", "en10296", "en 10296",
                                 "en10255", "en 10255", "en10220", "gänga"))):
        if any(w in t + " " for w in words):
            return key
    return "okänt"


def spacing(rules: dict[str, Any], material: str, dn: float | None, system: str = "", od: float | None = None) -> tuple[int, str]:
    """Största klamringsavstånd (mm) och var det står. Plaströr läses per ytterdiameter, kall- eller varmvatten
    efter systemet, när uppsättningen har tabellerna för det."""
    if material == "plast":
        hot = any((system or "").upper().replace(" ", "").startswith(s) for s in rules.get("hot_systems") or [])
        key = "plast_vv" if hot else "plast_kv"
        t = rules["spacing"].get(key)
        if t and (od or dn):
            d = od or dn
            for top, s in t:
                if d <= top:
                    src = (rules.get("sources") or {}).get(key, "")
                    return int(s), f"plast {'varmvatten' if hot else 'kallvatten'} D≤{top}: {s} mm - {src.split(' (')[0]}"
            return int(t[-1][1]), f"plast D>{t[-1][0]}: {t[-1][1]} mm (största i tabellen)"
    table = rules["spacing"].get(material) or rules["spacing"]["okänt"]
    d = dn or 0
    for top, s in table:
        if d <= top:
            return int(s), f"{material} DN≤{top}: {s} mm (regel v{rules.get('version')})"
    return int(table[-1][1]), f"{material}: {table[-1][1]} mm"


def kg_per_m(rules: dict[str, Any], material: str, od: float | None, system: str = "") -> float:
    """Vattenfyllt rör per meter, med isolering för de system som isoleras."""
    od = float(od or 22.0)
    L = rules["load"]
    t = min(L["wall_mm"].get(material, 2.0), od / 4)
    steel = math.pi * (od - t) * t * L["density"].get(material, 7.85) / 1000.0     # kg/m
    water = math.pi * ((od - 2 * t) / 2) ** 2 / 1000.0
    ins = L["insulation_kg_m"] if any(system.upper().startswith(s) for s in L["insulated_systems"]) else 0.0
    return round(steel + water + ins, 3)


def rod_size(rules: dict[str, Any], load_kn: float) -> str | None:
    need = load_kn * rules["load"]["safety_factor"]
    for size, cap in sorted(rules["load"]["rod_capacity_kn"].items(), key=lambda kv: kv[1]):
        if cap >= need:
            return size
    return None


def table(rows: list, value: float | None, default=None):
    """Värdet ur en tabell [[största, värde], ...] för ett mått."""
    if value is None:
        return default
    for top, v in rows or []:
        if value <= top:
            return v
    return rows[-1][1] if rows else default


def anchor_for(rules: dict[str, Any], slab: str | None, size: str) -> dict[str, Any]:
    st = slab or rules.get("default_slab_type") or "Platsgjutet"
    a = (rules.get("anchors") or {}).get(st) or (rules.get("anchors") or {}).get("Platsgjutet") or {}
    return {"slab_type": st, "text": str(a.get("text") or "Takinfästning {size}").replace("{size}", size),
            "capacity_kn": a.get("capacity_kn"), "height_mm": float(a.get("height_mm") or 0), "note": a.get("note")}
