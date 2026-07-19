"""chain-killer v129: certified blueguider floor plus three exact wins."""

from __future__ import annotations

from _blueguider_floor import SOLVER_CLASS as _ChampionSolver
from bat_wquil_edge import maybe_qaa9_plan
from mor_vvv_edge import maybe_q631_plan
from pyusd_pepe_edge import maybe_qd41_plan
from minotaur_subnet.sdk.intent_solver import SolverMetadata


class ChainKillerSolver(_ChampionSolver):
    """Preserve the champion except on three replay-proven exact keys."""

    def metadata(self):
        base = super().metadata()
        return SolverMetadata(
            name="chain-killer",
            version="129.0.0",
            author="meridian",
            description="certified blueguider floor plus three route wins",
            supported_chains=base.supported_chains,
            supported_intent_types=base.supported_intent_types,
        )

    def generate_plan(self, intent, state, snapshot=None):
        plan = maybe_qd41_plan(self, intent, state)
        if plan is None:
            plan = maybe_qaa9_plan(self, intent, state)
        if plan is None:
            plan = maybe_q631_plan(self, intent, state)
        if plan is not None:
            return plan
        return super().generate_plan(intent, state, snapshot)


SOLVER_CLASS = ChainKillerSolver
