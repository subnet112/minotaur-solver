"""Exact Blueguider finalist floor plus reviewed blind-spot covers."""

from __future__ import annotations

from _incoming_blueguider_entry import SOLVER_CLASS as _IncomingBase
from base_q87_edge import maybe_q87_plan
from base_qbfbd_edge import maybe_qbfbd_plan


class ChainKillerSolver(_IncomingBase):
    """Preserve the incoming finalist and fill two independently replayed zeros."""

    def metadata(self):
        metadata = super().metadata()
        try:
            import dataclasses

            if dataclasses.is_dataclass(metadata):
                return dataclasses.replace(
                    metadata,
                    name="chain-killer",
                    version="148.0.0",
                    author="meridian",
                )
        except Exception:
            pass
        replace = getattr(metadata, "_replace", None)
        if callable(replace):
            try:
                return replace(
                    name="chain-killer",
                    version="148.0.0",
                    author="meridian",
                )
            except Exception:
                pass
        return metadata

    def generate_plan(self, intent, state, snapshot=None):
        for handler in (maybe_qbfbd_plan, maybe_q87_plan):
            plan = handler(self, intent, state)
            if plan is not None and getattr(plan, "interactions", None):
                return plan
        return super().generate_plan(intent, state, snapshot)


SOLVER_CLASS = ChainKillerSolver
