"""The service's meter for language-model requests, as the engine's own transports see it.

The transports in this folder put questions to a language model; what a question may cost, and what it did, is
the service's business (backend/app/api_budget.py). The service installs its two functions here once per process:
`before(model)` raises when the request may not be made - the ceiling is reached, or the model has no price - and
`after(...)` writes what the request cost. Run as plain scripts, with nothing installed, the transports ask freely.
"""
from __future__ import annotations

_check = None
_charge = None


def install(check, charge) -> None:
    global _check, _charge
    _check, _charge = check, charge


def before(model: str) -> None:
    if _check is not None:
        _check(model)


def after(model: str, usage: dict | None, source: str) -> None:
    """usage as the provider reports it: OpenAI's Responses usage or Anthropic's Messages usage."""
    if _charge is None or not usage:
        return
    if "input_tokens_details" in usage or "output_tokens_details" in usage or "cache_read_input_tokens" not in usage:
        tin = int(usage.get("input_tokens") or 0)
        cached = int(((usage.get("input_tokens_details") or {}).get("cached_tokens")) or 0)
        _charge(model, tin, int(usage.get("output_tokens") or 0), cached, 0, source)
    else:
        read = int(usage.get("cache_read_input_tokens") or 0)
        write = int(usage.get("cache_creation_input_tokens") or 0)
        tin = int(usage.get("input_tokens") or 0) + read + write
        _charge(model, tin, int(usage.get("output_tokens") or 0), read, write, source)
