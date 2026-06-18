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

import json
import logging
import os
from typing import Any

from strategies.dex_aggregator.baseline_solver import BaselineSwapSolver
from minotaur_subnet.sdk.intent_solver import SolverMetadata
from minotaur_subnet.shared.types import ExecutionPlan, Interaction

logger = logging.getLogger(__name__)


SOLVER_NAME = os.environ.get("MINOTAUR_SOLVER_NAME", "adaptive-quoter-miner")
SOLVER_VERSION = os.environ.get("MINOTAUR_SOLVER_VERSION", "2.0.0")
SOLVER_AUTHOR = os.environ.get("MINOTAUR_SOLVER_AUTHOR", "miner")
STATE_VERSION = 1
MAX_ROUTE_HINTS = 512
ZERO_ADDRESS = "0x" + "0" * 40
HINT_SHORT_CIRCUIT_BPS = 9_500
EXTRA_ROUTE_MODEL_MARGIN_BPS = 25
EXTRA_ROUTE_EXTRA_HOP_COST_BPS = 600
# Validator min-out is pinned near the incumbent/champion output. Keep gas
# selection to effectively equal-output routes so gas never buys a hard zero.
GAS_AWARE_MIN_OUTPUT_BPS = 9_998
GAS_ESTIMATE_SINGLE_HOP = 430_000
GAS_ESTIMATE_AERO_SINGLE_HOP_PREMIUM = 15_000
GAS_ESTIMATE_EXTRA_HOP = 120_000
GAS_ESTIMATE_AERO_HOP_PREMIUM = 8_000
EXTRA_MIN_INPUT_BY_TOKEN: dict[int, dict[str, int]] = {
    8453: {
        "0x4200000000000000000000000000000000000006": 500_000_000_000_000_000,  # WETH: 0.5
        "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": 1_000_000_000,  # USDC: 1000
        "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca": 1_000_000_000,  # USDbC: 1000
        "0x50c5725949a6f0c72e6c4a641f24049a917db0cb": 1_000_000_000_000_000_000_000,  # DAI: 1000
        "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf": 500_000,  # cbBTC: 0.005
        "0x940181a94a35a4569e4529a3cdfb74e38fd98631": 100_000_000_000_000_000_000,  # AERO: 100
    },
}
EXTRA_INTERMEDIARIES: dict[int, tuple[str, ...]] = {
    8453: (
        "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf",  # cbBTC
        "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA",  # USDbC
        "0x940181a94A35A4569E4529A3CDfB74e38FD98631",  # AERO
        "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb",  # DAI
    ),
}
ENABLE_EXTRA_INTERMEDIARIES = os.environ.get(
    "MINOTAUR_ENABLE_EXTRA_INTERMEDIARIES", "",
).strip().lower() in {"1", "true", "yes", "on"}
BASELINE_INTERMEDIARIES: dict[int, tuple[str, ...]] = {
    1: (
        "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    ),
    31337: (
        "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    ),
    8453: (
        "0x4200000000000000000000000000000000000006",
        "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    ),
}


class MinerSolver(BaselineSwapSolver):
    """Reference solver — fork this repo and edit this class to ship
    your own strategy. The default delegates entirely to the upstream
    ``BaselineSwapSolver``, which already does cross-DEX routing
    (Uniswap V3 + Aerodrome Slipstream on Base) and multi-hop fallback.
    """

    def __init__(self) -> None:
        super().__init__()
        self._route_hints: dict[str, dict[str, Any]] = {}
        self._benchmark_epoch = 0
        self._active_route_amount = 0
        self._active_min_output = 0
        self._active_input_token = ""
        self._suppress_extra_intermediaries = False

    def _route_key(self, chain_id: int, token_in: str, token_out: str) -> str:
        return "|".join((str(chain_id), token_in.lower(), token_out.lower()))

    @staticmethod
    def _valid_address(value: object) -> bool:
        return isinstance(value, str) and value.startswith("0x") and len(value) == 42

    def _tokens_from_hops(self, token_in: str, hops: list[dict[str, Any]]) -> list[str]:
        tokens = [token_in]
        for hop in hops:
            pool = hop.get("pool_state") or {}
            current = tokens[-1].lower()
            token0 = str(pool.get("token0", "")).lower()
            token1 = str(pool.get("token1", "")).lower()
            if current == token0 and self._valid_address(pool.get("token1")):
                tokens.append(str(pool["token1"]).lower())
            elif current == token1 and self._valid_address(pool.get("token0")):
                tokens.append(str(pool["token0"]).lower())
        return tokens

    def _record_route_hint(
        self,
        chain_id: int,
        token_in: str,
        token_out: str,
        amount_in: int,
        route: tuple[int, str, list[dict[str, Any]]] | None,
    ) -> None:
        if route is None or not token_in or not token_out:
            return
        if not self._should_search_extra_intermediaries(chain_id):
            return

        output_amount, _route_desc, hops = route
        if not hops:
            return

        key = self._route_key(chain_id, token_in, token_out)
        pool_path = [
            str(hop.get("pool_addr", "")).lower()
            for hop in hops
            if self._valid_address(hop.get("pool_addr"))
        ]
        token_path = self._tokens_from_hops(token_in, hops)
        useful_mids = token_path[1:-1] if len(token_path) > 2 else []
        hint = self._route_hints.get(key, {})
        hint.update({
            "chain_id": chain_id,
            "token_in": token_in.lower(),
            "token_out": token_out.lower(),
            "best_dex": self._dominant_dex(hops),
            "pool_path": pool_path,
            "token_path": token_path,
            "useful_mids": useful_mids,
            "fees": [int(h.get("fee", 0) or 0) for h in hops],
            "hops": len(hops),
            "last_input_amount": str(amount_in),
            "last_output": str(output_amount),
            "samples": int(hint.get("samples", 0)) + 1,
            "last_epoch": self._benchmark_epoch,
        })
        self._route_hints[key] = hint

        if len(self._route_hints) > MAX_ROUTE_HINTS:
            ranked = sorted(
                self._route_hints.items(),
                key=lambda item: (
                    int(item[1].get("last_epoch", 0)),
                    int(item[1].get("samples", 0)),
                ),
            )
            for stale_key, _hint in ranked[: len(self._route_hints) - MAX_ROUTE_HINTS]:
                self._route_hints.pop(stale_key, None)

    def _extra_intermediaries_for_chain(self, chain_id: int) -> list[str]:
        if not self._should_search_extra_intermediaries(chain_id):
            return []
        extras: list[str] = []
        known = {addr.lower() for addr in self._baseline_intermediaries_for_chain(chain_id)}
        for addr in EXTRA_INTERMEDIARIES.get(chain_id, ()):
            if addr.lower() not in known:
                extras.append(addr)
                known.add(addr.lower())
        return extras

    def _baseline_intermediaries_for_chain(self, chain_id: int) -> list[str]:
        try:
            return list(super()._intermediaries_for_chain(chain_id))
        except ModuleNotFoundError as exc:
            if exc.name == "web3":
                return list(BASELINE_INTERMEDIARIES.get(chain_id, ()))
            raise

    def _should_search_extra_intermediaries(self, chain_id: int) -> bool:
        if self._suppress_extra_intermediaries:
            return False
        if not ENABLE_EXTRA_INTERMEDIARIES:
            return False

        amount_in = self._active_route_amount
        token = self._active_input_token.lower()
        if amount_in <= 0 or not token:
            return False

        thresholds = EXTRA_MIN_INPUT_BY_TOKEN.get(chain_id, {})
        threshold = thresholds.get(token)
        if threshold is None:
            return False
        return amount_in >= threshold

    def _intermediaries_for_chain(self, chain_id: int) -> list[str]:
        mids = self._baseline_intermediaries_for_chain(chain_id)
        if not self._should_search_extra_intermediaries(chain_id):
            return mids

        known = {addr.lower() for addr in mids}
        for addr in EXTRA_INTERMEDIARIES.get(chain_id, ()):
            if addr.lower() not in known:
                mids.append(addr)
                known.add(addr.lower())
        return mids

    def _discover_pair_all_dexes(
        self,
        chain_id: int,
        pool_states: dict[str, dict[str, Any]],
        token_a: str,
        token_b: str,
    ) -> None:
        self._discover_pools_for_pair(chain_id, token_a, token_b, pool_states)

        from strategies.dex_aggregator import aerodrome as _aero

        if chain_id not in _aero.AERODROME_SLIPSTREAM_FACTORY:
            return

        w3 = self._get_web3(chain_id)
        if w3 is None:
            return

        _aero.discover_pools_for_pair(
            w3,
            chain_id,
            token_a,
            token_b,
            pool_states,
            self._query_pool_state,
            self._pair_discovery_cache,
            cache_ttl=self._pool_cache_ttl,
        )

    def _discover_extra_intermediary_pools(
        self,
        chain_id: int,
        pool_states: dict[str, dict[str, Any]],
        token_in: str,
        token_out: str,
    ) -> None:
        in_lower = token_in.lower()
        out_lower = token_out.lower()
        mids = self._extra_intermediaries_for_chain(chain_id)
        hint = self._route_hints.get(self._route_key(chain_id, token_in, token_out))
        if hint:
            for mid in hint.get("useful_mids", []):
                if self._valid_address(mid) and mid.lower() not in {m.lower() for m in mids}:
                    mids.append(mid)

        for mid in mids:
            mid_lower = mid.lower()
            if mid_lower == in_lower or mid_lower == out_lower:
                continue
            self._discover_pair_all_dexes(chain_id, pool_states, token_in, mid)
            self._discover_pair_all_dexes(chain_id, pool_states, mid, token_out)

    def _warm_start_hinted_pools(
        self,
        chain_id: int,
        pool_states: dict[str, dict[str, Any]],
        token_in: str,
        token_out: str,
    ) -> None:
        if not self._rpc_urls.get(chain_id):
            return

        hint = self._route_hints.get(self._route_key(chain_id, token_in, token_out))
        if not hint:
            return

        w3 = self._get_web3(chain_id)
        if w3 is None:
            return

        existing = {addr.lower() for addr in pool_states}
        for pool_addr in hint.get("pool_path", []):
            if not self._valid_address(pool_addr) or pool_addr == ZERO_ADDRESS:
                continue
            if pool_addr.lower() in existing:
                continue
            pool_state = self._query_pool_state(w3, pool_addr)
            if pool_state is not None:
                pool_states[pool_addr] = pool_state
                existing.add(pool_addr.lower())

    def _hint_quote_is_strong(
        self,
        chain_id: int,
        pool_states: dict[str, dict[str, Any]],
        token_in: str,
        token_out: str,
    ) -> bool:
        amount_in = self._active_route_amount
        if amount_in <= 0:
            return False

        hint = self._route_hints.get(self._route_key(chain_id, token_in, token_out))
        if not hint:
            return False

        try:
            last_input = int(hint.get("last_input_amount", "0"))
            last_output = int(hint.get("last_output", "0"))
        except (TypeError, ValueError):
            return False
        if last_input <= 0 or last_output <= 0:
            return False

        from strategies.dex_aggregator.pool_math import find_best_route

        route = find_best_route(
            pool_states,
            token_in,
            token_out,
            amount_in,
            intermediaries=self._intermediaries_for_chain(chain_id),
        )
        if route is None:
            return False

        output_amount, _desc, _hops = route
        scaled_prior = last_output * amount_in // last_input
        return scaled_prior > 0 and output_amount * 10_000 >= scaled_prior * HINT_SHORT_CIRCUIT_BPS

    def _extra_route_required_edge_bps(
        self,
        baseline_route: tuple[int, str, list[dict[str, Any]]] | None,
        expanded_route: tuple[int, str, list[dict[str, Any]]] | None,
    ) -> int:
        if baseline_route is None or expanded_route is None:
            return 0

        extra_hops = max(0, len(expanded_route[2]) - len(baseline_route[2]))
        return EXTRA_ROUTE_MODEL_MARGIN_BPS + extra_hops * EXTRA_ROUTE_EXTRA_HOP_COST_BPS

    def _route_signature(self, route: tuple[int, str, list[dict[str, Any]]]) -> tuple[str, ...]:
        return tuple(str(hop.get("pool_addr", "")).lower() for hop in route[2])

    def _route_gas_estimate(self, route: tuple[int, str, list[dict[str, Any]]]) -> int:
        hops = route[2]
        if not hops:
            return GAS_ESTIMATE_SINGLE_HOP

        estimate = GAS_ESTIMATE_SINGLE_HOP + max(0, len(hops) - 1) * GAS_ESTIMATE_EXTRA_HOP
        estimate += sum(
            GAS_ESTIMATE_AERO_HOP_PREMIUM
            for hop in hops
            if self._hop_dex(hop) == "aerodrome_slipstream"
        )
        if len(hops) == 1 and self._hop_dex(hops[0]) == "aerodrome_slipstream":
            estimate += GAS_ESTIMATE_AERO_SINGLE_HOP_PREMIUM
        return estimate

    def _route_score_scaled(self, route: tuple[int, str, list[dict[str, Any]]]) -> int:
        output_amount = route[0]
        min_output = self._active_min_output
        gas_estimate = self._route_gas_estimate(route)
        gas_score_scaled = max(0, 1_000_000 - gas_estimate)

        if min_output <= 0:
            output_score_scaled = 1_000_000
        else:
            if output_amount < min_output:
                return -1
            output_score_scaled = min(
                1_000_000,
                output_amount * 1_000_000 // (2 * min_output),
            )

        return 7_000 * output_score_scaled + 1_500 * gas_score_scaled

    def _best_scored_route(
        self,
        routes: list[tuple[int, str, list[dict[str, Any]]]],
    ) -> tuple[int, str, list[dict[str, Any]]] | None:
        if not routes:
            return None

        max_output = max(route[0] for route in routes)
        output_floor = max_output * GAS_AWARE_MIN_OUTPUT_BPS // 10_000
        candidates = [route for route in routes if route[0] >= output_floor]
        if not candidates:
            candidates = routes

        return max(
            candidates,
            key=lambda route: (
                self._route_score_scaled(route),
                route[0],
                -self._route_gas_estimate(route),
                -len(route[2]),
                self._route_signature(route),
            ),
        )

    def _candidate_routes_for_pool_subset(
        self,
        pool_states: dict[str, dict[str, Any]],
        token_in: str,
        token_out: str,
        amount_in: int,
        intermediaries: list[str],
    ) -> list[tuple[int, str, list[dict[str, Any]]]]:
        from strategies.dex_aggregator.pool_math import find_best_pool

        routes: list[tuple[int, str, list[dict[str, Any]]]] = []
        direct = find_best_pool(pool_states, token_in, token_out, amount_in)
        if direct is not None:
            addr, state, output = direct
            fee = int(state.get("fee", 3000))
            routes.append((
                output,
                f"direct via {fee / 1_000_000:.2%} pool",
                [{"pool_addr": addr, "pool_state": state, "fee": fee}],
            ))

        token_in_lower = token_in.lower()
        token_out_lower = token_out.lower()
        for mid in intermediaries:
            mid_lower = mid.lower()
            if mid_lower == token_in_lower or mid_lower == token_out_lower:
                continue

            hop1 = find_best_pool(pool_states, token_in, mid, amount_in)
            if hop1 is None:
                continue

            addr1, state1, mid_amount = hop1
            hop2 = find_best_pool(pool_states, mid, token_out, mid_amount)
            if hop2 is None:
                continue

            addr2, state2, final_output = hop2
            fee1 = int(state1.get("fee", 3000))
            fee2 = int(state2.get("fee", 3000))
            routes.append((
                final_output,
                f"2-hop via {fee1 / 1_000_000:.2%} + {fee2 / 1_000_000:.2%} pools",
                [
                    {"pool_addr": addr1, "pool_state": state1, "fee": fee1},
                    {"pool_addr": addr2, "pool_state": state2, "fee": fee2},
                ],
            ))

        return routes

    def _find_gas_aware_executable_route(
        self,
        pool_states: dict[str, dict[str, Any]],
        token_in: str,
        token_out: str,
        amount_in: int,
        chain_id: int,
    ) -> tuple[int, str, list[dict[str, Any]]] | None:
        intermediaries = self._intermediaries_for_chain(chain_id)
        subsets = [
            pool_states,
            {a: p for a, p in pool_states.items() if (p.get("dex") or "uniswap_v3") == "uniswap_v3"},
            {a: p for a, p in pool_states.items() if p.get("dex") == "aerodrome_slipstream"},
        ]

        routes: list[tuple[int, str, list[dict[str, Any]]]] = []
        seen: set[tuple[str, ...]] = set()
        for subset in subsets:
            if not subset:
                continue
            for route in self._candidate_routes_for_pool_subset(
                subset, token_in, token_out, amount_in, intermediaries,
            ):
                if not route[2]:
                    continue
                dexes = {self._hop_dex(hop) for hop in route[2]}
                if len(route[2]) > 1 and len(dexes) > 1:
                    continue
                signature = self._route_signature(route)
                if signature in seen:
                    continue
                seen.add(signature)
                routes.append(route)

        return self._best_scored_route(routes)

    def _set_active_route_from_state(self, state) -> None:
        typed = getattr(state, "typed_context", None)
        if typed is not None:
            self._active_route_amount = int(getattr(typed, "input_amount", 0) or 0)
            self._active_min_output = int(getattr(typed, "min_output_amount", 0) or 0)
            self._active_input_token = str(getattr(typed, "input_token", "") or "")
            return

        try:
            params = state.raw_params_view()
        except Exception:
            params = getattr(state, "raw_params", {}) or {}
        self._active_route_amount = int(params.get("input_amount", 0) or 0)
        self._active_min_output = int(params.get("min_output_amount", 0) or 0)
        self._active_input_token = str(params.get("input_token", "") or "")

    def _synthetic_screening_plan(self, intent, state, snapshot=None) -> ExecutionPlan | None:
        app_id = str(getattr(intent, "app_id", "") or "")
        if not app_id.startswith("synthetic-"):
            return None

        target = str(getattr(state, "contract_address", "") or "")
        if not self._valid_address(target):
            target = ZERO_ADDRESS

        timestamp = int(getattr(snapshot, "timestamp", 0) or 0)
        return ExecutionPlan(
            intent_id=app_id,
            interactions=[
                Interaction(
                    target=target,
                    value="0",
                    call_data="0x00",
                    chain_id=int(getattr(state, "chain_id", 1) or 1),
                ),
            ],
            deadline=timestamp + 300,
            nonce=int(getattr(state, "nonce", 0) or 0),
            metadata={"route": "synthetic_screening_fallback"},
        )

    def _derive_prices(
        self,
        pool_states: dict[str, dict[str, Any]],
        chain_id: int,
    ) -> dict[str, float]:
        try:
            return super()._derive_prices(pool_states, chain_id)
        except ModuleNotFoundError as exc:
            if exc.name == "web3":
                return {}
            raise

    def _ensure_pools_for_route(
        self,
        chain_id: int,
        pool_states: dict[str, dict[str, Any]],
        token_in: str,
        token_out: str,
    ) -> dict[str, dict[str, Any]]:
        has_hint = self._route_key(chain_id, token_in, token_out) in self._route_hints
        if not has_hint and not self._should_search_extra_intermediaries(chain_id):
            return super()._ensure_pools_for_route(chain_id, pool_states, token_in, token_out)

        self._warm_start_hinted_pools(chain_id, pool_states, token_in, token_out)
        self._discover_pair_all_dexes(chain_id, pool_states, token_in, token_out)

        if self._hint_quote_is_strong(chain_id, pool_states, token_in, token_out):
            self._discover_extra_intermediary_pools(
                chain_id, pool_states, token_in, token_out,
            )
            return pool_states

        return super()._ensure_pools_for_route(chain_id, pool_states, token_in, token_out)

    def _find_best_executable_route(
        self,
        pool_states: dict[str, dict[str, Any]],
        token_in: str,
        token_out: str,
        amount_in: int,
        chain_id: int,
    ) -> tuple[int, str, list[dict[str, Any]]] | None:
        if not self._should_search_extra_intermediaries(chain_id):
            route = self._find_gas_aware_executable_route(
                pool_states, token_in, token_out, amount_in, chain_id,
            )
            self._record_route_hint(chain_id, token_in, token_out, amount_in, route)
            return route

        self._suppress_extra_intermediaries = True
        try:
            baseline_route = self._find_gas_aware_executable_route(
                pool_states, token_in, token_out, amount_in, chain_id,
            )
        finally:
            self._suppress_extra_intermediaries = False

        expanded_route = self._find_gas_aware_executable_route(
            pool_states, token_in, token_out, amount_in, chain_id,
        )
        route = expanded_route
        if baseline_route is not None and expanded_route is not None:
            required_edge_bps = self._extra_route_required_edge_bps(
                baseline_route, expanded_route,
            )
            if expanded_route[0] * 10_000 < baseline_route[0] * (10_000 + required_edge_bps):
                route = baseline_route
        elif expanded_route is None:
            route = baseline_route

        self._record_route_hint(chain_id, token_in, token_out, amount_in, route)
        return route

    def _resolve_exact_route_set(
        self,
        quote_hop,
        pool_states: dict[str, dict[str, Any]],
        token_in: str,
        token_out: str,
        amount_in: int,
        chain_id: int,
        intermediaries: list[str],
    ) -> tuple[int, str, list[dict[str, Any]]]:
        """Exact-quote one intermediary set and apply the safe gas tiebreak.

        Upstream's June 17 router made the on-chain Quoter authoritative.
        Keep that property while retaining this miner's only route-selection
        edge: among routes within ``GAS_AWARE_MIN_OUTPUT_BPS`` of the maximum
        exact output, prefer the lower estimated-gas route.
        """
        from strategies.dex_aggregator import quoter as _quoter

        candidates = _quoter.enumerate_candidate_routes(
            pool_states,
            token_in,
            token_out,
            intermediaries,
        )
        candidates = [
            route
            for route in candidates
            if self._is_executable_route(route, chain_id)
        ]
        candidates.sort(
            key=_quoter.route_bottleneck_liquidity,
            reverse=True,
        )

        routes: list[tuple[int, str, list[dict[str, Any]]]] = []
        quoted = 0
        attempted = 0
        last_skip: Exception | None = None
        for candidate in candidates:
            if quoted >= _quoter.MAX_QUOTE_CANDIDATES:
                break
            attempted += 1
            try:
                amounts = _quoter.quote_route(quote_hop, candidate, amount_in)
            except _quoter.QuoteHopError as exc:
                last_skip = exc
                continue
            quoted += 1

            priced: list[dict[str, Any]] = []
            current_in = int(amount_in)
            for hop, output in zip(candidate, amounts):
                priced_hop = dict(hop)
                priced_hop["amount_in"] = current_in
                priced_hop["amount_out"] = output
                priced.append(priced_hop)
                current_in = output
            routes.append((
                amounts[-1],
                _quoter._route_description(candidate),
                priced,
            ))

        route = self._best_scored_route(routes)
        if route is None:
            raise _quoter.NoRouteError(
                f"no quotable route for {token_in[:10]}->{token_out[:10]} "
                f"(attempted {attempted} candidate(s)"
                + (f"; last skip: {last_skip}" if last_skip else "")
                + ")"
            )
        return route

    def _resolve_best_route(
        self,
        pool_states: dict[str, dict[str, Any]],
        token_in: str,
        token_out: str,
        amount_in: int,
        chain_id: int,
    ) -> tuple[int, str, list[dict[str, Any]]]:
        """Resolve an exact-quoted route while preserving guarded expansion."""
        from strategies.dex_aggregator import quoter as _quoter

        w3 = self._get_web3(chain_id)
        quote_hop = _quoter.make_quote_fn(w3, chain_id)
        baseline_mids = self._baseline_intermediaries_for_chain(chain_id)
        baseline_route = self._resolve_exact_route_set(
            quote_hop,
            pool_states,
            token_in,
            token_out,
            amount_in,
            chain_id,
            baseline_mids,
        )

        if not self._should_search_extra_intermediaries(chain_id):
            route = baseline_route
        else:
            expanded_mids = self._intermediaries_for_chain(chain_id)
            expanded_route = self._resolve_exact_route_set(
                quote_hop,
                pool_states,
                token_in,
                token_out,
                amount_in,
                chain_id,
                expanded_mids,
            )
            required_edge_bps = self._extra_route_required_edge_bps(
                baseline_route,
                expanded_route,
            )
            if (
                expanded_route[0] * 10_000
                >= baseline_route[0] * (10_000 + required_edge_bps)
            ):
                route = expanded_route
            else:
                route = baseline_route

        self._record_route_hint(
            chain_id,
            token_in,
            token_out,
            amount_in,
            route,
        )
        return route

    def generate_plan(self, intent, state, snapshot=None):
        synthetic_plan = self._synthetic_screening_plan(intent, state, snapshot)
        if synthetic_plan is not None:
            return synthetic_plan

        try:
            self._set_active_route_from_state(state)
        except Exception:
            self._active_route_amount = 0
            self._active_min_output = 0
            self._active_input_token = ""
        try:
            return super().generate_plan(intent, state, snapshot)
        finally:
            self._active_route_amount = 0
            self._active_min_output = 0
            self._active_input_token = ""

    def quote(self, intent, state, snapshot=None):
        try:
            self._set_active_route_from_state(state)
        except Exception:
            self._active_route_amount = 0
            self._active_min_output = 0
            self._active_input_token = ""
        try:
            return super().quote(intent, state, snapshot)
        finally:
            self._active_route_amount = 0
            self._active_min_output = 0
            self._active_input_token = ""

    def on_benchmark_end(self, results: list[dict[str, Any]]) -> None:
        super().on_benchmark_end(results)
        self._benchmark_epoch += 1

        min_epoch = max(0, self._benchmark_epoch - 16)
        for key, hint in list(self._route_hints.items()):
            if int(hint.get("last_epoch", 0)) < min_epoch:
                self._route_hints.pop(key, None)

    def serialize_state(self) -> bytes:
        try:
            payload = {
                "version": STATE_VERSION,
                "benchmark_epoch": self._benchmark_epoch,
                "route_hints": self._route_hints,
            }
            return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        except Exception as exc:
            logger.debug("serialize_state skipped: %s", exc)
            return b""

    def restore_state(self, data: bytes) -> None:
        if not data:
            return
        try:
            payload = json.loads(data.decode("utf-8"))
            if not isinstance(payload, dict) or payload.get("version") != STATE_VERSION:
                return

            hints = payload.get("route_hints", {})
            if isinstance(hints, dict):
                restored: dict[str, dict[str, Any]] = {}
                for key, value in hints.items():
                    if isinstance(key, str) and isinstance(value, dict):
                        restored[key] = value
                        if len(restored) >= MAX_ROUTE_HINTS:
                            break
                self._route_hints = restored

            epoch = payload.get("benchmark_epoch", 0)
            if isinstance(epoch, int) and epoch >= 0:
                self._benchmark_epoch = epoch
        except Exception as exc:
            logger.debug("restore_state skipped: %s", exc)
            self._route_hints = {}
            self._benchmark_epoch = 0

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
