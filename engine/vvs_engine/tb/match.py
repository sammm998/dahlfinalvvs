"""Beskrivningens material mot det som går att köpa: materialboken och Dahls produktkatalog.

Tre utfall, och vad de vilar på står alltid med:

  hittad   ett RSK-nummer eller artikelnummer ur beskrivningen finns i källan - samma vara, inte en lik
  möjlig   fabrikatet och modellen finns i en artikels benämning eller på en katalogsida, men inget nummer
           binder ihop dem; den som beställer väljer bland förslagen
  saknas   inget av det: varan måste efterfrågas (se mail.py)

Jämförelsen sker på hela ord. Benämningar i en materialbok är korta och fulla av förkortningar, och en
delsträngssökning på "nibe" träffar "disponibel": ett ord i beskrivningen måste vara ett ord i artikeln.
Modellnummer jämförs också hopskrivna, eftersom samma modell skrivs "AT3700" i ena källan och "AT 3700" i den
andra.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from .reader import BRANDS

WORD = re.compile(r"[0-9A-Za-zÅÄÖåäöÜü]+")
RSK7 = re.compile(r"(?<!\d)(\d{7})(?!\d)")
DIM = re.compile(r"(\d{2,4})\s*[x×]\s*(\d{2,4})")


def words(text: str) -> list[str]:
    return [w.lower() for w in WORD.findall(text or "")]


def compact_tokens(text: str) -> set[str]:
    """Orden, och varje par av intilliggande ord där ett av dem bär en siffra hopskrivet: "AT 3700" ger at3700."""
    ws = words(text)
    out = set(ws)
    for a, b in zip(ws, ws[1:]):
        if re.search(r"\d", a + b):
            out.add(a + b)
    out |= {re.sub(r"[^0-9a-zåäö]", "", t.lower()) for t in (text or "").split() if re.search(r"\d", t)}
    out.discard("")
    return out


def brand_aliases(brand: str) -> set[str]:
    """Alla stavningar en källa kan skriva fabrikatet med: Furhoff, Furhoffs, Furo; IFÖ, Ifö; Gustavsberg, Gbg."""
    if not brand:
        return set()
    out = {k for k, v in BRANDS.items() if v == brand}
    out |= set(words(brand))
    if "ifö" in out:
        out.add("ifo")
    return out


@dataclass
class Hit:
    source: str             # materialbok | katalog
    ref: str                # artikelnummer/RSK, eller "s. 214"
    name: str
    why: str
    score: float
    page: int | None = None
    price: float | None = None
    unit: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"source": self.source, "ref": self.ref, "name": self.name, "why": self.why,
                "score": round(self.score, 2), "page": self.page, "price": self.price, "unit": self.unit}


@dataclass
class _Doc:
    source: str
    ref: str
    name: str
    tokens: set[str]
    page: int | None = None
    price: float | None = None
    unit: str = ""


class MaterialIndex:
    """Ett ordindex över artiklar och katalograder. Byggs en gång; varje fråga slår upp sina ord i det."""

    def __init__(self):
        self.docs: list[_Doc] = []
        self.by_token: dict[str, list[int]] = defaultdict(list)
        self.by_ref: dict[str, list[int]] = defaultdict(list)
        self.sources: dict[str, dict[str, Any]] = {}

    def _add(self, d: _Doc, refs: Iterable[str] = ()):
        i = len(self.docs)
        self.docs.append(d)
        for t in d.tokens:
            self.by_token[t].append(i)
        for r in refs:
            self.by_ref[r].append(i)

    def add_material_book(self, rows: list[dict[str, Any]], label: str = "Materialboken"):
        """Materialbokens rader: a är artikelnumret (oftast RSK), n benämningen, p priset, e enheten."""
        n = 0
        for r in rows:
            a, name = str(r.get("a") or ""), str(r.get("n") or "")
            if not name or name.lower().startswith("disponibel artikel"):
                continue
            self._add(_Doc("materialbok", a, name, compact_tokens(name + " " + a), price=r.get("p"), unit=r.get("e") or ""),
                      refs=[a] if a else [])
            n += 1
        self.sources["materialbok"] = {"label": label, "n": n}

    def add_catalog(self, index: dict[str, Any], label: str = "Dahls produktkatalog"):
        """Katalogens rader, sida för sida (catalog.index_pdf). Varje rad är ett dokument; RSK-nummer och
        artikelnummer på raden går att slå upp exakt."""
        n = 0
        for pg in index.get("pages", []):
            for line in pg.get("lines", []):
                refs = set(RSK7.findall(line)) | {t for t in compact_tokens(line) if re.search(r"\d", t) and len(t) >= 5}
                self._add(_Doc("katalog", f"s. {pg['page']}", line, compact_tokens(line), page=pg["page"]), refs=refs)
                n += 1
        self.sources["katalog"] = {"label": label, "n": n, "pages": len(index.get("pages", [])),
                                   "imported_at": index.get("imported_at"), "origin": index.get("origin")}

    # ------------------------------------------------------------ frågan
    def match(self, item: dict[str, Any], limit: int = 3) -> dict[str, Any]:
        hits: list[Hit] = []
        exact_refs = [("RSK", r) for r in item.get("rsk") or []] + [("art.nr", a) for a in item.get("art_nr") or []]
        for kind, ref in exact_refs:
            keys = {ref, re.sub(r"[^0-9A-Za-z]", "", ref).lower(), ref.lower()}
            for k in keys:
                for i in self.by_ref.get(k, []):
                    d = self.docs[i]
                    hits.append(self._hit(d, f"{kind} {ref}", 10.0))
        if hits:
            return self._result("hittad", hits, limit)

        brand = item.get("manufacturer") or ""
        aliases = brand_aliases(brand)
        model = item.get("type") or ""
        model_toks = {t for t in compact_tokens(model) if re.search(r"\d", t) and t not in ("eller",)}
        name_toks = {t for t in words(model) if not re.search(r"\d", t) and len(t) >= 4} - aliases
        if not aliases and len(model_toks) + len(name_toks) < 2:
            return self._result("saknas", [], limit, note="Inget fabrikat eller modellnummer att söka på")
        spec_text = " ".join([item.get("text") or ""] + list((item.get("spec") or {}).values()))
        dims = {f"{a}x{b}" for a, b in DIM.findall(spec_text)}
        sizes = set(re.findall(r"\b(\d{2,3})\s*mm\b", spec_text)) | set(re.findall(r"\bDN\s*(\d{2,3})\b", spec_text))

        cand: dict[int, float] = defaultdict(float)
        why: dict[int, list[str]] = defaultdict(list)
        for t in model_toks:
            for i in self.by_token.get(t, []):
                cand[i] += 3.0
                why[i].append(t)
        for t in name_toks:
            for i in self.by_token.get(t, []):
                cand[i] += 2.0
                why[i].append(t)
        for i in list(cand):
            d = self.docs[i]
            has_brand = bool(aliases & d.tokens)
            if aliases and not has_brand:
                # Utan fabrikatet är ett modellnummer bara ett tal: 142 finns i hundra benämningar. En
                # produktserie med eget namn ("Mapress", "Ballofix") skrivs däremot ofta utan fabrikat.
                series = any(len(t) >= 6 for t in name_toks if t in d.tokens)
                if not series and (d.source == "materialbok" or cand[i] < 6):
                    del cand[i]
                    continue
            if has_brand:
                cand[i] += 2.0
            cand[i] += sum(1.0 for x in dims if x in d.tokens or x.replace("x", "") in d.tokens)
            cand[i] += sum(0.5 for x in sizes if x in d.tokens or any(t.startswith(x) for t in d.tokens if re.fullmatch(rf"{x}[a-z]?", t)))
        if not cand:
            return self._result("saknas", [], limit)
        ranked = sorted(cand.items(), key=lambda kv: (-kv[1], self.docs[kv[0]].name))
        hits = [self._hit(self.docs[i], " + ".join(sorted(set(why[i]))[:4]) or brand, sc) for i, sc in ranked[:12]]
        best = ranked[0][1]
        # fabrikat + modellnummer (5), fabrikat + serienamn (4) eller två modellnummer (6)
        status = "möjlig" if best >= 4.0 else "saknas"
        return self._result(status, hits if status == "möjlig" else [], limit)

    @staticmethod
    def _hit(d: _Doc, why: str, score: float) -> Hit:
        return Hit(d.source, d.ref, d.name, why, score, page=d.page, price=d.price, unit=d.unit)

    def _result(self, status: str, hits: list[Hit], limit: int, note: str = "") -> dict[str, Any]:
        seen, out = set(), []
        for h in sorted(hits, key=lambda h: (-h.score, h.source != "katalog", h.name)):
            k = (h.source, h.ref, h.name)
            if k in seen:
                continue
            seen.add(k)
            out.append(h.as_dict())
            if len(out) >= limit:
                break
        in_catalog = any(h["source"] == "katalog" for h in out)
        return {"status": status, "hits": out, "in_catalog": in_catalog, "note": note}


def match_items(index: MaterialIndex, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for it in items:
        m = index.match(it)
        out.append({**it, "match": m})
    return out
