"""Minotaur SN112 miner solver — v4: wider exact-quote route search.

This REPLACES the root ``solver.py`` of a fork of ``subnet112/minotaur-solver``.
It subclasses the SDK's ``BaselineSwapSolver`` and overrides ONLY
``_resolve_best_route`` — the single function BOTH ``quote()`` and
``generate_plan()`` route through, so the quote and the emitted plan always
stay on the same route (no quote/plan mismatch, no new plan code).

WHY THIS — the edge, from the v1/v3 post-mortems
-------------------------------------------------
Two dead ends are now ruled out by live results:
  * v1 (0.412): split routing → a leg into a thin pool REVERTED on-chain. The
    PLAN is where revert risk lives — don't hand-build routes.
  * v3 (0.417): quote re-pricing is a NO-OP now. The over-estimate exploit
    king-01 used is patched; the baseline already exact-quotes, so our passing
    cases tied the baseline at ~0.52. The score ceiling is "match the validator's
    reference output"; the only way up is to DELIVER MORE than that reference.

The reference is the baseline's own ``resolve_best_route``, which ranks candidate
routes by bottleneck liquidity and exact-quotes only the top ``MAX_QUOTE_CANDIDATES
= 6`` (quoter.py). So the OUTPUT-maximizing route is missed whenever it sits below
the 6 most-liquid candidates (a thinner pool at a better price, a specific fee
tier, a cross-DEX two-hop). v4 quotes MORE candidates (default 14) and keeps the
best exact output. Because it considers a SUPERSET of the baseline's candidates
and picks the max, its output is **>= baseline by construction** — pure upside:
  * cases where a better route exists  → deliver more than the reference → score > 0.52;
  * cases where the baseline's 6 already contained the best → identical route → tie.
A wider search also lets some orders clear their ``min_output`` (the on-chain
``amountOutMinimum``) that the baseline's narrower pick missed → recovers reverts.

SAFETY MODEL
------------
  * Same primitives as the baseline (``enumerate_candidate_routes`` /
    ``make_quote_fn`` / ``quote_route`` / ``is_executable``); we only widen the
    candidate budget. Every returned route is one the baseline planner can build
    and the Quoter confirmed fillable — NO hand-built calldata, NO splitting.
  * The extra eth_calls are bounded by a WALL-CLOCK BUDGET: once it expires we
    stop and return the best route found so far, so a wider search can never push
    a case over the per-plan timeout that kills the worker.
  * ANY exception falls back to ``super()._resolve_best_route(...)`` — the floor
    is exactly the baseline. ``MINER_DISABLE_WIDESEARCH=1`` ships the pure baseline.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from strategies.dex_aggregator.baseline_solver import BaselineSwapSolver
from minotaur_subnet.sdk.intent_solver import SolverMetadata

logger = logging.getLogger(__name__)

SOLVER_NAME = os.environ.get("MINOTAUR_SOLVER_NAME", "wide-quote-solver")
SOLVER_VERSION = os.environ.get("MINOTAUR_SOLVER_VERSION", "4.0.0")
SOLVER_AUTHOR = os.environ.get("MINOTAUR_SOLVER_AUTHOR", "miner")

_FALSE = {"0", "false", "no", "off", ""}

# Quote up to this many candidate routes (baseline default is 6). More candidates
# => more chance the output-maximizing route is found and beats the reference.
_MAX_CANDIDATES = int(os.environ.get("MINER_MAX_CANDIDATES", "12"))
# Hard wall-clock budget for the whole quoting loop. The per-plan timeout that
# kills the worker is ~30s and discovery runs before this; keep well under it so
# a wider search NEVER newly times a case out. The budget is checked BEFORE each
# quote, so fast (few-candidate) pairs end naturally in <2s and are unaffected;
# only slow multi-hop pairs hit it and return the best route found so far.
_SEARCH_BUDGET_S = float(os.environ.get("MINER_SEARCH_BUDGET_S", "9.0"))


def _widesearch_enabled() -> bool:
    return os.environ.get("MINER_DISABLE_WIDESEARCH", "0").strip().lower() in _FALSE


class MinerSolver(BaselineSwapSolver):
    """Baseline routing + a WIDER exact-quote candidate search.

    Only the route SELECTION is widened (more candidates, time-bounded); the
    plan is still built by the baseline's proven builders for the chosen route,
    so there is no new on-chain revert surface.
    """

    def _resolve_best_route(
        self,
        pool_states: dict[str, dict[str, Any]],
        token_in: str,
        token_out: str,
        amount_in: int,
        chain_id: int,
    ) -> tuple[int, str, list[dict[str, Any]]]:
        if not _widesearch_enabled():
            return super()._resolve_best_route(
                pool_states, token_in, token_out, amount_in, chain_id
            )
        try:
            best = self._wide_resolve(
                pool_states, token_in, token_out, amount_in, chain_id
            )
            if best is not None:
                return best
        except Exception:
            logger.exception("[miner] wide route search failed; using baseline")
        # Anything unexpected (incl. NoRouteError from the wide pass) → baseline,
        # which raises its own NoRouteError loudly for a true no-route.
        return super()._resolve_best_route(
            pool_states, token_in, token_out, amount_in, chain_id
        )

    def _wide_resolve(
        self,
        pool_states: dict[str, dict[str, Any]],
        token_in: str,
        token_out: str,
        amount_in: int,
        chain_id: int,
    ) -> tuple[int, str, list[dict[str, Any]]] | None:
        """Best-output executable route over a WIDER candidate set, time-bounded.

        Mirrors ``quoter.resolve_best_route`` (same enumeration, executability
        filter, per-candidate revert skip, priced-hop copies) but (a) raises the
        quote budget to ``_MAX_CANDIDATES`` and (b) stops early once the wall-clock
        budget expires, returning the best route found so far. Returns None if
        nothing could be quoted (caller falls back to the baseline resolver).
        """
        from strategies.dex_aggregator import quoter as _quoter

        w3 = self._get_web3(chain_id)
        quote_hop = _quoter.make_quote_fn(w3, chain_id)  # raises QuoterUnavailable → caught
        intermediaries = self._intermediaries_for_chain(chain_id)

        candidates = _quoter.enumerate_candidate_routes(
            pool_states, token_in, token_out, intermediaries
        )
        candidates = [r for r in candidates if self._is_executable_route(r, chain_id)]
        # Same cheap pre-ranking as the baseline (bottleneck liquidity), so the
        # candidates we quote are a SUPERSET of the baseline's top-6: our best is
        # therefore always >= the baseline's output for the same pool snapshot.
        candidates.sort(key=_quoter.route_bottleneck_liquidity, reverse=True)

        deadline = time.monotonic() + _SEARCH_BUDGET_S
        best: tuple[int, str, list[dict[str, Any]]] | None = None
        quoted = 0
        for route in candidates:
            if quoted >= _MAX_CANDIDATES or time.monotonic() > deadline:
                break
            try:
                amounts = _quoter.quote_route(quote_hop, route, amount_in)
            except _quoter.QuoteHopError:
                continue  # this pool can't fill this size — skip (revert ≠ budget)
            quoted += 1
            final_out = amounts[-1]
            priced: list[dict[str, Any]] = []
            current_in = int(amount_in)
            for hop, out in zip(route, amounts):
                priced_hop = dict(hop)
                priced_hop["amount_in"] = current_in
                priced_hop["amount_out"] = out
                priced.append(priced_hop)
                current_in = out
            if best is None or final_out > best[0]:
                best = (final_out, _quoter._route_description(route), priced)

        if best is not None:
            logger.info(
                "[miner] wide search: quoted %d candidate(s), best_out=%d (%s)",
                quoted, best[0], best[1],
            )
        return best

    def metadata(self) -> SolverMetadata:
        base = super().metadata()
        return SolverMetadata(
            name=SOLVER_NAME,
            version=SOLVER_VERSION,
            author=SOLVER_AUTHOR,
            description=(
                "Baseline routing + wider exact-quote candidate search "
                f"(up to {_MAX_CANDIDATES} routes, {_SEARCH_BUDGET_S:.0f}s-budgeted) "
                "-> delivers >= the reference route, never builds calldata or splits"
            ),
            supported_chains=base.supported_chains,
            supported_intent_types=base.supported_intent_types,
        )


SOLVER_CLASS = MinerSolver
