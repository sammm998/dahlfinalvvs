"""AI-kontrollen av en teknisk beskrivning: anropet, cachen och kostnaden (logiken står i vvs_engine.tb.ai).

Billigt med flit:
  - den billigaste modellen som klarar uppgiften (GPT-6.1 Sol om inget annat är satt: VVS_TB_AI_MODEL)
    och låg resonemangsnivå (VVS_TB_AI_EFFORT, standard "low") - resonemang betalas som utdata
  - bara text, aldrig bilder av sidorna
  - bara det läsaren inte kan avgöra: raderna som inte blev en post men nämner en produkt, och posterna med
    flera kandidater i katalogen
  - korta svar: radnummer och kandidatnummer, inte fri text
  - instruktionerna först och lika i varje anrop, så att leverantörens promptcache tar dem till cachepris
  - samma fråga två gånger kostar ingenting: svaren sparas per fråga (nyckeln är modell + instruktion + indata)

Kostnaden dras från den gemensamma budgeten som "Teknisk beskrivning (AI)", med vem som körde den.
"""
from __future__ import annotations

import contextvars
import datetime as dt
import hashlib
import io
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from vvs_engine.tb import ai as tb_ai

from . import api_budget
from .storage import storage

log = logging.getLogger("vvs.tb_ai")
SOURCE = "tb"
CACHE = "ai_cache/tb"


def model() -> str:
    from .ai_models import SOL, model_id
    return os.environ.get("VVS_TB_AI_MODEL") or model_id(SOL)


def effort() -> str:
    return os.environ.get("VVS_TB_AI_EFFORT", "low")


def _client():
    from openai import OpenAI
    from .source_model import connection_settings
    key, _ = connection_settings()
    if not key:
        raise RuntimeError("OpenAI-anslutning saknas")
    return OpenAI(api_key=key, timeout=90, max_retries=1)


def _openai_ask(instructions: str, payload: str, schema: dict, mdl: str) -> tuple[dict, dict]:
    """Ett anrop. Returnerar (svaret, förbrukningen)."""
    client = _client()
    request = dict(model=mdl, store=False, max_output_tokens=4000,
                   prompt_cache_key="tb-ai-" + hashlib.sha256(instructions.encode()).hexdigest()[:16],
                   reasoning={"effort": effort()},
                   input=[{"role": "system", "content": instructions}, {"role": "user", "content": payload}],
                   text={"format": {"type": "json_schema", "name": "svar", "strict": True, "schema": schema}})
    try:
        r = client.responses.create(**request)
    except Exception as e:                                     # noqa: BLE001
        if "reasoning" not in str(e).lower():
            raise
        request.pop("reasoning")                               # en modell utan resonemang: samma fråga utan
        r = client.responses.create(**request)
    u = getattr(r, "usage", None)
    usage = {"in": getattr(u, "input_tokens", 0) or 0, "out": getattr(u, "output_tokens", 0) or 0,
             "cached": getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0}
    return json.loads(r.output_text or "{}"), usage


# Testerna byter ut anropet; tjänsten använder OpenAI.
TRANSPORT: Callable[[str, str, dict, str], tuple[dict, dict]] = _openai_ask


def make_ask(stats: dict[str, Any]) -> tb_ai.Ask:
    mdl = model()

    def ask(instructions: str, payload: str, schema: dict) -> dict:
        key = hashlib.sha256("|".join((tb_ai.VERSION, mdl, effort(), instructions, payload)).encode()).hexdigest()
        path = f"{CACHE}/{key}.json"
        if storage.exists(path):
            stats["cached_calls"] += 1
            with storage.open(path) as fh:
                return json.load(fh)
        api_budget.check(mdl)
        answer, usage = TRANSPORT(instructions, payload, schema, mdl)
        stats["calls"] += 1
        stats["tokens"] += int(usage.get("in", 0)) + int(usage.get("out", 0))
        stats["kr"] += api_budget.charge(mdl, usage.get("in", 0), usage.get("out", 0), usage.get("cached", 0), 0,
                                         SOURCE)
        storage.put(path, io.BytesIO(json.dumps(answer, ensure_ascii=False).encode("utf-8")))
        return answer
    return ask


