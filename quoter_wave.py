"""How long the CHAIN-1 quoter fan-out may wait, and how its replies are taken.

WHAT THIS IS FIXING
===================
`king_base._enumerate_eth_quotes` is the whole candidate set for Ethereum
mainnet. It fans every quote out at once and then ranks the survivors with
`max(out)`. Two properties of that fan-out were wrong, and they compound.

THE CLIENT. Every other quoter fan-out in the tree runs on
`_get_quoter_web3`, whose own docstring says why:

    same RPC, LONGER socket timeout (_QUOTER_TIMEOUT_S), provider retry-ladder
    OFF. Cold archive reads on the benchmark fork regularly exceed the shared
    2s client and silently drop venues from selection

    king_base.py:1001  _major_hub_cands                 _get_quoter_web3
    king_base.py:3043  _enumerate_crossvenue_2hop_proxy _get_quoter_web3
    king_base.py:4174  _enumerate_singlehop_quotes      _get_quoter_web3   (Base)
    king_base.py:5002  _vu_route_spec                   _get_quoter_web3
    king_base.py:3229  _enumerate_eth_quotes            _get_web3   <-- chain 1

So the LARGEST fan-out in the tree, and the only chain-1 one, was the single
site left on the shared client -- `_RPC_TIMEOUT_S`, 2.0s. Each quote is wrapped
in a bare `except Exception: return None` and a `None` is dropped by the
collector, so a reply that takes longer than two seconds does not fail loudly:
it removes a venue from the ranking and `max(out)` picks the best of whatever
was fast enough. Same leg count, well-formed plan, worse output.

THE WALL. `as_completed(futs)` was called with no timeout inside a
`with ThreadPoolExecutor(...)`, whose `__exit__` is `shutdown(wait=True)`. The
stage therefore drained every straggler before returning. Its only bound was
`_bounded_call(self._score_aware_singlehop, ..., timeout=_sel_to)` in
`king_base._dr243`, and overrunning THAT does not degrade the plan, it deletes
it: `_bounded_call` returns None, `enhanced` is None, and the order falls to the
baseline/offline path.

WHAT IT COST, MEASURED
======================
Two `worse` rows on the last scored round, both chain-1 `swap`, both a stable
input into a long-tail output, both well-formed two-leg plans on either side.
One was inside the tolerated band; the other was a catastrophic cut, i.e. past
the hard floor, and on its own enough to reject the tree.

The forensics for those rows -- ids, amounts, the requote at the pinned fork
block -- live in the pipeline state dir, which is NOT part of the submitted
tree. They are deliberately not repeated here.

Two readings fit the evidence and this file cures BOTH, which is why it is
worth writing even though neither can be corroborated locally:

  A VENUE WENT MISSING. The deepest pool for a long-tail output is often the
  1% tier, which `_ETH_UNI_FEES` already asks for. A quote slower than the
  socket timeout is not an error here -- it returns None, the collector drops
  it, and `max(out)` silently ranks the survivors. Same leg count, worse fill.

  THE WHOLE STAGE WAS DISCARDED. `_enumerate_eth_quotes` runs under
  `_bounded_call(self._score_aware_singlehop, ..., timeout=_sel_to)` in
  `_dr243`, and `_sel_to` is this order's paced share of the select stage.
  Overrunning it does not degrade the plan, it deletes it: `_bounded_call`
  returns None, `enhanced` is None, and the order ships the baseline plan --
  which is exactly the shape a large cut has.

The second reading is the dangerous one, because the fan-out had no wall of its
own at all and the socket it runs on was just widened. See
[[gate-opened-must-also-be-bounded]].

THE TWO CHANGES ARE MONOTONE IN OPPOSITE DIRECTIONS, WHICH IS THE POINT
=======================================================================
CANDIDATES CAN ONLY GROW. The socket timeout rises from 2.0s to
`_QUOTER_TIMEOUT_S`, and `window()` never returns less than the 2.0s floor the
site shipped on. Every reply that arrived before is still inside the window;
replies in the 2-5s band now arrive too. `max(out)` over a superset cannot fall,
so this cannot convert a matched order into a regression.

WALL CLOCK CAN ONLY SHRINK. `harvest()` stops collecting at the window and
abandons the rest instead of draining them, where the old code had no wall of
its own at all. The window is at most HALF the room the select stage has left,
so the plan-building half of that stage keeps at least the slack it has today.

WHY HALF, AND WHY THE FLOOR. `_paced_wait` returns room LEFT, folding this
order's share of the run pot and the plan window `pacing_bridge._pb_arm_window`
opens. The measured share is 4.0-7.05s (`pace_pot.surplus`, `aero_pin.py:63`),
so the window lands at 2.0s on the tightest orders -- exactly today's behaviour,
by construction -- and opens to 3.5s and beyond as room allows. A phase that
grants itself the whole remaining share is the defect `_paced_wait` was written
for; see [[dyn-order-budget-is-pace-not-plan-allowance]].

NO LOCAL GATE CAN CORROBORATE THIS, for the reason `phase_gate` gives about its
own change: offline `_dyn_order_budget` is None, `_SEARCH_DEADLINE` is unset and
there is no RPC to wait on, so every local gate sees byte-identical plans on
both sides. Only a scored round moves.

A module rather than a method, for the reason `twohop_tier` and `pancake_tier`
give in their own headers, and because the window is a policy two numbers
(`_QUOTER_TIMEOUT_S`, `_RPC_TIMEOUT_S`) already own in `king_base` -- both are
passed in, so the ladder stays owned there and this file only decides how they
combine. Kept as `#` comments rather than per-entry docstrings so the entries
cost no deadwood.
"""
from __future__ import annotations

import concurrent.futures

# The fraction of the select stage's REMAINING room the fan-out may spend
# waiting. The other half is what builds the plan out of what came back, and it
# has to be at least as well off as it is today or this trades a cut for a drop.
SHARE = 0.5


def window(solver, want, floor, stage_want):
    """Seconds the fan-out may spend collecting replies.

    `want` is the caller's `_QUOTER_TIMEOUT_S`, `floor` its `_RPC_TIMEOUT_S` --
    the socket timeout this site used to run on, so the window can never be
    tighter than what shipped -- and `stage_want` its `_SELECT_BUDGET_S`.

    Reached through getattr because this module is imported from a class chain
    that is not guaranteed to carry `king_base`'s pacing helpers; with no pacing
    layer the answer is `want`, which is what an ungoverned run already gets.
    """
    room = stage_want
    wait = getattr(solver, '_paced_wait', None)
    if callable(wait):
        try:
            room = float(wait(stage_want))
        except Exception:
            room = stage_want
    try:
        return max(float(floor), min(float(want), float(room) * SHARE))
    except (TypeError, ValueError):
        return float(floor)


def harvest(jobs, workers, budget):
    """Run `fn(arg)` for every `(fn, arg)` concurrently; return what answers in time.

    Never raises and never blocks past `budget`. A job that raises is dropped,
    which is the collector's existing behaviour, and a job that has not answered
    when the window closes is abandoned rather than waited on -- the one thing
    the `with ThreadPoolExecutor(...)` form cannot do, because its `__exit__`
    joins.
    """
    out = []
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    try:
        futs = [ex.submit(fn, arg) for fn, arg in jobs]
        try:
            for fu in concurrent.futures.as_completed(futs, timeout=budget):
                try:
                    c = fu.result()
                except Exception:
                    continue
                if c is not None:
                    out.append(c)
        except concurrent.futures.TimeoutError:
            pass
    finally:
        try:
            ex.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            ex.shutdown(wait=False)
    return out
