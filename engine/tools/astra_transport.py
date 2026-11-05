"""The transport that puts a reading's open cases to GPT-6 Astra. Kept out of the engine on purpose.

vvs_engine/semantics/astra.py holds the rules - what may be asked, what may be answered, and how an answer is
checked. This holds only the wire: how to reach the model and how to wait for it. The engine imports none of it
and runs with no network unless a caller hands `analyze_page` a transport built here.

No key appears in this file. Where the request leaves through an agent proxy that attaches the credential,
nothing is sent from here at all; where it does not - a container running the service - the key is read from
OPENAI_API_KEY in the environment at call time and put on the wire, and never written down, logged or returned.

The request goes out over httpx, which the service already depends on. It used to shell out to curl, and the
slim image has no curl: every question to the second reader died with "No such file or directory: 'curl'", which
is a strange way for a drawing to fail. A library that is installed cannot go missing.
"""
from __future__ import annotations

import json
import os
import time
from typing import Callable

API = "https://api.openai.com/v1/responses"
MODEL = os.environ.get("VVS_SECOND_READER_MODEL", "gpt-6-astra")
# reasoning tokens count against this, and a bounded multiple-choice question needs far less room than a review
MAX_OUTPUT_TOKENS = 4000
POLL_SECONDS, POLL_ROUNDS = 5, 60

SYSTEM = ("Du läser VVS-ritningar. Du får ett fall som den geometriska läsningen inte kunde avgöra, tillsammans "
          "med de kandidater ritningen faktiskt erbjuder. Välj en av dem eller svara OKLART. Hitta aldrig på "
          "geometri, koordinater, dimensioner eller beteckningar som inte står i frågan.")


def _auth() -> dict[str, str]:
    """The credential, if this machine is the one that has to supply it.

    Behind an agent proxy the request is authenticated after it leaves and no header belongs here. In a container
    there is no such proxy, so the key is read from the environment at the moment of the call. It goes on the
    wire and nowhere else: never stored, never echoed into an error, never part of a result.
    """
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


def available() -> tuple[bool, str]:
    """Whether a second reader can be reached from here, said plainly rather than found out by failing."""
    if os.environ.get("OPENAI_API_KEY", "").strip():
        return True, "nyckel i miljön"
    if os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"):
        return True, "proxy som fäster referensen"
    return False, "ingen OPENAI_API_KEY och ingen proxy: läsningen står på sin egen geometri"


def _post(body: dict, timeout: int = 120) -> dict:
    import httpx
    with httpx.Client(timeout=timeout) as c:
        r = c.post(API, json=body, headers={"Content-Type": "application/json", **_auth()})
    return _json(r)


def _get(url: str, timeout: int = 60) -> dict:
    import httpx
    with httpx.Client(timeout=timeout) as c:
        r = c.get(url, headers=_auth())
    return _json(r)


def _await(d: dict) -> str:
    """Put a background response to bed and hand back the words it produced."""
    if d.get("error"):
        raise RuntimeError(str(d["error"])[:200])
    rid = d["id"]
    for _ in range(POLL_ROUNDS):
        if d.get("status") in ("completed", "failed", "incomplete"):
            break
        time.sleep(POLL_SECONDS)
        d = _get(f"{API}/{rid}")
    return d


def _meter():
    try:
        from . import meter                                  # noqa: PLC0415
    except ImportError:
        import meter                                         # noqa: PLC0415
    return meter


def _call(body: dict, source: str) -> dict:
    """One request, asked of the service's meter first and paid for after."""
    m = _meter()
    m.before(body["model"])
    d = _await(_post(body))
    m.after(body["model"], d.get("usage"), source)
    return d


def _text_of(d: dict) -> str:
    return "".join(c.get("text", "")
                   for o in d.get("output", []) for c in (o.get("content") or [])
                   if c.get("type") == "output_text")


def _json(r) -> dict:
    try:
        return r.json()
    except Exception:
        # a credential can appear in a proxy's own diagnostics, so only the opening of the body is quoted back
        raise RuntimeError(f"icke-JSON från {API} ({r.status_code}): {(r.text or '')[:200] or 'inget svar'}")


def transport(effort: str = "low") -> Callable:
    """A callable for analyze_page(second_reader=...). Raising is safe: the case simply stays ambiguous."""
    def ask(q) -> str:
        body = {"model": MODEL, "instructions": SYSTEM, "input": q.as_prompt(),
                "max_output_tokens": MAX_OUTPUT_TOKENS, "reasoning": {"effort": effort}, "background": True}
        return _text_of(_call(body, "andra_läsaren"))
    return ask


