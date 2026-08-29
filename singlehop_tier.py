"""Which Uniswap V3 fee tier the LAST-RESORT single hop asks for.

WHAT THIS IS FIXING
===================
`king_base._best_effort_singlehop_plan` is rung (2) of `_last_resort_plan`: an
approve + `exactInputSingle` built with no RPC verification at all, for pairs
every primary path already gave up on. Its own docstring is honest about the
odds -- "may or may not fill" -- but until now it asked for fee tier 3000 on
EVERY chain and EVERY pair, a constant with no source behind it.

Two other places in this tree already record what that costs:

  _champ_base._chain1_baked_serve  ":910" and ":935" -- "the base engine's
    blind single-hop (exactInputSingle fee=3000, min_out=0) reverts on a pool
    that does not exist". Chain 1 answers that by refusing the hop entirely
    (`_CHAIN1_SKIP`), because on a champion-served order a revert scores
    `worse` and a clean drop scores less badly.

  `_KNOWN_POOLS[8453]` in `strategies/dex_aggregator/baseline_solver.py` --
    the ONE Base pool this tree seeds pool discovery from is
    `0xd0b53D9277642d899DF5C87A3966A349A798F224`, the WETH/USDC pool, and it is
    not the 3000 one.

Chain 8453 has no equivalent of the chain-1 refusal, so the blind 3000 hop
ships. `state/last-scored-verdict.json` (sub_ef966e486a99, the tree currently
on the throne) measures the result: FIVE Base WETH<->USDC rows -- hist
ord_4e9e550239ec41d5, ord_666009e8e85d40a5, ord_7dc3630137ea4c7c,
ord_9c399716c1354e28, ord_fe57757cf67c470a -- scored `champ "0" / chal "0"`,
verdict `skip`. `state/last-perf-ab.json` carries the calldata for all of them
and both trees emit the identical `0x04e45aaf ... fee=0xbb8` hop.

WHERE 500 COMES FROM
====================
Not from an outside quote -- from this tree's own known-good fill data.
`mino_fill_rows.json` and `hydra_replay.json` both carry a Base WETH->USDC
`exactInputSingle` against SwapRouter02 `0x2626664c...` at fee `0x1f4` = 500,
and nothing in either table uses 3000 for that pair except the blind hop's own
replayed output. So 500 is the tier this tree has already SEEN deliver on Base,
and 3000 is the tier it has only ever seen return zero.

WHY IT CANNOT COST A MATCHED ORDER
==================================
The table is consulted from exactly one call site, the last-resort hop, so it
can move no order that any primary path serves. On the pair it does move, the
validator's own report has the incumbent -- which is this tree, we hold the
throne -- delivering "0". A row at zero cannot be cut past the 100bps floor and
cannot be dropped, because the plan keeps its shape: still approve +
exactInputSingle, still two interactions, still `amount_out_minimum=0`. The
only reachable outcomes are the zero we already score and a `blind_spot_cover`.

The fallback is the old constant, and every failure path returns it, so a
malformed address, an unreadable chain id or a missing table entry all leave
the caller on precisely the behaviour it had before this module existed.

A MODULE RATHER THAN A METHOD, for the reason `xc_order` states in its own
header: a table copied into a class body drifts from the call site that reads
it, and `king_base`'s class regions are among the largest in the tree. Kept as
`#` comments rather than per-entry docstrings so the entries cost no deadwood.
"""
from __future__ import annotations

# MEASURED AFTER THE FACT — 2026-08-27, HEAD 016ecb0, from the calldata in
# state/last-perf-ab.json and the scored rows of sub_5f82de0ab652. Two of the
# three claims in the header above did not survive contact, so read this first.
#
# 1. THE TABLE WORKS, AND BOTH DIRECTIONS KEY CORRECTLY.
#    ord_9c399716c1354e28 (Base USDC->WETH, 1 USDC) emits
#    `0x04e45aaf ... fee=0x1f4` = 500. The sort in single_hop_fee does what it
#    claims and one entry really does answer the pair both ways.
#
# 2. "EXACTLY ONE CALL SITE" IS WRONG, and it matters.
#    ord_666009e8e85d40a5 (Base WETH->USDC) still emits fee=0xbb8 = 3000 on the
#    SAME chain, SAME pair, SAME router (0x2626664c) and SAME recipient. It
#    cannot have come through here -- the table would have said 500. So that
#    direction is served by an EARLIER rung that carries its own tier, and this
#    module only ever sees the orders that fall all the way to last resort.
#    king_base has two call sites (the fee helpers reached from :3645 and
#    :4193), not one, and neither is the only place a Base v3 tier is chosen.
#
# 3. THE TIER WAS NEVER WHY THOSE ROWS SCORED ZERO, so fixing it could not have
#    covered them, and the header's "the only reachable outcomes are the zero we
#    already score and a blind_spot_cover" was true but empty.
#
# WETH->USDC ON BASE IS ARITHMETICALLY DEAD AT THESE SIZES. DO NOT SPEND A TICK.
# The ladder replays ord_666009e8e85d40a5 and ord_fe57757cf67c470a at
# amount_in = 10 / 1000 / 10000 WEI of WETH (0.01x / 1x / 10x -- read them in
# last-perf-ab.json). WETH carries 18 decimals and USDC 6, so 1000 wei is ~1e-15
# WETH, and the output truncates to 0 USDC units before any pool is consulted.
# No tier, no venue and no router changes that: the integer result is zero.
# This is the same class as the rebasing-input pairs in the operator brief --
# unwinnable by construction, not by our routing -- and it is why these rows
# stay `skip`/`champ 0 / chal 0` no matter what this table returns.
#
# The tier entry below is still correct and still worth keeping: it is the
# measured-good pool for the pair, and it governs any REAL-sized Base WETH/USDC
# order that reaches last resort in a future round. It just never had the power
# to move the dust rows it was written for.

# The tier the blind hop asked for everywhere, and still the answer for any
# pair this table has no measurement for.
_DEFAULT_FEE = 3000

_BASE_WETH = '0x4200000000000000000000000000000000000006'
_BASE_USDC = '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'

# (chain id, the pair sorted) -> the tier this tree's fill rows deliver on.
# Sorted, so one entry answers both directions of the pair; an order is a
# direction, a pool is not.
_LIQUID_TIER = {
    (8453, (_BASE_WETH, _BASE_USDC)): 500,
}


def single_hop_fee(chain_id, token_in, token_out, default=_DEFAULT_FEE):
    """The fee tier to encode for this pair, or `default` when unmeasured.

    Never raises. The caller is the never-raising last-resort rung, and a
    lookup that threw there would fall out to `_empty_plan` -- a DROPPED order
    and a hard veto, which is far worse than the reverting hop this replaces.
    """
    try:
        low = str(token_in or '').lower()
        high = str(token_out or '').lower()
        if not low.startswith('0x') or not high.startswith('0x'):
            return default
        if low > high:
            low, high = high, low
        return _LIQUID_TIER.get((int(chain_id or 0), (low, high)), default)
    except (TypeError, ValueError, AttributeError):
        return default
