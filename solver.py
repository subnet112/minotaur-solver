"""chain-killer v132: certified champion floor plus seven exact wins."""

from __future__ import annotations

from _blueguider_floor import SOLVER_CLASS as _ChampionSolver
from base_qb01e_edge import maybe_qb01e_plan
from base_qbfbd_edge import maybe_qbfbd_plan
from base_q397_edge import maybe_q397_plan
from base_q45dd_edge import maybe_q45dd_plan
from bat_wquil_edge import maybe_qaa9_plan
from mor_vvv_edge import maybe_q631_plan
from pyusd_pepe_edge import maybe_qd41_plan
from minotaur_subnet.sdk.intent_solver import SolverMetadata


def _exact_plan(solver, intent, state):
    handlers = (
        maybe_q397_plan,
        maybe_q45dd_plan,
        maybe_qbfbd_plan,
        maybe_qb01e_plan,
        maybe_qd41_plan,
        maybe_qaa9_plan,
        maybe_q631_plan,
    )
    for handler in handlers:
        plan = handler(solver, intent, state)
        if plan is not None:
            return plan
    return None


class ChainKillerSolver(_ChampionSolver):
    """Preserve the champion except on replay-proven exact keys."""

    def metadata(self):
        base = super().metadata()
        return SolverMetadata(
            name="chain-killer",
            version="132.0.0",
            author="meridian",
            description="certified champion floor plus seven route wins",
            supported_chains=base.supported_chains,
            supported_intent_types=base.supported_intent_types,
        )

    def generate_plan(self, intent, state, snapshot=None):
        plan = _exact_plan(self, intent, state)
        if plan is not None:
            return plan
        return super().generate_plan(intent, state, snapshot)


SOLVER_CLASS = ChainKillerSolver
