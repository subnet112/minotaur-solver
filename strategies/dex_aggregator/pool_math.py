"""Shared Uniswap V3 pool math — optional SDK reference implementation.

Pure-Python within-tick swap math and routing. Solvers may use this as
a utility or implement their own (e.g. multi-tick, cross-DEX).

Works with pool_states dicts (from RPC queries or MarketSnapshot) where
each pool has: token0, token1, fee, sqrtPriceX96, liquidity.
"""

from __future__ import annotations

import math
from typing import Any

# Uniswap V3 uses Q64.96 fixed-point for sqrtPrice
Q96 = 1 << 96


def price_to_sqrt_price_x96(
    token0_per_token1: float,
    token0_decimals: int,
    token1_decimals: int,
) -> int:
    """Convert a human-readable price to Uniswap V3 sqrtPriceX96.

    Args:
        token0_per_token1: How many token0 per one token1 in human units.
            E.g. for USDC/WETH pool at $1850/ETH: 1850.0
        token0_decimals: Decimals of token0 (e.g. 6 for USDC).
        token1_decimals: Decimals of token1 (e.g. 18 for WETH).

    Returns:
        sqrtPriceX96 as integer.
    """
    # Uniswap V3 price = token1_raw / token0_raw
    # token0_per_token1 in human units → raw: token1_raw_per_token0_raw
    # 1 token1 = token0_per_token1 * token0
    # In raw: 10^token1_decimals token1_wei = token0_per_token1 * 10^token0_decimals token0_raw
    # price_raw = 10^token1_decimals / (token0_per_token1 * 10^token0_decimals)
    price_raw = 10**token1_decimals / (token0_per_token1 * 10**token0_decimals)
    return int(math.sqrt(price_raw) * Q96)


def compute_v3_output(
    sqrt_price_x96: int,
    liquidity: int,
    amount_in: int,
    zero_for_one: bool,
    fee_ppm: int,
) -> int:
    """Compute single-tick output for a Uniswap V3 swap.

    Within-tick only — large swaps crossing tick boundaries will be
    inaccurate. For production quoting with large amounts, use
    multi-tick simulation.

    Args:
        sqrt_price_x96: Current sqrtPriceX96 of the pool.
        liquidity: Current in-range liquidity.
        amount_in: Input amount (in token's smallest unit).
        zero_for_one: True if swapping token0 for token1.
        fee_ppm: Pool fee in parts-per-million, matching Uniswap V3's
            fee field (e.g., 500 = 0.05%, 3000 = 0.3%, 10000 = 1%).

    Returns:
        Output amount as integer (in output token's smallest unit).
        Returns 0 if inputs are invalid.
    """
    if liquidity <= 0 or amount_in <= 0 or sqrt_price_x96 <= 0:
        return 0

    # Deduct fee: Uniswap V3 fees are in 1/1_000_000 units (3000 = 0.3%)
    amount_after_fee = amount_in * (1_000_000 - fee_ppm) // 1_000_000

    if amount_after_fee <= 0:
        return 0

    # Maximum allowed price impact as a fraction of sqrtPrice.
    # Beyond this, the swap would cross multiple tick boundaries and our
    # single-tick math overestimates the output. 1% sqrtPrice movement
    # ≈ 2% price impact — a reasonable cap for reliable quoting.
    MAX_SQRT_PRICE_IMPACT = sqrt_price_x96 // 100  # 1%

    if zero_for_one:
        # token0 -> token1: price decreases
        # delta_sqrtP = dx * P / (L + dx * sqrtP)  where P = sqrtP^2
        # output = L * delta_sqrtP / Q96
        numerator = amount_after_fee * sqrt_price_x96
        denominator = liquidity * Q96 + amount_after_fee * sqrt_price_x96
        if denominator <= 0:
            return 0
        delta_sqrt_price = numerator * sqrt_price_x96 // denominator
        if delta_sqrt_price > MAX_SQRT_PRICE_IMPACT:
            return 0  # swap too large for this pool's liquidity
        output = liquidity * delta_sqrt_price // Q96
    else:
        # token1 -> token0: price increases
        # new_sqrtP = sqrtP + amount_in * Q96 / L
        # output = L * Q96 * (1/sqrtP - 1/new_sqrtP)
        delta_sqrt_price = amount_after_fee * Q96 // liquidity
        if delta_sqrt_price > MAX_SQRT_PRICE_IMPACT:
            return 0  # swap too large for this pool's liquidity
        new_sqrt_price = sqrt_price_x96 + delta_sqrt_price
        if new_sqrt_price <= 0:
            return 0
        # output = L * Q96 * (new_sqrtP - sqrtP) / (sqrtP * new_sqrtP)
        output = (
            liquidity * Q96 * delta_sqrt_price
            // (sqrt_price_x96 * new_sqrt_price)
        )

    return max(0, output)


