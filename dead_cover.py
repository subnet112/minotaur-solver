"""Cover an order whose CHAMPION ROUTE IS PROVABLY DEAD ON THE FORK.

THE ONE ROW CLASS THE LADDER CANNOT REACH
=========================================
`bg124_onfork.try_cover` fires on a champion plan with NO interactions.
`champ_route`'s header carries the measurement for the rows that are not that:
22 of 220 scenarios on `state/last-perf-ab.json` carry `live_champ_zero: true`
while the champion emits a well-formed two-leg plan, and our plan on every one of
them is byte-identical to it. Those score `blind_spot_repeat` -- delivered by
nobody, credited to nobody, and the validator's own note calls the row "the
single most actionable row for the miner".

The champion is not silent on them. It emits a default-fee `exactInputSingle`
with `amountOutMinimum` zero -- the answer it gives a pair it has no route for --
and that hop lands in a pool that does not hold the pair. It quotes itself a
number and delivers nothing.

WHAT IS PROVED BEFORE ANYTHING IS OVERRIDDEN
============================================
Reopening an override on a champion-SERVED order is the single most expensive
mistake in this lineage's history, and the ledger is explicit. `solver.py:388`:
the blind branch judged the champion on METADATA, the A/B showed all 50 of its
override-on-served rows carried `live_champ_zero: false`, and sub_e171b56c05b5
priced it at 7 better against 14 DROPPED. `solver.py:482`: kyber on served orders
cost SIX dropped rows on sub_83db1d62d155. `bg124_onfork:417`: one uncorroborated
quote cost sub_16a951feaf0c a hard veto on a net +5 run.

Every one of those overrode on a CLAIM. This module overrides only on a
MEASUREMENT, and it takes five independent facts before it will return a plan:

  1. The champion's route DECODES (`champ_route.route_of`) -- approve plus
     `exactInputSingle` on that same spender, every field checked.
  2. It carries `amountOutMinimum == 0`. A champion that quoted the pool sets a
     real floor from its own quote; a zero floor is the unquoted fallback. This
     is a hex read, costs no RPC, and is the filter that keeps the probe off the
     served orders that would otherwise pay for it.
  3. That exact route QUOTES ZERO on the fork -- the same block that will
     execute it. Not "we found something better": zero. A route the fork prices
     at nothing delivers nothing.
  4. The quoter is PROVABLY ALIVE: the champion's own quote contract has
     returned a positive quote -- on this order's batch, or earlier in this same
     process on this same fork (`bg124_onfork._LIVE_TARGETS`). Without this, a
     wrong quoter address or a chain-wide RPC fault reads exactly like a dead
     pool, and we would override every order on the chain on the strength of a
     broken call. What is asserted is that the CONTRACT answers, so any answer
     from it proves it; see `_quoter_live` for why insisting the proof come from
     this order's own batch refused the covers this module exists to make.
  5. Our replacement clears the order's own `min_output_amount` -- the check
     `bg124_onfork:428` names as the one every drop so far turned out to lack --
     and is either corroborated by a second independent venue within 2x or
     carries a real floor the chain will enforce for us; see `_floored` for why
     insisting on corroboration alone refused the thin-book pairs that are the
     whole population here.

Fail ANY of them and the champion plan stands untouched. The worst case is the
row we already have.

IT COSTS NO EXTRA eth_call
==========================
The champion's route is `("single", fee, None)`, and `_v3_cands` already emits
that descriptor for every fee tier in `A.T["fees"]` -- 3000 among them. So the
champion's own route is ALREADY in the batch `_quote_all` sends, at an index we
can find. Reading its slot is a list index, not a call. One Multicall3 round
trip answers "is the champion dead?" and "what should we do instead?" together.

WHY THE PACE POT IS SEPARATE
============================
That round trip is still real wall clock on an order the ladder does not visit
today, and wall clock on served orders is not a theoretical cost here:
`solver.py:498` records sub_f919509b61aa dropping THIRTEEN orders whose plans
read byte-identical to the champion's and which exec-check delivers on a real
fork -- the 30s generate_plan cutoff, not routing.

So this pot is its own, and small. It cannot draw on `_BG124_COVER_BUDGET_S`,
the one 12s cell the empty-order covers spend and the rows all our wins actually
come from; and `_MAX_PROBES` bounds the count even if every order in a pack wears
the fallback signature. Worst case for the whole run is `_BUDGET_S` against a
900s wall.

CHAIN 1 IS INERT HERE -- BUT IT WAS NOT, AND THE CLAIM IS WHAT MADE IT DANGEROUS.
The benchmark's `build_rpc_url_map` defaults `SOLVER_READ_PROXY_CHAINS=8453`, so
the solver's own `_get_web3(1)` is None, and the header used to conclude from
that alone that `_w3(solver, 1)` is None too -- "the absence of a read RPC is the
test". It is not. `bg124_onfork._w3` does not stop at the solver's handles: it
falls through to `_w3_fallback`, which builds a Web3 from `ETH_RPC_URL` off the
environment. So on a box that carries that variable this module was live on
chain 1, with no gate of its own, on the strength of a containment argument that
does not hold.

That matters more here than anywhere else in the ladder, because chain 1 is where
every drop in this lineage lives (`bg124_onfork:573` says so in as many words)
and because this module's whole evidence base is 8453 -- the 22 measured rows in
the header, and `_quoter_live`'s "that shape is the norm on 8453". There is no
chain-1 measurement behind any of the five facts.

So the test is made real rather than asserted: `_read_w3` asks the solver for its
OWN read handle and stops there. Where the read proxy exists this is exactly
`_w3`; where it does not, this returns None and the probe never runs -- which is
the behaviour the header has claimed since it was written. It cannot cost a cover
that was ever scored: the one round that ran `_try_dead` returned
`blind_spot_cover: 0`.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

_BUDGET_S = 3.0
_MAX_PROBES = 4


def _spend(solver):
    """One probe's worth of the run's own allowance, or False when it is out.

    Counted AND timed. The count bounds a pack of cheap failures, the clock
    bounds a few slow ones, and either alone leaves the other unbounded. Charged
    on the way IN so a raise inside the probe still costs its slot -- an
    exception that did not pay would let a persistently failing RPC be retried
    on every order in the corpus.
    """
    n = getattr(solver, '_dead_probes', 0)
    if n >= _MAX_PROBES:
        return False
    if getattr(solver, '_dead_secs', 0.0) >= _BUDGET_S:
        return False
    solver._dead_probes = n + 1
    return True


def _charge(solver, t0):
    solver._dead_secs = getattr(solver, '_dead_secs', 0.0) + time.monotonic() - t0


def _read_w3(solver, chain):
    """The solver's OWN read handle for this chain, never the env fallback.

    `bg124_onfork._w3` ends in `_w3_fallback`, which reads `ETH_RPC_URL` off the
    environment; that fallback exists so the empty-order covers keep working
    outside the sandbox, and it is right for them. It is wrong here, because it
    is the one thing standing between this module and the chain it has never
    measured. See the header.
    """
    for attr in ('_get_quoter_web3', '_get_web3'):
        fn = getattr(solver, attr, None)
        if fn is None:
            continue
        try:
            w3 = fn(chain)
        except Exception:
            continue
        if w3 is not None:
            return w3
    return None


def _index_of(cands, desc):
    """Where the champion's own route sits in our candidate batch, else -1."""
    for k, cand in enumerate(cands):
        if cand[0] == desc:
            return k
    return -1


