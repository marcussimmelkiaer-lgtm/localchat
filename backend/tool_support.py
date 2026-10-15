"""Plumbing behind backend/tools.py. You shouldn't need to edit this file.

`tool` is NobodyWho's own @tool decorator with two additions:
  * every call is reported to the chat window, so you can see which tool the
    model used, with which inputs, and what it got back;
  * an exception inside a tool becomes an "Error: ..." message for the model
    (which can then retry or explain) instead of breaking the reply.
"""
from __future__ import annotations

import functools
import inspect
import itertools
from typing import Callable

import nobodywho

# Shown in the chat window; the model always receives the full result.
MAX_RESULT_CHARS_SHOWN = 4000

# Receives tool-call events for the generation currently running. NobodyWho
# runs tools on its own thread, so this is a plain module global (set by
# llm.NobodyWhoEngine.stream), not a thread-local.
_listener: Callable[[dict], None] | None = None
_ids = itertools.count(1)


def set_listener(fn: Callable[[dict], None] | None) -> None:
    global _listener
    _listener = fn


def _emit(call: dict) -> None:
    listener = _listener
    if listener is None:
        return
    shown = dict(call)
    if len(shown["result"]) > MAX_RESULT_CHARS_SHOWN:
        shown["result"] = shown["result"][:MAX_RESULT_CHARS_SHOWN] + "\n… (truncated)"
    try:
        listener(shown)
    except Exception as e:  # noqa: BLE001 - reporting must never break a tool
        print(f"[tools] listener failed: {e}")


def tool(description: str, params: dict[str, str] | None = None):
    def decorate(fn):
        sig = inspect.signature(fn, eval_str=True)  # real types, even with string annotations

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            bound = sig.bind_partial(*args, **kwargs)
            call = {
                "id": next(_ids),
                "name": fn.__name__,
                "args": {k: v for k, v in bound.arguments.items()},
                "status": "running",
                "result": "",
            }
            _emit(call)
            try:
                result = str(fn(*args, **kwargs))
                call.update(status="done", result=result)
            except Exception as e:  # noqa: BLE001 - hand the error to the model
                result = f"Error: {e}"
                call.update(status="error", result=result)
            _emit(call)
            return result

        # NobodyWho reads the parameters from the signature; without this it
        # would only see the wrapper's (*args, **kwargs).
        wrapper.__signature__ = sig
        wrapper.__annotations__ = {
            name: p.annotation
            for name, p in sig.parameters.items()
            if p.annotation is not inspect.Parameter.empty
        } | {"return": sig.return_annotation}
        return nobodywho.tool(description, params=params)(wrapper)

    return decorate


def enabled_tools(switches: dict) -> list:
    """The tools switched on in config.toml's [tools] section."""
    from .tools import TOOLS

    enabled = []
    for name, on in (switches or {}).items():
        if name not in TOOLS:
            print(f"[tools] config.toml mentions unknown tool '{name}'; known: {', '.join(TOOLS)}")
            continue
        if on is True or (isinstance(on, str) and on.strip().lower() in ("1", "true", "yes", "on")):
            enabled.extend(TOOLS[name])
    return enabled
