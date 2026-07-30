"""curve_refresh — veto-safe LIVE ETH Curve AMOUNT-WIN cover.

Aimed squarely at the current champion (de00c9_router): it live-requotes ONLY Uniswap V3
on ETH. This cover targets the venue it structurally can't fresh-quote — Curve — and
serves a fresh Curve exchange ONLY when it strictly out-delivers the champion's own
plan by >30bps (matching the champion's own de00c9_router gate). Wins where the champion
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
_FR_UNSET = object()
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

            def _dz92():
                app = getattr(state, 'contract_address', '') or ''
                if amt <= 0 or not tin or (not tout) or (tin == tout) or (not app):
                    return (None,)
                base_ix = getattr(base, 'interactions', None) or []
                if base_ix and _base_untrusted(base):
                    return (None,)
                return (self._cr_route(intent, state, snapshot, p, tin, tout, amt, app),)
                return _DR_UNSET
            p = tin = tout = None

            def _fr_24():

                def _dz89():
                    if cover_state.is_cross_chain(base):
                        return (None,)
                    if int(getattr(state, 'chain_id', 0) or 0) != 1:
                        return (None,)
                    if float(getattr(self, '_dyn_order_budget', None) or 99.0) < _MIN_BUDGET_S:
                        return (None,)
                    p = self._normalized_swap_params(intent, state)
                    tin = str(p.get('input_token', '') or '').lower()
                    tout = str(p.get('output_token', '') or '').lower()
                    return _DR_UNSET
                nonlocal p, tin, tout
                'Guards + params; delegates the route+build to _cr_route (both stay small regions).\n            Returns (cplan, tin, tout, amt, app, w3) or None to defer.'
                if cover_state.disabled('curve_refresh'):
                    return None
                _r_dz89 = _dz89()
                if _r_dz89 is not _DR_UNSET:
                    return _r_dz89[0]
                return _FR_UNSET
            _rv_24 = _fr_24()
            if _rv_24 is not _FR_UNSET:
                return _rv_24
            amt = int(p.get('input_amount', 0) or 0)
            _r_dz92 = _dz92()
            if _r_dz92 is not _DR_UNSET:
                return _r_dz92[0]

        def _cr_route(self, intent, state, snapshot, p, tin, tout, amt, app):
            """Live-Curve route lookup + built candidate plan (own region)."""

            def _dz91():
                _rv_25 = _fr_25()
                if _rv_25 is not _FR_UNSET:
                    return (_rv_25,)
                w = {'pool': pool, 'i': i, 'j': j, 'ex': 'u256_recv' if sig == 'u256' else 'i128_recv'}
                cplan = ExecutionPlan(intent_id=intent.app_id, interactions=_curve_ix(w, amt, tin, recipient), deadline=int(self._apex_deadline(snapshot)), nonce=state.nonce, metadata={'solver': 'curve-refresh', 'chain_id': 1})
                return ((cplan, tin, tout, amt, app, w3),)
                return _DR_UNSET
            w3 = self._get_web3(1)
            i = j = pool = recipient = sig = None

            def _fr_25():
                nonlocal i, j, pool, recipient, sig
                if w3 is None:
                    return None
                block = getattr(snapshot, 'block_number', None) if snapshot else None
                try:
                    block = int(block) if block else 'latest'
                except Exception:
                    block = 'latest'
                dy, pool, i, j, sig = _curve_best_live(w3, tin, tout, amt, block)
                if pool is None or dy <= 0:
                    return None
                recipient = self._apex_recipient(state, p)
                return _FR_UNSET
            _r_dz91 = _dz91()
            if _r_dz91 is not _DR_UNSET:
                return _r_dz91[0]

        def generate_plan(self, intent, state, snapshot=None):

            def _dz90():
                _rv_26 = _fr_26()
                if _rv_26 is not _FR_UNSET:
                    return (_rv_26,)
                if curve_out > co * (1 + cover_state.margin_bps(_MARGIN_BPS) / 10000):
                    logger.info('[curve_refresh] WIN champ=%d curve=%d %s->%s amt=%d', co, curve_out, tin[:10], tout[:10], amt)
                    return (cplan,)
                return _DR_UNSET
            base = super().generate_plan(intent, state, snapshot)
            try:
                cand = self._cr_candidate(intent, state, snapshot, base)
                if cand is None:
                    return base
                amt = co = cplan = curve_out = tin = tout = None

                def _fr_26():

                    def _dz88():
                        curve_out = viking_sim.sim_floor(w3, cplan, tin, tout, amt, app)
                        if curve_out is None or curve_out <= 0:
                            return (base,)
                        if not (getattr(base, 'interactions', None) or []):
                            co = 0
                        else:
                            co = viking_sim.sim_floor(w3, base, tin, tout, amt, app)
                            if co is None or co <= 0:
                                return (base,)
                        return (_FR_UNSET,)
                        return _DR_UNSET
                    nonlocal amt, co, cplan, curve_out, tin, tout
                    cplan, tin, tout, amt, app, w3 = cand
                    _r_dz88 = _dz88()
                    if _r_dz88 is not _DR_UNSET:
                        return _r_dz88[0]
                _r_dz90 = _dz90()
                if _r_dz90 is not _DR_UNSET:
                    return _r_dz90[0]
            except Exception:
                logger.exception('[curve_refresh] failed; deferring to champion')
            return base
    return CurveRefreshSolver