def vision_transport(effort: str = "low") -> Callable:
    """A callable for review.vision.look(ask=...). Images go up; only words come back.

    Nothing this returns can become geometry - vision.look has no way to write into a reading - so the only
    risk here is cost and latency, not a wrong metre.
    """
    import base64

    def ask(prompt: str, images: list[bytes]) -> str:
        content: list[dict] = [{"type": "input_text", "text": prompt}]
        for png in images:
            content.append({"type": "input_image",
                            "image_url": "data:image/png;base64," + base64.b64encode(png).decode()})
        body = {"model": MODEL, "input": [{"role": "user", "content": content}],
                "max_output_tokens": 8000, "reasoning": {"effort": effort}, "background": True}
        return _text_of(_call(body, "granskning"))
    return ask


AGENT_SYSTEM = (
    "Du är Dahls agent. Du arbetar mot ritningar i användarens samtal och du svarar på svenska - utom när "
    "frågan ber om ett annat språk (\"Reply in English\"): då skrivs hela svaret på det språket.\n"
    "\n"
    "En uppladdad fil är inte läst förrän någon läst den. Ber användaren om mängder, beteckningar eller rör "
    "ur en fil som inte är läst: starta läsningen med las_ritning direkt. Fråga inte om skalan först - motorn "
    "hittar den själv ur bladets skalstock och utskrivna skala, och skickar du en egen skala åsidosätter du "
    "det den läste. Skicka `skala` bara om en läsning uttryckligen sagt att den inte kunde hitta någon.\n"
    "\n"
    "Läsningen tar en stund. Säg att du startat den, säg vad den kommer att ge, och be användaren fråga igen "
    "om ett ögonblick - eller fråga om mängderna direkt om filen redan var läst.\n"
    "\n"
    "Du räknar aldrig själv. Varje siffra du säger ska komma ur ett verktygsanrop, och du hittar aldrig på "
    "rör-id, koordinater, dimensioner eller beteckningar. Vet du inte, säg att du inte vet och säg vad som "
    "skulle avgöra det.\n"
    "\n"
    "Har användaren markerat något i ritningen står det i frågan. 'Det här' betyder då det markerade.\n"
    "\n"
    "Verktygen som börjar på foresla_ ändrar ingenting. De visar vilken rättelse som skulle skrivas och vad "
    "läsningen säger att den kostar i meter. Använd dem när användaren säger att läsningen är fel, redovisa "
    "förslaget som det kom tillbaka, och säg att det skrivs först när användaren godkänner det. Godkänner gör "
    "du aldrig åt någon.\n"
    "\n"
    "Obekräftat, att granska, utan beteckning eller tvetydigt: börja med hitta_obekraftade. För varje fall "
    "säger den vad bladet knyter geometrin till. Ber användaren att det olösta ska lösas, använd "
    "foresla_losning_for_obekraftade för allt bladet själv avgör, och foresla_tilldela_geometri eller "
    "foresla_bekrafta_ror för ett enskilt fall. Välj aldrig en beteckning som bladet inte knyter till just den "
    "geometrin; säg i stället varför fallet står kvar.\n"
    "\n"
    "Svara kort och i ren text. Panelen visar text som den är, så använd inga markdown-tabeller, ingen fetstil "
    "och inga rubriker - en rad per sak, indragen med två mellanslag när du räknar upp. När svaret rör geometri: "
    "säg siffran, säg var den kommer ifrån, och lista rör-id:n så att läsaren kan trycka på dem och se dem på "
    "ritningen."
)


def agent_transport(effort: str = "low") -> Callable:
    """One turn of a tool-calling conversation. The caller runs the loop and owns every tool.

    Given the messages so far and the tool contract, this returns either the calls the model wants made or the
    words it wants to say. Nothing here can reach the drawing: the tools are the caller's, so a number can only
    come from the reading that produced it.
    """
    def ask(items: list[dict], tools: list[dict], previous_response_id: str | None = None) -> dict:
        """One turn. `previous_response_id` chains onto the last answer instead of resending the conversation.

        A reasoning model keeps its own chain of thought server-side, and resending the transcript without it
        left the model where it started: it called the same tool for a takeoff nine times over and never got as
        far as saying the number. Chaining hands it back its own place in the conversation.
        """
        body = {"model": MODEL, "instructions": AGENT_SYSTEM, "input": items, "tools": tools,
                "max_output_tokens": 6000, "reasoning": {"effort": effort}, "background": True}
        if previous_response_id:
            body["previous_response_id"] = previous_response_id
        d = _call(body, "agent")
        calls = [{"call_id": o.get("call_id"), "name": o.get("name"), "arguments": o.get("arguments") or "{}"}
                 for o in d.get("output", []) if o.get("type") == "function_call"]
        return {"calls": calls, "text": _text_of(d), "status": d.get("status"), "id": d.get("id")}
    return ask
