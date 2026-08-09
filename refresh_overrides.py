from __future__ import annotations
import logging
logger = logging.getLogger(__name__)
_BRAND = 'dataCenter_kg29771551n1'
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
            base = super().generate_plan(intent, state, snapshot)
            try:
                if cover_state.disabled('refresh'):
                    return base
                if cover_state.is_cross_chain(base) or cover_state.base_untrusted(base):
                    return base
                o = self._order5(state)
                if o is None:
                    return base
                if float(getattr(self, '_dyn_order_budget', None) or 99.0) < _MIN_BUDGET_S:
                    return base
                cid, con, tin, tout, amt = o
                w3 = self._get_web3(cid)
                if w3 is None:
                    return base
                served = self._refresh_decide(w3, base, intent, state, snapshot, con, tin, tout, amt)
                if served is not None:
                    return served
            except Exception:
                logger.exception('[refresh] gate failed; deferring to champion')
            return base

        def _refresh_decide(self, w3, base, intent, state, snapshot, con, tin, tout, amt):
            """Sim frozen champion vs fresh requote; serve fresh iff it strictly out-delivers
            (esp. frozen==0 revert). Own region for factorization. None -> defer to champion."""
            f_out = viking_sim.sim_floor(w3, base, tin, tout, amt, con)
            if f_out is None:
                return None
            fresh = _McSolver.generate_plan(self, intent, state, snapshot)
            if fresh is None or not getattr(fresh, 'interactions', None):
                return None
            b_out = viking_sim.sim_floor(w3, fresh, tin, tout, amt, con)
            if b_out is None:
                return None
            if b_out > f_out * (1 + cover_state.margin_bps(_MARGIN_BPS) / 10000):
                logger.info('[refresh] override key requote WIN frozen=%d fresh=%d %s->%s amt=%d', f_out, b_out, tin[:10], tout[:10], amt)
                return fresh
            return None
    return RefreshOverridesSolver