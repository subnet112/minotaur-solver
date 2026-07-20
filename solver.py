"""Current Minotaur champion plus one independently replayed Base cover."""

from __future__ import annotations

from _incoming_min_router_entry import SOLVER_CLASS as _IncomingChampion
from base_qdd_kyber_edge import maybe_qdd_kyber_plan


class ChainKillerSolver(_IncomingChampion):
    """Preserve the incumbent everywhere except the proven qdd blind spot."""

    def metadata(self):
        metadata = super().metadata()
        try:
            import dataclasses

            if dataclasses.is_dataclass(metadata):
                return dataclasses.replace(
                    metadata,
                    name="chain-killer",
                    version="152.0.0",
                    author="meridian",
                )
        except Exception:
            pass
        replace = getattr(metadata, "_replace", None)
        if callable(replace):
            try:
                return replace(
                    name="chain-killer",
                    version="152.0.0",
                    author="meridian",
                )
            except Exception:
                pass
        return metadata

    def generate_plan(self, intent, state, snapshot=None):
        plan = maybe_qdd_kyber_plan(self, intent, state)
        if plan is not None and getattr(plan, "interactions", None):
            return plan
        return super().generate_plan(intent, state, snapshot)


SOLVER_CLASS = ChainKillerSolver
