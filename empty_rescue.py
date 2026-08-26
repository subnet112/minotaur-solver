"""Never ship an EMPTY plan while an RPC-free valid one is still available.

WHAT THIS FIXES
===============
`_apex_champ.JamesSolver.generate_plan` ends on `_dr12`, which returns the
king's plan when it is non-empty, then tries the per-app agent strategy, and
otherwise returns the EMPTY plan unchanged. The validator scores an empty plan
`chal: null` -- a dropped order and a HARD VETO, which no amount of budget or
deadwood work can outweigh (`epoch/relative_scoring.py`: a drop vetoes before
the tie-break ladder is ever consulted).

There is a third rung the outermost plan path never reaches.
`king_base._last_resort_plan` is documented as "best-effort, never-raising plan
for when every primary path failed", and its first two rungs need NO RPC AT ALL:

  (1) `_offline_fallback_plan` -- the RPC-free offline snapshot plan;
  (2) `_best_effort_singlehop_plan` -- "a default-fee Uniswap V3 approve+
      exactInputSingle for the pair WITHOUT any RPC verification ... strictly
      better than an empty plan for both screening structure checks and live
      coverage".

`JamesSolver._fast_plan` already wraps it, but the ONLY caller is the
`_behind_pace()` branch, which is evaluated BEFORE the search runs. So the
order that is not behind pace when it starts, then burns its whole window on a
cold heavy route and comes back with nothing, never gets offered the rung that
would have served it. That is precisely the shape of this lineage's drops.

WHY IT COSTS NOTHING, WHICH IS THE WHOLE POINT
==============================================
Both live rungs are RPC-free, so this cannot spend the validator's per-scenario
RPC-read budget (`solver_read_proxy.DEFAULT_GENERATE_PLAN_BUDGET = 5000`) and
cannot extend the run against the shared 900s wall
(`protocol.TOTAL_BENCHMARK_TIMEOUT`). It also does not need a search window:
`venues.eth_call` refuses to START a call once `_SEARCH_DEADLINE` has closed,
which is exactly the state an order is in when it arrives here -- so a rescue
that needed reads would get None from every one of them and be useless. This
one does not read.

WHY IT CANNOT COST A MATCHED ORDER
==================================
It is reachable only where `self._is_empty(plan)` is already true -- `_dr12`
returns the king's plan untouched on every non-empty result before this is
consulted. An order we currently serve cannot be routed through here, so the
rule "do not convert a matched order into a regression" is satisfied by
construction rather than by measurement. The worst case is an order that was a
hard-veto drop becoming a plan that still delivers nothing (scored the same
drop); the best case is a served order.

CROSS-CHAIN ORDERS ARE NOT UNTOUCHED, AND THE CLAIM THAT THEY WERE COST US TWO
DROPS. This header used to read "cross-chain orders are untouched:
`_best_effort_singlehop_plan` refuses any `eip155:` token address". Both rungs
do carry that guard (`king_base.py:3451`, `:3998`) -- and it is the wrong
guard, because it tests the TOKEN and cross-chain-ness is not carried on the
token. `baseline_solver.py:440` reads `dest_chain_id` off
`_cross_chain_compat_params(state)`, i.e. off the STATE, and dispatches to
`_generate_cross_chain_plan` on that alone (`:451`). The tokens of such an
order are ordinary `0x...` addresses, so neither rung refuses it and both
happily build a source-chain swap.

That would be merely useless if the incumbent plan were really empty. It is
worse than that, because a VALID cross-chain plan IS `interactions=[]` --
`baseline_solver.py:1181` returns exactly that, with the whole payload under
`metadata['cross_chain_plan']`. Judging emptiness on `interactions` alone
therefore mis-reads a working bridge plan as nothing, and this module then
replaces it with a source-chain route that delivers on the wrong chain. The
validator scores that as an ordinary single-chain plan that delivered nothing:
`{"orders": 2, "credited": 0, "reasons": {"no_cross_chain_plan": 2}}` on
sub_226692a9b998.

This is the same silent-clobber `1fc59e2` fixed at the apex-h5 cover and
`payload_cover_k._k_is_cross_chain` fixed below it -- and THIS layer is the
most dangerous of the three, because `min_amt_alias.install_plan_boundary` is
installed LAST (`solver.py:772`) and nothing sits above it. Whatever the cover
layers preserve, this one had the final say to throw away.

`_is_empty` below now counts the cross-chain marker as substance, which both
keeps the bridge plan and denies the rescue an order no source-chain rung
could have served.

THE DETERMINISM ARGUMENT, WHICH MATTERS MORE THAN THE DROPS
===========================================================
Adoption is not decided by the leader alone. `api/routes/submissions/
champion_consensus.py` runs an INDEPENDENT VOTE: every follower validator
re-benchmarks champion and challenger on ITS OWN host and applies the identical
`_meets_adoption_criteria`, and `champion_manager._approval_matches_proposal`
counts an approval only when it matches the proposal exactly. A candidate whose
result depends on host speed cannot collect a quorum -- named as an open risk in
`docs/deterministic-budget/README.md:78`: "A solver that branches on wall-clock
timing reintroduces a host-dependent call sequence -- mitigated only fail-safe
(it can't reach quorum, so it can't be certified)."

This tree branches on wall-clock everywhere (`_SEARCH_DEADLINE`, the run pot,
the per-plan ceiling), so a slow follower cuts its search off earlier than the
leader did and lands on an EMPTY plan where the leader had a full one. That
turns one host's win into another host's drop, and a single dissent can strand
the round. Backstopping the empty case with an RPC-free plan does not make the
tree deterministic, but it removes the variance's worst outcome: hosts now
disagree about plan QUALITY rather than about whether an order was served at
all.

Written as a module rather than as statements inside `generate_plan` because
that method's region is already among the tree's largest and the module top
level is itself a region the validator measures -- the same reasoning that put
`read_meter` in its own file.
"""
from __future__ import annotations
_DR_UNSET = object()

