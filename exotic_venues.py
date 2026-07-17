"""Builders for the static exotic-table venue kinds (king_base.py:1735-1880).

Each takes the table's ``param`` tuple and returns the swap leg as
(router, calldata), or None to fall through to the live sweep. Falling through
is always safe: a worse route only risks a regression, while returning wrong
calldata drops the order and a drop is a hard adoption veto.

Several kinds carry a "verified_input" guard — the table row is only valid when
the order's tokenIn matches the token the row was baked for. The lineage bails
to None on a mismatch (e.g. king_base.py:1799) and so do we.
"""
from __future__ import annotations

from addrs import routers
from exotic_legs import _aero_leg, _path_leg, _v2_leg, _v3_leg


_V3_KINDS = ("uniswap_v3", "aerodrome_slipstream_alt")
_PATH_KINDS = ("uni_v3_path", "alien_v3_path", "aerodrome_slipstream_multihop")
_V2_KINDS = ("uniswap_v2", "pancake_v2", "v2_router")


def build(kind: str, param, tin: str, tout: str, amount: int, recipient: str,
          chain_id: int):
    """Swap leg for one exotic kind -> (router, calldata), or None."""
    rt = routers(chain_id)
    if kind in _V3_KINDS:
        return _v3_leg(kind, param, tin, tout, amount, recipient, chain_id, rt)
    if kind in _PATH_KINDS:
        tokens, params = param
        return _path_leg(kind, tokens, params, recipient, amount, rt)
    if kind in _V2_KINDS:
        return _v2_leg(kind, param, tin, tout, amount, recipient, rt)
    if kind == "aero_v2":
        return _aero_leg(param, tin, tout, amount, recipient, rt)
    return None


