"""Whether a routing PHASE may enter, and how many seconds it may spend inside.

WHAT THIS IS FIXING
===================
Three phases in `king_base` decide whether to run by comparing THIS ORDER'S
WHOLE SHARE of the run pot against a flat constant:

    king_base.py:4711  sweep      `_dyn_sw is not None and _dyn_sw < _SWEEP_MIN_BUDGET_S`
    king_base.py:4018  discovery  `_dyn_dc is None or _dyn_dc >= _DISCOVERY_MIN_BUDGET_S`

and all three constants default to 8.0 (`king_base.py:153-155`). The share is
not 8.0. `pace_pot.surplus` states it -- "a declined surplus leaves the caller
on the even share, 860/122 = 7.05s" -- and `aero_pin.py:63` states the
consequence in as many words:

    It deliberately does NOT copy the sibling covers' `_dyn_order_budget < 8.0`
    guard: in production that attribute is ~4.0, which is why
    curve/twohop/blindfill never fire at all.

"Never fire at all" is the measured behaviour of both phases above on every
order of every governed run. Offline they DO fire, because no governor writes
`_dyn_order_budget` and the cell is None -- which is why no local gate here has
ever shown a difference, and why the dead phases read as live code.

This is the same defect `engine_probe` was written for, at two more sites.
`_champ_base._v_engine_fresh` refused its probe on `_dyn_order_budget < 8.0`,
fell through to a >6h-stale replay row, and round-e29795256-n1 priced that at
`reject: 2 order(s) cut >1% (hard floor)` -- q_ddfde992 CRO->USDC at ratio
0.7179 and q_7c7ae411 at 0.9024. The sweep is this tree's exotic-pair route
finder and CRO->USDC is an exotic pair; the discovery rescue is what answers an
EMPTY pool set, which is the same "base plan empty" path that probe sits on.

TWO QUESTIONS, NOT ONE -- the split `engine_probe` already makes
=============================================================
AFFORDABLE. `_paced_wait` answers it exactly: it returns `min(want,
_dyn_order_budget, _SEARCH_DEADLINE - now)`, so it charges against this order's
share AND against the plan window `pacing_bridge._pb_arm_window` opens at the
top of generate_plan. Room LEFT, not room ALLOTTED. That distinction is the
whole bug: the old test asked whether the order was ALLOWED 8 seconds, never
whether it had any left.

BOUNDED, WHICH NEITHER SITE WAS. `_sweep_quotes` and `_dynamic_discovery_plan`
were both called raw, so a hung RPC ran against no clock at all and the crude
8.0 test was the only thing between them and the harness's 30s
per-GENERATE_PLAN kill -- which is `chal: null`, a dropped order, a hard veto.
Here the budget IS the timeout, so a phase can never spend more room than it
actually had. That is why opening these gates is safe in a way that simply
lowering the constants would not be: the same number now both admits the phase
and bounds it.

THE BUDGET LAW IS RESPECTED, NOT WAIVED
=======================================
`cover_state.json` (2026-07-30) records why these guards exist: blindfill's RPC
starved the champion's `_RUN_BUDGET_S` governor -> `last_resort_empty` -> one
dropped order -> whole submission REJECTED under #1207 drop-reject. That
overrun was unbounded and uncharged. Every call opened here is charged against
`_SEARCH_DEADLINE` through `_paced_wait`, so time this phase burns is
subtracted from what the phases after it may ask for -- the clamp
`king_base._paced_wait` was written to enforce, whose own docstring says the
entry gate "is not this check: it decides whether the share is big enough to
ENTER discovery, not how much of that share the wait may spend once inside."
This module is that entry gate, asked with the same clock.

WHAT IT CANNOT COST. The sweep serves only when `best_x > max(reach, 1) *
_SWEEP_MIN_EDGE` (`king_base.py:4729`), i.e. only when it strictly beats the
baseline it would otherwise have served; discovery runs only when the pool set
came back `_empty`, whose alternative is `last_resort_empty` -- a plan that
delivers nothing. Neither can turn a served order into a worse one; they can
only fail to improve it. The exposure is time, and time is now bounded.

NO LOCAL GATE CAN CORROBORATE THIS, for the reason `engine_probe` gives:
`_dyn_order_budget` is written by `pacing_bridge._pb_prepare` only under the
governor, which bin/perf-check and bin/exec-check never arm. Offline the cell
is None, both old gates already admitted the phase, and `_paced_wait(want)`
returns `want` -- so every local gate sees byte-identical plans on both sides
of this change. Only a scored round moves.

A module rather than a method, and a SHARED one rather than a second copy:
`engine_probe` asked this same question four days earlier and now delegates
here, because a copied predicate is the e57efe3 -> dcc15d2 drift this tree
keeps paying for -- the reasoning that already put `pace_pot`, `read_meter`,
`empty_rescue`, `xc_delivery` and `xc_order` in their own files.
"""
from __future__ import annotations

# The smallest room worth entering a phase for. Both a floor and, through
# `enter`, the number a phase that cannot get this much is refused on: a
# discovery or sweep pass that starts with less than this cannot finish its RPC
# round trips and would spend the window without producing a route.
MIN_WINDOW_S = 4.0


def phase_budget(solver, want=MIN_WINDOW_S) -> float:
    """Seconds this phase may spend, folding the order share and the plan window.

    `_paced_wait` is the tree's own clock and already folds in both. Reached
    through getattr because this module is imported from layers whose class
    chains onto whatever SOLVER_CLASS is at import time -- the MRO is not
    guaranteed to carry `king_base`'s helpers.
    """
    wait = getattr(solver, '_paced_wait', None)
    if not callable(wait):
        # No pacing layer: fall back to the order share alone, which is what
        # the old gates read. Unset stays "no limit", as it always has here.
        dyn = getattr(solver, '_dyn_order_budget', None)
        if dyn is None:
            return float(want)
        try:
            return max(0.0, min(float(want), float(dyn)))
        except (TypeError, ValueError):
            return float(want)
    try:
        return max(0.0, float(wait(want)))
    except Exception:
        # Refusing is the conservative direction: it leaves the caller on the
        # fallthrough this change is trying to escape, i.e. on today's plan.
        return 0.0


def enter(solver, want=MIN_WINDOW_S, floor=MIN_WINDOW_S) -> float:
    """The budget to run this phase under, or 0.0 to skip it.

    A single number answering both questions, so a caller cannot admit a phase
    it has no clock for -- the shape that let `_sweep_quotes` run unbounded.
    """
    budget = phase_budget(solver, want)
    return budget if budget >= floor else 0.0


def run(solver, fn, args, budget):
    """Call `fn(*args)` inside `budget` seconds, or None if it overruns.

    None is every caller's existing "this phase found nothing" answer, so an
    overrun lands on the behaviour that shipped rather than on a new path.
    """
    call = getattr(solver, '_bounded_call', None)
    if not callable(call):
        return fn(*args)
    return call(fn, args, timeout=budget)
