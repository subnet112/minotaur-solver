"""WHEN must the fast path arm? As LATE as the wall allows, and not one order sooner.

Asked by `_apex_champ.JamesSolver._behind_pace` and by
`pacing_bridge._pb_prepare._dz284`, the two gates on the emergency fast path.
Answering True means the order is served by `king_base._last_resort_plan` -- an
offline snapshot or a default-fee single hop, built with no RPC -- instead of by
the real router.

WHY ARMING EARLY IS NEVER A SAVING
==================================
The fast path is not a cheaper way to serve an order, it is a WORSE way. Its
plan is well-formed enough that `_is_empty` keeps it and the stack stops
looking, and it then reverts on the fork (orchestrator.py:1812
`real_sim_reverted`). The validator records `chal: null`, which is a DROPPED
order, which is a hard veto that sinks the whole submission regardless of every
other row.

The thing it is traded against is also a drop. The 900s TOTAL_BENCHMARK_TIMEOUT
is per-CONTAINER (orchestrator.py:338 sets `_start_time`, :668 kills the
session) and a killed session drops every order it never reached. So both sides
of this trade are measured in dropped orders, and the ONLY quantity that matters
is HOW MANY:

    stub N orders now   ->  N drops, certain
    run out of wall     ->  M drops, the tail we never reach

Arming is worth it only while N < M, and N is a function of WHEN we arm. Arm at
order 8 of 122 and N is up to 114. Arm at the last possible moment and N is
exactly the tail that would have been lost anyway. Every order routed before
that moment is a row we win for free.

WHAT THE LAST POSSIBLE MOMENT IS
================================
A stub costs no RPC and no search. The 7 orders sub_b5b5ba50f5f8 stubbed were
measured at 0.1ms to 1.4ms each (state/last-perf-ab.json). So the run can always
answer everything it has left in `remaining_orders * _STUB_S` seconds, plus one
`_INFLIGHT_S` for the order already being routed when the reserve is reached.

That is the entire condition. While the pot still holds that reserve there is no
tail at risk -- whatever happens next, every remaining order can still be
answered -- so stubbing buys nothing and costs a hard veto per order. Once the
pot is down to the reserve, the tail IS at risk and stubbing is what saves it.

WHY THE MEASURED-RATE PROJECTION IS GONE
========================================
Two tests have now been tried here and both armed early:

  d6219cd and before   `remaining_time / remaining_orders < _FAST_BELOW_S`: a
                       static 6.0s floor divided into a pot the prologue had
                       already drained. A full corpus paces at 860/122 = 7.05s
                       against that floor, 15% of headroom, so any prologue past
                       ~128s put the run "behind" on its FIRST order.

  6886eba, 8497448     `mean * remaining_orders > remaining_time`, the rate
                       orders are actually completing. Honest arithmetic, but it
                       answers the WRONG QUESTION. "We will not finish at this
                       rate" does not imply "stub THIS order": the projection is
                       true from the moment it is true, so it arms at the FIRST
                       order that trips it and stubs every order after, when the
                       run had the pot to route most of them and stub only the
                       tail.

  this                 "is the pot down to what the tail needs?" -- the question
                       the trade above actually turns on.

The projection also had a failure mode the reserve does not: `remaining_orders`
comes from `on_benchmark_start(intent_count)`, which reports the WHOLE corpus.
Under `BENCHMARK_CONCURRENCY` > 1 the corpus is sharded across K runtimes and
each is still told the full length, so `remaining_orders` runs K times too high.
Multiplied by a per-order mean that is a K-fold overstatement of the work left
and arms the fast path across the whole run. Multiplied by `_STUB_S` it is a
K-fold overstatement of a reserve that is tens of seconds -- the rule degrades
into arming slightly early instead of inverting.

THIS MODULE IS NOT THE REMAINING DROP CAUSE. READ BEFORE TUNING IT AGAIN.
========================================================================
Every fix in this file and at its two call sites -- the move onto `overruns`
(3def342, 8497448), the 0.5 -> 0.05 reserve (a065e70) and the cross-chain escape
(f754cae) -- is an ancestor of 88490f3, which shipped as sub_e171b56c05b5.
`git show 88490f3c2d:pace_mean.py` reads `_STUB_S = 0.05`, so the tuned rule is
what the validator actually benchmarked. That verdict: better=7 worse=14
matched=79, worse == dropped == 14, against 10 drops on sub_10821047e512 before
it. The drop count did not fall when the reserve was fixed; it rose.

So the fingerprint this file is built around -- "a sub-millisecond plan is a
stub" -- no longer identifies the cause. It was inferred from
`state/last-perf-ab.json`, and perf-check plans with `rpc_urls: {}`: with no RPC
reachable at all, a baked exact-key table hit also answers in well under a
millisecond, and this tree is mostly baked tables. Sub-millisecond means
"answered without reads", which the stub and the tables both do.

The rule below is still the right rule and should stay -- it is False for the
whole of any run not about to hit the wall, which is the only property the trade
needs. What is closed is the inference that tightening it further buys drops
back. It cannot: at 122 orders the reserve is 122 * 0.05 + 20 = 26.1s of an 860s
pot, so the gate is already inert for all but the last seconds of a run. Spend
the next tick on the override surface (51 rows, `abandon` 0) instead.

MEASUREMENT, sub_b5b5ba50f5f8 / round-e29789456-n1
==================================================
7 dropped orders at corpus indices 8, 18, 19, 32, 33, 43 and 83 of 122, our own
plan cost for all 7 under 1ms, and every row after index 83 SERVED -- the run
reached the end of the corpus and the wall never tripped. All 7 stubs bought
time the run did not need, and those 7 were the entire deficit on that verdict:
better=5, worse=7, worse == dropped. Under this rule the pot never came near the
reserve, so not one of them arms.

A module rather than a method because `JamesSolver` is the region that holds
this tree's `max_region_nodes` maximum, and a helper defined on it raises the
Stage-1 factorization number for every caller. Same reasoning that put
`pace_pot`, `read_meter`, `empty_rescue` and `xc_order` in their own files.
"""
from __future__ import annotations
_STUB_S = 0.05
_INFLIGHT_S = 20.0

def reserve_s(remaining_orders: int) -> float:
    """Seconds the run must keep back to answer everything it has left.

    `max(1, ...)` because the count is one behind at one call site and exact at
    the other (`_dr8` increments `_bm_done` before pacing, `_dz284` reads the
    count before the increment); the difference is one order and the floor makes
    a zero or negative count harmless either way.
    """
    return max(1, int(remaining_orders)) * _STUB_S + _INFLIGHT_S

def overruns(remaining_orders: int, remaining_time_s: float, floor_s: float) -> bool:
    """True when the pot no longer covers the tail, i.e. fast-path from here on.

    `floor_s` is `_FAST_BELOW_S`, kept as a lower bound so a corpus short enough
    for the reserve to fall below it still arms with a last-order margin.

    No sample, no mean, no clock: this reads only the pot and the count, so it
    cannot be wrong about a run it has not measured yet. It is False for the
    whole of any run that is not actually about to hit the wall, which is the
    only property the drop analysis above needs it to have.
    """
    return remaining_time_s <= max(float(floor_s), reserve_s(remaining_orders))