def find_best_pool(
    pool_states: dict[str, dict[str, Any]],
    token_in: str,
    token_out: str,
    amount_in: int,
) -> tuple[str, dict[str, Any], int] | None:
    """Find the pool giving the best output for a token pair swap.

    Scans pool_states for pools matching the token pair (checking both
    token0/token1 orderings), computes output for each, returns the best.

    Args:
        pool_states: Pool states keyed by pool address (from RPC queries
            or MarketSnapshot).
        token_in: Input token address.
        token_out: Output token address.
        amount_in: Input amount in smallest unit.

    Returns:
        (pool_addr, pool_state, output_amount) for the best pool,
        or None if no matching pool found.
    """
    token_in_lower = token_in.lower()
    token_out_lower = token_out.lower()
    best: tuple[str, dict[str, Any], int] | None = None

    # First pass: collect all matching pools and their liquidity
    candidates: list[tuple[str, dict[str, Any], int, bool, int]] = []
    max_liquidity = 0

    for pool_addr, pool in pool_states.items():
        t0 = pool.get("token0", "").lower()
        t1 = pool.get("token1", "").lower()

        if t0 == token_in_lower and t1 == token_out_lower:
            zero_for_one = True
        elif t0 == token_out_lower and t1 == token_in_lower:
            zero_for_one = False
        else:
            continue

        liquidity = int(pool.get("liquidity", 0))
        max_liquidity = max(max_liquidity, liquidity)
        candidates.append((pool_addr, pool, liquidity, zero_for_one, int(pool.get("fee", 3000))))

    # Second pass: compute output, skipping pools with <5% of max liquidity.
    # Low-liquidity pools often quote well in single-tick math but revert
    # on-chain because the swap crosses tick boundaries.
    min_liquidity = max_liquidity // 20  # 5% threshold

    for pool_addr, pool, liquidity, zero_for_one, fee in candidates:
        if liquidity < min_liquidity:
            continue

        sqrt_price = int(pool.get("sqrtPriceX96", 0))
        output = compute_v3_output(sqrt_price, liquidity, amount_in, zero_for_one, fee)

        if output > 0 and (best is None or output > best[2]):
            best = (pool_addr, pool, output)

    return best


def price_to_tick(token0_per_token1: float, token0_decimals: int, token1_decimals: int) -> int:
    """Convert a human-readable price to the nearest Uniswap V3 tick.

    Uses the same price convention as ``price_to_sqrt_price_x96``.
    """
    if token0_per_token1 <= 0:
        return 0
    price_raw = 10**token1_decimals / (token0_per_token1 * 10**token0_decimals)
    if price_raw <= 0:
        return 0
    return int(math.log(price_raw) / math.log(1.0001))


def find_best_route(
    pool_states: dict[str, dict[str, Any]],
    token_in: str,
    token_out: str,
    amount_in: int,
    intermediaries: list[str] | None = None,
) -> tuple[int, str, list[dict[str, Any]]] | None:
    """Find the best route for a swap, including multi-hop paths.

    Tries direct pools first, then two-hop routes through common
    intermediary tokens (WETH, USDC by default).

    Args:
        pool_states: Pool states keyed by pool address (from RPC queries
            or MarketSnapshot).
        token_in: Input token address.
        token_out: Output token address.
        amount_in: Input amount in smallest unit.
        intermediaries: Addresses to try as intermediate hops. These MUST be
            chain-appropriate (e.g. the chain's WETH/USDC) — the caller is
            responsible for resolving them per chain. When omitted, only
            direct pools are considered (no multi-hop). A mainnet default here
            would silently break multi-hop on every other chain.

    Returns:
        (output_amount, route_description, hops) or None.
        Each hop is a dict with pool_addr, pool_state, fee, zero_for_one.
    """
    if intermediaries is None:
        intermediaries = []

    token_in_lower = token_in.lower()
    token_out_lower = token_out.lower()

    best_output = 0
    best_description = ""
    best_hops: list[dict[str, Any]] = []

    # 1. Try direct pool
    direct = find_best_pool(pool_states, token_in, token_out, amount_in)
    if direct is not None:
        addr, state, output = direct
        fee = int(state.get("fee", 3000))
        best_output = output
        best_description = f"direct via {fee / 1_000_000:.2%} pool"
        best_hops = [{"pool_addr": addr, "pool_state": state, "fee": fee}]

    # 2. Try two-hop through each intermediary
    for mid in intermediaries:
        mid_lower = mid.lower()
        if mid_lower == token_in_lower or mid_lower == token_out_lower:
            continue

        hop1 = find_best_pool(pool_states, token_in, mid, amount_in)
        if hop1 is None:
            continue

        _, state1, mid_amount = hop1
        hop2 = find_best_pool(pool_states, mid, token_out, mid_amount)
        if hop2 is None:
            continue

        _, state2, final_output = hop2
        if final_output > best_output:
            fee1 = int(state1.get("fee", 3000))
            fee2 = int(state2.get("fee", 3000))
            best_output = final_output
            best_description = (
                f"2-hop via {fee1 / 1_000_000:.2%} + {fee2 / 1_000_000:.2%} pools"
            )
            best_hops = [
                {"pool_addr": hop1[0], "pool_state": state1, "fee": fee1},
                {"pool_addr": hop2[0], "pool_state": state2, "fee": fee2},
            ]

    if best_output <= 0:
        return None

    return (best_output, best_description, best_hops)
