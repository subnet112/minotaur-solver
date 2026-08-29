"""Which fee tiers the CHAIN-1 single-hop ladder asks PANCAKESWAP V3 for.

`king_base._enumerate_eth_quotes` is the whole candidate set for Ethereum
mainnet. It fans one job per (quoter, fee) pair and picks `max(out)`. The
Uniswap quoter and the Pancake quoter are handed the SAME ladder --
`_ETH_UNI_FEES` -- and the two venues do not have the same ladder.

This module owns only the merge rule. Both ladders stay owned by `king_base`
and are passed in, for the reason `twohop_tier` gives in its own header: a
table copied away from the call site that reads it drifts from it.
"""
from __future__ import annotations

# WHAT IS WRONG, and the tree already knows it. king_base:78-79 carries both
# ladders as separate constants, and they differ in exactly one place:
#
#     _PANCAKE_FEES = (100, 500, 2500, 10000)
#     _UNI_FEES     = (100, 500, 3000, 10000)
#
# PancakeSwap V3 chose 0.25% as its mid tier, matching its own V2 fee; Uniswap
# chose 0.30%. Only 100/500/2500/10000 are enabled tick spacings on the
# PancakeV3Factory, so fee 3000 resolves to `address(0)` and the quoter reverts.
#
# Every OTHER site in this tree pairs each venue with its own ladder:
#
#     king_base:4454   [(_quote_pancake, f) for f in _PANCAKE_FEES]
#     king_base:4965   [('pancake_v3', f) for f in _PANCAKE_FEES]
#
# and its own harvested pool census only ever records Pancake at 2500 --
# `_mp2_ext.py:10`, `viking_data.py:6`, four pairs, every one `('pancake_v3',
# 2500)`, none at 3000.
#
# king_base:3348 is the single site that does not, and it is the mainnet one:
#
#     [(_quote_eth_pancake, f) for f in _ETH_UNI_FEES]
#
# So on chain 1 one of the four Pancake jobs is dead by construction, and 2500
# -- the tier where Pancake's non-stable liquidity actually sits -- is never
# priced at all. Same shape as the `twohop_tier` defect (a ladder that never
# asks for a tier that exists), on the single-hop half, and on the chain that
# carries every regression on sub_8bb97076a093's verdict.
#
# WHY THE UNION AND NOT THE SWAP. Asking Pancake for its own four tiers would
# be the tidier fix, but it REMOVES the 3000 job, and removing a candidate can
# only ever lower `max(out)`. Appending cannot: the list stays a strict
# superset of today's, so no order this tree already serves can move, and the
# change cannot manufacture the one thing we cannot afford -- a new regression
# against a champion we are one order away from. The cost of keeping 3000 is a
# single `eth_call` that reverts inside a fan that is already bounded by one
# `_QUOTER_TIMEOUT_S`.
#
# IT STAYS INSIDE ONE QUOTER WAVE. `workers = min(_QUOTER_MAX_WORKERS,
# len(jobs))` with the cap at 48, so the wall clock is one round trip while
# `len(jobs) <= 48`; past that the surplus queues behind a freed worker and the
# stage costs a second trip against the 30s per-plan kill.
#
#     before  4 uni + 4 pancake + (3 mids x 8 + 2 mids x 7) = 46
#     after   4 uni + 5 pancake + (3 mids x 8 + 2 mids x 7) = 47
#
# One slot to spare. A further tier here needs the fan widened first.


def pancake_fees(core_fees, venue_fees):
    """`core_fees`, plus every tier in `venue_fees` it does not already carry.

    Order-preserving, so the ladder the caller passes is quoted first and the
    venue's own additions follow.

    Never raises. Its failure mode is the old behaviour exactly: anything it
    cannot merge returns `core_fees` untouched, which is the tuple this call
    site used before this module existed.
    """
    core = tuple(core_fees or ())
    try:
        return core + tuple(f for f in tuple(venue_fees or ()) if f not in core)
    except (TypeError, ValueError):
        return core
