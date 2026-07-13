"""Shared input normalization helpers for miner strategies."""

from __future__ import annotations

import json
from typing import Any


def parse_list(value: Any) -> list[Any]:
    """Normalize structured runtime values into a Python list."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            return parsed
        return [value] if value else []
    return []


def normalize_float_map(value: dict[str, Any] | None) -> dict[str, float]:
    """Normalize a string-keyed mapping to lowercase keys and float values."""
    normalized: dict[str, float] = {}
    for key, raw in (value or {}).items():
        try:
            normalized[str(key).lower()] = float(raw)
        except (TypeError, ValueError):
            continue
    return normalized
