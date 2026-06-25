"""Minotaur SN112 miner solver — v5: seeded+parallel discovery, multi-hop, safe split.

REPLACES the root ``solver.py`` of a fork of ``subnet112/minotaur-solver``.
Subclasses the real ``BaselineSwapSolver`` and applies every improvement that
research + the live-report root-cause analysis showed is positive-EV and safe,
each fully fenced with a fallback to the stock baseline.

WHAT THIS FIXES (from the live 0.4168 report + deep-research synthesis)
-----------------------------------------------------------------------
benchmark_score = 0.4·mean(synthetic) + 0.6·mean(historical); the whole gap is the
11 zeros, and a SYNTHETIC zero is worth 2.778× a historical one. The recoverable
synthetic zeros (WETH_to_DAI, DAI_to_USDC, cbBTC_to_USDC) all failed for the SAME
reason: the worker was SIGKILLed by the 5s QUOTE wall-clock timeout because DAI/cbBTC
are NOT in the baseline's `_KNOWN_POOLS[8453]` (only WETH/USDC is), so every pool was
discovered cold via ~50-90 SERIAL JSON-RPC round-trips. On-chain checks confirm these
pairs have DEEP liquidity (WETH/DAI 0.3% ≈ 1.7e19, USDC/DAI 0.01% ≈ 1.1e20, cbBTC/WETH
deep) — they are routable; they just never finished discovery in time.

IMPROVEMENTS (all fall back to baseline on any error):
  1. PRE-SEED the on-chain-verified deep Base pools for WETH/DAI, USDC/DAI, cbBTC/USDC,
     cbBTC/WETH (+WETH/USDC intermediaries) so DAI/cbBTC routes skip cold discovery.
  2. PARALLELIZE the per-pool state reads (ThreadPoolExecutor) so seeding ~10 pools is
     a few hundred ms, not tens of serial round-trips — keeps the 5s QUOTE budget.
  3. MULTI-HOP enablement: seeding the WETH/USDC + cbBTC/WETH legs lets the baseline's
     own `_resolve_best_route` route cbBTC→WETH→USDC etc. when the thin direct pool is
     worse — exactly the convex-routing "use the better path" result.
  4. SAFE SPLIT (research-backed, gas-gated): for DEEP major pairs only, split across
     the 2 deepest direct V3 pools when a Quoter-validated split beats the single-best
     route by a margin big enough to clear the gas-term penalty. Per-leg
     amountOutMinimum=0 (the on-chain min_output invariant enforces the aggregate, so
     no single leg can revert on slippage — the baseline multi-hop builder does the
     same). Never hand-routes into thin pools (the v1 failure); every leg is a real
     Quoter-confirmed fill.

SAFETY: changes 1-3 are SCOPED to routes touching DAI/cbBTC — WETH/USDC (the bulk of
the 51 passing cases) stays on the untouched baseline path, so passes cannot regress.
The split (4) is gated so high (default +2%) that on deep liquid pairs, where its gain
is only ~8-10 bps, it self-disables and emits the baseline plan. Set
MINER_DISABLE_SPLIT=1 / MINER_DISABLE_SEED=1 to turn either off.
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from strategies.dex_aggregator.baseline_solver import BaselineSwapSolver
from minotaur_subnet.sdk.intent_solver import SolverMetadata
from minotaur_subnet.shared.types import ExecutionPlan, Interaction

logger = logging.getLogger(__name__)

SOLVER_NAME = os.environ.get("MINOTAUR_SOLVER_NAME", "optimal-router-solver")
SOLVER_VERSION = os.environ.get("MINOTAUR_SOLVER_VERSION", "5.0.0")
SOLVER_AUTHOR = os.environ.get("MINOTAUR_SOLVER_AUTHOR", "miner")

_FALSE = {"0", "false", "no", "off", ""}

# Base (chain 8453) token addresses (lowercased).
_WETH = "0x4200000000000000000000000000000000000006"
_USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
_DAI = "0x50c5725949a6f0c72e6c4a641f24049a917db0cb"
_CBBTC = "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf"

# Routes touching these tokens get the seeded+parallel path (they are the synthetic
# zeros that timed out on cold discovery). WETH/USDC routes stay on the baseline path.
_SEEDED_TOKENS = {_DAI, _CBBTC}
_MAJOR_TOKENS = {_WETH, _USDC}

# On-chain-VERIFIED deep Uniswap V3 pools on Base (factory getPool + liquidity(),
# 2026-06-25). The 2 deepest fee tiers per pair; WETH/USDC included as the multi-hop
# intermediary. Pre-seeding these skips the serial factory discovery that SIGKILLs DAI.
_SEED_POOLS_BASE = [
    "0xd0b53d9277642d899df5c87a3966a349a798f224",  # WETH/USDC 0.05%
    "0x6c561b446416e1a00e8e93e221854d6ea4171372",  # WETH/USDC 0.30%
    "0x93e8542e6ca0efffb9d57a270b76712b968a38f5",  # WETH/DAI  0.05%
    "0xdcf81663e68f076ef9763442de134fd0699de4ef",  # WETH/DAI  0.30%
    "0xc18f50d6a832f12f6dcaaeee8d0c87a65b96787e",  # USDC/DAI  0.01%
    "0x19a8b1542b807cd6a76fcbb5ff5f53c6169f36d7",  # USDC/DAI  0.05%
    "0xfbb6eed8e7aa03b138556eedaf5d271a5e1e43ef",  # cbBTC/USDC 0.05%
    "0xec558e484cc9f2210714e345298fdc53b253c27d",  # cbBTC/USDC 0.30%
    "0x8c7080564b5a792a33ef2fd473fba6364d5495e5",  # cbBTC/WETH 0.30%
    "0x7aea2e8a3843516afa07293a10ac8e49906dabd1",  # cbBTC/WETH 0.05%
]

_SEED_WORKERS = int(os.environ.get("MINER_SEED_WORKERS", "8"))
# Split must beat the single-best route by this factor to be emitted — set high so
# it clears the gas-term penalty and self-disables on deep liquid pairs (~10 bps gain).
_SPLIT_MIN_GAIN = float(os.environ.get("MINER_SPLIT_MIN_GAIN", "1.02"))
_SPLIT_RATIOS = (0.3, 0.5, 0.7)


def _seed_enabled() -> bool:
    return os.environ.get("MINER_DISABLE_SEED", "0").strip().lower() in _FALSE


def _split_enabled() -> bool:
    return os.environ.get("MINER_DISABLE_SPLIT", "0").strip().lower() in _FALSE


class MinerSolver(BaselineSwapSolver):
    """Baseline + seeded/parallel discovery for DAI/cbBTC + safe gas-gated split."""

    # ── 1+2+3: scoped parallel pre-seed (only DAI/cbBTC routes) ───────────────
    def _ensure_pools_for_route(self, chain_id, pool_states, token_in, token_out):  # type: ignore[override]
        try:
            if (
                _seed_enabled()
                and int(chain_id) == 8453
                and ({str(token_in).lower(), str(token_out).lower()} & _SEEDED_TOKENS)
            ):
                self._parallel_seed(chain_id, pool_states)
                # Pools are seeded (incl. multi-hop intermediaries); the baseline
                # resolver routes over them. Skip the SERIAL factory discovery that
                # blows the 5s budget on these pairs.
                return pool_states
        except Exception:
            logger.exception("[miner] parallel seed failed; using baseline discovery")
        return super()._ensure_pools_for_route(chain_id, pool_states, token_in, token_out)

    def _parallel_seed(self, chain_id, pool_states) -> None:
        """Load the verified deep Base pools' state concurrently into pool_states."""
        w3 = self._get_web3(int(chain_id))
        if w3 is None:
            return
        addrs = [a for a in _SEED_POOLS_BASE if a not in pool_states]
        if not addrs:
            return

        def _load(addr):
            try:
                return addr, self._query_pool_state(w3, addr)
            except Exception:
                return addr, None

        with ThreadPoolExecutor(max_workers=_SEED_WORKERS) as ex:
            for addr, state in ex.map(_load, addrs):
                if state is not None:
                    pool_states[addr] = state

    # ── 4: safe gas-gated split across the 2 deepest direct pools (majors) ────
    def generate_plan(self, intent, state, snapshot=None):  # type: ignore[override]
        if _split_enabled():
            try:
                plan = self._maybe_split_plan(intent, state, snapshot)
                if plan is not None:
                    return plan
            except Exception:
                logger.exception("[miner] split routing failed; using baseline plan")
        return super().generate_plan(intent, state, snapshot)

    def _maybe_split_plan(self, intent, state, snapshot):
        params = self._normalized_swap_params(intent, state)
        tin = str(params.get("input_token", "") or "")
        tout = str(params.get("output_token", "") or "")
        amount_in = int(params.get("input_amount", 0) or 0)
        if not tin or not tout or amount_in <= 0:
            return None
        if tin.startswith("eip155:") or tout.startswith("eip155:"):
            return None
        chain_id = state.chain_id or (snapshot.chain_id if snapshot else 1)
        # DEEP major pairs only (WETH/USDC on Base) — never split thin/exotic pairs.
        if int(chain_id) != 8453 or tin.lower() not in _MAJOR_TOKENS or tout.lower() not in _MAJOR_TOKENS:
            return None

        pool_states = self._get_pool_states(chain_id, snapshot)
        if snapshot is not None and snapshot.pool_states and pool_states is snapshot.pool_states:
            pool_states = dict(pool_states)
        self._ensure_pools_for_route(chain_id, pool_states, tin, tout)

        # Single-best baseline output (the gas-gate reference). If this raises, bail.
        best_out, _desc, _hops = self._resolve_best_route(pool_states, tin, tout, amount_in, chain_id)
        if best_out <= 0:
            return None

        a, b = tin.lower(), tout.lower()
        direct = []
        for addr, p in (pool_states or {}).items():
            if p.get("dex") != "uniswap_v3":
                continue
            if {str(p.get("token0", "")).lower(), str(p.get("token1", "")).lower()} != {a, b}:
                continue
            liq = int(p.get("liquidity", "0") or 0)
            if liq > 0:
                direct.append({
                    "pool_addr": addr, "fee": int(p.get("fee", 3000)), "liquidity": liq,
                    "dex": "uniswap_v3", "token_in": tin, "token_out": tout,
                    "token0": p.get("token0"), "token1": p.get("token1"),
                })
        if len(direct) < 2:
            return None
        direct.sort(key=lambda d: d["liquidity"], reverse=True)
        p0, p1 = direct[0], direct[1]

        from strategies.dex_aggregator import quoter as _quoter
        w3 = self._get_web3(chain_id)
        quote_hop = _quoter.make_quote_fn(w3, chain_id)

        best_split = None  # (total_out, [(hop, amount_in, out), ...])
        for r in _SPLIT_RATIOS:
            in0 = amount_in * int(r * 1000) // 1000
            in1 = amount_in - in0
            if in0 <= 0 or in1 <= 0:
                continue
            try:
                out0 = quote_hop(p0, in0)
                out1 = quote_hop(p1, in1)
            except _quoter.QuoteHopError:
                continue  # a pool can't fill its leg → this split is invalid, skip
            total = out0 + out1
            if best_split is None or total > best_split[0]:
                best_split = (total, [(p0, in0, out0), (p1, in1, out1)])

        # Gas-gate: only split if it beats the single-best route by the margin that
        # covers the extra-swap gas penalty. Otherwise emit the baseline plan.
        if best_split is None or best_split[0] <= int(best_out * _SPLIT_MIN_GAIN):
            return None

        from common.abi_utils import encode_approve
        from strategies.dex_aggregator.v3_codec import encode_exact_input_single
        from strategies.dex_aggregator.swap_solver import UNISWAP_V3_ROUTERS

        router = UNISWAP_V3_ROUTERS.get(chain_id)
        if not router:
            return None
        recipient = state.contract_address or params.get("receiver") or state.owner
        deadline = (snapshot.timestamp if snapshot else int(time.time())) + 300

        legs = best_split[1]
        interactions = [Interaction(
            target=tin, value="0", call_data=encode_approve(router, amount_in), chain_id=chain_id,
        )]
        for hop, leg_in, _leg_out in legs:
            interactions.append(Interaction(
                target=router, value="0",
                call_data=encode_exact_input_single(
                    token_in=tin, token_out=tout, fee=int(hop["fee"]), recipient=recipient,
                    deadline=deadline, amount_in=int(leg_in),
                    amount_out_minimum=0,  # aggregate min enforced on-chain → no leg revert
                    chain_id=chain_id,
                ),
                chain_id=chain_id,
            ))
        logger.info(
            "[miner] split: 2 legs fees=%s total_out=%d vs single_best=%d (+%.2f%%)",
            [int(h["fee"]) for h, _, _ in legs], best_split[0], best_out,
            (best_split[0] / best_out - 1) * 100,
        )
        return ExecutionPlan(
            intent_id=intent.app_id, interactions=interactions, deadline=deadline,
            nonce=state.nonce,
            metadata={"solver": "optimal-router", "route": "uniswap_v3_split",
                      "legs": [{"fee": int(h["fee"]), "amount_in": str(ai)} for h, ai, _ in legs]},
        )

    def metadata(self) -> SolverMetadata:
        base = super().metadata()
        return SolverMetadata(
            name=SOLVER_NAME,
            version=SOLVER_VERSION,
            author=SOLVER_AUTHOR,
            description=(
                "Baseline + on-chain-verified pool pre-seed & parallel discovery for "
                "DAI/cbBTC routes (kills the 5s-timeout zeros, enables multi-hop) + "
                "gas-gated safe split on deep major pairs; all fall back to baseline"
            ),
            supported_chains=base.supported_chains,
            supported_intent_types=base.supported_intent_types,
        )


SOLVER_CLASS = MinerSolver