def _quoter_live(O, cands, outs, target, skip):
    """Is the champion's own quote contract PROVEN reachable and correctly addressed?

    Fact 4 in the header. `decode_agg3` maps a failed subcall to 0, so a dead
    pool and a broken quoter are the same zero at this layer; the only thing that
    separates them is whether that contract answered anything. It has to be the
    SAME contract: a positive V2 router says nothing about whether the V3 quoter
    is reachable.

    THE SAME CONTRACT, NOT THE SAME ORDER. The first test below is the original
    one and still runs first, but requiring the proof to come from this order's
    own batch was an accident of where the evidence happened to sit, not part of
    what fact 4 asserts -- and it silently declines exactly the class this module
    exists for. A pair whose only liquidity is V2-style quotes zero at every V3
    fee tier AND on every V3 path through `A.T["mids"]`, because all of those are
    the same quoter; the batch's only positives are V2 routers, on a different
    target. The same-order test then reads "quoter broken" for what is really
    "this token has no V3 pool at all", and the cover is refused on an order the
    champion is measurably dead on. That shape is the norm on 8453, where the
    deep books for tokens like these are Solidly-style rather than V3.

    `_LIVE_TARGETS` closes that without weakening the assertion: it holds the
    contracts that returned a POSITIVE quote earlier in this same process, on
    this same fork, recorded on the one path every quote in `bg124_onfork` goes
    through. A contract that answered is reachable and correctly addressed --
    which is the entirety of what fact 4 has ever claimed. It is still a
    MEASUREMENT off this fork, never metadata, so the `solver.py:388` memo is
    untouched: nothing here asks the champion about itself.

    Chain-safe for free: the key is the address, and chain 1 and 8453 carry
    different quoters in `onfork_tables.json`. A chain with no read RPC never
    quotes, so it can never write an entry either.

    AN ALL-ZERO BATCH IS NOT EVIDENCE, AND `_LIVE_TARGETS` CANNOT MAKE IT SO.
    `_note_live`'s own docstring names the three things a zero can be -- a dead
    pool, a wrong address, a CHAIN-WIDE RPC FAULT -- and says the only separator
    is whether the contract ever answered. That is true per CONTRACT. It is not
    true per BATCH, and the batch is what fact 3 reads: a `_quote_all` that came
    back zero on EVERY candidate is the exact shape of a fault, and remembering
    that the same quoter answered a DIFFERENT order earlier cannot rule it out.
    The relaxation this memory was written for is untouched -- a pair whose only
    liquidity is V2-style still has POSITIVE V2 entries in its own batch, just on
    another target -- so the test below refuses only the batch that measured
    nothing at all, which is the one batch fact 3 must never be read off.

    WHAT THE OPEN VERSION COST. The benchmark logs a transient RPC timeout as
    `bounded_call timed out -> fallback` and the harness annotates it "may
    silently zero an order". With the read open, one such fault on a chain-1
    order made fact 3 read "champion route is dead" on a champion-SERVED order,
    and this module then overrode it -- the one move every hard veto in this
    lineage has come from.
    """
    if any(out > 0 and k != skip and cands[k][1] == target
           for k, out in enumerate(outs)):
        return True
    if not any(out > 0 for out in outs):
        return False
    return target in getattr(O, '_LIVE_TARGETS', ())


