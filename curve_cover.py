"""curve_cover — veto-safe GENERAL Curve venue cover.

The champion's engine only routes Curve on the ETH 3pool + a 4-pair allowlist,
even though its own `mv_venue._curve_best_live` is a general Curve router (finds
every pool via the MetaRegistry and quotes get_dy). This delta invokes that same
router on ALL ETH pairs and, ONLY when a Curve route strictly out-delivers the
champion's own plan (both measured with viking_sim.sim_floor execution sim),
serves the Curve route. So:
  * champion serves a sub-optimal Uni/PCS route, Curve delivers more -> WIN
  * champion serves nothing (empty), Curve delivers                  -> blind-fill WIN
  * Curve not better / unverifiable                                  -> DEFER (never regress)
Veto-safe by construction; reuses the champion's own audited Curve calldata.
"""
from __future__ import annotations
_DR_UNSET = object()
import logging
logger = logging.getLogger(__name__)
_MARGIN_BPS = 10
_MIN_BUDGET_S = 8.0

def _load_curve_tokens():
    """Set of tokens that appear in ANY Curve pool (from the champion's own
    viking_curve.json 'bytoken' index) — a CHEAP pre-gate so we never pay the
    on-chain find_pools + double-sim on the ~95% of ETH orders that can't be
    Curve at all (exotic/memecoin pairs)."""
    import json as _j, os as _o
    try:
        d = _j.load(open(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)), 'viking_curve.json')))
        bt = d.get('bytoken') or {}
        return {str(k).lower() for k in bt}
    except Exception:
        return set()

def wrap(base_cls):
    from mv_venue import _curve_best_live, _curve_ix
    from minotaur_subnet.shared.types import ExecutionPlan
    import viking_sim
    import cover_state
    _CURVE_TOKENS = _load_curve_tokens()

    class CurveCoverSolver(base_cls):
        """Champion + general ETH-Curve cover on the pairs its engine won't route (fail-closed)."""

        def _cc_params(self, intent, state):
            p = self._normalized_swap_params(intent, state)
            tin = str(p.get('input_token', '') or '').lower()
            tout = str(p.get('output_token', '') or '').lower()
            amt = int(p.get('input_amount', 0) or 0)
            return (p, tin, tout, amt)

        def _cc_candidate(self, intent, state, snapshot, base):
            """Guards + params; delegates route+build to _cc_route (both stay small regions).
            Returns (cplan, tin, tout, amt, app, w3) or None to defer."""

            def _dz115():
                p, tin, tout, amt = self._cc_params(intent, state)
                app = getattr(state, 'contract_address', '') or ''
                if amt <= 0 or not tin or (not tout) or (tin == tout) or (not app):
                    return (None,)
                return (self._cc_route(intent, state, snapshot, p, tin, tout, amt, app),)
                return _DR_UNSET
            if cover_state.disabled('curve'):
                return None
            if int(getattr(state, 'chain_id', 0) or 0) != 1:
                return None
            if float(getattr(self, '_dyn_order_budget', None) or 99.0) < _MIN_BUDGET_S:
                return None
            _r_dz115 = _dz115()
            if _r_dz115 is not _DR_UNSET:
                return _r_dz115[0]

        def _cc_route(self, intent, state, snapshot, p, tin, tout, amt, app):
            """Live-Curve route lookup + built candidate plan (own region)."""

            def _dz114():
                if pool is None or dy <= 0:
                    return (None,)
                _r_dz113 = _dz113()
                if _r_dz113 is not _DR_UNSET:
                    return (_r_dz113[0],)
                return _DR_UNSET

            def _dz113():
                recipient = self._apex_recipient(state, p)
                w = {'pool': pool, 'i': i, 'j': j, 'ex': 'u256_recv' if sig == 'u256' else 'i128_recv'}
                cplan = ExecutionPlan(intent_id=intent.app_id, interactions=_curve_ix(w, amt, tin, recipient), deadline=int(self._apex_deadline(snapshot)), nonce=state.nonce, metadata={'solver': 'curve-cover', 'chain_id': 1})
                return ((cplan, tin, tout, amt, app, w3),)
                return _DR_UNSET
            w3 = self._get_web3(1)
            if w3 is None:
                return None
            block = getattr(snapshot, 'block_number', None) if snapshot else None
            try:
                block = int(block) if block else 'latest'
            except Exception:
                block = 'latest'
            dy, pool, i, j, sig = _curve_best_live(w3, tin, tout, amt, block)
            _r_dz114 = _dz114()
            if _r_dz114 is not _DR_UNSET:
                return _r_dz114[0]

        def generate_plan(self, intent, state, snapshot=None):

            def _dz111(base, cand):
                cplan, tin, tout, amt, app, w3 = cand
                champ_out = viking_sim.sim_floor(w3, base, tin, tout, amt, app)
                _r_dz110 = _dz110()
                return (_r_dz110, amt, app, champ_out, cplan, tin, tout, w3)

            def _dz110():
                curve_out = viking_sim.sim_floor(w3, cplan, tin, tout, amt, app)
                if champ_out is None or curve_out is None:
                    return (base,)
                if curve_out > champ_out * (1 + cover_state.margin_bps(_MARGIN_BPS) / 10000):
                    logger.info('[curve] cover WIN champ=%d curve=%d %s->%s amt=%d', champ_out, curve_out, tin[:10], tout[:10], amt)
                    return (cplan,)
                return _DR_UNSET
            base = super().generate_plan(intent, state, snapshot)
            try:
                if cover_state.is_cross_chain(base) or cover_state.base_untrusted(base):
                    return base
                cand = self._cc_candidate(intent, state, snapshot, base)
                if cand is None:
                    return base
                _r_dz110, amt, app, champ_out, cplan, tin, tout, w3 = _dz111(base, cand)
                if _r_dz110 is not _DR_UNSET:
                    return _r_dz110[0]
            except Exception:
                logger.exception('[curve] cover failed; deferring to champion')
            return base
    return CurveCoverSolver