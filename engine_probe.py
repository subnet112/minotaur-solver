"""Whether the last-resort live-engine probe may run, and for how long.

WHAT THIS IS FIXING
===================
`_champ_base.VikingSolver._v_engine_fresh` is the only fresh-route escape in
`viking_serve.tail_serve`. The order it sits in is:

    base plan EMPTY -> stale_serve  (replay row older than _V_ROW_FRESH_S=6h)
                         -> _v_engine_fresh   <- this probe
                    -> fill_empty   -> _v_replay_plan, the >6h-STALE row

so when the probe is refused, the fallthrough serves the stale row: same two
legs, materially less delivered. That is invisible to every plan-level gate
here, which compares leg counts and sees 2 == 2.

The probe used to be refused on

    float(getattr(self, '_dyn_order_budget', None) or 99.0) < 8.0

and `_dyn_order_budget` is THIS ORDER'S WHOLE SHARE OF THE RUN POT, not the
room left when the probe is reached. `pace_pot.surplus` states the share in as
many words -- "a declined surplus leaves the caller on the even share,
860/122 = 7.05s" -- and 7.05 is below 8.0. So on every order of a full corpus
whose surplus is declined, which is the head of every run, the gate refused a
probe the plan had barely spent anything of.

WHAT IT COST, from the validator's own report on round-e29795256-n1
(sub_8bb97076a093, benchmark_rank 4): `reject: 2 order(s) cut >1% (hard floor)`
on 1 better / 3 worse / 82 matched.

    q_ddfde992747215346c800649b19cbde9  ratio 0.7179  (-28%)  CRO->USDC chain 1
    q_7c7ae411e6d8c69a1166d2be85b63ba3  ratio 0.9024  (-10%)
    q_e40fd62da7b9152512f3af7c505b51ba  ratio 0.9972  (-0.3%, inside the floor)

Identity m3 was rejected in the SAME ROUND on the SAME THREE IDS AT THE SAME
RATIOS, from the same gate reached down a different clock, and fixed it by
splitting the one number into two questions. This is that split, asked with the
clocks THIS tree keeps.

TWO QUESTIONS, NOT ONE
======================
AFFORDABLE is the question the gate was trying to ask, and `_paced_wait`
already answers it exactly -- it returns `min(want, _dyn_order_budget,
_SEARCH_DEADLINE - now)`, so it charges against this order's share AND against
the plan-level window `pacing_bridge._pb_arm_window` opened at the top of this
generate_plan. Room LEFT, not room ALLOTTED. The orders that reach this probe
are the ones whose base plan came back empty, which is the cheap path through
the routing chain, so they arrive with nearly their whole window unspent --
precisely the case the old test refused.

BOUNDED, WHICH IT WAS NOT. The other call site of `_score_aware_singlehop`
(`king_base.py:3934`) already wraps it as
`_bounded_call(..., timeout=_paced_wait(_SELECT_BUDGET_S))`. This one called it
raw, so a hung RPC here ran against no clock at all and the crude 8.0 test was
the only thing standing between it and the harness's 30s per-GENERATE_PLAN
kill -- which is `chal: null`, a dropped order and a hard veto. Routing it
through the same pair means the probe can now be opened MORE often while being
bounded for the first time.

NO LOCAL GATE CAN CORROBORATE THIS, and the reason is the same one the
`read_meter` commit gives. `_dyn_order_budget` is written by
`pacing_bridge._pb_prepare` only under the governor (`_bm_t0` and `_bm_total`
set by `on_benchmark_start`). bin/perf-check and bin/exec-check never call it,
so the cell is None there, `_pb_plan_window` falls back to `_PLAN_CEILING_S`
(20.0), and `_paced_wait(4.0)` returns 4.0 on both sides of this change. Every
local gate sees byte-identical plans; only a scored round moves.

THE EXPOSURE, stated rather than hidden. The set this can move is exactly
"base plan empty AND replay row older than 6h AND probe previously refused".
Those orders serve a >6h-stale row today; they will serve a live-priced route
when one clears the order min. That is the behaviour `stale_serve` was written
for -- its own name says the stale row is the thing to escape -- but a row that
is currently `matched` through a stale plan can move off it in either
direction. It cannot DROP: `_v_engine_fresh` returning None leaves the caller
on `fill_empty` exactly as before, so the fallthrough is unchanged.
"""
from __future__ import annotations

# Room the probe needs to finish once started, and the most it may take. One
# number: a probe that cannot get this much is not started, and one that is
# started may not spend more. Worst case is the plan window (7.05s at a
# 122-order pace, 20.0s off the ceiling) plus nothing, since the wait is
# charged against that same window.
MIN_WINDOW_S = 4.0

import phase_gate as _pg


def fresh_route(solver, fn, args):
    # Run the probe inside the room this plan actually has left, or decline.
    # None is the caller's existing "no fresh route" answer, so every refusal
    # path lands on the behaviour that shipped. `phase_gate.run` bounds the
    # WAIT and returns None on overrun, the same discipline king_base:3934
    # applies to this very function.
    budget = _pg.enter(solver, MIN_WINDOW_S, MIN_WINDOW_S)
    if budget <= 0.0:
        return None
    return _pg.run(solver, fn, args, budget)
