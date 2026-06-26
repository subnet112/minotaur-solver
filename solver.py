"""Miner solver for Subnet 112 (Minotaur).

Strategy: inherit the full upstream ``BaselineSwapSolver`` (Uniswap V3 +
Aerodrome Slipstream routing, multi-hop, RPC pool discovery) and ADD a venue
it doesn't cover — **Aerodrome v2** (the original volatile/stable AMM that holds
the deepest Base liquidity for stable pairs and ve(3,3)-native tokens).

The override is strictly additive: for each order it computes Aerodrome v2's
exact on-chain quote and the baseline's own quote, and only emits the v2 plan
when v2 delivers MORE output. So it can never score worse than the baseline —
it ties everywhere the baseline already wins, and *rescues* orders the baseline
can't route at all (no Uniswap V3 / Slipstream pool -> baseline scores ~0,
v2 fills them). That asymmetry is what can clear the 5% dethrone margin.

Fork-verified on Base: v2 quote == executed output, no reverts, beats the
baseline on stable pairs and AERO-style tokens, defers on WETH/USDC.

NOTE: no ``from __future__ import annotations`` — the harness loads this via
``exec_module`` without registering it in ``sys.modules`` and PEP 563 string
annotations break a module-level dataclass under that loader.
"""

import logging
import os

from strategies.dex_aggregator.baseline_solver import BaselineSwapSolver
from strategies.dex_aggregator.aerodrome_v2 import (
    aerodrome_v2_supported,
    best_v2_quote,
    build_v2_plan,
)
from strategies.dex_aggregator.quoter import NoRouteError, QuoterUnavailable
from minotaur_subnet.sdk.intent_solver import SolverMetadata
from minotaur_subnet.v3.manifest import normalize_swap_intent_params

logger = logging.getLogger(__name__)

SOLVER_NAME = os.environ.get("MINOTAUR_SOLVER_NAME", "aerodrome-v2-edge")
SOLVER_VERSION = os.environ.get("MINOTAUR_SOLVER_VERSION", "1.0.0")
SOLVER_AUTHOR = os.environ.get("MINOTAUR_SOLVER_AUTHOR", "miner")

_ZERO = "0x0000000000000000000000000000000000000000"
_NATIVE = {"", _ZERO, "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"}


def _state_params(state):
    typed = getattr(state, "typed_context", None)
    if typed is not None:
        raw = getattr(typed, "raw_params", None)
        if isinstance(raw, dict):
            return raw
    return state.raw_params_view()


def _is_native(token):
    return (token or "").strip().lower() in _NATIVE


class MinerSolver(BaselineSwapSolver):
    """Baseline cross-DEX router + Aerodrome v2 venue (strictly additive)."""

    def generate_plan(self, intent, state, snapshot=None):
        """Prefer an Aerodrome v2 plan when it strictly beats the baseline."""
        try:
            plan = self._aerodrome_v2_override(intent, state, snapshot)
            if plan is not None:
                return plan
        except Exception as exc:  # never regress: fall back to the proven baseline
            logger.warning("aerodrome_v2 override failed (%s); using baseline", exc)
        return super().generate_plan(intent, state, snapshot)

    def _aerodrome_v2_override(self, intent, state, snapshot):
        """Return a v2 ExecutionPlan only when it out-delivers the baseline."""
        chain_id = state.chain_id or (snapshot.chain_id if snapshot else 8453)
        if not aerodrome_v2_supported(chain_id):
            return None

        params = normalize_swap_intent_params(
            _state_params(state),
            receiver_default=state.contract_address or state.owner,
        )
        token_in = params.get("input_token", "")
        token_out = params.get("output_token", "")
        amount_in = int(params.get("input_amount") or 0)
        # Only plain ERC-20 same-chain swaps; native input / odd intents -> baseline.
        if not token_in or not token_out or amount_in <= 0 or _is_native(token_in):
            return None

        w3 = self._get_web3(chain_id)
        if w3 is None:
            return None

        v2_out, v2_route = best_v2_quote(w3, chain_id, token_in, token_out, amount_in)
        if v2_route is None or v2_out <= 0:
            return None  # no v2 pool for this pair

        # Baseline's own best output for this order. Only a GENUINE no-route
        # (NoRouteError / QuoterUnavailable) counts as 0 — that's the order we
        # rescue. A transient/unknown error must NOT force v2 (it could be a
        # pair the baseline actually wins), so we defer to the proven baseline.
        try:
            base_out = int(super().quote(intent, state, snapshot).estimated_output)
        except (NoRouteError, QuoterUnavailable):
            base_out = 0
        except Exception as exc:
            logger.warning("baseline quote errored (%s); deferring to baseline", exc)
            return None

        if v2_out <= base_out:
            return None  # baseline ties or wins -> defer, never regress

        recipient = state.contract_address or params.get("receiver") or state.owner
        min_out = int(params.get("min_output_amount") or 0)
        logger.info(
            "aerodrome_v2 wins %s->%s: %d > baseline %d (%s pool)",
            token_in, token_out, v2_out, base_out,
            "stable" if v2_route[2] else "volatile",
        )
        return build_v2_plan(
            intent.app_id, chain_id, token_in, v2_route,
            amount_in, min_out, recipient, state.nonce,
        )

    def metadata(self) -> SolverMetadata:
        base = super().metadata()
        return SolverMetadata(
            name=SOLVER_NAME,
            version=SOLVER_VERSION,
            author=SOLVER_AUTHOR,
            description="Baseline cross-DEX router + Aerodrome v2 (stable/volatile) venue",
            supported_chains=base.supported_chains,
            supported_intent_types=base.supported_intent_types,
        )


SOLVER_CLASS = MinerSolver
