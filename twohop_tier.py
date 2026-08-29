"""Which Uniswap V3 fee tiers the CHAIN-1 two-hop ladder asks for.

WHAT THIS IS FIXING
===================
`king_base._enumerate_eth_quotes` is the whole candidate set for Ethereum
mainnet -- `_score_aware_swap` sends every `chain_id == _ETH` order straight to
`_score_aware_eth`, which calls it and then picks `max(out)` (`_GAS_WEIGHT`
defaults to `0.0`, so the score is pure output). Its two-hop half was built from

    _ETH_UNI_FEES        = (100, 500, 3000, 10000)
    _ETH_UNI_FEES_TWOHOP = ((500,500), (500,3000), (3000,500), (3000,3000),
                            (100,500), (500,100), (100,3000), (3000,100))

The single-hop ladder asks for the 1% tier. The two-hop ladder never does --
`10000` appears in no pair. So for any token whose real V3 liquidity sits in the
1% pool, this tree can quote it DIRECT against the target and cannot quote it
through a hub at all, while every hub route it does quote is priced out of a
0.3%-or-thinner pool that the token barely trades in.

Long-tail tokens are exactly the ones that live at 1%, and they are exactly the
rows we lose.

WHAT IT COST, MEASURED
======================
`state/last-verdict.json`, sub_8bb97076a093, round-e29795256-n1:

    1 better / 3 worse / 82 matched / 0 dropped
    reject: 2 order(s) cut >1% (hard floor)

Both cuts are chain 1, `intent_function: swap`, and both read RISK in
`state/last-perf-ab.json` with `our_legs == champ_legs == 2` -- two working
two-hop plans, ours priced worse:

    q_ddfde9927472  0xA0b73E1F (8dp, ~10.9k units) -> USDC
                    champ 624,819,368   ours 448,540,849   ratio 0.7179
    q_7c7ae411e6d8  0x68bbEd6A -> 0x67466BE1  (both long-tail, 18dp)
                    champ 6.746e25      ours 6.088e25      ratio 0.9024

A leg-count comparison cannot see this -- `lib/perf_ab.py` normalises
`quoted_output` and `min_output_amount` away before diffing, and says so at
":61": "output comparison, so it cannot rank two working plans". Both ids sit in
`state/veto-ids.json` already, so perf-check forces them into the draw and the
next SCORED verdict is what settles it.

THE VERDICT CAME BACK AND IT SETTLED AGAINST THIS THEORY
========================================================
sub_a95f9e8cb546 / round-e29796909-n1 was built from 7496c47, which has c7b2fd9
-- this module, 1% tiers and all -- as an ancestor. So the fix below WAS in the
scored tree, and the row it was written for did not move:

    q_ddfde9927472   before c7b2fd9   champ 624,819,368  ours 448,540,849  0.7179
                     WITH c7b2fd9     champ 637,100,194  ours 455,285,675  0.7146

Both sides drifted up ~2% with the market and the RATIO held to three decimals.
A ladder that had been missing the pool this token actually trades in would not
reproduce its own loss to within 0.3% of itself; a constant size-independent
ratio is the signature of a route that is being priced consistently, just not
the route the champion takes. `q_7c7ae411e6d8`, the other id named above, is not
in the scored per_order at all -- it was not drawn -- so this module has ONE
measured row and that row says no.

WHAT THIS DOES NOT MEAN. The 1% pairs are not wrong and should not be reverted:
`twohop_routes` is strictly additive over a `max(out)` selection, so it cannot
have caused the 0.7146 either, and the WHY IT CANNOT COST A MATCHED ORDER
argument below is unaffected -- 93 rows scored `matched` on this tree. It means
the CAUSE is elsewhere and the next reader should not spend a tick re-widening
the tier ladder. What is still unread is WHICH route the champion takes: both
plans are one approve + one router call (`our_legs == champ_legs == 2`), so the
difference is the path inside that single call, and no gate in this tree prints
it. `bin/exec-check` is the only one that executes -- and note it must be left
to the pipeline, which already runs it every cycle, because a hand-run collides
with the certify daemon on anvil 18650 and poisons the fork mid-run.

A BAKED PIN WAS THE NEXT OBVIOUS SUSPECT, AND IT IS NOT ONE EITHER
==================================================================
A constant size-independent ratio is also the signature of a PINNED route -- a
baked cover row serving this pair from a table, which would be immune to tier
widening for the same reason it is immune to everything else. Worth ruling out
before anyone spends a tick on it, because the tree does hold such tables and
CRO is in one of them:

    mino_fill_rows.json   two rows, 1|<app>|<CRO>|<USDC>|<amount>
                          amount 1029104332564  out 479646612  tgt 474122181
                          amount  732462808656  out 355720659  tgt 277908855

Both are the SAME path this ladder would pick, decoded from their calldata:
CRO --10000--> WETH --100--> USDC. Both BEAT their recorded target.

They do not serve `q_ddfde9927472`. The key is amount-EXACT and the veto row's
amount is 1091784053108, which appears in no table in this tree
(`grep -c` over mino_fill_rows.json and g2_covers.json: 0). So no baked row is
pinning this order; the live ladder really does route it, and the 0.7146 is the
ladder's own answer.

WHAT THOSE ROWS CANNOT TELL YOU, stated because the numbers invite the
arithmetic. Comparing their rate against the veto row's looks like it should
locate the loss, and it cannot: `minted` on the newer row is 1786422740, about
16 days before round-e29796909 scored the veto. The champion's own rate across
those two observations moves 4.607e-4 -> 5.835e-4, i.e. +27%, which is a market
move and a different fork block, not a routing difference. Two quotes taken 16
days apart cannot be differenced. `bin/exec-check` prices both trees at ONE
pinned block and is still the only gate that can settle which path the champion
takes -- and it must be left to the pipeline, which runs it every cycle.

WHY THE JOB COUNT IS THE REAL CONSTRAINT
========================================
`_enumerate_eth_quotes` fans every quote out at once:

    workers = max(1, min(_QUOTER_MAX_WORKERS, len(jobs)))     # _QUOTER_MAX_WORKERS = 48

so while `len(jobs) <= 48` the wall clock is one round trip bounded by
`_QUOTER_TIMEOUT_S` (5.0), NOT a function of how many tiers are asked for. Past
48 the surplus queues behind a freed worker and the stage costs a second trip --
against `harness/orchestrator`'s 30s per-plan kill, which is the wall
`search_wall.py` was written for.

Today: 4 uni + 4 pancake + 3 mids x 8 pairs = 32 jobs.
Here:  4 + 4 + 3 x 8 + 2 x 7 = 46 jobs. Still one wave, still one 5s bound.

THAT 46 IS NO LONGER THE COUNT, AND THE WAVE CLAIM WITH IT. Two later modules
append to the same list, so the arithmetic above describes a call site that has
not existed for several commits. Counted at the call site,
`king_base._enumerate_eth_quotes:3417`:

    v2_specs        2 routers x (1 direct + _HUB_WIDTH 1 mid)      =  4
    _ETH_UNI_FEES                                                  =  4
    pancake_fees    the 4 core tiers + 2500, which is not in them   =  5
    uni_routes      3 mids x 8 core + 2 mids x 7 exotic             = 38
                                                                     ---
                                                                      51

against `_QUOTER_MAX_WORKERS` 48, so THREE jobs already queue behind a freed
worker rather than starting in the first wave. The call site knows this and
orders the list around it -- v2 first, deliberately, so that what waits is the
tail of this module's 1% block and not the only constant-product quotes on the
chain. Queued is not lost: `harvest` bounds the whole stage on one window, and
an eth_call that returns well inside 5s still lands. The three that wait are
the last three of the SECOND exotic mid -- (10000,100), (100,10000) and
(10000,10000).

So the headroom this header appears to offer is not there. Anyone adding a
tier pair here is not spending slack, they are pushing one more entry of this
block past the cap and lengthening the queue behind it. Re-count at the call
site before believing any number in this file: two of the three summands above
were added by modules that did not exist when it was written.

That budget is the reason the 1% tiers go on the first TWO mids rather than
all three: on the count above a third mid is 58 jobs, ten past the cap and
seven more than today. `_ETH_HUBS` is
ordered `(WETH, USDC, USDT, DAI, WBTC)` and `_enumerate_eth_quotes` drops the
order's own tokens before slicing, so the first two heads are the two deepest
hubs still available for this pair -- WETH plus whichever of USDC/USDT the
order is not already denominated in. A long-tail token's 1% pool is against one
of those or it is against nothing.

WHY IT CANNOT COST A MATCHED ORDER
==================================
Additive only. The core pairs are enumerated exactly as before, over the same
`eth_mids[:3]`, and the 1% pairs are appended -- so the candidate list is a
strict superset of today's and `max(out)` over a superset cannot fall. With
`_GAS_WEIGHT` at its `0.0` default the selection is output alone, and the two
tie-breaks behind it (`-gas_est`, then the `base_plan` guard) only ever see a
candidate that already out-quoted the incumbent pick.

Shape is unchanged too: a new pair produces the same
`venue: 'uniswap_v3_multihop'` candidate `_shp_uniswap_v3_multihop` already
builds, still `encode_exact_input(..., amount_out_minimum=0)`, still one
approve + one router call. So a 1% route cannot revert on a slippage floor the
0.3% route would have cleared -- the harness enforces the order's min_output at
the intent level, which is the same floor either plan faces.

A quote that fails returns `None` and is dropped by the collector, so a tier
with no pool costs one `eth_call` and changes nothing.

A MODULE RATHER THAN A METHOD, for the reason `singlehop_tier` gives in its own
header: a table copied into a class body drifts from the call site that reads
it, and `king_base`'s regions are among the largest in the tree. Kept as `#`
comments rather than per-entry docstrings so the entries cost no deadwood.
"""
from __future__ import annotations