def is_cross_chain(plan) -> bool:
    """True when `plan` carries a bridge payload, whatever its `interactions` say.

    ONE OWNER FOR THE PREDICATE, which is the point of it living here. Four
    layers of this MRO have now had to answer "would replacing this plan throw a
    bridge away?" and three of them grew their own copy after it had already
    cost a round -- `payload_cover_apex._is_cross_chain` (1fc59e2),
    `payload_cover_k._k_is_cross_chain`, `mino_fill_layer._is_empty`. Copies of
    a rule drift apart; that is the e57efe3 -> dcc15d2 lesson this tree keeps
    re-learning. New callers import this one rather than inlining a fourth.

    Note this cannot be answered off the intent's TOKENS. Cross-chain-ness is
    read off `dest_chain_id` in `_cross_chain_compat_params(state)`
    (`baseline_solver.py:440`), so such an order's tokens are ordinary `0x`
    addresses and every `eip155:`-prefix test in the tree misses it -- the
    mistake that made this module overwrite bridge plans in the first place.

    Never raises: a plan whose metadata cannot be read is reported as not
    cross-chain, which leaves every caller on the behaviour it had before.
    """
    try:
        return bool((getattr(plan, 'metadata', None) or {}).get('cross_chain_plan'))
    except Exception:
        return False

def _xc_leg_on(leg, dst) -> bool:
    """True when `leg` is a leg on chain `dst` that has something to execute."""
    if not isinstance(leg, dict) or not leg.get('interactions'):
        return False
    try:
        return int(leg.get('chain_id') or 0) == dst
    except (TypeError, ValueError):
        return False

