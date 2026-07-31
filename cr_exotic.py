"""Static exotic-route dispatch — the lineage's `_static_exotic_plan`
(king_base.py:3164), which runs BEFORE the live sweep.

Some pairs are not DEX routes at all. USDC<->sUSDS is a Sky PSM3 peg swap:
oracle-priced, no slippage, and no Uniswap/Aerodrome quote can match it. The
champion resolves these from a static (tokenIn, tokenOut) -> (kind, params)
table shipped as data (king_tables_data.txt), so the lookup costs no RPC.

That table is the majority of the live orderbook — USDC->sUSDS alone was 292 of
300 recent orders — so skipping this layer means dropping or badly regressing
nearly every real order, whatever the live sweep finds.

Only the kinds we can build are served here; anything else returns None and
falls through to the live sweep, which is the safe direction (a worse route
beats a dropped order, and a drop is a hard adoption veto).
"""
from __future__ import annotations

import cr_banks as banks
import cr_consts as consts
import cr_exotic_v4 as exotic_v4
import cr_exotic_venues as exotic_venues
import cr_venues as venues


def _sky_psm() -> str:
    """Sky PSM3 on Base (king_consts.py:82)."""
    return "0x1601843c5E9bc251A3272907010AFa41Fa18347E"


def _psm_swap(tin: str, tout: str, amount: int, recipient: str) -> str:
    """PSM3.swapExactIn(assetIn, assetOut, amountIn, minOut, receiver, referral).

    minOut is 0 on the call, as in the lineage (king_base.py:2107-2120): the
    harness enforces the intent's min, and the PSM rate is deterministic, so a
    per-call min only adds a revert path.
    """
    from eth_abi import encode
    from eth_utils import to_checksum_address as ck
    sig = ["address", "address", "uint256", "uint256", "address", "uint256"]
    args = [ck(tin), ck(tout), int(amount), 0, ck(recipient), 0]
    return "0x" + ("1a019e37" + encode(sig, args).hex())


def _build_sky_psm(tin: str, tout: str, amount: int, recipient: str) -> list:
    """approve + PSM swap. Fully static — no RPC, no quote."""
    psm = _sky_psm()
    return [
        {"target": tin, "value": "0", "data": venues.encode_approve(psm, int(amount))},
        {"target": psm, "value": "0", "data": _psm_swap(tin, tout, amount, recipient)},
    ]


def lookup(tin: str, tout: str):
    """(kind, params) for this pair from the static exotic tables, else None.

    exotic_b WINS on key collisions: the lineage merges them as
    ``{**exotic_a, **exotic_b}`` (king_tables1.py:12), so a pair present in both
    resolves to b's row. Checking a first silently serves the superseded route —
    a wrong venue, i.e. a regression, on exactly the pairs that were re-baked.
    """
    key = (tin.lower(), tout.lower())
    return banks.get("exotic_b").get(key) or banks.get("exotic_a").get(key)


def _interactions(router: str, data: str, tin: str, amount: int) -> list:
    """approve + swap, the shape every exotic leg shares."""
    return [
        {"target": tin, "value": "0",
         "data": venues.encode_approve(router, int(amount))},
        {"target": router, "value": "0", "data": data},
    ]


def _split(hit) -> tuple:
    """table row -> (kind, param)."""
    if not isinstance(hit, (list, tuple)):
        return str(hit), None
    return hit[0], (hit[1] if len(hit) > 1 else None)


def _dispatch(kind, param, tin, tout, amount, recipient, chain_id):
    """Build interactions for one exotic kind. None => fall through to sweep.

    sky_psm and uniswap_v4_ur have their own (non approve+swap) interaction
    shapes; every other kind is a (router, calldata) leg wrapped as approve+swap.
    """
    if kind == "sky_psm":
        return _build_sky_psm(tin, tout, amount, recipient)
    if kind == "uniswap_v4_ur":
        return exotic_v4.build(param, tin, tout, amount, recipient)
    try:
        leg = exotic_venues.build(kind, param, tin, tout, amount, recipient, chain_id)
    except Exception:
        leg = None
    return _interactions(leg[0], leg[1], tin, amount) if leg else None


def plan(tin: str, tout: str, amount: int, recipient: str, chain_id: int):
    """Static exotic interactions for this pair, or None to fall through.

    Base only: every row was baked against Base venues, and the lineage gates
    the whole layer on ``chain_id != _BASE`` (king_base.py:1916).
    """
    if int(chain_id) != consts.BASE:
        return None
    hit = lookup(tin, tout)
    if not hit:
        return None
    kind, param = _split(hit)
    return _dispatch(kind, param, tin, tout, amount, recipient, chain_id)
