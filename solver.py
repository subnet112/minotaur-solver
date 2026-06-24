"""Reference solver for Subnet 112 (Minotaur).

This is the file miners fork to ship their own strategy. The validator
harness imports ``SOLVER_CLASS`` from this module and calls
``generate_plan(intent, state, snapshot)`` on every order.

Default behaviour comes from ``BaselineSwapSolver`` in
``common/baseline_solver.py``, which on Base routes across both
Uniswap V3 and Aerodrome Slipstream pools, picks the best output
across DEXes, and falls back to multi-hop through common intermediary
tokens (WETH, USDC) when no direct pool wins.

To beat that baseline, override ``generate_plan`` (or any other method)
on ``MinerSolver`` below — for example by adding new DEXes, splitting a
trade across pools, learning routes from past orders, or pre-computing
plans on a faster path than RPC discovery allows.

The validator's screening pipeline builds this repo as a Docker image
``FROM ghcr.io/subnet112/solver-base:v1`` and runs the runner harness,
which loads ``SOLVER_CLASS`` from ``/app/solver/solver.py``.
"""

from __future__ import annotations

import logging
import os

from strategies.dex_aggregator.baseline_solver import BaselineSwapSolver
from minotaur_subnet.sdk.intent_solver import SolverMetadata

logger = logging.getLogger(__name__)


SOLVER_NAME = os.environ.get("MINOTAUR_SOLVER_NAME", "reference-solver")
SOLVER_VERSION = os.environ.get("MINOTAUR_SOLVER_VERSION", "1.0.0")
SOLVER_AUTHOR = os.environ.get("MINOTAUR_SOLVER_AUTHOR", "miner")


class MinerSolver(BaselineSwapSolver):
    """Reference solver — fork this repo and edit this class to ship
    your own strategy. The default delegates entirely to the upstream
    ``BaselineSwapSolver``, which already does cross-DEX routing
    (Uniswap V3 + Aerodrome Slipstream on Base) and multi-hop fallback.
    """

    def metadata(self) -> SolverMetadata:
        base = super().metadata()
        return SolverMetadata(
            name=SOLVER_NAME,
            version=SOLVER_VERSION,
            author=SOLVER_AUTHOR,
            description=base.description,
            supported_chains=base.supported_chains,
            supported_intent_types=base.supported_intent_types,
        )


SOLVER_CLASS = MinerSolver

# --- Tier-C observe-test candidate ---
# Distinct commit of the reference baseline solver, submitted to exercise the
# validator screening + content-addressed image push + benchmark pipeline on
# the live fleet (observe-only; champion adoption remains frozen).
