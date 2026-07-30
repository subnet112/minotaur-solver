"""curve_refresh — veto-safe LIVE ETH Curve AMOUNT-WIN cover.

Aimed squarely at the current champion (d95ed3_router): it live-requotes ONLY Uniswap V3
on ETH. This cover targets the venue it structurally can't fresh-quote — Curve — and
serves a fresh Curve exchange ONLY when it strictly out-delivers the champion's own
plan by >30bps (matching the champion's own d95ed3_router gate). Wins where the champion
routes a pegged/stable/LST pair via Uni V3 (or a decayed frozen cover) but a fresh
Curve get_dy delivers more.

Improvement over curve_cover (blind-fill only, 10bps): amount-wins at 30bps, with a
FAIL-CLOSED measurement so a mis-measured champion output can't cause a regression:
  * champion plan uses UniversalRouter/V4 (viking under-measures bare)  -> DEFER
  * champion non-empty but sims to 0 (phantom-zero)                     -> DEFER
  * Curve receiver-variant exchange doesn't execute (sims to 0)         -> DEFER
  * Curve not strictly >30bps better than the champion                  -> DEFER
Reuses the champion's own audited mv_venue Curve router + curve_ix plan builder.
"""
from __future__ import annotations
_DR_UNSET = object()
import logging
logger = logging.getLogger(__name__)
_MARGIN_BPS = 30
_MIN_BUDGET_S = 8.0
_UNIVERSAL_ROUTERS = {'0x6ff5693b99212da76ad316178a184ab56d299b43'}
_UR_SELECTORS = ('0x3593564c', '0xcac88ea9')

def _base_untrusted(base):
    for ix in getattr(base, 'interactions', None) or []:
        try:
            if str(getattr(ix, 'target', '') or '').lower() in _UNIVERSAL_ROUTERS:
                return True
        except Exception:
            pass
        cd = (getattr(ix, 'call_data', '') or '').lower()
        if any((cd.startswith(s) for s in _UR_SELECTORS)):
            return True
    return False

def wrap(base_cls):
    from mv_venue import _curve_best_live, _curve_ix
    from minotaur_subnet.shared.types import ExecutionPlan
    import viking_sim
    import cover_state

    class CurveRefreshSolver(base_cls):
        """Champion + live ETH-Curve amount-win cover, fail-closed (never regresses)."""

        def _cr_candidate(self, intent, state, snapshot, base):
            """Guards + params; delegates the route+build to _cr_route (both stay small regions).
            Returns (cplan, tin, tout, amt, app, w3) or None to defer."""

            def _dz116(intent, self, state):
                p = self._normalized_swap_params(intent, state)
                tin = str(p.get('input_token', '') or '').lower()
                tout = str(p.get('output_token', '') or '').lower()
                amt = int(p.get('input_amount', 0) or 0)
                _r_dz115 = _dz115()
                return (_r_dz115, amt, p, tin, tout)

            def _dz115():
                app = getattr(state, 'contract_address', '') or ''
                if amt <= 0 or not tin or (not tout) or (tin == tout) or (not app):
                    return (None,)
                base_ix = getattr(base, 'interactions', None) or []
                if base_ix and _base_untrusted(base):
                    return (None,)
                return (self._cr_route(intent, state, snapshot, p, tin, tout, amt, app),)
                return _DR_UNSET
            if cover_state.disabled('curve_refresh'):
                return None
            if cover_state.is_cross_chain(base):
                return None
            if int(getattr(state, 'chain_id', 0) or 0) != 1:
                return None
            if float(getattr(self, '_dyn_order_budget', None) or 99.0) < _MIN_BUDGET_S:
                return None
            _r_dz115, amt, p, tin, tout = _dz116(intent, self, state)
            if _r_dz115 is not _DR_UNSET:
                return _r_dz115[0]

        def _cr_route(self, intent, state, snapshot, p, tin, tout, amt, app):
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
                cplan = ExecutionPlan(intent_id=intent.app_id, interactions=_curve_ix(w, amt, tin, recipient), deadline=int(self._apex_deadline(snapshot)), nonce=state.nonce, metadata={'solver': 'curve-refresh', 'chain_id': 1})
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

            def _dz111(cand):
                cplan, tin, tout, amt, app, w3 = cand
                curve_out = viking_sim.sim_floor(w3, cplan, tin, tout, amt, app)
                return (amt, app, cplan, curve_out, tin, tout, w3)

            def _dz110():
                nonlocal co
                co = viking_sim.sim_floor(w3, base, tin, tout, amt, app)
                if co is None or co <= 0:
                    return (base,)
                return _DR_UNSET

            def _dz109():
                if curve_out > co * (1 + cover_state.margin_bps(_MARGIN_BPS) / 10000):
                    logger.info('[curve_refresh] WIN champ=%d curve=%d %s->%s amt=%d', co, curve_out, tin[:10], tout[:10], amt)
                    return (cplan,)
                return _DR_UNSET
            base = super().generate_plan(intent, state, snapshot)
            try:
                cand = self._cr_candidate(intent, state, snapshot, base)
                if cand is None:
                    return base
                amt, app, cplan, curve_out, tin, tout, w3 = _dz111(cand)
                if curve_out is None or curve_out <= 0:
                    return base
                if not (getattr(base, 'interactions', None) or []):
                    co = 0
                else:
                    _r_dz110 = _dz110()
                    if _r_dz110 is not _DR_UNSET:
                        return _r_dz110[0]
                _r_dz109 = _dz109()
                if _r_dz109 is not _DR_UNSET:
                    return _r_dz109[0]
            except Exception:
                logger.exception('[curve_refresh] failed; deferring to champion')
            return base
    return CurveRefreshSolver