def delivers_cross_chain(plan) -> bool:
    """True when `plan` carries a bridge payload THAT ACTUALLY MOVES SOMETHING.

    `is_cross_chain` above answers "would replacing this throw a bridge away?".
    This answers the question the callers of that predicate actually meant:
    "would replacing this throw away anything of VALUE?". They are not the same
    question, and the gap between them is a scored drop.

    A cross-chain plan is delivered as empty `interactions` plus the payload
    under `metadata['cross_chain_plan']`, and
    `baseline_solver._build_dest_swap_interactions` has FIVE `return []` paths
    (no bridge token, bridge token == output token, no pool states, an empty
    nested plan, any exception) while `_generate_cross_chain_plan` appends the
    destination ChainLeg regardless. So "has the key" and "has a destination leg
    to run" come apart routinely, and the validator scores the difference as
    ``cross_chain_delivery: {"orders": N, "credited": 0, "reasons":
    {"nothing_delivered": N}}`` -- in this repo's own words, "Returning [] here
    bridges and then stops".

    MEASURED TWICE. sub_a00b73cb6f94 / round-e29788062-n1 scored nothing_delivered
    x2, which is what put the `_g_xc_delivers` test in front of the one PRODUCER
    of these plans (`_bg124_arch_c63a894._g_try_xchain`). sub_10821047e512 /
    round-e29789540-n1 scored nothing_delivered x2 AGAIN, because fixing the
    producer left every CONSUMER still asking the key-alone question: the three
    guards at `_apex_champ:470`, `_apex_champ:515` and `_champ_base:103` exist to
    stop a bridge plan being replaced, and on the key alone they faithfully
    protect a plan that delivers nothing. That is the same welded-guard shape as
    249fb18 (a USDT approve-reset guard fixed on one of three routers) and as the
    `_STUB_S` copy in `pacing_bridge` -- one rule, fixed in one of its places.

    IT CANNOT LOSE DELIVERY, which is why it is safe to widen the guards with.
    An empty destination leg delivers nothing BY CONSTRUCTION, so declining to
    protect it trades a CERTAIN zero for whatever the replacement is worth. It
    never touches a bridge that does carry a destination leg.

    The destination leg is found by CHAIN, not by position: the compiler requires
    ``legs[i+1].chain_id == bridge_requests[i].dst_chain_id``, so it is whichever
    leg sits on the plan's own `dst_chain_id`.

    Never raises, and reports False on anything it cannot read -- the same
    fail-safe direction as `is_cross_chain`, since False here means "treat this
    as empty", i.e. let the rescue layers do what they did before bridges
    existed.

    WHICH GUARDS WANT THIS AND WHICH MUST KEEP `is_cross_chain`. Not every
    key-alone test in this tree is the same defect, and a later pass that
    converts them all would be doing harm for tidiness. The question is what the
    guard's ALTERNATIVE can serve:

      wants `delivers_cross_chain`  -- guards whose alternative can itself serve
        a cross-chain order, so refusing a dead bridge lets something better
        run: `_apex_champ:470`, `_apex_champ:515`, `_champ_base:103`, and the
        producer test `_bg124_arch_c63a894._g_xc_delivers`.

      keeps `is_cross_chain`  -- guards over a SINGLE-CHAIN overlay, which by
        their own docstrings "can never serve such an order, only destroy it":
        `lattice_fill_layer._lat_is_cross_chain`, `g2_fill._g2_is_cross_chain`,
        `payload_cover_apex._is_cross_chain`, `payload_cover_k._k_is_cross_chain`.
        Swapping a non-delivering bridge for a source-chain route there turns
        `nothing_delivered` into `no_cross_chain_plan` -- both drops, no gain --
        while widening a guard that three separate rounds were spent narrowing
        (sub_226692a9b998, no_cross_chain_plan x2). Zero-for-zero is not a fix,
        and it is regression surface for nothing.

    `_is_empty` below deliberately stays on `is_cross_chain` for the same
    reason: it is the generic predicate this module offers every layer, and most
    of its callers are in the second group.
    """

    def _dz67():
        xc = md.get('cross_chain_plan')
        if not isinstance(xc, dict):
            return (False,)
        try:
            dst = int(md.get('dst_chain_id') or 0)
        except (TypeError, ValueError):
            return (False,)
        legs = xc.get('legs')
        if not dst or not isinstance(legs, list):
            return (False,)
        return (any((_xc_leg_on(leg, dst) for leg in legs)),)
        return _DR_UNSET
    try:
        md = getattr(plan, 'metadata', None) or {}
        _r_dz67 = _dz67()
        if _r_dz67 is not _DR_UNSET:
            return _r_dz67[0]
    except Exception:
        return False

