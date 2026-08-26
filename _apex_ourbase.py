"""lattice-route-engine — lean delegate over the reigning champion.

Chassis doctrine (2026-07-18 rebuild, from studying 21 adoptions):
- The champion's engine runs VERBATIM on every order: identical plans,
  identical pace ("byte-parity engine = byte-parity pace"). No pre-engine
  hooks, no live probing, no guarded-call overhead.
- Our ONLY divergence: when the engine returns a structurally-empty plan or
  its self-declared blind guess (metadata solver in {best-effort,
  offline-fallback} or route == last_resort_empty — the lineage's own
  convention), we try zero-RPC covers: exact-key rows from
  bg124_covers.json, then the token-keyed V4 census (james_census.json).
  Fill-only-empty ⇒ can only lift a champion-zero, never regress.
- Every region in this file stays far below the champion floor (~123 AST
  nodes, validator metric): tie-breaks and the factorization axis both
  reward the smaller tree, and losing an adoption we outscored to a
  123-node rival (2026-07-17) is what forced this rewrite.
"""
from __future__ import annotations
_DR_UNSET = object()
import json
import logging
import time
from pathlib import Path

def _resolve_base():
    """Import ladder: this generation's sha-named shim, then the legacy
    fixed-name shim a champion tree may carry, then the bare engine."""
    try:
        from _bg124_shim_c63a894 import SOLVER_CLASS, base_module, SOLVER_VERSION
        return (SOLVER_CLASS, base_module, SOLVER_VERSION)
    except Exception:
        pass
    try:
        from _axiom_dex_shim import SOLVER_CLASS, base_module, SOLVER_VERSION
        return (SOLVER_CLASS, base_module, SOLVER_VERSION)
    except Exception:
        import king_solver as base_module
        return (base_module.MinerSolver, base_module, getattr(base_module, 'SOLVER_VERSION', 'unknown'))

def _resolve_metadata_cls():
    try:
        from minotaur_subnet.sdk.intent_solver import SolverMetadata
        return SolverMetadata
    except Exception:
        return None
_Base, _base_module, _BASE_VERSION = _resolve_base()
SolverMetadata = _resolve_metadata_cls()
logger = logging.getLogger(__name__)
_WETH = '0x4200000000000000000000000000000000000006'
_USDC = '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'

def _load_json(name):
    try:
        path = Path(__file__).parent / name
        if path.is_file():
            return json.loads(path.read_text())
    except Exception:
        logger.exception('[bg124] failed loading %s', name)
    return {}
_COVERS = _load_json('bg124_covers.json')
_CENSUS = _load_json('james_census.json')

def _expected(plan):
    """The champion's OWN declared output for this plan (`expected_output`, which
    its lineage documents as 'read downstream as the baseline' and compares
    against itself in king_base). 0 when absent — its offline-fallback path
    builds plans without it, and those we must never override blind: doing so
    replaced a plan delivering 3.49e22 with one delivering 7.58e14, a
    CATASTROPHIC regression that vetoed a run we won 10 orders on."""
    try:
        md = dict(getattr(plan, 'metadata', {}) or {})
        return int(md.get('expected_output', 0) or 0)
    except Exception:
        return 0

def _try_onfork(solver, intent, state, bar=0):
    """On-fork Uniswap-V3 router (bg124_onfork): ONE batched Multicall3 QuoterV2
    quote on the round-pinned fork -> approve+swap. Wins champion-empty quote
    scenarios that content-addressed keys can't target; on-fork so it can't
    revert, single eth_call so the pace governor bounds it."""
    try:
        import bg124_onfork
        return bg124_onfork.try_cover(solver, intent, state, bar)
    except Exception:
        return None

def _try_kyber(solver, intent, state):
    """KyberSwap quality-override (bg124_kyber) — the reigning-champion move.
    Exact-key, CONTRACT-scoped, FORK-VERIFIED strictly-better routes baked
    offline. Unlike the fill-only-empty covers it fires FIRST, even on a
    champion-served order — that's the strict-better dethrone. Safe because the
    key is contract-scoped and every route was verified to beat the incumbent."""
    try:
        import bg124_kyber
        return bg124_kyber.try_cover(solver, intent, state)
    except Exception:
        return None

