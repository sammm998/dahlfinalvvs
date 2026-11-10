"""En IFC-modell läst till VVS-material: varje produkttyp en post, med antal per våning och fabrikat.

IFC är strukturerad data. Antalet är antalet objekt i modellen och ingenting annat; en rörlängd är summan av
modellens egna längder (Qto/Pset "Length"). Ingenting gissas: saknar ett rör sin längd räknas det i styck och
det står så.

Läsaren är egen och liten (STEP/ISO 10303-21, IFC2X3 och IFC4) och läser bara det den behöver:

  objekten      sanitet, armaturer och ventiler, rör och rördelar, brunnar, pumpar, beredare, värme, ventilation
                - och de "proxy"-objekt som Revit exporterar för VVS-familjer utan egen IFC-klass
  typen         IfcRelDefinesByType: Revits "familj:typ" ("...Franke_Disko:Franke KBX 210-34, 510 mm")
  våningen      IfcRelContainedInSpatialStructure -> IfcBuildingStorey, annars egenskapen StoreyName
  egenskaperna  IfcRelDefinesByProperties: Manufacturer, Model, ArticleNumber, System, Size, Length ...

Ut kommer poster i samma form som en teknisk beskrivnings (vvs_engine.tb.reader.Item), så att samma matchning
mot Dahls katalog, samma RSK-förslag, mejlutkast och export gäller.
"""
from __future__ import annotations

import io
import re
import zipfile
from collections import Counter, defaultdict
from typing import Any, Iterable

from ..tb.reader import BRANDS, NOT_BRANDS

# ---------------------------------------------------------------- STEP

_REC = re.compile(r"^#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\)\s*;\s*$", re.S)


def _records(text: Iterable[str]) -> dict[int, tuple[str, str]]:
    """#id -> (KLASS, råa argument). En post kan gå över flera rader."""
    out: dict[int, tuple[str, str]] = {}
    buf = ""
    data = False
    for raw in text:
        line = raw.strip()
        if not data:
            data = line.startswith("DATA;")
            continue
        if not line:
            continue
        buf = f"{buf} {line}" if buf else line
        if not buf.endswith(";") or (buf.count("'") % 2):
            continue
        m = _REC.match(buf)
        if m:
            out[int(m.group(1))] = (m.group(2), m.group(3))
        buf = ""
    return out


def _decode(s: str) -> str:
    """IFC-strängar: \\X\\E5 (Latin-1), \\X2\\00E5\\X0\\ (UTF-16), \\S\\e och '' för '."""
    def x2(m):
        h = m.group(1)
        return "".join(chr(int(h[i:i + 4], 16)) for i in range(0, len(h), 4))
    s = re.sub(r"\\X2\\([0-9A-Fa-f]+)\\X0\\", x2, s)
    s = re.sub(r"\\X\\([0-9A-Fa-f]{2})", lambda m: bytes([int(m.group(1), 16)]).decode("latin-1"), s)
    s = re.sub(r"\\S\\(.)", lambda m: chr(ord(m.group(1)) + 128), s)
    return s.replace("''", "'")