def run(s, items_with_match: list[dict[str, Any]], user_email: str = "") -> dict[str, Any]:
    """Kör kontrollen på en läst beskrivning och returnerar det som sparas på den (TechSpec.ai)."""
    import pymupdf
    stats = {"calls": 0, "cached_calls": 0, "tokens": 0, "kr": 0.0}
    ask = make_ask(stats)
    raw = [{k: v for k, v in it.items() if k != "match"} for it in items_with_match]
    doc = None
    if (getattr(s, "source", "tb") or "tb") == "tb" and (s.storage_key or "").lower().endswith(".pdf"):
        # en IFC-modell har inga rader att ha missat: antalet är antalet objekt. Bara valet i katalogen.
        with storage.open(s.storage_key) as fh:
            doc = pymupdf.open(stream=fh.read(), filetype="pdf")
    try:
        # de två delarna är oberoende: samtidigt, var och en med vem som körde (för den gemensamma budgeten)
        with ThreadPoolExecutor(max_workers=2) as pool:
            fm = pool.submit(contextvars.copy_context().run, tb_ai.find_missed, doc, raw, ask) if doc is not None \
                else None
            fp = pool.submit(contextvars.copy_context().run, tb_ai.find_picks, items_with_match, ask)
            missed = fm.result() if fm else {"lines_sent": 0, "calls": 0, "missed": []}
            picks = fp.result()
    finally:
        if doc is not None:
            doc.close()
    # det någon redan bestämt står kvar: ett godkänt förslag är en post nu och kommer inte tillbaka, ett avfärdat
    # föreslås inte igen
    decided = {m["key"]: m for m in ((s.ai or {}).get("missed") or []) if m.get("key") and m.get("state") != "förslag"}
    out_missed = []
    for m in missed["missed"]:
        k = hashlib.sha1(f"{m['page']}|{m['manufacturer']}|{m['type']}|{m['rsk']}".encode()).hexdigest()[:12]
        out_missed.append(decided.pop(k, None) or {**m, "key": k, "state": "förslag"})
    out_missed += list(decided.values())
    return {"status": "COMPLETED", "version": tb_ai.VERSION, "model": model(),
            "ran_at": dt.datetime.now(dt.timezone.utc).isoformat(), "by": user_email,
            "kr": round(stats["kr"], 4), "calls": stats["calls"], "cached_calls": stats["cached_calls"],
            "tokens": stats["tokens"], "lines_sent": missed["lines_sent"], "asked": picks["asked"],
            "missed": out_missed, "picks": picks["picks"]}


def overlay(match: dict[str, Any], pick: dict[str, Any] | None) -> dict[str, Any]:
    """En post med AI:ns val: RSK-förslaget blir det valda numret, märkt som AI, och det tidigare står kvar."""
    if not pick:
        return match
    before = match.get("rsk") or {}
    return {**match, "ai": pick, "rsk": {**before, "value": pick["ref"], "kind": "ai", "name": pick["name"],
                                         "sure": pick.get("sure", False), "before": before.get("value")}}


def as_item(m: dict[str, Any], items: list[dict[str, Any]], who: str) -> dict[str, Any]:
    """En godkänd missad produkt som en post: omnämnd i texten, utan antal, med var den står och vem som godkände."""
    near = [it for it in items if it.get("page") == m["page"] and it.get("category")] or \
           [it for it in items if it.get("category")]
    cat = near[0] if near else {}
    return {"parent": "", "supplied_by": "", "id": f"ai-{m['key']}", "kind": "omnamnd", "code": "", "name": m["name"], "quantity": None,
            "unit": "", "quantity_text": "enl. beskrivning", "manufacturer": m["manufacturer"],
            "manufacturer_text": m["manufacturer_text"], "type": m["type"], "rsk": [m["rsk"]] if m["rsk"] else [],
            "art_nr": [], "or_equal": False, "spec": {}, "text": m["line_text"],
            "category": cat.get("category", ""), "subcategory": cat.get("subcategory", ""),
            "ama_code": cat.get("ama_code", ""), "ama_path": cat.get("ama_path") or [], "section": "",
            "page": m["page"], "total_quantity": None,
            "inferred": f"AI-förslag ur sidan {m['page']}, godkänt av {who}"}
