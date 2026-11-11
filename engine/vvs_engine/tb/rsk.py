"""RSK-nummer i alla skrivsätt: "573 24 87", "573 2487", "573.24.87", "573-24-87", "5732487" är samma nummer.

Normen är "XXX XX XX", men handlingar skriver dem olika. Allt normaliseras till sju siffror innan något jämförs:
mellanslag, punkter och bindestreck tas bort, och det som blir kvar måste vara exakt sju siffror.

Ett nummer räknas som RSK när det står efter ordet RSK ("RSK 573 24 87", "RSK-nr: 5732487", "RSK nr. 573.24.87"),
eller när det står i normens egen form "XXX XX XX" - den formen skrivs inte om något annat i en VVS-handling. Sju
siffror i ett svep utan "RSK" före (ett telefonnummer, ett projektnummer) räknas inte.
"""
from __future__ import annotations

import re

_SEP = r"[  .\-]?"
_NUM = rf"\d{{3}}{_SEP}\d{{2}}{_SEP}\d{{2}}"
# efter ordet RSK: alla skrivsätt, också flera nummer i rad ("RSK 573 24 87, 573 24 88")
LABELLED = re.compile(rf"RSK[\s\-]*(?:nr|nummer)?\.?\s*:?\s*((?:{_NUM})(?:\s*(?:,|/|och|el\.?|eller)\s*{_NUM})*)(?!\d)", re.I)
# normens egen form utan ord före: "573 24 87"
NORM_FORM = re.compile(r"(?<![\d.,\-])(\d{3}) (\d{2}) (\d{2})(?![\d.,]\d)")
_ONE = re.compile(_NUM)
DIMENSION_BEFORE = re.compile(r"(?:\bDN|\bdim\w*|Ø|\bx|\bmm|\bcc|\bc/c|[:=])\s*$", re.I)
UNIT_AFTER = re.compile(r"\s*(?:mm|cm|m\b|x\b|kw|w\b|l/s|kpa|bar)", re.I)


def normalize(value: str | None) -> str | None:
    """Sju siffror, eller None om värdet inte är ett RSK-nummer."""
    if value is None:
        return None
    digits = re.sub(r"[\s .\-]", "", str(value))
    return digits if re.fullmatch(r"\d{7}", digits) else None


def pretty(value: str) -> str:
    """Normens skrivsätt: 5732487 -> 573 24 87."""
    v = normalize(value) or value
    return f"{v[:3]} {v[3:5]} {v[5:]}" if len(v) == 7 and v.isdigit() else v


def find(text: str | None) -> list[str]:
    """Alla RSK-nummer i en text, normaliserade och i den ordning de står, utan dubbletter."""
    out: list[str] = []
    if not text:
        return out
    for m in LABELLED.finditer(text):
        for one in _ONE.findall(m.group(1)):
            n = normalize(one)
            if n and n not in out:
                out.append(n)
    for m in NORM_FORM.finditer(text):
        before, after = text[max(0, m.start() - 8):m.start()], text[m.end():m.end() + 4]
        if DIMENSION_BEFORE.search(before) or UNIT_AFTER.match(after) or re.search(r"\d\s$", before) \
                or re.match(r"\s\d", after):           # en del av ett längre tal: "070 123 45 67"
            continue                                       # "DN 110 25 30", "120 20 30 mm" är mått, inga nummer
        n = "".join(m.groups())
        if n not in out:
            out.append(n)
    return out
