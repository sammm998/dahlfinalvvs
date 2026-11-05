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

import bisect
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
        self._sorted: list[str] | None = None

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
        art = " ".join(item.get("art_nr") or [])
        model_toks = {t for t in compact_tokens(model + " " + art) if re.search(r"\d", t) and len(t) >= 3}
        # ett kort serienummer (Eminent 55) räknas bara tillsammans med fabrikatet
        short_nums = {t for t in words(model) if re.fullmatch(r"\d{2}", t)} if aliases else set()
        series = {t for t in words(model) if not re.search(r"\d", t) and len(t) >= 4} - aliases - {"eller", "typ"}
        pipe = _is_pipe(item)
        # en lednings namn är vad den för ("spillvatten till oljeavskiljare"), inte vad den är
        stems = set() if pipe else _stems(item)
        material = {w for w in words(_text_of(item) + " " + model) if w in MATERIAL_WORDS}
        sizes = _sizes(item)
        dims = {f"{a}x{b}" for a, b in DIM.findall(_text_of(item))}
        if not aliases and not model_toks and not series and not any(len(x) >= 12 for x in stems):
            return self._result("saknas", [], limit, note="Inget fabrikat, modellnummer eller entydigt varunamn att söka på")

        cand: dict[int, float] = defaultdict(float)
        why: dict[int, set] = defaultdict(set)
        strong: dict[int, bool] = defaultdict(bool)

        def hit(i, w, label, is_strong=False):
            cand[i] += w
            why[i].add(label)
            strong[i] = strong[i] or is_strong

        for t in model_toks:
            lettered = bool(re.search(r"[a-zåäö]", t))
            for i in self.by_token.get(t, []):
                hit(i, 4.0, t, lettered)
            if len(t) >= 4:
                # "AT 4003A" är "AT 4003A25" i boken: storleken skriven ihop med modellen
                for tok in self._with_prefix(t):
                    if tok != t and re.fullmatch(re.escape(t) + r"\d{1,3}[a-z]?", tok):
                        for i in self.by_token.get(tok, []):
                            hit(i, 3.0, t, lettered)
        if pipe and aliases and not model_toks:
            # en ledning skrivs med fabrikat och material ("Wafix PP"), sällan med modell: fabrikatets rör
            for a in aliases:
                for i in self.by_token.get(a, []):
                    hit(i, 1.0, a, True)
        for t in short_nums:
            for i in self.by_token.get(t, []):
                hit(i, 1.5, t)
        for t in series:
            for i in self.by_token.get(t, []):
                hit(i, 3.0 if len(t) >= 6 else 2.5, t, len(t) >= 6)
        for st in stems:
            long = len(st) >= 12
            for tok in self._with_prefix(st):
                for i in self.by_token.get(tok, []):
                    hit(i, (4.0 if long and not aliases else 2.0), st, long and not aliases)
        for i in list(cand):
            d = self.docs[i]
            has_brand = bool(aliases & d.tokens)
            if aliases and not has_brand and not strong[i]:
                # Utan fabrikatet är ett tal bara ett tal: 142 finns i hundra benämningar. Ett modellnummer med
                # bokstäver (AT3700, S600017) eller ett eget serienamn (Mapress, Ballofix) räcker ensamt.
                del cand[i]
                continue
            if not aliases and not strong[i]:
                del cand[i]
                continue
            if has_brand:
                cand[i] += 2.0
                why[i].add(brand)
            lead = _lead_size(d.name)
            if lead and lead in sizes:
                cand[i] += 2.5                      # "25 AT 4003A25": rätt storlek först i benämningen
                why[i].add(f"storlek {lead}")
            cand[i] += sum(1.0 for x in dims if x in d.tokens)
            if pipe:
                # en ledning är raka rör - "15x1,2 Mapress elförz rör 3 m" - inte ett T-rör, en böj eller en fördelare
                straight = ("rör" in d.tokens or any(t.endswith("rör") for t in d.tokens)) \
                    and not (FITTING_WORDS & d.tokens) and re.match(r"^\d+(?:x[\d,]+)?\s", d.name or "")
                if not straight:
                    del cand[i]
                    continue
                cand[i] += 1.0
            cand[i] += sum(1.0 for w in material if w in d.tokens or any(t.startswith(w) for t in d.tokens))
            if "f" in d.tokens:
                cand[i] -= 2.5                      # "lock f rensrör": ett tillbehör för varan, inte varan
            if stems and not strong[i] and not (aliases & d.tokens):
                cand[i] -= 1.0
        if not cand:
            return self._result("saknas", [], limit)
        ranked = sorted(cand.items(), key=lambda kv: (-kv[1], self.docs[kv[0]].name))
        hits = [self._hit(self.docs[i], " + ".join(sorted(why[i]))[:80] or brand, sc) for i, sc in ranked[:40]]
        best = ranked[0][1]
        status = "möjlig" if best >= 4.0 else "saknas"
        return self._result(status, hits if status == "möjlig" else [], limit, sizes=sizes, models=model_toks)

    def _with_prefix(self, prefix: str) -> list[str]:
        """Index tokens that start with prefix (sorted lookup, not a scan)."""
        if self._sorted is None:
            self._sorted = sorted(self.by_token)
        lo = bisect.bisect_left(self._sorted, prefix)
        out = []
        for tok in self._sorted[lo:lo + 400]:
            if not tok.startswith(prefix):
                break
            out.append(tok)
        return out

    @staticmethod
    def _hit(d: _Doc, why: str, score: float) -> Hit:
        return Hit(d.source, d.ref, d.name, why, score, page=d.page, price=d.price, unit=d.unit)

    def _result(self, status: str, hits: list[Hit], limit: int, note: str = "", sizes: set | None = None,
                models: set | None = None) -> dict[str, Any]:
        seen, ranked = set(), []
        for h in sorted(hits, key=lambda h: (-h.score, h.source != "katalog", h.name)):
            k = (h.source, h.ref, h.name)
            if k in seen:
                continue
            seen.add(k)
            ranked.append(h)
        out = [h.as_dict() for h in ranked[:limit]]
        in_catalog = any(h.source == "katalog" for h in ranked[:limit])
        return {"status": status, "hits": out, "in_catalog": in_catalog, "note": note,
                "rsk": _rsk_of(status, ranked, sizes or set(), models or set())}


