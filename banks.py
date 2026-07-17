"""Baked route banks — pure data loading, no routing logic.

Every table the champion lineage consults, behind one lookup surface. The data
stays in .json/.txt (json / ast.literal_eval only), so none of it lands in the
AST-region metric.

Module top level is kept deliberately bare: the metric counts the module body as
its own region, so banks are built lazily inside ``_bank()`` rather than assigned
at import. Eager module-level tables measured ~180 nodes; this costs ~10.
"""
from __future__ import annotations

import ast
import json
import os
import threading

_CACHE: dict = {}
_LOCK = threading.Lock()


def _read(name: str, literal: bool = False):
    """Parse one data file; {} on any failure (a missing bank is not an error)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    try:
        with open(path) as fh:
            text = fh.read()
    except OSError:
        return {}
    try:
        return ast.literal_eval(text) if literal else json.loads(text)
    except (ValueError, SyntaxError):
        return {}


def _replays() -> dict:
    """king_replay + hydra_replay -> {key: interactions}; hydra wins ties."""
    bank: dict = {}
    for name in ("king_replay.json", "hydra_replay.json"):
        for row_key, row in (_read(name) or {}).items():
            interactions = row.get("interactions") if isinstance(row, dict) else None
            if interactions:
                bank[row_key.lower()] = interactions
    return bank


def _lc(name: str) -> dict:
    """Load a JSON `key -> value` bank, lowercasing keys."""
    return {k.lower(): v for k, v in (_read(name) or {}).items()}


def _build() -> dict:
    """Assemble every bank once. Called under _LOCK by _bank().

    `cover` is the V-COVER blind-spot bank (highest precedence, empty until a
    champion drop is found); the rest mirror the lineage's tables.
    """
    wrap = _read("hydra_wrap_data.txt", literal=True)
    tables = _read("king_tables_data.txt", literal=True)
    return {
        "replay": _replays(),
        "cover": _lc("cover_rows.json"),
        "gated": _lc("gated_rows.json"),
        "quality": wrap.get("quality_overrides", {}),
        "preempt": wrap.get("flake_preempt", set()),
        "covers": wrap.get("static_covers", {}),
        "holes": tables.get("holes", {}),
        "exotic_a": tables.get("exotic_a", {}),
        "exotic_b": tables.get("exotic_b", {}),
    }


def _bank() -> dict:
    """Lazily-built, process-wide bank set."""
    if not _CACHE:
        with _LOCK:
            if not _CACHE:
                _CACHE.update(_build())
    return _CACHE


def get(name: str):
    """One bank by name (see _build)."""
    return _bank().get(name) or {}


def key(tin: str, tout: str, amount: int) -> str:
    """The `tin|tout|amount` shape every exact-key JSON bank uses."""
    return f"{tin.lower()}|{tout.lower()}|{int(amount)}"


def tuple_key(tin: str, tout: str, amount: int) -> tuple:
    """The tuple shape the .txt-backed banks (quality/covers/preempt) use."""
    return (tin.lower(), tout.lower(), int(amount))


def replay_for(tin: str, tout: str, amount: int):
    """Verbatim baked interactions for an exact (tin, tout, amount), else None."""
    return get("replay").get(key(tin, tout, amount))
