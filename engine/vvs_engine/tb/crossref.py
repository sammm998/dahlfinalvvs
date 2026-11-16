"""Korsreferenslistan för rör: när det förskrivna fabrikatet saknas, vår likvärdiga i samma material och dimension.

Valregeln för rör, i den här ordningen:
  a) exakt fabrikat och dimension finns i katalogen: det väljs (matchningen, match.py)
  b) fabrikatet saknas men material och dimension finns i korsreferenslistan: vår likvärdiga produkt
  c) inget av det: raden flaggas för manuell hantering - aldrig en tyst gissning

Listan är Dahls egen (en fil med en rad per kombination): Material, Dimension, Fabrikat (förskrivet), Serie,
RSK (vår artikel), Benämning, och gärna "Pris saknas" för dimensioner vi vet saknar pris (t.ex. vissa MA-press,
Cupori) - de flaggas direkt.
"""
from __future__ import annotations

import re
from typing import Any

from .rsk import normalize as rsk_norm

MATERIALS = {
    "koppar": ("koppar", "kopparrör", "cu"), "rostfritt": ("rostfri", "rostfritt", "syrafast", "rf"),
    "förzinkat": ("förzinkat", "elförzinkat", "elförz", "galv"), "pex": ("pex",), "pp": ("pp", "polypropen"),
    "pe": ("pe", "pem", "polyeten"), "pvc": ("pvc",), "gjutjärn": ("gjutjärn", "sml", "segjärn"),
    "stål": ("stål", "svartstål", "kolstål"), "komposit": ("komposit", "alupex", "flerskikt"),
}


def material_of(text: str) -> str | None:
    t = " " + re.sub(r"[^a-zåäö0-9]+", " ", (text or "").lower()) + " "
    for key, words in MATERIALS.items():
        if any(f" {w} " in t or (len(w) > 3 and w in t) for w in words):
            return key
    return None


def dims_of(text: str) -> list[str]:
    """Dimensioner som de skrivs: 22x1,0 -> "22", DN25 -> "25", 110 mm -> "110"."""
    t = (text or "").lower().replace(",", ".")
    out = re.findall(r"\b(\d{2,3})\s*x\s*\d+(?:\.\d+)?", t)
    out += re.findall(r"\bdn\s*(\d{2,3})\b", t)
    out += re.findall(r"\b(\d{2,3})\s*mm\b", t)
    return list(dict.fromkeys(out))


def _norm_dim(v: Any) -> str:
    m = re.search(r"(\d{2,3})", str(v or ""))
    return m.group(1) if m else ""


def lookup(material: str | None, dim: str | None, maker: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Raden i listan för material och dimension; samma förskrivna fabrikat går före en rad för vilket som helst."""
    if not rows or not material or not dim:
        return None
    hits = [r for r in rows if material_of(str(r.get("material") or "")) == material and _norm_dim(r.get("dimension")) == dim]
    if not hits:
        return None
    mk = (maker or "").lower()
    hits.sort(key=lambda r: (0 if mk and mk in str(r.get("fabrikat") or "").lower() else 1))
    h = hits[0]
    return {"rsk": rsk_norm(str(h.get("rsk") or "")) or str(h.get("rsk") or ""), "name": h.get("benamning") or "",
            "material": material, "dimension": dim, "price_missing": bool(h.get("pris_saknas")),
            "for": h.get("fabrikat") or ""}


def for_item(item: dict[str, Any], rows: list[dict[str, Any]], dim: str | None = None) -> dict[str, Any] | None:
    text = " ".join(str(item.get(k) or "") for k in ("name", "type", "text")) + " " + \
        " ".join(f"{k} {v}" for k, v in (item.get("spec") or {}).items())
    material = material_of(text)
    dims = [dim] if dim else dims_of(text)
    for d in dims:
        hit = lookup(material, d, item.get("manufacturer") or "", rows)
        if hit:
            return hit
    return None
