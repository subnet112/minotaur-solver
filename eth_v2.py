"""Which Uniswap-V2-family pools the CHAIN-1 ladder asks for. Today: none.

WHAT THIS IS FIXING
===================
`king_base._enumerate_eth_quotes` is the whole candidate set for Ethereum
mainnet -- `_score_aware_swap` sends every `chain_id == _ETH` order straight to
`_score_aware_eth`, which calls it and then picks `max(out)`. Everything it
asks for is a concentrated-liquidity or stable-pool venue:

    _quote_eth_uni           Uniswap V3, four tiers, DIRECT
    _quote_eth_pancake       Pancake V3, four tiers, DIRECT
    _quote_eth_uni_multihop  Uniswap V3 through a hub
    _quote_eth_curve         Curve 3pool, and ONLY if both tokens are in it
    DiscoveryEngine          Uniswap V4

There is no constant-product venue in that list at all. The tree does know how
to quote and build one -- `_sweep_quotes_slow` fans `getAmountsOut` across
`_SWEEP_V2_ROUTERS` and `_shp_v2_fork` encodes the swap -- but every router in
that table is a BASE deployment, as are `_UNIV2_ROUTER` (the constant
`_shp_uniswap_v2` hardcodes) and `_SWEEP_WETH`. The whole V2 layer in this tree
is chain 8453. Mainnet has no V2 coverage on any path.

WHY THAT IS THE EXPENSIVE HALF OF THE MARKET
============================================
A long-tail mainnet ERC20 usually has ONE deep pool and it is a constant-
product pair against WETH -- the pair a project seeds at launch and never
migrates. Its V3 pools, where they exist at all, are thin. So for exactly those
tokens this tree prices the order out of a pool holding a few tens of thousands
of dollars while the pair that holds the token's real depth is never quoted.
That is not a few basis points: a four-figure swap against a shallow tick range
is a double-digit-percent haircut, and a plan comparison cannot see it, because
the losing plan is a perfectly well-formed two-leg approve+swap with the same
leg count as the winner.

WHY IT IS WORTH HAVING ALONGSIDE THE TIER AND SOCKET WORK
=========================================================
`twohop_tier` widened which Uniswap V3 tiers the hub ladder asks for, and
`quoter_wave` widened the socket that ladder runs on and put a wall around it.
Both of those assume the right pool is a V3 pool the ladder failed to reach.
This one says the right pool is not a V3 pool at all. The three are additive
and independent, so each is worth having whichever of them turns out to bind.
The measurements behind all three live in the pipeline state dir, which is not
part of the submitted tree, and are deliberately not repeated here.

WHY IT CANNOT COST A MATCHED ORDER
==================================
Additive only. Every quote the ladder asks for today is asked for unchanged;
these are appended, so the candidate list is a strict superset and `max(out)`
over a superset cannot fall. With `_GAS_WEIGHT` at its `0.0` default the
selection is output alone, and the two tie-breaks behind it (`-gas_est`, then
the `base_plan` guard) only ever see a candidate that already out-quoted the
incumbent pick. A pair that does not exist reverts inside the quote's own
`except Exception: return None` and is dropped by the collector, exactly as a
missing V3 tier is.

The plan shape is one the tree already ships and has executed: venue
`v2_fork`, dispatched by `_build_singlehop_plan` to `_shp_v2_fork`, which reads
its router off the candidate rather than off a chain-8453 constant -- which is
why this emits `v2_fork` and not `uniswap_v2`. Still approve + one router call,
still two interactions, still `amountOutMin` 0, so the harness's intent-level
min_output is the same floor either plan faces.

TRANSFER-FEE TOKENS ARE NOT A NEW REVERT SURFACE, which is the one thing a
`swapExactTokensForTokens` route has to answer for. A fee-on-transfer INPUT
does revert the plain router entry point. It also cannot be funded: the harness
deals the executor its input with `_deal_erc20`, which brute-forces the
`balanceOf` slot and requires `balanceOf(to) == amount` exactly, so an order
whose input charges a transfer fee delivers zero for every solver in the round
and never scores. A fee-on-transfer OUTPUT does not revert here at all --
`amountOutMin` is 0, so the router's only output check passes and the receiver
is simply credited the post-fee amount, which is what the shadow scorer counts.

WHY THE JOB COUNT IS THE REAL CONSTRAINT, and where these go in the list
=======================================================================
`_enumerate_eth_quotes` fans every quote out at once under
`workers = max(1, min(_QUOTER_MAX_WORKERS, len(jobs)))`, cap 48. The ladder
already builds 46 jobs (4 uni + 4 pancake + 38 two-hop), so these four take it
to 50 and the last two queue behind a freed worker.

Which two queue is a choice, and the caller makes it by putting these FIRST:
the jobs pushed past the cap are then the tail of the 1% two-hop block, the
cheapest quotes in the list to delay, rather than the venue class the ladder
has never once asked for. A queued job starts the moment any of the 48 answers,
and `quoter_wave.harvest` abandons whatever has not answered when the window
closes, so the overflow costs latency and never correctness.

WHY ONE HUB IS THE WHOLE ANSWER HERE
====================================
Four jobs is two routers x (direct pair + one hub), and widening the hub does
not buy coverage worth two more jobs each. `_ETH_HUBS` is ordered
`(WETH, USDC, USDT, DAI, WBTC)` and the caller drops the order's own tokens
before slicing, so the single head is WETH for every order that does not
already hold it -- which is the only constant-product hub that matters, because
a long-tail token's seeded pair is a WETH pair or it does not exist. For an
order that IS denominated in WETH the head falls through to a stable, and the
pair that would have served it is the DIRECT one, which is quoted regardless.
So the second and third hubs would be a USDT or DAI leg for a token that has
no USDT or DAI pair: jobs spent past the worker cap to quote pools that are
not there.

A MODULE RATHER THAN A METHOD, for the reason `twohop_tier`, `pancake_tier` and
`quoter_wave` give in their own headers -- and here for a second reason that is
specific to the addresses below. `king_base._sweep_known_tokens` reads its OWN
source and builds `_SWEEP_KNOWN` from every `0x[0-9a-f]{40}` literal in it; the
Base sweep then DEFERS on any token in that set. Putting a router literal in
`king_base` would enlarge that set and silently change which tokens the sweep
declines -- a routing change on the other chain, from a constant that has
nothing to do with it. Kept as `#` comments rather than per-entry docstrings so
the entries cost no deadwood.
"""
from __future__ import annotations

