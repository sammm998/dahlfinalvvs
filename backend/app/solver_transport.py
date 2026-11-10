"""One turn of a tool-calling conversation with whichever model the reading was given.

The solving agent's loop is the same whatever answers it: the loop keeps the conversation, the model looks at it and
either calls tools or says it is done. Each provider writes that conversation differently, so each gets a small
adapter with one method:

    turn(new) -> {"text": str, "calls": [{"id", "name", "args"}], "usage": {...}}

`new` is what happened since the last turn - the opening task, or the results of the calls the model made - and the
adapter keeps the rest of the conversation in its own provider's shape. Nothing here runs a tool or reads a drawing.
"""
from __future__ import annotations

import json
from typing import Any

MAX_OUTPUT = 16000


def _tool_specs(schemas: list[dict]) -> list[dict]:
    return [{"name": s["name"], "description": s["description"], "parameters": s["parameters"]} for s in schemas]


class OpenAITurns:
    """OpenAI Responses API: the conversation stays on the server, chained by response id."""

    def __init__(self, client, model: str, system: str, schemas: list[dict]):
        self.client, self.model, self.system = client, model, system
        self.tools = [{"type": "function", **t} for t in _tool_specs(schemas)]
        self.prev: str | None = None

    def turn(self, new: list[dict]) -> dict:
        items = []
        for n in new:
            if n["kind"] == "task":
                items.append({"role": "user", "content": n["text"]})
            else:
                items.append({"type": "function_call_output", "call_id": n["id"], "output": n["output"]})
        kw = dict(model=self.model, instructions=self.system, input=items, tools=self.tools,
                  max_output_tokens=MAX_OUTPUT)
        if self.prev:
            kw["previous_response_id"] = self.prev
        r = self.client.responses.create(**kw)
        self.prev = r.id
        calls, text = [], []
        for o in r.output or []:
            if o.type == "function_call":
                calls.append({"id": o.call_id, "name": o.name, "args": _args(o.arguments)})
            elif o.type == "message":
                text.extend(c.text for c in (o.content or []) if getattr(c, "type", "") == "output_text")
        u = getattr(r, "usage", None)
        return {"text": "".join(text), "calls": calls,
                "usage": {"model": self.model, "tokens_in": getattr(u, "input_tokens", 0) or 0,
                          "tokens_out": getattr(u, "output_tokens", 0) or 0}}


class ClaudeTurns:
    """Anthropic Messages API: the whole conversation is sent each turn, with the system prompt cached."""

    def __init__(self, client, model: str, system: str, schemas: list[dict]):
        self.client, self.model = client, model
        self.system = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        self.tools = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                      for t in _tool_specs(schemas)]
        self.messages: list[dict] = []

    def turn(self, new: list[dict]) -> dict:
        tasks = [n for n in new if n["kind"] == "task"]
        results = [{"type": "tool_result", "tool_use_id": n["id"], "content": n["output"],
                    **({"is_error": True} if n.get("error") else {})} for n in new if n["kind"] == "result"]
        content = results + [{"type": "text", "text": t["text"]} for t in tasks]
        self.messages.append({"role": "user", "content": content})
        with self.client.beta.messages.stream(
                model=self.model, max_tokens=MAX_OUTPUT, system=self.system, tools=self.tools,
                messages=self.messages, thinking={"type": "adaptive"}, output_config={"effort": "high"},
                betas=["server-side-fallback-2026-07-01"], fallbacks="default") as stream:
            r = stream.get_final_message()
        if r.stop_reason == "refusal":
            raise RuntimeError("modellen avböjde uppgiften")
        self.messages.append({"role": "assistant", "content": r.content})
        calls = [{"id": b.id, "name": b.name, "args": b.input if isinstance(b.input, dict) else {}}
                 for b in r.content if b.type == "tool_use"]
        text = "".join(b.text for b in r.content if b.type == "text")
        u = r.usage
        return {"text": text, "calls": calls,
                "usage": {"model": r.model, "tokens_in": (u.input_tokens or 0) + (u.cache_read_input_tokens or 0)
                          + (u.cache_creation_input_tokens or 0), "tokens_out": u.output_tokens or 0,
                          "cached_tokens": u.cache_read_input_tokens or 0}}


class GeminiTurns:
    """Google Gemini: function calling, the conversation kept here as Content objects."""

    def __init__(self, client, model: str, system: str, schemas: list[dict]):
        from google.genai import types
        self.client, self.model, self.types = client, model, types
        decls = [types.FunctionDeclaration(name=t["name"], description=t["description"],
                                           parameters_json_schema=t["parameters"]) for t in _tool_specs(schemas)]
        self.config = types.GenerateContentConfig(system_instruction=system, max_output_tokens=MAX_OUTPUT,
                                                  tools=[types.Tool(function_declarations=decls)])
        self.contents: list[Any] = []

    def turn(self, new: list[dict]) -> dict:
        T = self.types
        parts = [T.Part.from_function_response(name=n["name"], response={"result": n["output"]})
                 for n in new if n["kind"] == "result"]
        parts += [T.Part.from_text(text=n["text"]) for n in new if n["kind"] == "task"]
        self.contents.append(T.Content(role="user", parts=parts))
        r = self.client.models.generate_content(model=self.model, contents=self.contents, config=self.config)
        cand = (r.candidates or [None])[0]
        if cand is None or cand.content is None:
            raise RuntimeError("modellen gav inget svar")
        self.contents.append(cand.content)
        calls, text = [], []
        for i, p in enumerate(cand.content.parts or []):
            if getattr(p, "function_call", None):
                calls.append({"id": f"{p.function_call.name}-{len(self.contents)}-{i}", "name": p.function_call.name,
                              "args": dict(p.function_call.args or {})})
            elif getattr(p, "text", None):
                text.append(p.text)
        u = r.usage_metadata
        return {"text": "".join(text), "calls": calls,
                "usage": {"model": self.model, "tokens_in": getattr(u, "prompt_token_count", 0) or 0,
                          "tokens_out": (getattr(u, "candidates_token_count", 0) or 0)
                          + (getattr(u, "thoughts_token_count", 0) or 0)}}


def _args(raw) -> dict:
    try:
        v = json.loads(raw or "{}")
        return v if isinstance(v, dict) else {}
    except ValueError:
        return {}


def turns(choice: str, system: str, schemas: list[dict]):
    """The adapter for the reading's chosen model, or None when no model is chosen or connected."""
    from . import ai_models
    if choice in (ai_models.ASTRA, ai_models.SOL):
        from .source_model import connection_settings
        key, _ = connection_settings()
        if not key:
            return None
        from openai import OpenAI
        return OpenAITurns(OpenAI(api_key=key, timeout=300, max_retries=1), ai_models.model_id(choice), system, schemas)
    if choice in (ai_models.OPUS, ai_models.FABLE):
        from .claude_model import anthropic_key
        key = anthropic_key()
        if not key:
            return None
        import anthropic
        # Fable tänker längre per tur än Opus: mer tid innan anropet ges upp
        timeout = 1200 if choice == ai_models.FABLE else 600
        return ClaudeTurns(anthropic.Anthropic(api_key=key, timeout=timeout, max_retries=1), choice, system, schemas)
    if choice == ai_models.GEMINI:
        from .gemini_model import gemini_key
        key = gemini_key()
        if not key:
            return None
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=300_000))
        return GeminiTurns(client, ai_models.model_id(choice), system, schemas)
    return None
