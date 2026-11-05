"""Disciplinerna tjänsten läser, och det som skiljer dem åt - som data, inte som kod.

En disciplin är en fil i `data/`: namn, läge (aktiv, beta, kommer, senare), vad den mäter (rör, kanaler, symboler,
ytor), vilka mättyper raderna bär och - under `engine` - de värden i läsningen som inte är desamma för den som för
VVS. Läsningen frågar `value(nyckel, standard)` där den förr hade en konstant, och standardvärdet är konstanten
själv. VVS-filen har inga avvikelser, så en VVS-läsning ser exakt de tal den alltid sett; en annan disciplin får
sina egna värden utan att en rad i VVS-läsningen ändras.

Disciplinen binds till den läsning som körs, på samma sätt som reglerna (`rules.using`): jobb körs på trådar i
samma process, och ett värde satt för en ritning får aldrig gälla någon annans.

Ett projekt eller en ritning utan disciplin - allt som fanns innan disciplinerna - är VVS.

En disciplin kan också läsa bladet en andra gång, vidgad (`widened()`): "Alla" läser rören som VVS och sedan en gång
till med värdena under `wide`, där andra discipliners etiketter får namnge sina ledningar. Värdena under `wide`
gäller bara i den andra läsningen. Den första är VVS-läsningen, oförändrad.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

DATA = Path(__file__).with_name("data")
DEFAULT = "vvs"
ACTIVE, BETA, PLANNED, LATER = "active", "beta", "planned", "later"
STATUSES = (ACTIVE, BETA, PLANNED, LATER)
KINDS = ("pipe", "duct", "symbol", "area", "all")     # all: every designation on the sheet, whatever it names


@dataclass(frozen=True)
class Discipline:
    id: str
    name: str
    status: str
    kind: str
    measures: tuple[str, ...]
    order: int
    engine: dict
    notes: str = ""
    wide: dict = field(default_factory=dict)     # the second, widened reading's own values (see widened())

    @property
    def reads_all(self) -> bool:
        """A discipline that reads more than the VVS pipes: the sheet is read as VVS and then once more, widened,
        and every designation is put in the register. "Alla" keeps all of it; the others say which kind of entry
        they are about (`register.FOCUS`): ducts for ventilation, symbols for electrical, rooms for building."""
        return self.id == "alla" or bool(self.wide)

    def out(self) -> dict:
        return {"id": self.id, "name": self.name, "status": self.status, "kind": self.kind,
                "measures": list(self.measures), "notes": self.notes}


@lru_cache(maxsize=1)
def registry() -> dict[str, Discipline]:
    found: list[Discipline] = []
    for p in sorted(DATA.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        found.append(Discipline(id=d["id"], name=d["name"], status=d["status"], kind=d["kind"],
                                measures=tuple(d.get("measures") or ()), order=int(d.get("order", 99)),
                                engine=dict(d.get("engine") or {}), notes=d.get("notes", ""),
                                wide=dict(d.get("wide") or {})))
    return {d.id: d for d in sorted(found, key=lambda d: d.order)}


def normalize(discipline_id: str | None) -> str:
    """'' and None are VVS - a project made before disciplines existed is what it always was. An id nobody knows is
    returned as it is, so that the caller can refuse it rather than have it quietly read as VVS."""
    d = (discipline_id or "").strip().lower()
    return d or DEFAULT


def known(discipline_id: str | None) -> bool:
    return normalize(discipline_id) in registry()


def selectable(discipline_id: str | None) -> bool:
    """A discipline a project may be given: one that is built."""
    d = registry().get(normalize(discipline_id))
    return d is not None and d.status == ACTIVE


def get(discipline_id: str | None) -> Discipline:
    return registry()[normalize(discipline_id)]


_CURRENT: ContextVar[str] = ContextVar("vvs_discipline", default=DEFAULT)


@contextmanager
def using(discipline_id: str | None) -> Iterator[None]:
    """Bind a discipline to the reading on this thread, and only to it."""
    d = normalize(discipline_id)
    if d not in registry():
        raise KeyError(f"okänd disciplin: {discipline_id}")
    tok = _CURRENT.set(d)
    try:
        yield
    finally:
        _CURRENT.reset(tok)


def current() -> Discipline:
    return registry()[_CURRENT.get()]


_WIDENED: ContextVar[bool] = ContextVar("vvs_discipline_widened", default=False)


@contextmanager
def widened() -> Iterator[None]:
    """The second reading of a discipline that reads more than the pipes: its `wide` values hold here, and only
    here, on this thread."""
    tok = _WIDENED.set(True)
    try:
        yield
    finally:
        _WIDENED.reset(tok)


def is_widened() -> bool:
    return _WIDENED.get()


def value(key: str, default: Any) -> Any:
    """What the reading uses for `key` in the discipline being read. The default is the engine's own constant; only
    a discipline that differs from VVS names the key at all. In its widened reading a discipline's `wide` values
    come first."""
    d = current()
    if _WIDENED.get() and key in d.wide:
        return d.wide[key]
    return d.engine.get(key, default)
