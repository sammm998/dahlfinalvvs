"""Mejlutkast för material som inte finns i materialboken eller katalogen.

Utkastet är en förfrågan inför beställningen: vad beskrivningen föreskriver, så exakt som den säger det - kod,
mängd, fabrikat, typ, RSK-nummer, specifikation - och var i beskrivningen det står, så att den som svarar kan slå
upp det själv. Det skickas aldrig av tjänsten; det öppnas i användarens egen e-post och skickas därifrån.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote


def _fmt_qty(it: dict[str, Any]) -> str:
    q = it.get("total_quantity") if it.get("total_quantity") is not None else it.get("quantity")
    if q is None:
        return it.get("quantity_text") or "mängd enligt ritning"
    q = int(q) if float(q).is_integer() else q
    return f"{q} {it.get('unit') or 'st'}"


def item_lines(it: dict[str, Any], n: int) -> list[str]:
    head = " – ".join(x for x in (it.get("code"), it.get("name")) if x)
    out = [f"{n}. {head}, {_fmt_qty(it)}"]
    maker = " ".join(x for x in (it.get("manufacturer"), ("typ " + it["type"]) if it.get("type") else "") if x)
    if maker:
        out.append(f"   Fabrikat: {maker}" + (" (eller likvärdig)" if it.get("or_equal") else ""))
    if it.get("rsk"):
        out.append(f"   RSK: {', '.join(it['rsk'])}")
    if it.get("art_nr"):
        out.append(f"   Art.nr: {', '.join(it['art_nr'])}")
    spec = it.get("spec") or {}
    if spec:
        out.append("   Specifikation: " + "; ".join(f"{k} {v}".strip() for k, v in spec.items() if v or k))
    where = f"{it.get('ama_code') or ''} {it.get('subcategory') or it.get('category') or ''}".strip()
    out.append(f"   I beskrivningen: {where}, sida {it.get('page')}")
    return out


def draft(items: list[dict[str, Any]], project: str = "", document: str = "", to: str = "",
          sender: str = "") -> dict[str, Any]:
    """Ett utkast för en eller flera poster: ämne, text och en mailto-länk som öppnar det i e-postprogrammet."""
    one = len(items) == 1
    what = (items[0].get("name") or items[0].get("code") or "artikel") if one else f"{len(items)} artiklar"
    subject = f"Förfrågan: {what}" + (f" – {project}" if project else "")
    lines = ["Hej,", ""]
    ref = f" i projektet {project}" if project else ""
    doc = f" ({document})" if document else ""
    lines.append(f"Vi räknar{ref} och den tekniska beskrivningen{doc} föreskriver "
                 + ("en artikel" if one else "följande artiklar")
                 + " som vi inte hittar i Dahls sortiment. Kan ni ge oss pris, leveranstid och artikelnummer "
                   "– eller föreslå ett likvärdigt alternativ?")
    lines.append("")
    for i, it in enumerate(items, 1):
        lines += item_lines(it, i)
        lines.append("")
    lines += ["Tack på förhand!", "", "Med vänliga hälsningar"]
    if sender:
        lines.append(sender)
    body = "\n".join(lines)
    mailto = f"mailto:{quote(to)}?subject={quote(subject)}&body={quote(body)}"
    return {"to": to, "subject": subject, "body": body, "mailto": mailto, "n": len(items)}
