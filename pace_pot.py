"""The run pot's arithmetic: what one order may spend once the rest are reserved for.

WHY THE EVEN SHARE STARVES THE ORDERS THAT MATTER
=================================================
`_apex_champ.JamesSolver._pace_order_budget` sized every order at
`remaining_time / remaining_orders`. That divides the pot evenly, but the
corpus is not even: most orders are a warm table hit that returns in well under
a second, while the handful that need a cold multi-hop sweep are the only ones
that can use a full window. At a ~122-order pace the even share is
860/122 = 7.05s, so each heavy order was held to 7.05s -- and the cheap ones
handed their unspent seconds back to the pot, where `remaining_time` kept
growing against a shrinking `remaining_orders`.

The surplus therefore arrived LATE. An order early in the corpus could not
borrow from a future it can already be shown to have: the run ended with the
pot unspent and the orders that were starved to protect it came back EMPTY. The
validator scores an empty plan `chal: null` -- a dropped order and a HARD VETO,
which vetoes before the tie-break ladder is consulted at all
(`epoch/relative_scoring.py`).

That is this lineage's entire scoreline gap. On sub_97566d1a7842 the record is
better=7 worse=14 matched=73 dropped=13, and 13 of the 14 worse rows ARE the
drops. It is load-dependent by construction, which is why every one of those
orders replays through `bin/exec-check` at js=1.0000 with EXEC GATE: PASS --
replayed alone, `remaining_orders` is 1 and the order is handed the whole pot.

RESERVE, NOT SHARE
==================
`surplus` holds back a reserve instead of dividing a share. `worked /
completed` is this run's OWN measured mean cost per order -- no guessed
constant, and it is the rate the pot is actually being spent at. Reserving that
mean for each of the OTHER remaining orders leaves everything above it available
now, so the surplus the cheap orders generate is spendable by the heavy order in
front of it rather than only by the run's tail.

WHY IT CANNOT OVERSPEND THE POT
===============================
The reserve is subtracted before the value is offered, so the later orders keep
the mean they have been costing. An order that does draw on the surplus feeds
back a larger mean, so the next call's reserve is correspondingly bigger -- the
loop is self-correcting. Once the mean exceeds the even share the surplus goes
negative and the caller's `max(share, allow)` is exactly the old number.

WHY IT CANNOT COST A MATCHED ORDER
==================================
The caller takes the LARGER of this and the even share, then clamps to
`_PLAN_CEILING_S`. So no order gets less time than it did before and none gets
more than the harness's 30s GENERATE_PLAN killer allows. This can only convert a
drop into a plan; it cannot convert a matched order into a regression, which is
the rule that matters most (`a regression costs more than an extra win gains`).

A separate module rather than a method on `JamesSolver`: that class's body is
already the tree's LARGEST region at 146 nodes (`bin/preflight`), and
`max_region_nodes` drops only by splitting regions into named helpers --
minifying moves it by exactly zero. The same reasoning put `read_meter` and
`empty_rescue` in their own files.
"""
from __future__ import annotations
_BACKSTOP_S = 300.0
_PROXY_MARK = '/rpc/'

def _proxied(rpc_urls) -> bool:
    """True when the reads this run issues are routed through the read proxy.

    That is the harness's own predicate for the loosened wall: `budget_enforced`
    is `read_proxy_config() is not None and cfg.budget > 0`, the config exists
    exactly when `SOLVER_READ_PROXY` is set -- which is exactly when the solver
    was handed proxy URLs -- and the budget defaults to the consensus constant
    `DEFAULT_GENERATE_PLAN_BUDGET = 5000` when the env is unset
    (`solver_read_proxy.py:112`), so configured implies enforced.

    Both ways of being wrong are safe. A false True only WIDENS a window, and
    the widening is still bounded by the pot share below. A false False leaves
    the caller on the 20.0s it has today. Never raises: an unreadable map reads
    as not proxied.
    """
    try:
        for url in (rpc_urls or {}).values():
            tail = str(url or '').split(_PROXY_MARK, 1)
            if len(tail) == 2 and '/' in tail[1].strip('/'):
                return True
    except (TypeError, ValueError, AttributeError):
        pass
    return False
