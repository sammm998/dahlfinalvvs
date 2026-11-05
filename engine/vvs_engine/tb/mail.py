"""Förfrågningar om det som inte finns i materialboken eller katalogen.

En förfrågan per fabrikat. Det är så en förfrågan faktiskt skickas: till Furhoff om brunnarna, till Armatec om
ventilerna - inte en lista på åttio rader till ingen särskild. Det som saknar fabrikat samlas i en egen.

Varje förfrågan finns i tre former:

  text   kort och rak, en rad per artikel med det viktigaste; går in i en mailto-länk
  html   samma innehåll som en tabell, för e-postprogram som visar formaterad text
  eml    ett färdigt e-postutkast (RFC 5322 med HTML och text) som Outlook och Apple Mail öppnar som ett nytt
         meddelande: mottagare, ämne och tabell på plats, redo att skickas

Tjänsten skickar aldrig något själv.
"""
from __future__ import annotations

import html as _html
from email.message import EmailMessage
from email.utils import formatdate
from typing import Any
from urllib.parse import quote


def _qty(it: dict[str, Any]) -> str:
    q = it.get("total_quantity") if it.get("total_quantity") is not None else it.get("quantity")
    if q is None:
        t = (it.get("quantity_text") or "").strip()
        return "enl. ritning" if not t or t.lower().startswith("enl") else t
    q = int(q) if float(q).is_integer() else q
    return f"{q} {it.get('unit') or 'st'}"


def _spec(it: dict[str, Any]) -> str:
    parts = [f"{k} {v}".strip() for k, v in (it.get("spec") or {}).items() if v]
    if it.get("or_equal"):
        parts.append("eller likvärdig")
    return ", ".join(parts)


def _numbers(it: dict[str, Any]) -> str:
    out = [f"RSK {r}" for r in it.get("rsk") or []] + [f"Art.nr {a}" for a in it.get("art_nr") or []]
    return ", ".join(out)


def rows(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    out = []
    for n, it in enumerate(items, 1):
        out.append({
            "pos": str(n), "code": it.get("code") or "", "name": it.get("name") or "",
            "qty": _qty(it), "maker": " ".join(x for x in (it.get("manufacturer"), it.get("type")) if x),
            "spec": _spec(it), "numbers": _numbers(it),
            "where": f"s. {it.get('page')}" + (f" · {it['ama_code']}" if it.get("ama_code") else ""),
        })
    return out


def _intro(project: str, document: str, n: int) -> str:
    what = "en artikel" if n == 1 else f"{n} artiklar"
    ref = f" för {project}" if project else ""
    doc = f" ({document})" if document else ""
    return (f"Vi räknar på ett anbud{ref} och behöver pris och leveranstid för {what} ur den tekniska beskrivningen"
            f"{doc}. Har ni inte exakt artikel tar vi gärna emot förslag på likvärdig.")


def text_body(r: list[dict[str, str]], intro: str, sender: str) -> str:
    lines = ["Hej,", "", intro, ""]
    for x in r:
        head = " – ".join(v for v in (x["code"], x["name"]) if v)
        lines.append(f"{x['pos']}. {head}, {x['qty']}")
        detail = " · ".join(v for v in (x["maker"], x["spec"], x["numbers"]) if v)
        if detail:
            lines.append(f"   {detail}")
    lines += ["", "Vänligen ange pris, leveranstid och artikelnummer (RSK) per rad.", "", "Med vänliga hälsningar"]
    if sender:
        lines.append(sender)
    return "\n".join(lines)


def html_body(r: list[dict[str, str]], intro: str, sender: str) -> str:
    e = _html.escape
    head = ("<tr>" + "".join(f'<th style="text-align:{a};padding:7px 9px;border-bottom:2px solid #004976;'
                             f'font-size:12px;color:#004976">{t}</th>'
                             for t, a in (("Pos", "left"), ("Kod", "left"), ("Benämning", "left"), ("Antal", "right"),
                                          ("Fabrikat / typ", "left"), ("Specifikation", "left"), ("RSK / art.nr", "left")))
            + "</tr>")
    body = "".join(
        "<tr>" + "".join(f'<td style="padding:7px 9px;border-bottom:1px solid #e3e8ec;vertical-align:top;'
                         f'text-align:{a};font-size:13px">{e(v) or "–"}</td>'
                         for v, a in ((x["pos"], "left"), (x["code"], "left"), (x["name"], "left"), (x["qty"], "right"),
                                      (x["maker"], "left"), (x["spec"], "left"), (x["numbers"], "left")))
        + "</tr>" for x in r)
    sign = f"<br>{e(sender)}" if sender else ""
    return ('<div style="font-family:Arial,Helvetica,sans-serif;color:#1d2a33;font-size:14px;line-height:1.5">'
            f"<p>Hej,</p><p>{e(intro)}</p>"
            f'<table style="border-collapse:collapse;width:100%;margin:10px 0 14px">{head}{body}</table>'
            "<p>Vänligen ange pris, leveranstid och artikelnummer (RSK) per rad.</p>"
            f"<p>Med vänliga hälsningar{sign}</p></div>")


def draft(items: list[dict[str, Any]], project: str = "", document: str = "", to: str = "",
          sender: str = "", maker: str = "") -> dict[str, Any]:
    """En förfrågan för de här posterna: ämne, text, html, mailto och ett e-postutkast (eml)."""
    r = rows(items)
    one = len(items) == 1
    what = (items[0].get("name") or items[0].get("code") or "artikel") if one else f"{len(items)} artiklar"
    subject = "Prisförfrågan" + (f" {maker}" if maker else "") + f": {what}" + (f" – {project}" if project else "")
    intro = _intro(project, document, len(items))
    text = text_body(r, intro, sender)
    html = html_body(r, intro, sender)
    msg = EmailMessage()
    msg["Subject"] = subject
    if to:
        msg["To"] = to
    if sender:
        msg["From"] = sender
    msg["Date"] = formatdate(localtime=True)
    msg["X-Unsent"] = "1"                  # Outlook öppnar filen som ett nytt meddelande att skicka
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return {"to": to, "subject": subject, "body": text, "text": text, "html": html, "rows": r, "maker": maker,
            "mailto": f"mailto:{quote(to)}?subject={quote(subject)}&body={quote(text)}", "n": len(items),
            "eml": msg.as_string()}


def drafts_by_maker(items: list[dict[str, Any]], **kw) -> list[dict[str, Any]]:
    """En förfrågan per fabrikat, störst först; det utan fabrikat sist."""
    groups: dict[str, list] = {}
    for it in items:
        groups.setdefault(it.get("manufacturer") or "", []).append(it)
    order = sorted(groups, key=lambda m: (m == "", -len(groups[m]), m.lower()))
    return [draft(groups[m], maker=m or "Övrigt", **kw) for m in order]