def _args(raw: str) -> list:
    """Argumenten som en lista: strängar, '#12', tal, '$', '.ENUM.', och listor som listor."""
    out: list = []
    stack = [out]
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if c == "'":
            j = i + 1
            while j < n:
                if raw[j] == "'":
                    if j + 1 < n and raw[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            stack[-1].append(_decode(raw[i + 1:j]))
            i = j + 1
        elif c == "(":
            new: list = []
            stack[-1].append(new)
            stack.append(new)
            i += 1
        elif c == ")":
            stack.pop()
            i += 1
        elif c in ", ":
            i += 1
        else:
            j = i
            while j < n and raw[j] not in ",()":
                j += 1
            tok = raw[i:j].strip()
            m = re.match(r"^[A-Z0-9_]+$", tok)
            if m and j < n and raw[j] == "(" and not tok.isdigit():
                # ett typat värde: IFCLABEL('x'), IFCLENGTHMEASURE(12.)
                k, depth = j, 0
                while k < n:
                    depth += raw[k] == "("
                    depth -= raw[k] == ")"
                    if depth == 0:
                        break
                    k += 1
                inner = _args(raw[j + 1:k])
                stack[-1].append(inner[0] if inner else None)
                i = k + 1
                continue
            try:
                stack[-1].append(float(tok) if re.match(r"^-?\d", tok) else tok)
            except ValueError:
                stack[-1].append(tok)
            i = j
    return out


def _ref(v) -> int | None:
    return int(v[1:]) if isinstance(v, str) and v.startswith("#") and v[1:].isdigit() else None


# ---------------------------------------------------------------- vad som är VVS

CLASSES: dict[str, tuple[str, str]] = {
    # IFC-klass -> (kategori, standardnamn)
    "IFCSANITARYTERMINAL": ("Sanitet", "Sanitetsprodukt"),
    "IFCWASTETERMINAL": ("Brunnar och avlopp", "Brunn"),
    "IFCVALVE": ("Armaturer och ventiler", "Ventil"),
    "IFCFLOWCONTROLLER": ("Armaturer och ventiler", "Ventil"),
    "IFCFLOWTERMINAL": ("Sanitet", "Tappställe"),
    "IFCPIPESEGMENT": ("Rör", "Rör"),
    "IFCPIPEFITTING": ("Rördelar", "Rördel"),
    "IFCFLOWFITTING": ("Rördelar", "Rördel"),
    "IFCFLOWSEGMENT": ("Rör", "Rör"),
    "IFCPUMP": ("Pumpar", "Pump"),
    "IFCTANK": ("Beredare och tankar", "Tank"),
    "IFCFLOWSTORAGEDEVICE": ("Beredare och tankar", "Tank"),
    "IFCBOILER": ("Värme", "Panna"),
    "IFCSPACEHEATER": ("Värme", "Radiator"),
    "IFCHEATEXCHANGER": ("Värme", "Värmeväxlare"),
    "IFCFLOWMETER": ("Armaturer och ventiler", "Mätare"),
    "IFCINTERCEPTOR": ("Brunnar och avlopp", "Avskiljare"),
    "IFCFIRESUPPRESSIONTERMINAL": ("Sprinkler", "Sprinkler"),
    "IFCDISTRIBUTIONCHAMBERELEMENT": ("Brunnar och avlopp", "Brunn"),
    "IFCUNITARYEQUIPMENT": ("Aggregat", "Aggregat"),
    "IFCAIRTERMINAL": ("Ventilation", "Don"),
    "IFCDUCTSEGMENT": ("Ventilation", "Kanal"),
    "IFCDUCTFITTING": ("Ventilation", "Kanaldel"),
    "IFCPIPESEGMENTTYPE": ("Rör", "Rör"),
}
PROXY = "IFCBUILDINGELEMENTPROXY"
PROXY_WORDS = re.compile(r"plumb|sanit|vvs|pipe|rör|valve|ventil|drain|brunn|mechanical|pump|radiator|beredare|"
                         r"blandare|wc|tvättställ|dusch|avlopp|vatten", re.I)

PREDEFINED = {
    "SINK": "Diskbänk", "WASHHANDBASIN": "Tvättställ", "TOILETPAN": "WC", "WCSEAT": "WC-sits", "SHOWER": "Dusch",
    "BATH": "Badkar", "BIDET": "Bidé", "URINAL": "Urinoar", "CISTERN": "Cistern", "SANITARYFOUNTAIN": "Fontän",
    "TAP": "Blandare", "MIXING": "Blandare", "ISOLATING": "Avstängningsventil", "CHECK": "Backventil",
    "REGULATING": "Injusteringsventil", "SAFETYCUTOFF": "Säkerhetsventil", "PRESSURERELIEF": "Säkerhetsventil",
    "DRAWOFFCOCK": "Tappventil", "FLOORTRAP": "Golvbrunn", "FLOORWASTE": "Golvbrunn", "GULLYTRAP": "Dagvattenbrunn",
    "ROOFDRAIN": "Takbrunn", "WASTETRAP": "Vattenlås", "BEND": "Böj", "JUNCTION": "Grenrör", "TRANSITION": "Övergång",
    "CONNECTOR": "Koppling", "RIGIDSEGMENT": "Rör", "FLEXIBLESEGMENT": "Slang", "GUTTER": "Hängränna",
    "CULVERT": "Trumma", "CIRCULATOR": "Cirkulationspump", "CONVECTOR": "Konvektor", "RADIATOR": "Radiator",
}

# ord i Revits familjenamn som säger vad familjen är, inte vem som gjort den
GENERIC = {"arc", "vs", "vvs", "rör", "plumbing", "fixtures", "sanitary", "construction", "mechanical", "equipment",
           "pipe", "pipes", "fittings", "accessories", "roof-accessories", "wash-basins", "storage", "generic", "m",
           "p", "ifc", "family", "familj", "standard", "roof", "accessories", "wash", "basins", "fixture", "sanitaryware"}

PSET_KEYS = {"manufacturer": "Fabrikat", "model": "Modell", "modelreference": "Modell", "modellabel": "Modell",
             "articlenumber": "Art.nr", "productnumber": "Art.nr", "rsk": "RSK", "rsknumber": "RSK", "rsk-nr": "RSK",
             "systemname": "System", "system name": "System", "system type": "System", "system classification": "System",
             "size": "Dimension", "nominaldiameter": "Dimension", "diameter": "Dimension", "material": "Material",
             "typedescription": "Typbeskrivning", "description": "Beskrivning"}


def _brand_of(text: str) -> str:
    for part in re.split(r"[_:\-,/]+", text):
        words = part.strip().split()
        for k in range(min(2, len(words)), 0, -1):
            key = " ".join(words[:k]).lower().strip(" .")
            if key in BRANDS and key not in NOT_BRANDS:
                return BRANDS[key]
        for w in words:
            k = w.lower().strip(" .")
            if k in BRANDS and k not in NOT_BRANDS:
                return BRANDS[k]
    return ""


def _family_parts(family: str) -> tuple[str, str]:
    """Revits familjenamn "ARC_Plumbing Fixtures_FM Mattsson_Siljan_Duschblandare" -> (fabrikat, resten)."""
    parts = [p.strip() for p in re.sub(r"#\w+$", "", family).split("_") if p.strip()]
    rest = [p for k, p in enumerate(parts) if not all(w in GENERIC for w in re.split(r"[\s\-]+", p.lower()) if w)
            and not (k == 0 and re.fullmatch(r"[A-Z]{1,4}", p))]       # ett disciplinprefix först: ARC, VS
    brand = _brand_of(family)
    if not brand and len(rest) >= 2 and len(rest[0]) <= 24 and rest[0][:1].isupper():
        brand = rest[0]                      # tillverkaren står först efter kategorierna: "Svedbergs", "Lindab"
    if brand:
        rest = [p for p in rest if p.lower() != brand.lower() and not p.lower().startswith(brand.lower() + " ")]
    return brand, " ".join(rest).replace("-", " ").strip()


def _clean_type(type_name: str, brand: str) -> str:
    t = re.sub(r"#\w+$", "", type_name or "").strip()
    if "_" in t or t.lower().startswith("default"):
        return ""                            # typen är familjens namn igen, eller Revits platshållare
    if brand and t.lower().startswith(brand.lower()):
        t = t[len(brand):].strip(" -_:")
    return t


# ---------------------------------------------------------------- modellen

def read_ifc(text: Iterable[str]) -> dict[str, Any]:
    R = _records(text)
    P: dict[int, list] = {}

    def args(i: int) -> list:
        if i not in P:
            P[i] = _args(R[i][1]) if i in R else []
        return P[i]

    schema = ""
    # enheten: millimeter i Revits export, meter i andras
    length_to_m = 1.0
    for i, (cls, raw) in R.items():
        if cls == "IFCSIUNIT" and ".LENGTHUNIT." in raw:
            a = args(i)
            length_to_m = {".MILLI.": 0.001, ".CENTI.": 0.01, ".DECI.": 0.1}.get(a[2] if len(a) > 2 else "$", 1.0)
            break

    storeys = {i: (args(i)[2] or args(i)[7] if len(args(i)) > 7 else args(i)[2]) or f"#{i}"
               for i, (c, _) in R.items() if c == "IFCBUILDINGSTOREY"}
    elements = {i: c for i, (c, raw) in R.items() if c in CLASSES and not c.endswith("TYPE")}
    for i, (c, raw) in R.items():
        if c == PROXY and PROXY_WORDS.search(_decode(raw[:400])):
            elements[i] = c

    # ett rum hör till sin våning (IfcRelAggregates), och en sak i ett rum hör till rummets våning
    spaces = {i for i, (c, _) in R.items() if c == "IFCSPACE"}
    parent: dict[int, int] = {}
    for i, (c, raw) in R.items():
        if c == "IFCRELAGGREGATES":
            a = args(i)
            whole = _ref(a[4])
            for part in a[5] or []:
                part = _ref(part)
                if part is not None and whole is not None:
                    parent[part] = whole

    def storey_of(x: int | None) -> int | None:
        for _ in range(6):
            if x is None or x in storeys:
                return x
            x = parent.get(x)
        return None

    where: dict[int, int] = {}
    room: dict[int, int] = {}
    typ: dict[int, int] = {}
    psets: dict[int, list[int]] = defaultdict(list)
    for i, (c, raw) in R.items():
        if c == "IFCRELCONTAINEDINSPATIALSTRUCTURE":
            a = args(i)
            container = _ref(a[5])
            st = storey_of(container)
            for e in a[4] or []:
                e = _ref(e)
                if e in elements:
                    if st is not None:
                        where[e] = st
                    if container in spaces:
                        room[e] = container
        elif c == "IFCRELDEFINESBYTYPE":
            a = args(i)
            t = _ref(a[5])
            for e in a[4] or []:
                e = _ref(e)
                if e in elements:
                    typ[e] = t
        elif c == "IFCRELDEFINESBYPROPERTIES":
            a = args(i)
            ps = _ref(a[5])
            for e in a[4] or []:
                e = _ref(e)
                if e in elements:
                    psets[e].append(ps)

    def props(ps_ids: Iterable[int]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for ps in ps_ids:
            if ps not in R:
                continue
            c = R[ps][0]
            a = args(ps)
            if c == "IFCPROPERTYSET" and len(a) > 4:
                for pr in a[4] or []:
                    pr = _ref(pr)
                    if pr in R and R[pr][0] == "IFCPROPERTYSINGLEVALUE":
                        pa = args(pr)
                        if len(pa) > 2 and pa[2] not in (None, "$"):
                            out.setdefault(str(pa[0]), pa[2])
            elif c == "IFCELEMENTQUANTITY" and len(a) > 5:
                for q in a[5] or []:
                    q = _ref(q)
                    if q in R and R[q][0] == "IFCQUANTITYLENGTH":
                        qa = args(q)
                        if len(qa) > 3 and isinstance(qa[3], float):
                            out.setdefault("Qto:" + str(qa[0]), qa[3])
        return out

    groups: dict[tuple, dict[str, Any]] = {}
    for e, cls in elements.items():
        a = args(e)
        name = a[2] if len(a) > 2 and isinstance(a[2], str) and a[2] != "$" else ""
        otype = a[4] if len(a) > 4 and isinstance(a[4], str) and a[4] != "$" else ""
        predef = (a[-1] if a and isinstance(a[-1], str) and a[-1].startswith(".") else "").strip(".")
        t = typ.get(e)
        tname = ""
        t_psets: list[int] = []
        if t in R:
            ta = args(t)
            tname = ta[2] if len(ta) > 2 and isinstance(ta[2], str) and ta[2] != "$" else ""
            t_psets = [_ref(x) for x in (ta[5] if len(ta) > 5 and isinstance(ta[5], list) else [])]
            if not predef and ta and isinstance(ta[-1], str) and ta[-1].startswith("."):
                predef = ta[-1].strip(".")
        full = otype or name
        family, _, rest = full.partition(":")
        type_name = rest.split(":")[0] if rest else (tname.split(":")[-1] if tname else "")
        pr = props([p for p in t_psets if p]) | props(psets.get(e, []))
        low = {k.lower(): v for k, v in pr.items()}
        info = {PSET_KEYS[k]: str(v) for k, v in low.items() if k in PSET_KEYS and str(v).strip()}
        brand_f, what = _family_parts(family)
        brand = info.get("Fabrikat") or _brand_of(type_name) or brand_f
        model = info.get("Modell") or _clean_type(type_name, brand) or (what if "_" in type_name else "")
        category, default_name = CLASSES.get(cls, ("Övrigt VVS", "VVS-objekt"))
        if re.search(r"roof|tak|gutter|ränn|stupr", family, re.I) and cls in ("IFCPIPESEGMENT", "IFCPIPEFITTING"):
            category = "Takavvattning"
        kind_label = (PREDEFINED.get(predef, "") if predef not in ("NOTDEFINED", "USERDEFINED") else "") or default_name
        # benämningen ur familjen ("Siljan Duschblandare", "WC golvstående"); familjens slag annars
        label = (what[:70] if what else "") or kind_label
        if brand and label.lower().startswith(brand.lower()):
            label = label[len(brand):].strip() or kind_label
        storey = storeys.get(where.get(e)) or str(pr.get("StoreyName") or "") or "Utan våning"
        length = pr.get("Qto:Length") or (pr.get("Length") if isinstance(pr.get("Length"), float) else None)
        # höger- och vänstervarianten (#Left, #Right) är samma vara
        key = (cls, re.sub(r"#\w+$", "", family.strip()), re.sub(r"#\w+$", "", type_name.strip()), brand, model)
        g = groups.setdefault(key, {"cls": cls, "family": family.strip(), "type_name": type_name.strip(),
                                    "brand": brand, "model": model, "label": label, "category": category,
                                    "kind_label": kind_label, "rooms": set(),
                                    "predef": predef, "info": info, "n": 0, "per_storey": Counter(),
                                    "length_m": 0.0, "with_length": 0, "tags": []})
        g["n"] += 1
        g["per_storey"][storey] += 1
        if e in room:
            g["rooms"].add(room[e])
        if isinstance(length, float) and length > 0:
            g["length_m"] += length * length_to_m
            g["with_length"] += 1

    items = [_item(k, g) for k, g in enumerate(sorted(groups.values(), key=lambda g: (g["category"], g["label"],
                                                                                      g["brand"], g["model"])))]
    by_class = Counter(elements.values())
    return {"meta": {"schema": schema, "storeys": sorted(set(storeys.values())), "n_elements": len(elements),
                     "classes": dict(by_class), "length_unit_m": length_to_m},
            "items": items, "stats": _stats(items, len(elements))}


def _item(k: int, g: dict[str, Any]) -> dict[str, Any]:
    pipe = g["cls"] in ("IFCPIPESEGMENT", "IFCFLOWSEGMENT", "IFCDUCTSEGMENT")
    metres = pipe and g["with_length"] == g["n"] and g["length_m"] > 0
    qty = round(g["length_m"], 2) if metres else float(g["n"])
    unit = "m" if metres else "st"
    storeys = sorted(g["per_storey"].items(), key=lambda kv: kv[0])
    spec = {"Per våning": " · ".join(f"{s}: {n}" for s, n in storeys), "IFC-klass": g["cls"][3:].title()}
    if g["rooms"]:
        spec["I rum"] = str(len(g["rooms"]))
    if pipe:
        spec["Antal rör"] = str(g["n"])
        if not metres:
            spec["Längd"] = (f"{g['length_m']:.2f} m för {g['with_length']} av {g['n']} rör"
                             if g["with_length"] else "saknas i modellen – räknat i styck")
    spec.update({k2: v for k2, v in g["info"].items() if k2 not in ("Fabrikat", "Modell")})
    name = g["label"]
    words = lambda t: set(re.findall(r"\w+", t.lower()))
    if g["model"] and not words(g["model"]) <= words(name):
        name = f"{name} {g['model']}"
    # typen bär serien ur familjen ("Siljan") och typens mått ("G3/8"): det är vad katalogen söks på
    series = [w for w in re.findall(r"[A-Za-zÅÄÖåäö][\w\-]+", g["label"]) if w[:1].isupper() and len(w) >= 4
              and w.lower() not in {x.lower() for x in re.findall(r"\w+", g["model"])}][:2]
    model = " ".join(series + ([g["model"]] if g["model"] else [])).strip()
    rsk = re.findall(r"\b\d{7}\b", g["info"].get("RSK", ""))
    art = [g["info"]["Art.nr"]] if g["info"].get("Art.nr") else []
    return {"id": f"ifc{k}", "kind": "post", "code": "", "name": name[:160], "quantity": qty, "unit": unit,
            "quantity_text": f"{qty:g} {unit}", "manufacturer": g["brand"], "manufacturer_text": g["brand"],
            "type": model[:120], "rsk": rsk, "art_nr": art, "or_equal": False, "spec": spec,
            "text": f"{g['family']}:{g['type_name']}".strip(":"), "category": g["category"],
            "subcategory": g["kind_label"], "ama_code": "", "ama_path": [], "section": "", "page": 0, "parent": "",
            "total_quantity": qty, "supplied_by": "", "inferred": "Ur IFC-modellen: antalet är antalet objekt"
            + (", längden summan av modellens längder" if metres else "")}


def _stats(items: list[dict[str, Any]], n: int) -> dict[str, Any]:
    return {"items": len(items), "posts": len(items), "accessories": 0, "mentioned": 0,
            "with_rsk": sum(1 for i in items if i["rsk"]), "elements": n,
            "categories": len({i["category"] for i in items}),
            "manufacturers": len({i["manufacturer"] for i in items if i["manufacturer"]})}


def ifc_text(data: bytes) -> tuple[str, str]:
    """Texten ur en .ifc eller en .zip med en .ifc i. Returnerar (filnamn i arkivet, text)."""
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".ifc") and not n.startswith("__MACOSX")]
            if not names:
                raise ValueError("Arkivet innehåller ingen .ifc-fil")
            info = max((z.getinfo(n) for n in names), key=lambda i: i.file_size)
            if info.file_size > 1024 * 1024 * 1024:
                raise ValueError("IFC-filen i arkivet är större än 1 GB")
            return info.filename, z.read(info).decode("utf-8", "replace")
    head = data[:200].decode("ascii", "replace")
    if "ISO-10303-21" not in head:
        raise ValueError("Filen är ingen IFC-fil (ISO-10303-21)")
    return "", data.decode("utf-8", "replace")


def read_ifc_bytes(data: bytes) -> dict[str, Any]:
    inner, text = ifc_text(data)
    m = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", text[:5000])
    out = read_ifc(io.StringIO(text))
    out["meta"]["schema"] = m.group(1) if m else ""
    out["meta"]["inner"] = inner
    out["meta"]["n_pages"] = 0
    out["meta"]["title"] = ""
    fn = re.search(r"FILE_NAME\s*\(\s*'([^']*)'", text[:5000])
    if fn:
        out["meta"]["title"] = _decode(fn.group(1))[:200]
    return out