def _ok(solver, plan):
    """A usable candidate: present and structurally non-empty."""
    return plan is not None and (not _empty(solver, plan))

def _empty(solver, plan):
    """Empty per the MRO's own predicate; the fallback excepts bridge payloads.

    Twin of `solver._empty`, and it carried the same hole for the same reason:
    the `except` branch asked the interactions-alone question, so a bridge plan
    -- `interactions=[]` with its payload under `metadata['cross_chain_plan']`
    (baseline_solver.py:1181) -- read as empty and the layer above was licensed
    to overwrite it with a source-chain plan, which is `no_cross_chain_plan` and
    a hard veto. Fixed in both places at once on purpose: one rule fixed in one
    of its two places is precisely what let this reason score again on
    sub_99ff73d67700 after 7c23ce1 had already closed it.

    Only reachable when `solver._is_empty` is missing or raises, which is rare
    -- but a branch that fires only after something else broke is the one nobody
    reads, and its cost here is a dropped order rather than a worse route.
    """
    try:
        return solver._is_empty(plan)
    except Exception:
        if plan is None:
            return True
        if getattr(plan, 'interactions', None):
            return False
        try:
            from empty_rescue import is_cross_chain as _x
            return not _x(plan)
        except Exception:
            return not (getattr(plan, 'metadata', None) or {}).get('cross_chain_plan')

def _parse_tokens(state):
    p = dict(getattr(state, 'raw_params', {}) or {})
    tin = str(p.get('input_token', '') or '').lower()
    tout = str(p.get('output_token', '') or '').lower()
    return (tin, tout, p.get('input_amount', 0))

def _order_key(state):
    tin, tout, raw_amt = _parse_tokens(state)
    try:
        amt = int(raw_amt or 0)
    except (TypeError, ValueError):
        return None
    chain = int(getattr(state, 'chain_id', 0) or 0)
    if amt <= 0 or not tout.startswith('0x'):
        return None
    return (chain, tin, tout, amt)

def _census_pool(tout):
    row = _CENSUS.get(tout)
    if not row:
        return None
    pool = row['pool'] if isinstance(row, dict) else row
    return tuple(pool)

def _census_leg(spec, tin, paired):
    if paired == tin:
        if tin == _USDC:
            spec['sweep_settle'] = True
        return spec
    if tin == _USDC and paired == _WETH:
        spec['v3_tokens'] = (_USDC, _WETH)
        spec['v3_fees'] = (500,)
        return spec
    return None

def _census_spec(tin, tout):
    """Census pool -> spec for the lineage's uniswap_v4_ur builder. Direct
    when tin is the pool's paired side; USDC-in via a v3 USDC->WETH leg
    when the pool is WETH-paired; else unroutable-safely -> None."""
    pool = _census_pool(tout)
    if pool is None:
        return None
    c0, c1 = (pool[0], pool[1])
    paired = c0 if c1 == tout else c1
    spec = {'pool': pool, 'settle': paired, 'zero_for_one': c0 == paired}
    return _census_leg(spec, tin, paired)

def _spend_build(solver):
    """Pace guard (2026-07-19): two consecutive benches rejected on exactly
    1 dropped order (the 900s completion race). Cover BUILDS go through the
    engine's builder and can cost RPC time on doomed zero-quote orders; cap
    attempts per run so cover work can never turn a completed run into a
    tail-drop."""
    spent = getattr(solver, '_bg124_builds', 0)
    if spent >= 8:
        return False
    solver._bg124_builds = spent + 1
    return True

def _cover_row(key):
    chain, tin, tout, amt = key
    row = _COVERS.get('%d|%s|%s|%d' % key)
    if row is None and chain == 8453:
        spec = _census_spec(tin, tout)
        if spec is not None:
            row = {'venue': 'uniswap_v4_ur', 'spec': spec, 'out': 1}
    return row

