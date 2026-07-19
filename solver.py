"""chain-killer v138: pymsno champion floor plus proven route edges."""

from __future__ import annotations

from _incoming_b034_floor import SOLVER_CLASS as _ChampionSolver
from base_q397_edge import maybe_q397_plan
from base_q45dd_edge import maybe_q45dd_plan
from base_q87_edge import maybe_q87_plan
from base_qbfbd_edge import maybe_qbfbd_plan
from bat_wquil_edge import maybe_qaa9_plan
from minotaur_subnet.sdk.intent_solver import SolverMetadata
from pyusd_pepe_edge import maybe_qd41_plan


def _exact_plan(solver, intent, state):
    handlers = (
        maybe_q397_plan,
        maybe_q45dd_plan,
        maybe_q87_plan,
        maybe_qbfbd_plan,
        maybe_qd41_plan,
        maybe_qaa9_plan,
    )
    for handler in handlers:
        plan = handler(solver, intent, state)
        if plan is not None:
            return plan
    return None


class ChainKillerSolver(_ChampionSolver):
    """Preserve the incoming champion except on replay-proven exact keys."""

    def metadata(self):
        base = super().metadata()
        return SolverMetadata(
            name="chain-killer",
            version="138.0.0",
            author="meridian",
            description="pymsno champion floor plus six replay-proven routes",
            supported_chains=base.supported_chains,
            supported_intent_types=base.supported_intent_types,
        )

    def generate_plan(self, intent, state, snapshot=None):
        plan = _exact_plan(self, intent, state)
        if plan is not None:
            return plan
        return super().generate_plan(intent, state, snapshot)


SOLVER_CLASS = ChainKillerSolver
