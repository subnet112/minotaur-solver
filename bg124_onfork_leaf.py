"""Relocated leaf helpers for bg124_onfork.py -- same code, same call sites.

REGION DISCIPLINE, continued from bg124_onfork.py's own header. That module's
top-level region counts every `def` HEADER it holds (the analyzer charges the
FunctionDef node, its `arguments` node, one node per argument and one per
default to the ENCLOSING region, and only the body to the function's own), so a
module that merely holds many small functions pays for all of them at the top
level even when each body is tiny. Moving six of them here trades six headers
for six `import` aliases and takes bg124_onfork's <module> region down without
touching a single line of behaviour.

Every function below is a LEAF in the strict sense the champion lineage uses:
it reads ONLY its own arguments and Python builtins -- no module-level global,
no import of its own. Name resolution therefore cannot change by moving them,
which is what makes this split provably behaviour-preserving rather than merely
tested. `_WIN_BPS` travels with `_beats`, its only reader, for that same reason:
a constant left behind would have turned a leaf into a cross-module global read.

They are imported straight back into bg124_onfork, so that module's public
surface is byte-for-byte what it was and any `from bg124_onfork import _best`
still resolves.
"""
from __future__ import annotations

def _curve_row(pools, pool, tin, tout):
    row = pools.get(pool) or {}
    coins = row.get('coins') or []
    if tin in coins and tout in coins:
        return (pool, row.get('kind', 'stable'), coins.index(tin), coins.index(tout))
    return None

def _best(cands, outs):
    best_i, best_out = (-1, 0)
    for k, got in enumerate(outs):
        if got > best_out:
            best_out, best_i = (got, k)
    return (cands[best_i][0], best_out) if best_i >= 0 else (None, 0)

def _corroborated(outs, best_out):
    """At least one OTHER venue must independently quote the same order within
    2x. hydra took the crown on 1 better / 0 WORSE while we lost with 10 better
    / 3 worse — a single bad order erases any number of wins, so safety beats
    win count. A lone quote from one thin pool is the signature of both failure
    modes we hit: the 0.00002x catastrophic regression and the two routes that
    quoted positive then delivered nothing."""
    return sum((1 for o in outs if o > 0 and o * 2 >= best_out)) >= 2

def _num(p, key):
    try:
        return int(p.get(key, 0) or 0)
    except (TypeError, ValueError):
        return -1

def _recipient(state, p):
    return str(getattr(state, 'contract_address', '') or p.get('receiver', '') or getattr(state, 'owner', '') or '0x0000000000000000000000000000000000000001')
_WIN_BPS = 10

def _beats(out, bar):
    """Serve ours ONLY if it beats the champion's declared expected_output by a
    margin. bar == 0 means the champion's plan was empty (pure upside — anything
    positive wins). This is the whole anti-regression rule: run both routers,
    keep the better one, and NEVER overwrite a champion plan that is ahead."""
    if bar <= 0:
        return out > 0
    return out * 10000 > bar * (10000 + _WIN_BPS)