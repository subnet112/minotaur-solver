from __future__ import annotations
_DR_UNSET = object()
import logging
logger = logging.getLogger(__name__)
_BRAND = 'dataCenter430'
_MARGIN_BPS = 10
_MIN_BUDGET_S = 8.0

def wrap(base_cls):
    from solver import _GORAN_OVERRIDES, _goran_key, _McSolver
    import viking_sim
    import cover_state

    class RefreshOverridesSolver(base_cls):
        """Champion + live-requote of its own decayed override keys (fail-closed)."""

        def metadata(self):
            m = super().metadata()
            try:
                m.name = _BRAND
            except Exception:
                try:
                    import dataclasses as _dc
                    if _dc.is_dataclass(m):
                        return _dc.replace(m, name=_BRAND)
                except Exception:
                    pass
            return m

        def _order5(self, state):
            k = _goran_key(state)
            if not k or k not in _GORAN_OVERRIDES:
                return None
            cid, con, tin, tout, amt = k.split('|')
            return (int(cid), con, tin, tout, int(amt))

        def generate_plan(self, intent, state, snapshot=None):

            def _dz23():
                if o is None:
                    return (base,)
                if float(getattr(self, '_dyn_order_budget', None) or 99.0) < _MIN_BUDGET_S:
                    return (base,)
                return _DR_UNSET

            def _dz22():
                if fresh is None or not getattr(fresh, 'interactions', None):
                    return (base,)
                b_out = viking_sim.sim_floor(w3, fresh, tin, tout, amt, con)
                if b_out is None:
                    return (base,)
                if b_out > f_out * (1 + cover_state.margin_bps(_MARGIN_BPS) / 10000):
                    logger.info('[refresh] override key requote WIN frozen=%d fresh=%d %s->%s amt=%d', f_out, b_out, tin[:10], tout[:10], amt)
                    return (fresh,)
                return _DR_UNSET
            base = super().generate_plan(intent, state, snapshot)
            try:
                if cover_state.disabled('refresh'):
                    return base
                o = self._order5(state)
                _r_dz23 = _dz23()
                if _r_dz23 is not _DR_UNSET:
                    return _r_dz23[0]
                cid, con, tin, tout, amt = o
                w3 = self._get_web3(cid)
                if w3 is None:
                    return base
                f_out = viking_sim.sim_floor(w3, base, tin, tout, amt, con)
                if f_out is None:
                    return base
                fresh = _McSolver.generate_plan(self, intent, state, snapshot)
                _r_dz22 = _dz22()
                if _r_dz22 is not _DR_UNSET:
                    return _r_dz22[0]
            except Exception:
                logger.exception('[refresh] gate failed; deferring to champion')
            return base
    return RefreshOverridesSolver