_POT_SHARE = 0.05
_WALL_MARGIN = 3.0

def ceiling(rpc_urls, wall_s: float, remaining_time: float, floor_s: float) -> float:
    """The widest window one plan may hold: from the pot and the REAL wall.

    THE STALE MODEL. `_apex_champ._PLAN_CUTOFF_S = 30.0` is `TIMEOUTS[GENERATE_PLAN]`,
    and `orchestrator.py:674`-`:680` reads that table and then immediately
    replaces the value for this one command:

        timeout = TIMEOUTS.get(request.command, 30.0)
        if request.command == Command.GENERATE_PLAN:
            timeout = generate_plan_recv_timeout(timeout)

    Under the deterministic read budget -- default-on, a consensus code constant,
    no env needed -- that returns 300.0. So the 30s killer the ceiling was sized
    against is not the killer a scored round enforces, and `_PLAN_CEILING_S`,
    a CONSTANT 20.0, has been capping every heavy order's search at a third of
    what the harness would have allowed it.

    That is the shared cap the drop verdict describes. sub_3f2e0ea8a834 dropped
    7 orders at corpus indices 8, 33, 52, 53, 56, 58 and 83 with 77 rows served
    AFTER the first drop -- scattered, so the run was solvent every time it
    dropped one, and the pot was never the thing that ran out. Per-order cost
    under a cap, with the cheap orders handing their share back unspent.

    IT CAN ONLY WIDEN. The result is floored at `floor_s`, the caller's existing
    `_PLAN_CEILING_S`, so no order gets a narrower window than it has today and
    a matched order cannot become a regression. When the proxy is absent the
    wall really is 30.0, `wall_s / _WALL_MARGIN` is 10.0, and the floor returns
    exactly the 20.0 in force now.

    Never raises: unreadable arguments fall back to the floor.
    """
    try:
        wall = _BACKSTOP_S if _proxied(rpc_urls) else float(wall_s)
        return max(float(floor_s), min(wall / _WALL_MARGIN, float(remaining_time) * _POT_SHARE))
    except (TypeError, ValueError, ZeroDivisionError):
        return float(floor_s or 0.0)

def allowance(worked: float, done: int, remaining_orders: int, remaining_time: float, rpc_urls, wall_s: float, floor_s: float) -> float:
    """Seconds this order may spend: the larger of its share and its surplus, capped.

    The whole pot arithmetic in one place. It lived as four statements in
    `_apex_champ.JamesSolver._pace_order_budget`, which `bin/preflight` measured
    at 132 nodes against a tree maximum of 145 -- adding the ceiling lookup there
    would have made that method the tree's largest region, and `max_region_nodes`
    drops only by splitting regions into named helpers. Moving them here lowers
    that region instead of raising it, the same trade that put `read_meter`,
    `empty_rescue`, `xc_delivery` and `surplus` itself in their own files.

    The 4.0 floor and the `max(share, allow)` choice are unchanged; the only
    behavioural difference is that the cap is now `ceiling(...)` rather than the
    constant `floor_s`, and `ceiling` is floored at `floor_s`.
    """
    share = float(remaining_time) / max(1, int(remaining_orders))
    allow = surplus(worked, done, remaining_orders, remaining_time)
    return max(4.0, min(max(share, allow), ceiling(rpc_urls, wall_s, remaining_time, floor_s)))