def _floored(O, outs, out, min_out):
    """Fact 5: a second venue agrees, OR the chain itself will refuse a bad fill.

    `_corroborated` is a SERVED-ORDER guard and `bg124_onfork._phase:511` says so
    in as many words -- it is reached under `strict`, which that function defines
    as "we would be OVERRIDING a champion-served plan, so require the quote to be
    corroborated before taking that risk". Its docstring prices the risk it was
    calibrated against: a 0.00002x catastrophic regression, and routes that
    quoted positive then delivered nothing. Both are CUTS, and a cut needs
    champion value to be cut from.

    Facts 2 and 3 have already measured that there is none. The route below us
    carries `amountOutMinimum == 0` -- the unquoted fallback, never a shape we
    emit for a pair we quoted -- and it prices at ZERO on the block that will
    execute it. So on this order the arithmetic in `evaluate_relative_adoption`
    cannot reach `regression` or `dropped`: both require a positive champ. The
    outcomes are `blind_spot_cover` if the replacement delivers and
    `blind_spot_repeat` if it does not, which is the row we already have. The
    downside is bounded at NEUTRAL by the same facts that select the class.

    Requiring corroboration anyway declines the exact pairs this module exists
    for. A pair with one thin book quotes once in the whole batch -- one router,
    one path -- and `sum(...) >= 2` refuses it. That is the same accident fact 4
    carried: a test that was true of the evidence, imported into a regime whose
    premise it no longer describes.

    It is relaxed, not dropped. A LONE quote is taken only when the order sets a
    real `min_output_amount`, because `_cover_ix` passes that straight into
    `swap_cd` as the swap's own `amount_out_minimum` -- so a route that cannot
    deliver it REVERTS on chain rather than under-delivering, and a revert here
    is a zero, which is the neutral row again. Either a second venue agrees or
    the chain enforces the floor; both are measurements off this fork, and
    neither is a claim about what the champion is doing.
    """
    return O._corroborated(outs, out) or min_out > 0


def _best_other(cands, outs, skip):
    """The best-quoting candidate that is not the champion's own route."""
    best_i, best_out = -1, 0
    for k, out in enumerate(outs):
        if k != skip and out > best_out:
            best_i, best_out = k, out
    return (cands[best_i][0], best_out) if best_i >= 0 else (None, 0)