def _is_empty(plan) -> bool:
    """True when `plan` is nothing the validator would score.

    A CROSS-CHAIN plan is delivered as empty `interactions` plus the real
    payload under `metadata['cross_chain_plan']` (`baseline_solver.py:1181`), so
    `interactions` alone cannot answer this question -- see the header for the
    two drops that cost. `mino_fill_layer._is_empty` already reaches the same
    verdict the same way; this is that predicate at the outermost boundary,
    which is the one whose answer survives.

    Deliberately narrow, and narrow in the direction that keeps the rescue
    working: only the cross-chain marker counts as substance. `_last_resort_plan`'s
    own final rung is an empty plan carrying no such marker, so it still reads
    as empty and can still be rescued -- the case this module exists for.

    Otherwise mirrors `_apex_champ.JamesSolver._is_empty` rather than calling it:
    this module is imported by that class's own method, and reaching back through the
    instance for a predicate would make the rescue fail closed on any tree whose
    MRO does not define it. Never raises -- an unreadable plan is empty.
    """
    try:
        if plan is None:
            return True
        if getattr(plan, 'interactions', None):
            return False
        return not is_cross_chain(plan)
    except Exception:
        return True

def rescue(solver, intent, state, snapshot=None):
    """An RPC-free plan for an order about to be dropped, else None.

    None means "no rescue available -- leave the caller's empty plan standing",
    which is also what a raising or still-empty last-resort path reports. The
    caller keeps its own result on None, so this can only ever add a plan where
    there was none.
    """
    fast = getattr(solver, '_fast_plan', None)
    if fast is None:
        return None
    try:
        plan = fast(intent, state, snapshot)
    except Exception:
        return None
    return None if _is_empty(plan) else plan

def rescue_if_empty(solver, plan, args, kwargs):
    """`plan`, or an RPC-free stand-in when `plan` is empty. Never raises.

    ALTITUDE IS THE WHOLE POINT, and getting it wrong is what 4aed53c did.
    The first version of this module was called from
    `_apex_champ.JamesSolver.generate_plan._dr12`, and that class is at the
    BOTTOM of the live MRO -- `solver.py:78` builds `_Base` from the arch
    module and `Bg124Solver(_Base)` sits above it, with payload_cover_apex and
    this boundary above that. Every fill-only-empty layer in the tree keys on
    `_is_empty(super().generate_plan(...))`, so filling the plan down there
    does not hand them a better plan, it TELLS THEM THERE IS NOTHING TO DO:

      * `Bg124Solver.generate_plan` (solver.py:345) runs the cover ladder at
        `bar = 0` only while the inherited plan is empty. A last-resort plan
        carries no `expected_output`, so `_expected` reads 0 and `_blind` reads
        true, which routes to `bar = -1` -- and `_bg124_ladder` gates onfork
        `if bar == 0` and c1weth "runs at bar == 0, so it can only lift a
        champion-zero". Both rungs go dark.
      * `payload_cover_apex._HybridLayer` "only assembles from the table when
        we come back empty" (solver.py:529), 1900 baked exact-key rows on the
        `quote:q_*` class that solver.py:524 names as carrying "every drop and
        every cover in the last scored round". It is skipped entirely.

    Called from `min_amt_alias.install_plan_boundary` instead -- the LAST
    install, documented there as "this must go on OUTSIDE everything else ...
    nothing can sit above it". Every layer has already seen the true empty plan
    and declined by the time this runs, so the rescue adds a plan where the
    whole stack produced none and cannot take a cover away from a layer that
    would have produced one.

    `args`/`kwargs` are forwarded verbatim rather than unpacked into named
    parameters: the boundary is declared `generate_plan(self, *a, **kw)` and
    the snapshot argument is optional, so naming them here would fail on the
    two-argument call the harness is free to make.
    """
    if not _is_empty(plan):
        return plan
    try:
        saved = rescue(solver, *args, **kwargs)
    except Exception:
        return plan
    return plan if saved is None else saved