"""Current champion floor plus exact-scoped measured route improvements."""

from __future__ import annotations

from eth_blindspot_edge import maybe_q010_plan as _chain_killer_q010
from eth_qdba_edge import maybe_qdba_plan as _chain_killer_qdba
from fresh_base_edge import maybe_fresh_base_plan as _chain_killer_fresh_base
from minotaur_subnet.sdk.intent_solver import SolverMetadata
from mor_vvv_edge import maybe_q631_plan as _chain_killer_q631
from robust_floor_base import SOLVER_CLASS as _ChampionSolver


class ChainKillerSolver(_ChampionSolver):
    def metadata(self):
        base = super().metadata()
        return SolverMetadata(
            name="chain-killer",
            version="123.0.0",
            author="meridian",
            description=(
                "champion floor plus measured q631/q010/qdba and fresh Base coverage"
            ),
            supported_chains=base.supported_chains,
            supported_intent_types=base.supported_intent_types,
        )

    def generate_plan(self, intent, state, snapshot=None):
        fresh_base = _chain_killer_fresh_base(self, intent, state)
        if fresh_base is not None:
            return fresh_base
        q631 = _chain_killer_q631(self, intent, state)
        if q631 is not None:
            return q631
        q010 = _chain_killer_q010(self, intent, state)
        if q010 is not None:
            return q010
        qdba = _chain_killer_qdba(self, intent, state)
        if qdba is not None:
            return qdba
        return super().generate_plan(intent, state, snapshot)


SOLVER_CLASS = ChainKillerSolver
