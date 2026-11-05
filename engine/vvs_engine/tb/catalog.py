"""Dahls produktkatalog som sökbart index.

Katalogen är en PDF på flera hundra sidor. Den läses en gång, rad för rad och sida för sida, och det som sparas är
texten med sidnumret: tillräckligt för att slå upp ett RSK-nummer eller ett fabrikat med modell, och för att
kunna säga på vilken sida varan står.

Katalogen ligger på katalog.dahl.se, ofta bakom en bläddringsvy och ibland bakom en omdirigering (en länk ur ett
mejl går via google.com/url?q=...). find_pdf_link letar upp själva PDF:en i sidan när länken pekar på vyn.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import pymupdf


def unwrap_url(url: str) -> str:
    """En länk ur ett mejl: https://www.google.com/url?q=<riktig länk>&... -> den riktiga länken."""
    u = (url or "").strip()
    p = urlparse(u)
    if p.netloc.endswith("google.com") and p.path == "/url":
        q = parse_qs(p.query).get("q") or parse_qs(p.query).get("url")
        if q:
            return unquote(q[0])
    return u


_PDF_HREF = re.compile(r"""(?:href|src|data-url|data-pdf|"url"|"pdfUrl"|"downloadUrl")\s*[:=]\s*["']([^"']+?\.pdf(?:\?[^"']*)?)["']""", re.I)
_ANY_PDF = re.compile(r"""https?://[^\s"'<>]+?\.pdf(?:\?[^\s"'<>]*)?""", re.I)


def find_pdf_link(html: str, base: str) -> str | None:
    """Själva PDF:en i en bläddringsvy: en länk som slutar på .pdf, i ett attribut eller i sidans data."""
    for rx in (_PDF_HREF, _ANY_PDF):
        for m in rx.finditer(html or ""):
            href = m.group(1) if m.groups() else m.group(0)
            href = href.replace("\\/", "/")
            return urljoin(base, href)
    return None


def index_pdf(data: bytes, origin: str = "", max_pages: int | None = None) -> dict[str, Any]:
    """Katalogens text, rad för rad med sidnummer. Tomma rader och rader utan bokstäver eller siffror tas bort."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    pages = []
    try:
        for pn, page in enumerate(doc):
            if max_pages is not None and pn >= max_pages:
                break
            lines = []
            for raw in page.get_text("text").splitlines():
                t = re.sub(r"\s+", " ", raw).strip()
                if len(t) >= 3 and re.search(r"[0-9A-Za-zÅÄÖåäö]", t):
                    lines.append(t)
            # en rad med bara ett nummer hör ihop med raden före: "Furo 142 273x273" / "7115125"
            merged: list[str] = []
            for t in lines:
                if merged and re.fullmatch(r"[\d\s\-]{5,12}", t):
                    merged[-1] = merged[-1] + " " + t
                else:
                    merged.append(t)
            if merged:
                pages.append({"page": pn + 1, "lines": merged})
        n = len(doc)
    finally:
        doc.close()
    return {"origin": origin, "n_pages": n, "pages": pages,
            "imported_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
