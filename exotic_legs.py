"""Per-kind leg builders for the static exotic table.

Split from exotic_venues.py for the AST-region budget.
"""
from __future__ import annotations

import venues
from abi_util import encode_path
from v2_codec import _solidly_call, _v2_call


def _aero_param(param) -> tuple:
    """aero_v2 param -> (factory, verified_input, hub, leg1_stable).

    The row ships 2, 3 or 4 fields (king_base.py:1792-1798).
    """
    padded = tuple(param) + (None, False)
    return padded[0], padded[1], padded[2], bool(padded[3])


def _aero_routes(param, tin: str, tout: str):
    """aero_v2 param -> solidly Route[] (king_base.py:1790-1810). None on guard fail."""
    factory, verified_in, hub, leg1_stable = _aero_param(param)
    if tin.lower() != str(verified_in).lower():
        return None
    if hub is not None:
        return ((tin, hub, leg1_stable, factory), (hub, tout, False, factory))
    return ((tin, tout, False, factory),)


def _v3_leg(kind, param, tin, tout, amount, recipient, chain_id, rt):
    """Single-hop v3-family kinds."""
    if kind == "uniswap_v3":
        return rt["uniswap_v3"], venues._v3_single(
            tin, tout, int(param), recipient, amount, 0, chain_id)
    router, tick = param
    return str(router), venues._slipstream_single(
        tin, tout, int(tick), recipient, amount, 0)


def _v2_leg(kind, param, tin, tout, amount, recipient, rt):
    """V2-fork kinds: fixed-path routers and the explicit-router variant."""
    if kind == "v2_router":
        return _v2_router_leg(param, tin, tout, amount, recipient)
    router = (rt["uniswap_v2"] if kind == "uniswap_v2"
              else "0x8cFe327CEc66d1C090Dd72bd0FF11d690C33a2Eb")
    return router, _v2_call(tuple(param), amount, recipient)


def _aero_leg(param, tin, tout, amount, recipient, rt):
    """Aerodrome/solidly Route[] kind."""
    routes = _aero_routes(param, tin, tout)
    if not routes:
        return None
    return rt["aerodrome_v2"], _solidly_call(routes, amount, recipient)




def _v2_exact_input(path: bytes, recipient: str, amount: int) -> str:
    """SwapRouter02 exactInput — selector b858183f, NO deadline field.

    Distinct from the V1 c04b8d59 layout used elsewhere: the params tuple is
    (path, recipient, amountIn, amountOutMinimum), 4 fields not 5. Encoding the
    V1 shape here shifts every word and the swap reverts, dropping the order
    (king_base.py:795, :813).
    """
    from eth_abi import encode
    from eth_utils import to_checksum_address as ck
    args = (path, ck(recipient), int(amount), 0)
    payload = encode(["(bytes,address,uint256,uint256)"], [args])
    return "0x" + ("b858183f" + payload.hex())


def _path_leg(kind: str, tokens, params, recipient: str, amount: int, rt: dict):
    """Packed-path multi-hop for the v3/slipstream path kinds.

    Three different (router, encoding) pairs hide behind one table shape:
      uni_v3_path                   -> SwapRouter02, b858183f (no deadline)
      alien_v3_path                 -> Alien's own router, same b858183f
      aerodrome_slipstream_multihop -> Slipstream router, c04b8d59 (deadline)
    """
    path = encode_path(list(tokens), [int(p) for p in params])
    if kind == "aerodrome_slipstream_multihop":
        router = rt.get("aerodrome_slipstream")
        if not router:
            return None
        return router, venues._exact_input_path(path, recipient, amount)
    if kind == "alien_v3_path":
        return "0xB20C411FC84FBB27e78608C24d0056D974ea9411", _v2_exact_input(path, recipient, amount)
    router = rt.get("uniswap_v3")
    if not router:
        return None
    return router, _v2_exact_input(path, recipient, amount)


def _v2_router_leg(param, tin: str, tout: str, amount: int, recipient: str):
    """v2_router param -> (router, calldata) (king_base.py:1766-1772)."""
    router, verified_in = param[0], param[1]
    if tin.lower() != str(verified_in).lower():
        return None
    tokens = (tin, param[2], tout) if len(param) > 2 else (tin, tout)
    return str(router), _v2_call(tokens, amount, recipient)
