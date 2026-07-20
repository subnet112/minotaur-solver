"""chain-killer v139: Hydra discovery floor plus six proven route edges."""

from __future__ import annotations

from _hydra_5b345_floor import SOLVER_CLASS as _HydraSolver
from base_q397_edge import maybe_q397_plan
from base_q45dd_edge import maybe_q45dd_plan
from base_q87_edge import maybe_q87_plan
from base_qbfbd_edge import maybe_qbfbd_plan
from bat_wquil_edge import maybe_qaa9_plan
from minotaur_subnet.sdk.intent_solver import SolverMetadata
from pyusd_pepe_edge import maybe_qd41_plan
from usdt_a9d4_edge import maybe_qa9d4_plan


_EDGE_HANDLERS = (
    maybe_qa9d4_plan,
    maybe_q397_plan,
    maybe_q45dd_plan,
    maybe_q87_plan,
    maybe_qbfbd_plan,
    maybe_qd41_plan,
    maybe_qaa9_plan,
)


class ChainKillerSolver(_HydraSolver):
    """Preserve Hydra exactly except on replay-proven exact order keys."""

    def metadata(self):
        base = super().metadata()
        return SolverMetadata(
            name="chain-killer",
            version="139.0.0",
            author="meridian",
            description="Hydra discovery floor plus seven replay-proven routes",
            supported_chains=base.supported_chains,
            supported_intent_types=base.supported_intent_types,
        )

    def generate_plan(self, intent, state, snapshot=None):
        for handler in _EDGE_HANDLERS:
            plan = handler(self, intent, state)
            if plan is not None:
                return plan
        return super().generate_plan(intent, state, snapshot)


SOLVER_CLASS = ChainKillerSolver