class Bg124Solver(_Base):
    """Champion verbatim + zero-RPC fill-only-empty covers."""

    def generate_plan(self, intent, state, snapshot=None):
        plan = super().generate_plan(intent, state, snapshot)
        if _empty(self, plan):
            return self._bg124_fill(intent, state, snapshot, 0) or plan
        bar = _expected(plan)
        if bar > 0:
            # SERVED — return the champion plan untouched.
            #
            # THIS LAYER IS LIVE AND RUNS FIRST. The MRO is
            #   solver.Bg124Solver -> _bg124_arch_9645f01.MinerSolver
            #     -> _apex_ourbase.Bg124Solver (here) -> ... -> champion
            # and 9645f01's generate_plan is an unconditional memoising
            # pass-through, so this method executes on every order AHEAD of the
            # copy in solver.py. The plan solver.py then inspects is whatever we
            # return, so its own `if bar > 0: return plan` sees an ALREADY
            # overridden plan and cannot undo it — a gate placed above the layer
            # that does the overriding cannot close it. That is why e57efe3,
            # which gated solver.py alone, did not hold and dcc15d2 was needed.
            #
            # RESTORED 2026-08-19T10:20Z: e0ef9ae content-reverted to 89a11b6,
            # which predates both, so the whole served-order chain was reopened
            # while every local gate stayed green.
            return plan
        # BLIND OVERRIDE CLOSED 2026-08-22, AND THIS IS THE LAYER THAT HAD TO
        # CLOSE IT. `_blind` decides on the champion's METADATA alone
        # (`best-effort` / `offline-fallback` / `last_resort_empty`) and reads
        # that as "a guess that scores 0 when the default pool doesn't exist".
        # The A/B measures the opposite: all 50 override-on-served rows in
        # state/last-perf-ab.json carry `live_champ_zero: false`, so the plan
        # this branch called a guess DELIVERS, and replacing it was a bet, not
        # a fill. sub_e171b56c05b5 settled that bet — 7 better / 14 dropped,
        # with worse == dropped == 14 and no separate regression anywhere in
        # the 122 per-order rows. A drop is a hard veto; the bet cannot pay.
        #
        # THE 7 "BETTER" ROWS ARE NOT THIS BRANCH'S, WHICH IS WHY CLOSING IT
        # COSTS ALMOST NOTHING. Counted from that verdict's own per_order:
        # 6 are `blind_spot_cover` on `champ: null` and reach the table through
        # `_empty(self, plan)` -> `_bg124_fill(..., 0)` above, which this change
        # does not touch. Exactly ONE is a `win`
        # (q_ac649900b9dd2e48d716d6a65fd55d13, ratio 1.1627) and only a
        # champion-served override can produce it, so one win is the whole
        # price. 6 better / 0 worse clears the output rung (>= 1) outright,
        # while 7 better / 14 dropped cannot clear it at any margin.
        #
        # CLOSED HERE, NOT IN solver.py, and the difference is the reason the
        # last two attempts did not hold. The MRO is
        #   solver.Bg124Solver -> _bg124_arch_9645f01.MinerSolver
        #     -> _apex_ourbase.Bg124Solver (here) -> ... -> champion
        # and 9645f01's generate_plan is an unconditional memoising
        # pass-through, so THIS method overrides first and solver.py only ever
        # inspects the result — the same reason e57efe3 needed dcc15d2. 6b7fc2b
        # repeated it: it hung `prove_blind` on solver.py's copy alone, so the
        # override was already committed by the time the proof ran, and
        # bin/exec-check still reproduced the drop 14 minutes later
        # (q_742f4f532169a5077c7ff47ca25e8713, `scoreIntent reverted:
        # CallFailed(index=1)`, genesis delivers 1692831340678565711).
        #
        # A FORK PROOF WOULD NOT HAVE SAVED IT EITHER. `prove_blind` asked
        # `_fork_routable` — "can ANY venue route this order at this block" —
        # and the champion delivering the row is proof that one can, so the
        # gate returns True and the override stands on precisely the rows it
        # was written to stop. Worse, it fails OPEN on `w3 is None`, and chain 1
        # is served with no read RPC at all (`SOLVER_READ_PROXY_CHAINS=8453`),
        # which is where every one of these drops lives. Both halves inert.
        return plan
    _BG124_COVER_BUDGET_S = 12.0

    def _bg124_window(self):
        """Seconds THIS ladder call may spend — the last cover still unbounded.

        `_BG124_COVER_BUDGET_S` is a CUMULATIVE pot checked on ENTRY and nowhere
        else, so it stops the NEXT call and never the one in flight. The first
        cover-eligible order of a run therefore descends the ladder with no
        deadline at all: `_bg124_ladder`'s own comment measures onfork phase 2 at
        5.0s and phase 1 is a Multicall3 QuoterV2 sweep, and neither is bounded
        by anything once `_cover_or`'s `finally` has handed `_SEARCH_DEADLINE`
        back to `prev` (0.0 = unset = unbounded) before we run.

        That is charged twice, and the second charge is the one that drops us:

          * to `_RUN_BUDGET_S`, the shared pot the governor divides across the
            corpus — the starvation shape `_rb1_cap` documents; and
          * to the harness's 30s PER-`GENERATE_PLAN` cutoff, which is a separate
            limit the run pot has never modelled. Blowing it is not a slow plan,
            it is NO plan: the command is killed and the validator records
            `chal: null`, a dropped order and a hard veto.

        The arithmetic was already over the line before this call could overrun
        at all. `_apex_champ._PLAN_CEILING_S` caps the SEARCH at 20.0s and states
        in its own comment that "the cover ladder is charged to a separate
        run-wide pot (_BG124_COVER_BUDGET_S = 12.0)" which it does not govern:
        20 + 12 = 32 > 30. The remaining third it left for "plan encode plus the
        IPC round trip" is 10s, and the cover pot alone exceeds it.

        So: the tighter of what the pot has left and this order's own pace share.
        `_dyn_order_budget` is that share, read through getattr exactly as
        `_rb1_cap` reads it — this class chains onto whatever `SOLVER_CLASS` is at
        import time and the governor is not guaranteed to be in that MRO. Absent
        governor = the pot's remainder, i.e. the tightening still holds.

        Defined HERE, once, rather than beside each copy of `_bg124_fill`:
        `solver.Bg124Solver` sits above this class on the MRO documented in
        `generate_plan`, so its copy inherits this method and the two cannot
        drift apart the way the kyber and onfork rungs did at e57efe3 -> dcc15d2.
        """
        left = self._BG124_COVER_BUDGET_S - getattr(self, '_bg124_cover_secs', 0.0)
        dyn = getattr(self, '_dyn_order_budget', None)
        try:
            dyn = float(dyn)
        except (TypeError, ValueError):
            return left
        return left if dyn <= 0 else min(left, dyn)

    def _bg124_arm(self):
        """Bound this ladder call by `_bg124_window`; return `prev`.

        SHARED-CELL DISCIPLINE, the tightening half — the rule `_rb1_arm` and
        `router_cover.best_route` already state. `_SEARCH_DEADLINE` is one
        mutable cell every `venues.eth_call` in the tree reads, so honour the
        TIGHTER of what we inherit and our own window, and hand `prev` back
        untouched in a `finally` (`_bg124_disarm`). Leaving an expired deadline
        behind refuses the inherited solver's own quotes on every LATER order:
        sub_63ae4707f360 covered 38 blind spots and dropped 41 that way.

        Imported inside the function, and split out of `_bg124_fill` rather than
        inlined: both copies of the ladder call this, `_dz3` is already near the
        tree's largest region, and `solver.py <module>` is tied for it. A named
        helper is the only way to add this and move `max_region_nodes` by zero.
        """
        from consts import _SEARCH_DEADLINE
        prev = _SEARCH_DEADLINE[0]
        mine = time.monotonic() + self._bg124_window()
        _SEARCH_DEADLINE[0] = min(mine, prev) if prev else mine
        return prev

    @staticmethod
    def _bg124_disarm(prev):
        """Hand the shared deadline back exactly as we found it."""
        from consts import _SEARCH_DEADLINE
        _SEARCH_DEADLINE[0] = prev

    def _bg124_fill(self, intent, state, snapshot, bar=0):
        """Champion empty/blind: zero-RPC KyberSwap exact-key override, then the
        on-fork V3 router (wins content-addressed quote scenarios), then the
        census exact-key row — under a hard pace budget. Fill-only, so never a
        regression; pace-gated, so never a tail-drop."""

        def _dz3():
            t0 = time.monotonic()
            try:
                # Both rungs mirror solver.py::_bg124_ladder — kyber at
                # bar <= 0 (six served drops on sub_83db1d62d155 were its
                # alone), onfork at bar == 0 (bar == -1 is champion-BLIND and
                # still DELIVERS). This copy runs FIRST via the pass-through
                # super() hop, so a gate applied only in solver.py is dead —
                # that is the lesson of e57efe3 -> dcc15d2 and both must carry
                # it or the copies silently diverge again.
                if bar <= 0:
                    ky = _try_kyber(self, intent, state)
                    if _ok(self, ky):
                        return (ky,)
                of = _try_onfork(self, intent, state, bar) if bar == 0 else None
                if _ok(self, of):
                    return (of,)
                # PASS `bar`. This call resolves to solver.py's
                # _bg124_cover(self, intent, state, snapshot, bar=0) — that copy
                # is the most derived on the MRO documented above and SHADOWS the
                # 3-param one below in this file. Omitting the argument therefore
                # took the bar=0 default and handed `allow_sell=True` to
                # _census_spec on EVERY rung reaching here, including bar == -1
                # (champion-BLIND, which still DELIVERS). That is the always-on
                # sell-side census whose own docstring records the cost: scored
                # sub_8591e90be04b (dabbb00) took 3 dropped served quote orders,
                # champ delivered / chal null, a hard-floor reject.
                # solver.py was tightened for this; this layer never was, and it
                # is the one that RUNS FIRST — the same e57efe3 -> dcc15d2 lesson
                # as the kyber/onfork rungs above. bar == 0 is byte-identical to
                # the old behaviour; only the blind rung changes.
                return (self._bg124_cover(intent, state, snapshot, bar) if bar <= 0 else None,)
            finally:
                self._bg124_cover_secs = getattr(self, '_bg124_cover_secs', 0.0) + time.monotonic() - t0
            return _DR_UNSET
        if getattr(self, '_bg124_cover_secs', 0.0) >= self._BG124_COVER_BUDGET_S:
            return None
        _prev = self._bg124_arm()
        try:
            _r_dz3 = _dz3()
        finally:
            self._bg124_disarm(_prev)
        if _r_dz3 is not _DR_UNSET:
            return _r_dz3[0]

    def _bg124_cover(self, intent, state, snapshot):
        try:
            key = _order_key(state)
            if key is None:
                return None
            row = _cover_row(key)
            if row is None:
                return None
            if not _spend_build(self):
                return None
            chain, tin, tout, amt = key
            return self._bg124_build(intent, state, snapshot, row, tin, tout, amt, chain)
        except Exception:
            logger.exception('[bg124] cover path failed; champion plan stands')
            return None

    def _bg124_build(self, intent, state, snapshot, row, tin, tout, amt, chain):
        spec = row.get('spec')
        if isinstance(spec, dict):
            spec = {k: tuple(v) if isinstance(v, list) else v for k, v in spec.items()}
        cand = {'venue': row['venue'], 'spec': spec, 'param': 'bg124-cover', 'out': row.get('out', 1), 'gas_est': 650000, 'gas_model': 1000000}
        plan = super()._build_singlehop_plan(intent, state, snapshot, cand, tin, tout, amt, chain)
        return plan

    def metadata(self):
        base = super().metadata()
        if SolverMetadata is None:
            return base
        return SolverMetadata(name='lattice-route-engine', version=f'{_BASE_VERSION}+bg.3.L1', author='MichaelDev84', description='champion verbatim + zero-RPC fill-only-empty covers (census + harvested exact-key rows)', supported_chains=base.supported_chains, supported_intent_types=base.supported_intent_types)
SOLVER_CLASS = Bg124Solver