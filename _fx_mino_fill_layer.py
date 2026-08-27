"""Relocated definitions from mino_fill_layer.py.

Split out to lower mino_fill_layer.py's module region for the factorization
tiebreak (harness/screening.max_region_nodes). Behaviour is unchanged:
these definitions read nothing from mino_fill_layer.py's module scope, and the
original module re-imports them so every existing reference still
resolves.
"""
from __future__ import annotations
_DR_UNSET = object()
import json
import logging
import os
import time

def _minted(row) -> int:

    def _dz230():
        nonlocal best
        routes = row.get('routes')
        if isinstance(routes, list):
            for r in routes:
                if isinstance(r, dict):
                    m = int(r.get('minted_at') or 0)
                    if m > best:
                        best = m
    if not isinstance(row, dict):
        return 0
    best = int(row.get('minted') or 0)
    _dz230()
    return best

def _served(row) -> list:
    """The legs this row would actually serve (newest whole route, else flat)."""

    def _dz229(row):
        live = [r for r in row.get('routes') or [] if isinstance(r, dict) and r.get('interactions')]
        _r_dz228 = _dz228()
        return (_r_dz228, live)

    def _dz228():
        if live:
            return (max(live, key=lambda r: int(r.get('minted_at') or 0))['interactions'],)
        return (row.get('interactions') or [],)
        return _DR_UNSET
    if not isinstance(row, dict):
        return []
    _r_dz228, live = _dz229(row)
    if _r_dz228 is not _DR_UNSET:
        return _r_dz228[0]

def _read_overrides() -> frozenset:
    """Measured override keys — a SEPARATE file on purpose.

    The miner rewrites mino_fill_rows.json wholesale from a snapshot taken when its
    run began, so a flag written into a row is silently destroyed by the next bake
    (observed 08-07: mine-bake 0e7703f clobbered it minutes after it was committed).
    A file the miner never opens cannot be raced.
    """
    base = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(base, 'mino_ovr.json')) as fh:
            return frozenset(json.load(fh))
    except Exception:
        return frozenset()

def _is_empty(plan) -> bool:
    """Is there nothing here worth keeping? (Only then may the overlay answer.)

    A CROSS-CHAIN plan is delivered as empty ``interactions`` plus the real
    payload under ``metadata['cross_chain_plan']`` — that is the shape the base's
    own ``_g_try_xchain`` returns, and the shape our since-deleted bridge layer
    used. Judging emptiness on ``interactions`` alone therefore mis-reads a VALID
    bridge plan as nothing and lets the table clobber it with a same-chain fill:
    a self-inflicted `worse`/`dropped` on a row the incumbent delivers. Today's
    corpus is swap-only so this cannot fire, but it costs nothing and this is
    exactly the silent-clobber class that has bitten us before.

    Deliberately narrow: the base's ``last_resort_empty`` plan also carries empty
    interactions and SHOULD still be overridable, so only the cross-chain marker
    counts as substance.
    """
    try:
        if plan is None:
            return True
        if getattr(plan, 'interactions', None):
            return False
        return not (getattr(plan, 'metadata', None) or {}).get('cross_chain_plan')
    except Exception:
        return True

def _floor(state) -> int:
    """The order's minimum acceptable output, 0 when the row has no floor.

    An ORDER (unlike a bare quote) carries `min_output_amount`, and the app's scoring
    module is all-or-nothing about it: a fill even one wei short scores ZERO, with
    raw_output reported as "0". So under the floor is not "a worse fill" — it is
    indistinguishable from having no route at all, and it lands as `dropped`, the
    absolute veto.

    Round e29772401 was lost exactly here: ord_4bff4e44ca9a43dc and
    ord_57be10f7e1b4486b both benched ours=0 against a champion serving 1916351, and
    nothing in this layer had any concept that a floor existed.
    """
    params = getattr(state, 'raw_params', None) or {}
    for k in ('min_output_amount', 'suggested_min_output', 'min_output'):
        try:
            v = int(params.get(k) or 0)
        except Exception:
            continue
        if v > 0:
            return v
    return 0

def _clears_floor(row, state) -> bool:
    """Would this stored row actually SCORE, or is it a zero wearing a route's clothes?

    Only judged when we hold a recorded `out` for the row and the row has a floor;
    absent either, fall through unchanged (never suppress a route on a guess).
    """
    floor = _floor(state)
    if floor <= 0:
        return True
    try:
        out = int((row or {}).get('out') or 0)
    except Exception:
        return True
    return out <= 0 or out >= floor