def _text_of(item: dict[str, Any]) -> str:
    return " ".join([item.get("text") or ""] + [f"{k} {v}" for k, v in (item.get("spec") or {}).items()])


# materialord som skiljer varianter av samma serie åt: Mapress i koppar eller elförzinkat
MATERIAL_WORDS = {"koppar", "elförz", "elförzinkad", "elförzinkade", "rostfri", "rostfritt", "rfri", "krom", "förkromad",
                  "pp", "pem", "pex", "pvc", "gjutjärn", "mässing", "rödgods", "stål", "epoxi", "massa", "btg", "klinker"}

FITTING_WORDS = {"t", "böj", "böjar", "muff", "muffar", "fördelare", "radiatorfördelare", "koppling", "reducering",
                 "övergång", "grenrör", "proppar", "propp", "lock", "manschett", "nippel", "tee", "rensrör"}

STOP = {"golvmonterade", "ytbehandlade", "sammansatta", "elektrisk", "standardiserade", "ledningar", "rostfritt",
        "vätskesystem", "porslin", "tappkallvatten", "tappvarmvatten", "spillvatten", "tryckluft", "avstängningsventiler"}


def _stems(item: dict[str, Any]) -> set[str]:
    """Varunamnets ord som stammar: "Tvättrännor" -> tvättränn, som är början på "tvättränna" i boken."""
    out = set()
    for w in words(item.get("name") or ""):
        if len(w) < 5 or w in STOP or re.search(r"\d", w):
            continue
        for end in ("orna", "arna", "erna", "or", "ar", "er", "na"):
            if w.endswith(end) and len(w) - len(end) >= 5:
                w = w[: -len(end)]
                break
        out.add(w)
    if (item.get("name") or "").lower().startswith("avstängningsventil"):
        out.add("kulventil")           # en avstängningsventil till ett tvättställ är en kulventil i boken
    return out