def _order(O, state, plan):
    """Facts 1 and 2, both free: the champion's route, and that it never quoted it.

    Returns `(parsed_order, desc)` where `parsed_order` is `_parse`'s own tuple,
    or None. Also insists the decoded route names the SAME pair and amount the
    order does -- a plan built for a different order would otherwise be scored
    dead on this one's behalf.
    """
    import champ_route
    route = champ_route.route_of(plan)
    if route is None:
        return None
    desc, c_tin, c_tout, c_amt, c_min = route
    if c_min != 0:
        return None
    parsed = O._parse(state)
    if parsed is None:
        return None
    if (c_tin, c_tout, c_amt) != (parsed[1], parsed[2], parsed[3]):
        return None
    return parsed, desc


def _batch(O, chain, tin, tout, amt, desc):
    """The FREE half -- our candidate list, and where the champion's route sits in it.

    `_v3_cands` and `_v2_cands` build calldata off `A.T` and `_index_of` scans a
    list; neither reads RPC, and `_quote_all` is the module's only `eth_call`.
    Split out for the reason `champ_route._shape` records: written as one body
    with `_pick` this measured 332 nodes and became the largest region in a tree
    whose maximum was 139. Named helpers are the only thing that moves that
    metric; minifying moves it by exactly zero.
    """
    cands = (O._v3_cands(chain, tin, tout, amt)
             + O._v2_cands(chain, tin, tout, amt))
    k = _index_of(cands, desc)
    return None if k < 0 else (cands, k)


def _pick(O, w3, cands, k, min_out):
    """Facts 3, 4 and 5, off one Multicall3 round trip. The replacement, or None."""
    outs = O._quote_all(w3, cands)
    if len(outs) != len(cands) or outs[k] > 0:
        return None
    if not _quoter_live(O, cands, outs, cands[k][1], k):
        return None
    best, out = _best_other(cands, outs, k)
    if best is None or out < min_out or not _floored(O, outs, out, min_out):
        return None
    return best


def _measure(O, solver, chain, tin, tout, amt, min_out, desc):
    """`_pick` under the run's own allowance -- charged only for the ROUND TRIP.

    THE RUN GETS ONE PROBE, SO IT MUST NOT BE SPENT ON A FREE FAILURE. `_spend`
    is checked before the probe and charged on the way in, and `_charge` records
    the wall clock the probe actually took; a Multicall3 QuoterV2 sweep is
    measured at ~5s a call (`solver.py:487`) against `_BUDGET_S = 3.0`. So the
    first probe that reaches the RPC pushes `_dead_secs` past the pot and every
    later order is refused: `_MAX_PROBES = 4` never binds, and the real allowance
    for a whole pack is ONE round trip.

    That is the intended cost -- the pace governor's ledger prices a tail-drop as
    a hard veto -- but it makes WHICH order gets the probe the whole question,
    and this used to be answered first-come-first-served. `_spend` ran before
    `_batch`, so an order whose champion route is not in our candidate list at
    all (`_index_of` -> -1, no RPC, no possible cover) consumed the only ticket
    and left the rows this module exists for unprobed for the rest of the run.

    Charging after the free half fixes that without buying a single extra
    eth_call: the pot still stops after one round trip, and the ticket now
    always lands on an order that can actually reach one.
    """
    w3 = _read_w3(solver, chain)
    if w3 is None:
        return None
    got = _batch(O, chain, tin, tout, amt, desc)
    if got is None or not _spend(solver):
        return None
    cands, k = got
    t0 = time.monotonic()
    try:
        return _pick(O, w3, cands, k, min_out)
    finally:
        _charge(solver, t0)


def _probe(O, solver, intent, state, plan):
    """The five facts, cheapest first, then the plan. None unless all five hold."""
    got = _order(O, state, plan)
    if got is None:
        return None
    parsed, desc = got
    p, tin, tout, amt, min_out, chain = parsed
    best = _measure(O, solver, chain, tin, tout, amt, min_out, desc)
    if best is None:
        return None
    return O._cover_ix(intent, state, p, best, tin, tout, amt, min_out, chain)


def try_dead_cover(solver, intent, state, plan):
    """Serve an order answered by a route the fork prices at zero.

    `plan` is what the stack BELOW us is about to return, which is the stricter
    reading and the deliberate one. `solver.py:411` records that `_apex_ourbase`
    has already had its say by the time this copy of `generate_plan` looks, so
    decoding the champion's raw plan would measure a route that is not the one
    being scored. On all 22 measured rows the two are byte-identical anyway.

    Nothing here can turn a served order into a drop by failing to produce a
    plan: every path that is not a proven cover returns None, and None means the
    caller keeps `plan`.
    """
    try:
        import bg124_onfork as O
        return _probe(O, solver, intent, state, plan)
    except Exception:
        logger.exception('[dead] probe failed; champion plan stands')
        return None