# How many hubs the two-hop ladder walks. The historical `eth_mids[:3]`, kept
# as it was -- widening it is a separate question with its own job-count bill,
# and this change is deliberately only about the tier.
_MID_WIDTH = 3

# How many of those hubs also get the 1% pairs. Two, because three is 53 jobs
# and a second quoter wave; see WHY THE JOB COUNT IS THE REAL CONSTRAINT.
_EXOTIC_MID_WIDTH = 2

# The 1% tier, paired against every tier the hub leg actually trades in, plus
# itself for a long-tail -> long-tail order where both legs are thin.
# `_ETH_UNI_FEES` already asks for 10000 on the DIRECT hop; this is the same
# tier the hub routes were missing.
_EXOTIC_FEES = (
    (10000, 500),
    (500, 10000),
    (10000, 3000),
    (3000, 10000),
    (10000, 100),
    (100, 10000),
    (10000, 10000),
)


def twohop_routes(mids, core_fees):
    """(hub, fee pair) for every chain-1 two-hop quote to enumerate.

    `core_fees` is the caller's own `_ETH_UNI_FEES_TWOHOP`, so the tier ladder
    stays owned by `king_base` and this module only appends to it.

    Never raises, and its failure mode is the old behaviour exactly: `core` is
    built the way the inline comprehension built it, and any problem appending
    the 1% pairs returns that list untouched.
    """
    heads = list(mids or ())[:_MID_WIDTH]
    core = [(mid, fees) for mid in heads for fees in tuple(core_fees or ())]
    try:
        return core + [(mid, fees)
                       for mid in heads[:_EXOTIC_MID_WIDTH]
                       for fees in _EXOTIC_FEES]
    except (TypeError, ValueError, AttributeError):
        return core
