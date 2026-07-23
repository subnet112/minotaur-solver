
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)
_BRAND = "dataCenter430"  # coin our OWN solver name (not a copycat of the forked champion)
_MARGIN_BPS = 10       # fresh must beat frozen by >0.1% (the scorer's own noise band)
_MIN_BUDGET_S = 8.0    # our extra sims+requote cost; below this, DEFER so we never
                       # trip the champion's governor into a self-inflicted drop


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
            cid, con, tin, tout, amt = k.split("|")
            return int(cid), con, tin, tout, int(amt)

        def generate_plan(self, intent, state, snapshot=None):
            base = super().generate_plan(intent, state, snapshot)  # champion (frozen on override keys)
            try:
                if cover_state.disabled("refresh"):
                    return base
                o = self._order5(state)
                if o is None:
                    return base                      # not an override key -> untouched
                if float(getattr(self, "_dyn_order_budget", None) or 99.0) < _MIN_BUDGET_S:
                    return base                      # tight budget -> defer (no self-inflicted drop)
                cid, con, tin, tout, amt = o
                w3 = self._get_web3(cid)
                if w3 is None:
                    return base
                f_out = viking_sim.sim_floor(w3, base, tin, tout, amt, con)
                if f_out is None:
                    return base                      # can't verify champion delivery -> defer
                # fresh live route = champion engine WITHOUT the frozen override layer
                fresh = _McSolver.generate_plan(self, intent, state, snapshot)
                if fresh is None or not getattr(fresh, "interactions", None):
                    return base
                b_out = viking_sim.sim_floor(w3, fresh, tin, tout, amt, con)
                if b_out is None:
                    return base
                if b_out > f_out * (1 + cover_state.margin_bps(_MARGIN_BPS) / 10000):
                    logger.info("[refresh] override key requote WIN frozen=%d fresh=%d %s->%s amt=%d",
                                f_out, b_out, tin[:10], tout[:10], amt)
                    return fresh                     # strictly out-delivers (esp. frozen==0 revert)
            except Exception:
                logger.exception("[refresh] gate failed; deferring to champion")
            return base

    return RefreshOverridesSolver
