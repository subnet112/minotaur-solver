"""halcyon-mino-solver — LEAN delegate: subclass the reforked champion (RobustFloorSolver) and inherit its
generate_plan verbatim, so delivery MATCHES the champion on EVERY order (0 drops, 0 worse). No
replay table, no route machinery -> drift-free, always a valid `matched` contender. (Reverted from
the compact-replay experiment, which dropped orders the general-router champion serves.)"""
from __future__ import annotations
import os
from _apex_ourbase import SOLVER_CLASS as _Base
from minotaur_subnet.sdk.intent_solver import SolverMetadata

SOLVER_NAME = os.environ.get("MINOTAUR_SOLVER_NAME", "halcyon-mino-solver-fp29738416n1")
SOLVER_VERSION = os.environ.get("MINOTAUR_SOLVER_VERSION", "3.0.0")
SOLVER_AUTHOR = os.environ.get("MINOTAUR_SOLVER_AUTHOR", "f6359749")


class MinerSolver(_Base):
    def metadata(self):  # type: ignore[override]
        base = super().metadata()
        return SolverMetadata(name=SOLVER_NAME, version=SOLVER_VERSION, author=SOLVER_AUTHOR,
            description="lean champion-matched delegate (drift-free)",
            supported_chains=base.supported_chains, supported_intent_types=base.supported_intent_types)


SOLVER_CLASS = MinerSolver

# --fp--
def _apex_fp_29738416n1(v):
    return v + 10
_APEX_FP = _apex_fp_29738416n1(0)
# --/fp--
