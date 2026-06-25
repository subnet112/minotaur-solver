"""Exact on-chain quoting + cross-DEX route resolution.

Replaces the single-tick output math in ``pool_math`` with **exact**
per-hop quotes obtained by ``eth_call``-ing each hop's own on-chain
Quoter. The Quoter is the source of truth for BOTH the output amount AND
whether a route is viable — single-tick math (with its 1% price-impact
cap and 5% liquidity filter) must no longer decide either, because both
were producing wrong answers: spurious "Too little received" reverts
(over-estimation) and false "no route" rejections (under-estimation to 0).

Two Quoters are wired, one uniform per-hop path covers both:

  - **Uniswap V3** → QuoterV2 ``quoteExactInputSingle((tokenIn, tokenOut,
    amountIn, fee, sqrtPriceLimitX96))`` → ``(amountOut, ...)``.
  - **Aerodrome Slipstream** → its Quoter, same shape but the struct uses
    ``int24 tickSpacing`` in place of ``uint24 fee``.

A route is just an ordered list of hops; a single-DEX route quotes every
hop on one Quoter, a cross-DEX route chains across both. Chaining is exact:
``amountIn(hopN) = amountOut(hopN-1)``.

**No fallback / fail loud.** Missing Quoter for the chain, or a transport
failure on the ``eth_call``, raises and propagates — the caller never
silently degrades to single-tick math. A Quoter *revert* (the pool
genuinely can't fill this size) is a per-candidate "not routable here"
signal, not a system failure: that candidate is skipped and the next is
tried. If no candidate can be quoted at all, ``NoRouteError`` is raised —
a TRUE no-route, surfaced loudly rather than masked by approximate math.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── Quoter deployments ─────────────────────────────────────────────────────
#
# chain_id → {dex → quoter address}. Verified live (eth_call returns a real
# quote) against each chain before wiring:
#   - Uniswap QuoterV2 (Ethereum 0x61fF…, Anvil mainnet fork shares it).
#   - Uniswap QuoterV2 (Base 0x3d4e…).
#   - Aerodrome Slipstream Quoter (Base 0x254c…).
# Chains absent here have no Quoter → quoting fails loud (see no-fallback).
DEX_UNISWAP_V3 = "uniswap_v3"
DEX_AERODROME_SLIPSTREAM = "aerodrome_slipstream"

QUOTERS: dict[int, dict[str, str]] = {
    1: {
        DEX_UNISWAP_V3: "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",
    },
    8453: {
        DEX_UNISWAP_V3: "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",
        DEX_AERODROME_SLIPSTREAM: "0x254cf9e1e6e233aa1ac962cb9b05b2cfeaae15b0",
    },
}
# Anvil local fork shares Ethereum mainnet deployments.
QUOTERS[31337] = dict(QUOTERS[1])


# Uniswap V3 QuoterV2.quoteExactInputSingle — struct uses uint24 fee.
_UNISWAP_QUOTER_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"},
                ],
                "name": "params",
                "type": "tuple",
            }
        ],
        "name": "quoteExactInputSingle",
        "outputs": [
            {"name": "amountOut", "type": "uint256"},
            {"name": "sqrtPriceX96After", "type": "uint160"},
            {"name": "initializedTicksCrossed", "type": "uint32"},
            {"name": "gasEstimate", "type": "uint256"},
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

# Aerodrome Slipstream Quoter.quoteExactInputSingle — struct uses int24
# tickSpacing in place of fee; outputs match Uniswap's QuoterV2.
_AERODROME_QUOTER_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "tickSpacing", "type": "int24"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"},
                ],
                "name": "params",
                "type": "tuple",
            }
        ],
        "name": "quoteExactInputSingle",
        "outputs": [
            {"name": "amountOut", "type": "uint256"},
            {"name": "sqrtPriceX96After", "type": "uint160"},
            {"name": "initializedTicksCrossed", "type": "uint32"},
            {"name": "gasEstimate", "type": "uint256"},
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

# How many candidate routes to actually exact-quote. Candidates are
# liquidity-ranked first (cheap, avoids paying an eth_call for obviously
# thin pools), then the top-N are quoted and the best exact output wins.
MAX_QUOTE_CANDIDATES = 6

# Per-leg breadth when forming two-hop candidates: only the K
# highest-liquidity pools per (token, intermediary) leg are combined, to
# keep the candidate count (and thus eth_call count) bounded.
_TOP_POOLS_PER_LEG = 3


# ── Exceptions ─────────────────────────────────────────────────────────────


class QuoterUnavailable(Exception):
    """No Quoter is configured for the chain, or no Web3 is available.

    Propagates (fail loud) — there is no single-tick fallback.
    """


class QuoteHopError(Exception):
    """A single hop could not be quoted (the Quoter reverted — the pool
    can't fill this size). Skippable: the caller tries the next candidate.
    """


class NoRouteError(Exception):
    """No candidate route could be exact-quoted. A TRUE no-route, raised
    loudly rather than masked by approximate math.
    """


# ── Hop / route helpers ────────────────────────────────────────────────────


def hop_dex(hop: dict[str, Any]) -> str:
    """DEX tag for a hop, defaulting to Uniswap V3 for legacy/snapshot
    pools that predate the ``dex`` marker."""
    return hop.get("dex") or (hop.get("pool_state") or {}).get("dex") or DEX_UNISWAP_V3


def hop_quoter_param(hop: dict[str, Any]) -> int:
    """The fee/tickSpacing value this hop's Quoter expects.

    Uniswap V3 quotes by ``fee`` (uint24); Aerodrome Slipstream quotes by
    ``tickSpacing`` (int24). Both live on the pool_state.
    """
    pool = hop.get("pool_state") or {}
    if hop_dex(hop) == DEX_AERODROME_SLIPSTREAM:
        return int(pool.get("tickSpacing", 0))
    return int(hop.get("fee", pool.get("fee", 0)))


def _pools_for_pair(
    pool_states: dict[str, dict[str, Any]],
    token_a: str,
    token_b: str,
) -> list[dict[str, Any]]:
    """Every discovered pool that swaps ``token_a`` → ``token_b``.

    Returns a list of hop dicts (one per matching pool, either token
    ordering), carrying the direction (``token_in``/``token_out``), the
    DEX tag, fee, and liquidity. Pure — no RPC, no single-tick math.
    """
    a = token_a.lower()
    b = token_b.lower()
    hops: list[dict[str, Any]] = []
    for addr, pool in pool_states.items():
        t0 = (pool.get("token0") or "").lower()
        t1 = (pool.get("token1") or "").lower()
        if not ((t0 == a and t1 == b) or (t0 == b and t1 == a)):
            continue
        hops.append(
            {
                "pool_addr": addr,
                "pool_state": pool,
                "fee": int(pool.get("fee", 0) or 0),
                "dex": pool.get("dex") or DEX_UNISWAP_V3,
                "token_in": token_a,
                "token_out": token_b,
                "liquidity": int(pool.get("liquidity", 0) or 0),
            }
        )
    return hops


def enumerate_candidate_routes(
    pool_states: dict[str, dict[str, Any]],
    token_in: str,
    token_out: str,
    intermediaries: list[str] | None = None,
) -> list[list[dict[str, Any]]]:
    """Structurally enumerate candidate routes — NOT gated by output math.

    Produces every direct pool (across DEXes and fee tiers/tickSpacings)
    plus two-hop routes through each intermediary. Two-hop legs are formed
    from the top-``_TOP_POOLS_PER_LEG`` highest-liquidity pools per leg, so
    cross-DEX combinations (e.g. Uniswap leg 1 + Aerodrome leg 2) arise
    naturally. The single-tick 1%-cap and 5%-liquidity filters that used to
    zero out viable routes play no part here — routability is decided later
    by the Quoter.
    """
    in_lower = token_in.lower()
    out_lower = token_out.lower()
    routes: list[list[dict[str, Any]]] = []

    # 1. Direct pools.
    for hop in _pools_for_pair(pool_states, token_in, token_out):
        routes.append([hop])

    # 2. Two-hop routes through each intermediary.
    for mid in intermediaries or []:
        mid_lower = mid.lower()
        if mid_lower in (in_lower, out_lower):
            continue
        leg1 = sorted(
            _pools_for_pair(pool_states, token_in, mid),
            key=lambda h: h["liquidity"],
            reverse=True,
        )[:_TOP_POOLS_PER_LEG]
        leg2 = sorted(
            _pools_for_pair(pool_states, mid, token_out),
            key=lambda h: h["liquidity"],
            reverse=True,
        )[:_TOP_POOLS_PER_LEG]
        for h1 in leg1:
            for h2 in leg2:
                routes.append([h1, h2])

    return routes


def route_bottleneck_liquidity(route: list[dict[str, Any]]) -> int:
    """Cheap pre-ranking signal: the thinnest hop's liquidity. The route is
    only as good as its tightest pool, and liquidity (unlike single-tick
    output) never zeroes a viable route."""
    return min((hop["liquidity"] for hop in route), default=0)


# ── eth_call quoting layer ─────────────────────────────────────────────────


def make_quote_fn(w3: Any, chain_id: int) -> Callable[[dict[str, Any], int], int]:
    """Bind a per-hop exact-quote function to a Web3 + chain.

    The returned ``quote_hop(hop, amount_in) -> amount_out`` performs one
    ``eth_call`` to the hop's DEX Quoter. It raises:
      - ``QuoterUnavailable`` if no Quoter is configured for ``chain_id``
        on the hop's DEX, or ``w3`` is None (fail loud, propagates);
      - ``QuoteHopError`` if the Quoter *reverts* (pool can't fill the
        size) — skippable by the caller;
      - any transport-level exception is left to propagate (fail loud).
    """
    if w3 is None:
        raise QuoterUnavailable(f"no Web3 available for chain {chain_id}")

    chain_quoters = QUOTERS.get(chain_id)
    if not chain_quoters:
        raise QuoterUnavailable(f"no Quoter configured for chain {chain_id}")

    from web3.exceptions import ContractLogicError  # lazy: keep import light

    # Cache contract objects per (dex) so we don't rebuild them per hop.
    contracts: dict[str, Any] = {}

    def _contract(dex: str) -> Any:
        cached = contracts.get(dex)
        if cached is not None:
            return cached
        addr = chain_quoters.get(dex)
        if not addr:
            raise QuoterUnavailable(
                f"no Quoter for dex={dex} on chain {chain_id}"
            )
        abi = (
            _AERODROME_QUOTER_ABI
            if dex == DEX_AERODROME_SLIPSTREAM
            else _UNISWAP_QUOTER_ABI
        )
        c = w3.eth.contract(address=w3.to_checksum_address(addr), abi=abi)
        contracts[dex] = c
        return c

    def quote_hop(hop: dict[str, Any], amount_in: int) -> int:
        dex = hop_dex(hop)
        contract = _contract(dex)
        params = (
            w3.to_checksum_address(hop["token_in"]),
            w3.to_checksum_address(hop["token_out"]),
            int(amount_in),
            hop_quoter_param(hop),  # fee (uint24) or tickSpacing (int24)
            0,  # sqrtPriceLimitX96 = 0 → no limit
        )
        try:
            result = contract.functions.quoteExactInputSingle(params).call()
        except ContractLogicError as exc:
            # The Quoter reverted: this pool can't fill this size. Not a
            # system failure — caller skips this candidate and tries another.
            raise QuoteHopError(
                f"{dex} quote reverted for {hop['token_in'][:10]}→"
                f"{hop['token_out'][:10]} amount={amount_in}: {exc}"
            ) from exc
        amount_out = int(result[0])
        if amount_out <= 0:
            raise QuoteHopError(
                f"{dex} quote returned 0 for {hop['token_in'][:10]}→"
                f"{hop['token_out'][:10]} amount={amount_in}"
            )
        return amount_out

    return quote_hop


def quote_route(
    quote_hop: Callable[[dict[str, Any], int], int],
    route: list[dict[str, Any]],
    amount_in: int,
) -> list[int]:
    """Exact-quote a whole route hop-by-hop, chaining the amounts.

    ``amountIn(hopN) = amountOut(hopN-1)``. Returns the per-hop output
    amounts (so ``[-1]`` is the route's final output). Propagates whatever
    ``quote_hop`` raises (``QuoteHopError`` for a skippable hop revert,
    ``QuoterUnavailable``/transport errors fail loud).
    """
    outputs: list[int] = []
    current_in = int(amount_in)
    for hop in route:
        out = quote_hop(hop, current_in)
        outputs.append(out)
        current_in = out
    return outputs


# ── Route resolution ───────────────────────────────────────────────────────


def _route_description(route: list[dict[str, Any]]) -> str:
    if len(route) == 1:
        hop = route[0]
        label = "aero" if hop_dex(hop) == DEX_AERODROME_SLIPSTREAM else "v3"
        return f"direct via {label} {hop['fee'] / 1_000_000:.2%} pool"
    parts = []
    for hop in route:
        label = "aero" if hop_dex(hop) == DEX_AERODROME_SLIPSTREAM else "v3"
        parts.append(f"{label}:{hop_quoter_param(hop)}")
    return f"{len(route)}-hop via " + " + ".join(parts)


def resolve_best_route(
    quote_hop: Callable[[dict[str, Any], int], int],
    pool_states: dict[str, dict[str, Any]],
    token_in: str,
    token_out: str,
    amount_in: int,
    intermediaries: list[str] | None = None,
    is_executable: Callable[[list[dict[str, Any]]], bool] | None = None,
    max_candidates: int = MAX_QUOTE_CANDIDATES,
) -> tuple[int, str, list[dict[str, Any]]]:
    """Pick the best EXECUTABLE route by EXACT output.

    Pipeline:
      1. enumerate candidate routes structurally (no output-math gating);
      2. drop routes the planner can't emit (``is_executable`` — e.g. a
         cross-DEX route whose intermediate hop can't be sequenced through
         the proxy), so we never waste an eth_call on an unemittable route
         and the returned route is always one the planner can build;
      3. rank the survivors by bottleneck liquidity (cheap);
      4. exact-quote the top ``max_candidates`` and keep the best by final
         output. Per-candidate ``QuoteHopError`` (pool can't fill) is
         skipped; ``QuoterUnavailable``/transport errors propagate.

    Returns ``(final_output, description, hops)`` where each hop carries
    its exact ``amount_in``/``amount_out`` from the Quoter chain. Raises
    ``NoRouteError`` if nothing could be quoted (a TRUE no-route).
    """
    candidates = enumerate_candidate_routes(
        pool_states, token_in, token_out, intermediaries
    )
    if is_executable is not None:
        candidates = [r for r in candidates if is_executable(r)]
    candidates.sort(key=route_bottleneck_liquidity, reverse=True)

    best: tuple[int, str, list[dict[str, Any]]] | None = None
    quoted = 0  # SUCCESSFULLY quoted candidates only (reverts don't count)
    attempted = 0
    last_skip: Exception | None = None
    for route in candidates:
        if quoted >= max_candidates:
            break
        attempted += 1
        try:
            amounts = quote_route(quote_hop, route, amount_in)
        except QuoteHopError as exc:
            # This pool can't fill this size — skip and try the next route. A
            # reverted candidate must NOT consume the quote budget: otherwise a
            # run of high-liquidity-but-unfillable candidates at the top of the
            # ranking would starve a viable thinner route and raise a FALSE
            # NoRouteError (the exact false-no-route this rewrite kills).
            last_skip = exc
            continue
        quoted += 1
        final_out = amounts[-1]
        # Attach exact per-hop amounts to FRESH copies of the hops. The 2-hop
        # cross product shares hop dicts across candidate routes, so mutating
        # them in place would let a later (losing) sibling overwrite the
        # winner's chained amounts — which _build_cross_dex_plan reads for each
        # hop's amountIn. Copies keep every resolved route independent.
        priced: list[dict[str, Any]] = []
        current_in = int(amount_in)
        for hop, out in zip(route, amounts):
            priced_hop = dict(hop)
            priced_hop["amount_in"] = current_in
            priced_hop["amount_out"] = out
            priced.append(priced_hop)
            current_in = out
        if best is None or final_out > best[0]:
            best = (final_out, _route_description(route), priced)

    if best is None:
        raise NoRouteError(
            f"no quotable route for {token_in[:10]}→{token_out[:10]} "
            f"(attempted {attempted} candidate(s)"
            + (f"; last skip: {last_skip}" if last_skip else "")
            + ")"
        )
    return best
