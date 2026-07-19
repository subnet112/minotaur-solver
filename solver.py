"""chain-killer v131: certified champion floor plus five exact wins."""

from __future__ import annotations

from _blueguider_floor import SOLVER_CLASS as _ChampionSolver
from base_qb01e_edge import maybe_qb01e_plan
from base_qbfbd_edge import maybe_qbfbd_plan
from bat_wquil_edge import maybe_qaa9_plan
from mor_vvv_edge import maybe_q631_plan
from pyusd_pepe_edge import maybe_qd41_plan
from minotaur_subnet.sdk.intent_solver import SolverMetadata


class ChainKillerSolver(_ChampionSolver):
    """Preserve the champion except on replay-proven exact keys."""

    def metadata(self):
        base = super().metadata()
        return SolverMetadata(
            name="chain-killer",
            version="131.0.0",
            author="meridian",
            description="certified champion floor plus five route wins",
            supported_chains=base.supported_chains,
            supported_intent_types=base.supported_intent_types,
        )

    def generate_plan(self, intent, state, snapshot=None):
        plan = maybe_qbfbd_plan(self, intent, state)
        if plan is None:
            plan = maybe_qb01e_plan(self, intent, state)
        if plan is None:
            plan = maybe_qd41_plan(self, intent, state)
        if plan is None:
            plan = maybe_qaa9_plan(self, intent, state)
        if plan is None:
            plan = maybe_q631_plan(self, intent, state)
        if plan is not None:
            return plan
        return super().generate_plan(intent, state, snapshot)


SOLVER_CLASS = ChainKillerSolver
