"""Bridge the inherited benchmark governor across short-circuiting wrappers.

Several champion layers can return before the deeply nested governor's
``generate_plan`` executes.  In that case ``_bm_done`` never advances and the
per-order budget remains unset.  This outermost wrapper restores the governor's
bookkeeping without changing routing while the solver is not benchmark-armed.
"""
from __future__ import annotations


def install(base_cls):
    class _PacingBridge(base_cls):
        _pacing_bridge_on = True

        @staticmethod
        def _pb_nonempty(plan) -> bool:
            try:
                return bool(getattr(plan, "interactions", None))
            except Exception:
                return False

        def _pb_prepare(self, intent, state, snapshot, done: int):
            """Set the budget visible to upper layers; return a safe fast plan or None."""
            import time

            total = int(getattr(self, "_bm_total", 0) or 0)
            started = getattr(self, "_bm_t0", None)
            if not started or total <= 0:
                return None
            remaining_time = float(getattr(self, "_RUN_BUDGET_S", 0.0) or 0.0) \
                - (time.monotonic() - float(started))
            remaining_orders = max(1, total - done)
            fast_below = float(getattr(self, "_FAST_BELOW_S", 0.0) or 0.0)
            self._dyn_order_budget = max(4.0, remaining_time / remaining_orders)
            if remaining_time / remaining_orders >= fast_below:
                return None
            fast = getattr(self, "_fast_plan", None)
            if not callable(fast):
                return None
            try:
                plan = fast(intent, state, snapshot)
            except Exception:
                return None
            return plan if self._pb_nonempty(plan) else None

        def generate_plan(self, intent, state, snapshot=None):
            armed = bool(getattr(self, "_bm_t0", None)) \
                and int(getattr(self, "_bm_total", 0) or 0) > 0
            before = int(getattr(self, "_bm_done", 0) or 0)
            if armed:
                fast = self._pb_prepare(intent, state, snapshot, before)
                if fast is not None:
                    self._bm_done = before + 1
                    return fast
            try:
                return super().generate_plan(intent, state, snapshot)
            finally:
                # If no deeper layer reached the inherited governor (the observed
                # vestigial path), consume exactly one order here.  If it did reach
                # it, preserve the deeper layer's count and avoid double-counting.
                if armed and int(getattr(self, "_bm_done", 0) or 0) <= before:
                    self._bm_done = before + 1

    return _PacingBridge
