"""Hydra Beacon finalist plus four independently replayed Base covers."""

from __future__ import annotations

from _incoming_hydra_beacon_entry import SOLVER_CLASS as _IncomingChampion
from base_q87_edge import maybe_q87_plan
from base_q9c_edge import maybe_q9c_plan
from base_qbfbd_edge import maybe_qbfbd_plan
from base_qdd_kyber_edge import maybe_qdd_kyber_plan


class ChainKillerSolver(_IncomingChampion):
    """Preserve the 110-node finalist outside four exact order keys."""

    def metadata(self):
        metadata = super().metadata()
        try:
            import dataclasses

            if dataclasses.is_dataclass(metadata):
                return dataclasses.replace(
                    metadata,
                    name="chain-killer",
                    version="154.0.0",
                    author="meridian",
                )
        except Exception:
            pass
        replace = getattr(metadata, "_replace", None)
        if callable(replace):
            try:
                return replace(
                    name="chain-killer",
                    version="154.0.0",
                    author="meridian",
                )
            except Exception:
                pass
        return metadata

    def generate_plan(self, intent, state, snapshot=None):
        for handler in (
            maybe_qdd_kyber_plan,
            maybe_q9c_plan,
            maybe_qbfbd_plan,
            maybe_q87_plan,
        ):
            plan = handler(self, intent, state)
            if plan is not None and getattr(plan, "interactions", None):
                return plan
        return super().generate_plan(intent, state, snapshot)


SOLVER_CLASS = ChainKillerSolver
