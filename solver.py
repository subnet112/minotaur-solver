"""Minotaur SN112 miner solver — v7: Aerodrome scoped to cbBTC (recover DAI_to_USDC).

v7 over v6: v6 hit 0.4469 (best yet, +0.018 over the dethrone bar) and recovered
cbBTC_to_USDC via Aerodrome — but its Aerodrome discovery added serial getPool latency
that kept DAI_to_USDC over the 5 s QUOTE budget (still a timeout crash). v7 scopes
Aerodrome discovery to **cbBTC pairs only** (thin Uniswap → aero genuinely helps);
DAI pairs skip it because the seeded Uniswap pools are already very deep, so DAI_to_USDC
now resolves fast (parallel quoting, no aero latency) and the deep USDC/DAI pool fills.
Everything else identical to v6.

--- v6 ---


REPLACES the root ``solver.py`` of a fork of ``subnet112/minotaur-solver``.
Subclasses the real ``BaselineSwapSolver``; every override falls back to the stock
baseline. v6 builds on v5 (pre-seed + parallel discovery + multi-hop + safe split)
and resolves the two open items the v5 live result exposed:

  * v5 PROVED pre-seeding removes the WETH_to_DAI cold-discovery timeout (crash →
    plan generated) but the plan then REVERTED on-chain — and DAI_to_USDC STILL
    timed out, this time in the QUOTING phase (serial QuoterV2 over the multi-hop
    candidate set blew the 5 s QUOTE budget), and v5 SKIPPED Aerodrome discovery for
    seeded routes (it bypassed super), so Uniswap-only routes that revert never got
    an Aerodrome alternative — and Aerodrome is the dominant DEX on Base.

v6 fixes both, SCOPED to DAI/cbBTC routes only (WETH/USDC passing cases stay 100% on
the untouched baseline path → zero regression):
  1. Seeded routes also run **Aerodrome Slipstream** discovery for the direct pair, so
     `_resolve_best_route` can pick an Aerodrome fill where the Uniswap route reverts.
  2. Seeded routes resolve the best route with **parallel** QuoterV2 calls
     (ThreadPoolExecutor) instead of serial, so the multi-hop candidate set is quoted
     in one wave and never blows the 5 s budget (the DAI_to_USDC timeout).

Plus v5, unchanged: on-chain-verified deep Uniswap pool pre-seed (kills cold
discovery), parallel pool-state reads, and a gas-gated safe split on deep major pairs
(per-leg amountOutMinimum=0 so the on-chain min_output invariant enforces the
aggregate; +2 % gain gate → self-disables on deep liquid pairs).

Toggles: MINER_DISABLE_SEED=1, MINER_DISABLE_SPLIT=1, MINER_DISABLE_PARALLEL_QUOTE=1.
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
SOLVER_VERSION = os.environ.get("MINOTAUR_SOLVER_VERSION", "7.0.0")
SOLVER_AUTHOR = os.environ.get("MINOTAUR_SOLVER_AUTHOR", "miner")

_FALSE = {"0", "false", "no", "off", ""}

# Base (chain 8453) token addresses (lowercased).
_WETH = "0x4200000000000000000000000000000000000006"
_USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
_DAI = "0x50c5725949a6f0c72e6c4a641f24049a917db0cb"
_CBBTC = "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf"

_SEEDED_TOKENS = {_DAI, _CBBTC}   # routes touching these get the seeded/parallel/aero path
_MAJOR_TOKENS = {_WETH, _USDC}    # the split applies only to these (deep) pairs

# On-chain-VERIFIED deep Uniswap V3 pools on Base (factory getPool + liquidity(),
# 2026-06-25). 2 deepest fee tiers per pair; WETH/USDC = the multi-hop intermediary.
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
_QUOTE_WORKERS = int(os.environ.get("MINER_QUOTE_WORKERS", "8"))
_MAX_CANDIDATES = int(os.environ.get("MINER_MAX_CANDIDATES", "10"))
_SPLIT_MIN_GAIN = float(os.environ.get("MINER_SPLIT_MIN_GAIN", "1.02"))
_SPLIT_RATIOS = (0.3, 0.5, 0.7)


def _enabled(disable_var: str) -> bool:
    """A feature is ENABLED unless its MINER_DISABLE_* env var is truthy."""
    return os.environ.get(disable_var, "0").strip().lower() in _FALSE


def _seeded_pair(token_in: str, token_out: str) -> bool:
    return bool({str(token_in).lower(), str(token_out).lower()} & _SEEDED_TOKENS)


class MinerSolver(BaselineSwapSolver):
    """Baseline + seeded/parallel discovery, Aerodrome, parallel quoting, safe split."""

    # ── discovery: seeded routes get parallel Uniswap seed + Aerodrome direct ──
    def _ensure_pools_for_route(self, chain_id, pool_states, token_in, token_out):  # type: ignore[override]
        try:
            if _enabled("MINER_DISABLE_SEED") and int(chain_id) == 8453 and _seeded_pair(token_in, token_out):
                self._parallel_seed(chain_id, pool_states)
                # Aerodrome discovery ONLY for cbBTC pairs, where the Uniswap direct pool
                # is THIN and an Aerodrome fill genuinely helps (v6 recovered cbBTC_to_USDC
                # this way). For DAI pairs the seeded Uniswap pools are already very deep
                # (USDC/DAI 0.01% ≈ 1.1e20), so skipping aero here removes its serial
                # getPool latency — that latency is exactly what kept DAI_to_USDC over the
                # 5 s QUOTE budget in v6. (WETH_to_DAI reverts as unfillable either way.)
                if _CBBTC in {str(token_in).lower(), str(token_out).lower()}:
                    self._aero_direct(chain_id, pool_states, token_in, token_out)
                # We have the deep Uniswap pools (+ Aerodrome for cbBTC); skip the SERIAL
                # Uniswap factory discovery that blows the 5 s budget on these pairs.
                return pool_states
        except Exception:
            logger.exception("[miner] seeded discovery failed; using baseline discovery")
        return super()._ensure_pools_for_route(chain_id, pool_states, token_in, token_out)

    def _parallel_seed(self, chain_id, pool_states) -> None:
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

    def _aero_direct(self, chain_id, pool_states, token_in, token_out) -> None:
        """Add the Aerodrome Slipstream DIRECT-pair pools (Base's dominant DEX) so the
        resolver has an Aerodrome fill where the Uniswap route reverts. Bounded: direct
        pair only, to stay under the quote budget."""
        try:
            from strategies.dex_aggregator import aerodrome as _aero
            if int(chain_id) not in _aero.AERODROME_SLIPSTREAM_FACTORY:
                return
            w3 = self._get_web3(int(chain_id))
            if w3 is None:
                return
            _aero.discover_pools_for_pair(
                w3, chain_id, token_in, token_out, pool_states,
                self._query_pool_state, self._pair_discovery_cache,
                cache_ttl=self._pool_cache_ttl,
            )
        except Exception:
            logger.debug("[miner] aerodrome direct discovery skipped", exc_info=True)

    # ── route resolution: seeded routes quote candidates in PARALLEL ──────────
    def _resolve_best_route(self, pool_states, token_in, token_out, amount_in, chain_id):  # type: ignore[override]
        if _enabled("MINER_DISABLE_PARALLEL_QUOTE") and int(chain_id) == 8453 and _seeded_pair(token_in, token_out):
            try:
                best = self._parallel_resolve(pool_states, token_in, token_out, amount_in, chain_id)
                if best is not None:
                    return best
            except Exception:
                logger.exception("[miner] parallel resolve failed; using baseline resolver")
        return super()._resolve_best_route(pool_states, token_in, token_out, amount_in, chain_id)

    def _parallel_resolve(self, pool_states, token_in, token_out, amount_in, chain_id):
        """Same as quoter.resolve_best_route but quotes the top candidates CONCURRENTLY,
        so the multi-hop candidate set never blows the 5 s QUOTE budget (the DAI_to_USDC
        timeout). Returns (final_out, desc, priced_hops) or None to fall back."""
        from strategies.dex_aggregator import quoter as _quoter

        w3 = self._get_web3(int(chain_id))
        quote_hop = _quoter.make_quote_fn(w3, chain_id)  # QuoterUnavailable → caught upstream
        intermediaries = self._intermediaries_for_chain(chain_id)
        candidates = _quoter.enumerate_candidate_routes(pool_states, token_in, token_out, intermediaries)
        candidates = [r for r in candidates if self._is_executable_route(r, chain_id)]
        candidates.sort(key=_quoter.route_bottleneck_liquidity, reverse=True)
        candidates = candidates[:_MAX_CANDIDATES]
        if not candidates:
            return None

        def _q(route):
            try:
                return route, _quoter.quote_route(quote_hop, route, amount_in)
            except _quoter.QuoteHopError:
                return route, None
            except Exception:
                return route, None

        best = None
        with ThreadPoolExecutor(max_workers=_QUOTE_WORKERS) as ex:
            for route, amounts in ex.map(_q, candidates):
                if amounts is None:
                    continue
                final_out = amounts[-1]
                priced, cur = [], int(amount_in)
                for hop, out in zip(route, amounts):
                    h = dict(hop); h["amount_in"] = cur; h["amount_out"] = out
                    priced.append(h); cur = out
                if best is None or final_out > best[0]:
                    best = (final_out, _quoter._route_description(route), priced)
        return best

    # ── plan: gas-gated safe split on deep MAJOR pairs (else baseline) ────────
    def generate_plan(self, intent, state, snapshot=None):  # type: ignore[override]
        if _enabled("MINER_DISABLE_SPLIT"):
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
        if int(chain_id) != 8453 or tin.lower() not in _MAJOR_TOKENS or tout.lower() not in _MAJOR_TOKENS:
            return None

        pool_states = self._get_pool_states(chain_id, snapshot)
        if snapshot is not None and snapshot.pool_states and pool_states is snapshot.pool_states:
            pool_states = dict(pool_states)
        self._ensure_pools_for_route(chain_id, pool_states, tin, tout)

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

        best_split = None
        for r in _SPLIT_RATIOS:
            in0 = amount_in * int(r * 1000) // 1000
            in1 = amount_in - in0
            if in0 <= 0 or in1 <= 0:
                continue
            try:
                total = quote_hop(p0, in0) + quote_hop(p1, in1)
            except _quoter.QuoteHopError:
                continue
            if best_split is None or total > best_split[0]:
                best_split = (total, [(p0, in0), (p1, in1)])

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
        for hop, leg_in in legs:
            interactions.append(Interaction(
                target=router, value="0",
                call_data=encode_exact_input_single(
                    token_in=tin, token_out=tout, fee=int(hop["fee"]), recipient=recipient,
                    deadline=deadline, amount_in=int(leg_in), amount_out_minimum=0, chain_id=chain_id,
                ),
                chain_id=chain_id,
            ))
        logger.info(
            "[miner] split: 2 legs fees=%s total_out=%d vs single_best=%d (+%.2f%%)",
            [int(h["fee"]) for h, _ in legs], best_split[0], best_out,
            (best_split[0] / best_out - 1) * 100,
        )
        return ExecutionPlan(
            intent_id=intent.app_id, interactions=interactions, deadline=deadline, nonce=state.nonce,
            metadata={"solver": "optimal-router", "route": "uniswap_v3_split",
                      "legs": [{"fee": int(h["fee"]), "amount_in": str(ai)} for h, ai in legs]},
        )

    def metadata(self) -> SolverMetadata:
        base = super().metadata()
        return SolverMetadata(
            name=SOLVER_NAME,
            version=SOLVER_VERSION,
            author=SOLVER_AUTHOR,
            description=(
                "Baseline + verified pool pre-seed, parallel discovery & quoting, "
                "Aerodrome direct-pair routing for DAI/cbBTC (kills timeouts, adds the "
                "dominant-DEX fill) + gas-gated safe split on deep majors; all fall back"
            ),
            supported_chains=base.supported_chains,
            supported_intent_types=base.supported_intent_types,
        )


SOLVER_CLASS = MinerSolver