def _sizes(item: dict[str, Any]) -> set[str]:
    """De storlekar posten skriver: DN25, "Ansl. nr. 25", "Utloppsdimension 110mm", 1200 x 451 mm."""
    t = _text_of(item)
    out = set(re.findall(r"\bDN\s*(\d{2,3})\b", t, re.I))
    out |= set(re.findall(r"(?:ansl\.?\s*nr\.?|dimension|utloppsdimension|anslutning)\s*:?\s*(\d{2,3})\b", t, re.I))
    for a, b in DIM.findall(t):
        out |= {a, b}
    spec = item.get("spec") or {}
    for k, v in spec.items():
        if re.fullmatch(r"\s*(\d{2,3})\s*", v or ""):
            out.add(v.strip())
    return out


def _is_pipe(item: dict[str, Any]) -> bool:
    return (item.get("subcategory") or item.get("category") or "").lower().startswith("ledningar")


def _lead_size(name: str) -> str | None:
    m = re.match(r"^(\d{2,3})(?:x[\d,]+)?\s", name or "")
    return m.group(1) if m else None


def _rsk_of(status: str, ranked: list[Hit], sizes: set, models: set = frozenset()) -> dict[str, Any] | None:
    """Ett RSK-nummer att föreslå när beskrivningen inte skriver något.

    Bara ur materialboken (dess artikelnummer är RSK-nummer). Är bästa träffen ensam bäst får den sitt nummer
    som förslag. Skiljer sig de bästa träffarna bara åt i storlek - samma artikel i 15, 20 och 25 - och
    beskrivningen inte säger vilken, föreslås inget nummer: storlekarna listas, och den som beställer väljer."""
    if status != "möjlig":
        return None
    book = [h for h in ranked if h.source == "materialbok" and re.fullmatch(r"\d{7}", h.ref or "")]
    if not book:
        return None
    top = book[0]
    same = [h for h in book if abs(h.score - top.score) < 0.01]
    family = lambda n: re.sub(r"^\d{2,3}(?:x[\d,]+)?\s+|\d{2,3}$", "", n).strip().lower()
    # storlekarna tas bland allt som ligger nära toppen: samma ventil finns i två serier (AT 3700 och AT 3700
    # Viridi), och bara den ena serien fick hela storleksskalan
    near = [h for h in book if top.score - h.score <= 2.0 and not re.search(r"(?<!\w)f(?!\w)", h.name.lower())
            and (not models or any(m in (h.why or "") for m in models))]   # varianter delar postens modell
    leads = {_lead_size(h.name) for h in near} - {None}
    if len(same) == 1 and not (len(book) > 1 and _lead_size(top.name) and not sizes
                               and _lead_size(book[1].name) not in (None, _lead_size(top.name))
                               and abs(book[1].score - top.score) < 1.0):
        return {"value": top.ref, "kind": "förslag", "name": top.name}
    if len(leads) >= 2 or len({family(h.name) for h in same}) == 1:
        # samma vara i flera storlekar, och beskrivningen säger inte vilken: storlekarna, inte ett nummer
        pool = near if len(leads) >= 2 else book
        pool = sorted({h.ref: h for h in pool}.values(), key=lambda h: (int(_lead_size(h.name) or 0), h.name))
        variants = [{"rsk": h.ref, "name": h.name, "size": _lead_size(h.name)} for h in pool][:16]
        return {"value": None, "kind": "storlek", "name": family(top.name), "variants": variants}
    return {"value": top.ref, "kind": "förslag", "name": top.name, "alternatives": [h.ref for h in same[1:6]]}


def match_items(index: MaterialIndex, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for it in items:
        m = index.match(it)
        out.append({**it, "match": m})
    return out