# The two constant-product routers that hold essentially all of mainnet's
# V2-era depth. Both expose the same getAmountsOut/swapExactTokensForTokens
# ABI, which is the ABI `_shp_v2_fork` already encodes.
_ETH_V2_ROUTERS = (
    '0x7a250d5630b4cf539739df2c5dacb4c659f2488d',
    '0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f',
)

# How many hubs each router's path list walks. ONE, and the second hub is not
# a coverage loss -- see WHY ONE HUB IS THE WHOLE ANSWER HERE.
_HUB_WIDTH = 1

# Rough cost of one constant-product hop, and the fixed part around it. Only
# ever a tie-break input: _GAS_WEIGHT defaults to 0.0, so selection is output
# alone. Matches the numbers the tree's own v2 candidates already carry.
_HOP_GAS = 150000
_BASE_GAS = 350000


def v2_specs(tin, tout, mids):
    """(router, token path) for every chain-1 constant-product quote to enumerate.

    `mids` is the caller's own hub list with the order's tokens already
    removed, so the ladder stays owned by `king_base` and this module only
    decides how far down it to walk.

    Never raises, and its failure mode is the ladder exactly as it is today:
    an empty list adds no jobs and changes no candidate.
    """
    try:
        heads = list(mids or ())[:_HUB_WIDTH]
        specs = []
        for router in _ETH_V2_ROUTERS:
            specs.append((router, (tin, tout)))
            specs.extend([(router, (tin, mid, tout)) for mid in heads])
        return specs
    except (TypeError, ValueError, AttributeError):
        return []


def v2_gas(tokens):
    """(gas_est, gas_model) for a path of `len(tokens) - 1` constant-product hops."""
    try:
        hops = max(1, len(tokens) - 1)
    except TypeError:
        hops = 1
    return (_HOP_GAS * hops, _BASE_GAS + _HOP_GAS * hops)
