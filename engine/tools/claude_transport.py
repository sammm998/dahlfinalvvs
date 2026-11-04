"""Tråden till Anthropics modell. Samma kontrakt som astra_transport.py, samma tystnad om nyckeln.

`vvs_engine/semantics/astra.py` håller reglerna - vad som får frågas, vad som får svaras och hur ett svar
prövas. Det här håller bara ledningen: hur modellen nås och hur svaret väntas in. Motorn importerar ingenting
härifrån och kör utan nät om ingen ger `analyze_page` en transport.

Ingen nyckel står i den här filen. Går anropet ut genom en agentproxy som fäster referensen skickas ingenting
härifrån; gör den inte det - en behållare som kör tjänsten - läses nyckeln ur ANTHROPIC_API_KEY i miljön i
samma ögonblick som anropet görs, läggs på tråden, och skrivs aldrig ned, loggas aldrig och kommer aldrig
tillbaka i ett resultat.

Varför en andra modell alls: ett fall som geometrin förklarat öppet har flera kandidater, och en enda läsare
som väljer fel gör ett tvetydigt fall till ett självsäkert fel. Två läsare som måste vara överens gör det inte
- de kan bara enas om ett av ritningens egna alternativ, eller låta fallet stå kvar öppet. Sammanvägningen
ligger i readers.py; här finns bara vägen ut.
"""
from __future__ import annotations

import json
import os
from typing import Callable

BASE = (os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com").rstrip("/")
API = f"{BASE}/v1/messages"
MODEL = os.environ.get("VVS_CLAUDE_MODEL", "claude-opus-5")
VERSION = "2023-06-01"
MAX_OUTPUT_TOKENS = 2000        # ett avgränsat flervalssvar med en rads motivering behöver inte mer
VISION_MAX_TOKENS = 4000

SYSTEM = ("Du läser VVS-ritningar. Du får ett fall som den geometriska läsningen inte kunde avgöra, tillsammans "
          "med de kandidater ritningen faktiskt erbjuder. Välj en av dem eller svara OKLART. Hitta aldrig på "
          "geometri, koordinater, dimensioner eller beteckningar som inte står i frågan.")


def _headers() -> dict[str, str]:
    """Referensen, om det är den här maskinen som måste bära den.

    Bakom en agentproxy autentiseras anropet efter att det lämnat oss och ingen nyckelrubrik hör hemma här. I
    en behållare finns ingen sådan proxy, och nyckeln läses då ur miljön i anropsögonblicket.
    """
    h = {"content-type": "application/json", "anthropic-version": VERSION}
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        h["x-api-key"] = key
    return h


def available() -> tuple[bool, str]:
    """Om en Claude-läsare går att nå härifrån, sagt rakt ut i stället för utrönt genom att misslyckas."""
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return True, "ANTHROPIC_API_KEY i miljön"
    if os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"):
        return True, "proxy som fäster referensen"
    return False, "ingen ANTHROPIC_API_KEY och ingen proxy"


def _post(body: dict, timeout: int = 180) -> dict:
    import httpx
    with httpx.Client(timeout=timeout) as c:
        r = c.post(API, json=body, headers=_headers())
    try:
        d = r.json()
    except Exception:
        # en referens kan dyka upp i en proxys egen felutskrift, så bara början av kroppen citeras tillbaka
        raise RuntimeError(f"icke-JSON från {API} ({r.status_code}): {(r.text or '')[:200] or 'inget svar'}")
    if isinstance(d, dict) and d.get("type") == "error":
        raise RuntimeError(str(d.get("error"))[:200])
    return d


def _call(body: dict, source: str) -> dict:
    """En fråga, prövad mot tjänstens mätare först och betald efteråt."""
    try:
        from . import meter                                  # noqa: PLC0415
    except ImportError:
        import meter                                         # noqa: PLC0415
    meter.before(body["model"])
    d = _post(body)
    meter.after(body["model"], d.get("usage") if isinstance(d, dict) else None, source)
    return d


def _text_of(d: dict) -> str:
    return "".join(b.get("text", "") for b in (d.get("content") or []) if b.get("type") == "text")


def transport(effort: str = "low") -> Callable:
    """En anropbar för analyze_page(second_reader=...). Att den kastar är ofarligt: fallet står kvar tvetydigt."""
    def ask(q) -> str:
        body = {"model": MODEL, "system": SYSTEM, "max_tokens": MAX_OUTPUT_TOKENS,
                "messages": [{"role": "user", "content": q.as_prompt()}]}
        return _text_of(_call(body, "andra_läsaren"))
    return ask


def vision_transport(effort: str = "low") -> Callable:
    """En anropbar för review.vision.look(ask=...). Bilder går upp; bara ord kommer tillbaka.

    Ingenting det här ger tillbaka kan bli geometri - vision.look har ingen väg att skriva in i en läsning - så
    det enda som står på spel här är kostnad och väntan, inte en felaktig meter.
    """
    import base64

    def ask(prompt: str, images: list[bytes]) -> str:
        content: list[dict] = [{"type": "text", "text": prompt}]
        for png in images:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                        "data": base64.b64encode(png).decode()}})
        body = {"model": MODEL, "max_tokens": VISION_MAX_TOKENS,
                "messages": [{"role": "user", "content": content}]}
        return _text_of(_call(body, "granskning"))
    return ask


def agent_transport(effort: str = "low") -> Callable:
    """En tur i ett verktygsanropande samtal. Anroparen kör slingan och äger varje verktyg.

    Verktygskontraktet kommer in i OpenAI-form, eftersom det är den form agenten redan talar. Det översätts
    här och svaret översätts tillbaka, så att en anropare kan byta läsare utan att skriva om sina verktyg.
    """
    from .astra_transport import AGENT_SYSTEM

    def ask(items: list[dict], tools: list[dict], previous_response_id: str | None = None) -> dict:
        msgs = _to_messages(items)
        body = {"model": MODEL, "system": AGENT_SYSTEM, "max_tokens": 6000, "messages": msgs,
                "tools": [_to_tool(t) for t in tools]}
        d = _call(body, "agent")
        calls = [{"call_id": b.get("id"), "name": b.get("name"), "arguments": json.dumps(b.get("input") or {})}
                 for b in (d.get("content") or []) if b.get("type") == "tool_use"]
        return {"calls": calls, "text": _text_of(d), "status": d.get("stop_reason"), "id": d.get("id")}
    return ask


def _to_tool(t: dict) -> dict:
    """Ett verktyg skrivet för Responses-API:t, sagt som Messages-API:t vill höra det."""
    fn = t.get("function") or t
    return {"name": fn.get("name"), "description": fn.get("description") or "",
            "input_schema": fn.get("parameters") or {"type": "object", "properties": {}}}


def _to_messages(items: list[dict]) -> list[dict]:
    """Samtalet så långt, översatt från Responses-formen till turer av roller."""
    out: list[dict] = []
    for it in items:
        kind = it.get("type")
        if kind == "function_call":
            out.append({"role": "assistant", "content": [{"type": "tool_use", "id": it.get("call_id"),
                                                          "name": it.get("name"),
                                                          "input": json.loads(it.get("arguments") or "{}")}]})
        elif kind == "function_call_output":
            out.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": it.get("call_id"),
                                                     "content": str(it.get("output") or "")}]})
        else:
            role = it.get("role") or "user"
            content = it.get("content")
            if isinstance(content, list):
                text = "".join(c.get("text", "") for c in content if isinstance(c, dict))
            else:
                text = str(content or "")
            if text:
                out.append({"role": "assistant" if role == "assistant" else "user", "content": text})
    return out or [{"role": "user", "content": ""}]
