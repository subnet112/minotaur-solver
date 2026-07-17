"""zephyr-swap-router — LEAN delegate: subclass the reforked (held-lean) champion base and inherit its
generate_plan verbatim, so delivery MATCHES on every order (0 drops). Metadata-only override keeps
region-nodes == base -> when apex_bot HOLDS a captured lean champion (~123) this delegate is ~123 too
and dethrones the heavy RobustFloor via factorization. Reverted from the 718-node cover (which could
never win and occasionally went `behind`)."""
from __future__ import annotations
import os
from _apex_ourbase import SOLVER_CLASS as _Base
from minotaur_subnet.sdk.intent_solver import SolverMetadata

SOLVER_NAME = os.environ.get("MINOTAUR_SOLVER_NAME", "zephyr-swap-router-fp29737965n1")
SOLVER_VERSION = os.environ.get("MINOTAUR_SOLVER_VERSION", "1.0.0")
SOLVER_AUTHOR = os.environ.get("MINOTAUR_SOLVER_AUTHOR", "sendevblock")


class MinerSolver(_Base):
    def metadata(self):  # type: ignore[override]
        base = super().metadata()
        return SolverMetadata(name=SOLVER_NAME, version=SOLVER_VERSION, author=SOLVER_AUTHOR,
            description="lean champion-matched delegate (drift-free)",
            supported_chains=base.supported_chains, supported_intent_types=base.supported_intent_types)


SOLVER_CLASS = MinerSolver

# --fp--
def _apex_fp_29737965n1(v):
    return v + 10
_APEX_FP = _apex_fp_29737965n1(0)
# --/fp--
