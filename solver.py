"""Current robust-floor champion plus two exact-scoped measured routes."""

from __future__ import annotations

from eth_blindspot_edge import maybe_q010_plan as _chain_killer_q010
from minotaur_subnet.sdk.intent_solver import SolverMetadata
from mor_vvv_edge import maybe_q631_plan as _chain_killer_q631
from robust_floor_base import SOLVER_CLASS as _ChampionSolver


class ChainKillerSolver(_ChampionSolver):
    def metadata(self):
        base = super().metadata()
        return SolverMetadata(
            name="chain-killer",
            version="120.0.0",
            author="meridian",
            description=(
                "robust-floor-eth-1 champion plus measured q631/q010 coverage"
            ),
            supported_chains=base.supported_chains,
            supported_intent_types=base.supported_intent_types,
        )

    def generate_plan(self, intent, state, snapshot=None):
        q631 = _chain_killer_q631(self, intent, state)
        if q631 is not None:
            return q631
        q010 = _chain_killer_q010(self, intent, state)
        if q010 is not None:
            return q010
        return super().generate_plan(intent, state, snapshot)


SOLVER_CLASS = ChainKillerSolver
