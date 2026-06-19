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
ZERO_ADDRESS = "0x" + "0" * 40
SCORE_SCALE = 1_000_000
MIN_ROUTE_HEADROOM_BPS = 25
GAS_ESTIMATE_SINGLE_HOP = 430_000
GAS_ESTIMATE_AERO_SINGLE_HOP_PREMIUM = 15_000
GAS_ESTIMATE_EXTRA_HOP = 120_000
GAS_ESTIMATE_AERO_HOP_PREMIUM = 8_000


class MinerSolver(BaselineSwapSolver):
    """Reference solver — fork this repo and edit this class to ship
    your own strategy. The default delegates entirely to the upstream
    ``BaselineSwapSolver``, which already does cross-DEX routing
    (Uniswap V3 + Aerodrome Slipstream on Base) and multi-hop fallback.
    """

    def __init__(self) -> None:
        super().__init__()
        self._last_route_analysis: dict[str, Any] | None = None
        self._active_min_output = 0
        self._active_quoted_output = 0

    @staticmethod
    def _valid_address(value: object) -> bool:
        return isinstance(value, str) and value.startswith("0x") and len(value) == 42

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
        """Mirror the current 0.8 output / 0.2 gas scorer with integer math."""
        output_amount = route[0]
        min_output = self._active_min_output
        anchor = self._active_quoted_output or min_output
        gas_estimate = self._route_gas_estimate(route)
        gas_score_scaled = max(0, SCORE_SCALE - gas_estimate)

        if (
            min_output > 0
            and output_amount * 10_000
            < min_output * (10_000 + MIN_ROUTE_HEADROOM_BPS)
        ):
            return -1
        if anchor <= 0:
            return -1

        if output_amount >= 2 * anchor:
            output_score_scaled = SCORE_SCALE
        elif output_amount >= anchor:
            output_score_scaled = (
                SCORE_SCALE // 2
                + (output_amount - anchor) * (SCORE_SCALE // 2) // anchor
            )
        else:
            output_score_scaled = output_amount * (SCORE_SCALE // 2) // anchor

        return 8 * output_score_scaled + 2 * gas_score_scaled

    def _best_scored_route(
        self,
        routes: list[tuple[int, str, list[dict[str, Any]]]],
    ) -> tuple[int, str, list[dict[str, Any]]] | None:
        if not routes:
            return None

        candidates = [
            route
            for route in routes
            if (
                self._active_min_output <= 0
                or route[0] * 10_000
                >= self._active_min_output * (10_000 + MIN_ROUTE_HEADROOM_BPS)
            )
        ]
        if not candidates:
            return None

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

    def _set_active_route_from_state(self, state) -> None:
        self._active_min_output = 0
        self._active_quoted_output = 0
        typed = getattr(state, "typed_context", None)
        if typed is not None:
            self._active_min_output = int(getattr(typed, "min_output_amount", 0) or 0)

        try:
            params = state.raw_params_view()
        except Exception:
            params = getattr(state, "raw_params", {}) or {}
        if self._active_min_output <= 0:
            self._active_min_output = int(params.get("min_output_amount", 0) or 0)
        self._active_quoted_output = int(params.get("quoted_output", 0) or 0)

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

    @staticmethod
    def _exact_route_description(route: list[dict[str, Any]]) -> str:
        """Describe an exact-quoted route without using Quoter internals."""
        from strategies.dex_aggregator.quoter import (
            DEX_AERODROME_SLIPSTREAM,
            hop_dex,
            hop_quoter_param,
        )

        if len(route) == 1:
            hop = route[0]
            label = "aero" if hop_dex(hop) == DEX_AERODROME_SLIPSTREAM else "v3"
            return f"direct via {label} {int(hop.get('fee', 0)) / 1_000_000:.2%} pool"

        parts: list[str] = []
        for hop in route:
            label = "aero" if hop_dex(hop) == DEX_AERODROME_SLIPSTREAM else "v3"
            parts.append(f"{label}:{hop_quoter_param(hop)}")
        return f"{len(route)}-hop via " + " + ".join(parts)

    @staticmethod
    def _memoized_quote_hop(quote_hop):
        """Memoize successful hop quotes for one route-resolution call.

        The wrapper is created inside ``_resolve_best_route``, so values never
        survive across plans, blocks, or epochs. Errors are deliberately not
        cached: fail-loud transport behavior and per-candidate Quoter reverts
        retain their upstream semantics.
        """
        cache: dict[tuple[str, str, str, int], int] = {}

        def memoized(hop: dict[str, Any], amount_in: int) -> int:
            key = (
                str(hop.get("pool_addr", "")).lower(),
                str(hop.get("token_in", "")).lower(),
                str(hop.get("token_out", "")).lower(),
                int(amount_in),
            )
            cached = cache.get(key)
            if cached is not None:
                return cached
            output = quote_hop(hop, amount_in)
            cache[key] = output
            return output

        return memoized

    def _route_category(
        self,
        route: tuple[int, str, list[dict[str, Any]]],
    ) -> str:
        dexes = {self._hop_dex(hop) for hop in route[2]}
        return "cross_dex" if len(dexes) > 1 else "single_dex"

    def _best_exact_output_route(
        self,
        routes: list[tuple[int, str, list[dict[str, Any]]]],
    ) -> tuple[int, str, list[dict[str, Any]]] | None:
        if not routes:
            return None
        return max(
            routes,
            key=lambda route: (
                route[0],
                -self._route_gas_estimate(route),
                -len(route[2]),
                self._route_signature(route),
            ),
        )

    def _route_analysis_fields(
        self,
        prefix: str,
        route: tuple[int, str, list[dict[str, Any]]] | None,
    ) -> dict[str, Any]:
        if route is None:
            return {
                f"{prefix}_output": None,
                f"{prefix}_gas": None,
                f"{prefix}_hops": None,
                f"{prefix}_description": None,
                f"{prefix}_min_headroom_bps": None,
                f"{prefix}_quote_ratio_bps": None,
                f"{prefix}_quote_edge_bps": None,
                f"{prefix}_score_scaled": None,
            }

        min_headroom_bps = None
        if self._active_min_output > 0:
            min_headroom_bps = (
                (route[0] - self._active_min_output) * 10_000
                // self._active_min_output
            )
        anchor = self._active_quoted_output or self._active_min_output
        quote_ratio_bps = route[0] * 10_000 // anchor if anchor > 0 else None
        quote_edge_bps = (
            (route[0] - anchor) * 10_000 // anchor
            if anchor > 0
            else None
        )
        return {
            f"{prefix}_output": route[0],
            f"{prefix}_gas": self._route_gas_estimate(route),
            f"{prefix}_hops": len(route[2]),
            f"{prefix}_description": route[1],
            f"{prefix}_min_headroom_bps": min_headroom_bps,
            f"{prefix}_quote_ratio_bps": quote_ratio_bps,
            f"{prefix}_quote_edge_bps": quote_edge_bps,
            f"{prefix}_score_scaled": self._route_score_scaled(route),
        }

    def _analyze_exact_route_set(
        self,
        quote_hop,
        pool_states: dict[str, dict[str, Any]],
        token_in: str,
        token_out: str,
        amount_in: int,
        chain_id: int,
        intermediaries: list[str],
    ) -> tuple[
        tuple[int, str, list[dict[str, Any]]],
        dict[str, Any],
    ]:
        """Exact-quote one intermediary set and maximize the current scorer.

        Upstream's June 17 router made the on-chain Quoter authoritative.
        Keep that property while selecting against the champion-supplied
        ``quoted_output`` anchor and rejecting routes below the execution min.
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
                self._exact_route_description(candidate),
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

        single_routes = [
            candidate
            for candidate in routes
            if self._route_category(candidate) == "single_dex"
        ]
        cross_routes = [
            candidate
            for candidate in routes
            if self._route_category(candidate) == "cross_dex"
        ]
        best_single = self._best_exact_output_route(single_routes)
        best_cross = self._best_exact_output_route(cross_routes)
        analysis: dict[str, Any] = {
            "quoted_candidates": quoted,
            "attempted_candidates": attempted,
            "selected_category": self._route_category(route),
            **self._route_analysis_fields("selected", route),
            **self._route_analysis_fields("single_dex", best_single),
            **self._route_analysis_fields("cross_dex", best_cross),
        }
        if best_single is not None and best_cross is not None:
            output_delta = best_cross[0] - best_single[0]
            analysis["cross_dex_output_delta"] = output_delta
            analysis["cross_dex_output_edge_bps"] = (
                output_delta * 10_000 // best_single[0]
                if best_single[0] > 0
                else None
            )
            analysis["cross_dex_gas_delta"] = (
                self._route_gas_estimate(best_cross)
                - self._route_gas_estimate(best_single)
            )
        else:
            analysis["cross_dex_output_delta"] = None
            analysis["cross_dex_output_edge_bps"] = None
            analysis["cross_dex_gas_delta"] = None
        return route, analysis

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
        route, _analysis = self._analyze_exact_route_set(
            quote_hop,
            pool_states,
            token_in,
            token_out,
            amount_in,
            chain_id,
            intermediaries,
        )
        return route

    def _record_cross_dex_analysis(
        self,
        analysis: dict[str, Any],
        *,
        chain_id: int,
        token_in: str,
        token_out: str,
        amount_in: int,
        candidate_set: str,
    ) -> None:
        report = {
            "chain_id": chain_id,
            "token_in": token_in.lower(),
            "token_out": token_out.lower(),
            "amount_in": amount_in,
            "min_output": self._active_min_output,
            "quoted_output": self._active_quoted_output,
            "score_anchor": self._active_quoted_output or self._active_min_output,
            "candidate_set": candidate_set,
            **analysis,
        }
        self._last_route_analysis = report
        logger.info(
            "cross_dex_edge %s",
            json.dumps(report, sort_keys=True, separators=(",", ":")),
        )

    def _resolve_best_route(
        self,
        pool_states: dict[str, dict[str, Any]],
        token_in: str,
        token_out: str,
        amount_in: int,
        chain_id: int,
    ) -> tuple[int, str, list[dict[str, Any]]]:
        """Resolve one generic exact-quoted candidate set."""
        from strategies.dex_aggregator import quoter as _quoter

        w3 = self._get_web3(chain_id)
        quote_hop = self._memoized_quote_hop(
            _quoter.make_quote_fn(w3, chain_id),
        )
        intermediaries = self._intermediaries_for_chain(chain_id)
        route, analysis = self._analyze_exact_route_set(
            quote_hop,
            pool_states,
            token_in,
            token_out,
            amount_in,
            chain_id,
            intermediaries,
        )
        self._record_cross_dex_analysis(
            analysis,
            chain_id=chain_id,
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            candidate_set="canonical",
        )
        return route

    def generate_plan(self, intent, state, snapshot=None):
        synthetic_plan = self._synthetic_screening_plan(intent, state, snapshot)
        if synthetic_plan is not None:
            return synthetic_plan

        self._last_route_analysis = None
        try:
            self._set_active_route_from_state(state)
        except Exception:
            self._active_min_output = 0
            self._active_quoted_output = 0
        try:
            plan = super().generate_plan(intent, state, snapshot)
            if self._last_route_analysis is not None:
                plan.metadata["miner_route_analysis"] = dict(self._last_route_analysis)
            return plan
        finally:
            self._active_min_output = 0
            self._active_quoted_output = 0

    def quote(self, intent, state, snapshot=None):
        self._last_route_analysis = None
        try:
            self._set_active_route_from_state(state)
        except Exception:
            self._active_min_output = 0
            self._active_quoted_output = 0
        try:
            return super().quote(intent, state, snapshot)
        finally:
            self._active_min_output = 0
            self._active_quoted_output = 0

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
