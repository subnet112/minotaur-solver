"""Hydra-compatible Blueguider floor plus reviewed performance covers."""

from __future__ import annotations

from _incoming_blueguider_entry import SOLVER_CLASS as _IncomingBase
from eth_q058_uniswap_v2_edge import maybe_q058_plan
from base_qdd_kyber_edge import maybe_qdd_kyber_plan
from base_q87_edge import maybe_q87_plan
from base_qbfbd_edge import maybe_qbfbd_plan
from base_uniswap_v2_edges import maybe_base_uniswap_v2_plan


class ChainKillerSolver(_IncomingBase):
    """Preserve the champion and add only independently replayed routes."""

    def metadata(self):
        metadata = super().metadata()
        try:
            import dataclasses

            if dataclasses.is_dataclass(metadata):
                return dataclasses.replace(
                    metadata,
                    name="chain-killer",
                    version="151.0.0",
                    author="meridian",
                )
        except Exception:
            pass
        replace = getattr(metadata, "_replace", None)
        if callable(replace):
            try:
                return replace(
                    name="chain-killer",
                    version="151.0.0",
                    author="meridian",
                )
            except Exception:
                pass
        return metadata

    def generate_plan(self, intent, state, snapshot=None):
        for handler in (
            maybe_q058_plan,
            maybe_qdd_kyber_plan,
            maybe_qbfbd_plan,
            maybe_q87_plan,
            maybe_base_uniswap_v2_plan,
        ):
            plan = handler(self, intent, state)
            if plan is not None and getattr(plan, "interactions", None):
                return plan
        return super().generate_plan(intent, state, snapshot)


SOLVER_CLASS = ChainKillerSolver