def surplus(worked: float, done: int, remaining_orders: int, remaining_time: float) -> float:
    """Seconds available to THIS order beyond the mean reserved for the others.

    `done` counts orders started INCLUDING this one -- the convention `_dr8`
    establishes when it increments `_bm_done` before pacing -- so `done - 1`
    have completed. On the first order of a run there is no mean yet and the
    surplus is declined, which leaves the caller on the even share.

    WHY `worked` IS NOT `remaining_time`'s CLOCK
    --------------------------------------------
    The two arguments are read off two different anchors on purpose.
    `remaining_time` is charged from `_PROC_T0`, because the harness's limit is
    a per-CONTAINER wall (`protocol.TOTAL_BENCHMARK_TIMEOUT = 900.0`) and the
    prologue is spent budget. `worked` is charged from `on_benchmark_start`,
    because it is divided by `completed` to get the cost of ONE ORDER, and the
    prologue is not part of any order.

    Anchoring both at `_PROC_T0` -- which is what this took until now -- puts the
    whole import into `mean`, and `mean` is then multiplied by
    `remaining_orders`. This tree imports ~50MB of module and table before the
    first order (`payload_cover_apex.py` alone is 18MB), so at the head of a run
    `completed` is small and the inflated mean is at its worst exactly where the
    multiplier is at its largest:

        done=8, prologue=40s, true order mean=3.0s
          worked=_PROC_T0 : mean=9.1  -> surplus = 796 - 114*9.1 = -242  (declined)
          worked=bm_start : mean=3.0  -> surplus = 796 - 114*3.0 =  454  (ceiling)

    A declined surplus leaves the caller on the even share, 860/122 = 7.05s, and
    that share is armed as the whole plan's `_SEARCH_DEADLINE`
    (`pacing_bridge._pb_plan_window`). An order whose route needs longer than
    that comes back EMPTY, which the validator scores `chal: null` -- a dropped
    order and a hard veto. On sub_97566d1a7842 the first three drops sit at
    corpus indices 8, 19 and 26, the head of the run, with 73 orders served
    after them: not a pot that ran out, a reserve that was too big while it was
    still being sized off the import.

    The correction can only ever RAISE the surplus, and the caller takes
    `max(share, allow)` then clamps to `_PLAN_CEILING_S`, so no order gets a
    narrower window than before and none gets one past what the harness's 30s
    GENERATE_PLAN killer allows. It cannot turn a matched order into a
    regression; it can only turn a drop into a plan.

    Never raises and never returns None: an unreadable count is treated as "no
    measurement yet", which declines the surplus rather than inventing one.
    """
    try:
        completed = int(done) - 1
        if completed < 1:
            return 0.0
        mean = float(worked) / completed
        if mean <= 0.0:
            return float(remaining_time)
        return float(remaining_time) - _others(remaining_orders, remaining_time, mean) * mean
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0

def _others(remaining_orders, remaining_time: float, mean: float) -> float:
    """How many FURTHER orders this process can still be asked to serve.

    `remaining_orders` is `_bm_total - done + 1`, and those two terms are
    counted against DIFFERENT populations. `_bm_total` is the whole corpus:
    `harness/orchestrator.py::_scenario_pool_worker` calls
    `on_benchmark_start(intents_len)` with the full length on EVERY runtime in
    the pool. `done` is only what THIS process served. So on a validator running
    `BENCHMARK_CONCURRENCY = K > 1` -- K isolated runtimes work-stealing from one
    shared queue -- the subtraction charges this process for the K-1 other
    workers' progress as though it were still its own work to do, and the reserve
    it sizes is up to K times too large.

    K is not observable from inside one worker: the queue is shared and nothing
    reports global progress. But an upper bound on the count is, and it does not
    need K. At a measured `mean` seconds per order, no process can serve more
    than `remaining_time / mean` further orders whatever the pool is doing --
    reserving for orders that the wall will never hand over is the defect,
    independent of what causes the miscount.

    Taking the min of the two therefore only ever LOWERS the reserve, so
    `surplus` only ever rises and the caller's `max(share, allow)` cannot hand
    any order a narrower window than it had. The bound is slack whenever the mean
    sits well under the even share -- the common case, where `remaining_orders`
    is already the smaller term and this returns exactly what it returned before.
    It binds only where the old arithmetic drove the surplus negative and
    declined it, which is the case that starved heavy orders into empty plans.
    """
    servable = remaining_time / mean - 1.0
    return min(float(int(remaining_orders) - 1), max(0.0, servable))