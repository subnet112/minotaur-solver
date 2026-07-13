"""Shared Uniswap V3 pool math — optional SDK reference implementation.

Pure-Python within-tick swap math and routing. Solvers may use this as
a utility or implement their own (e.g. multi-tick, cross-DEX).

Works with pool_states dicts (from RPC queries or MarketSnapshot) where
each pool has: token0, token1, fee, sqrtPriceX96, liquidity.
"""
from __future__ import annotations

def _lr19():
    global Any, Q96, _DR_UNSET, _dr7, compute_v3_output, find_best_pool, math
    _DR_UNSET = object()

    def _dr7():
        import math
        from typing import Any
        Q96 = 1 << 96

        def compute_v3_output(sqrt_price_x96: int, liquidity: int, amount_in: int, zero_for_one: bool, fee_ppm: int) -> int:
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
            amount_after_fee = None

            def _lr7():
                nonlocal amount_after_fee
                if liquidity <= 0 or amount_in <= 0 or sqrt_price_x96 <= 0:
                    return (1, 0)
                amount_after_fee = amount_in * (1000000 - fee_ppm) // 1000000
                if amount_after_fee <= 0:
                    return (1, 0)
                return (0, None)
            _lrt8 = _lr7()
            if _lrt8[0]:
                return _lrt8[1]
            MAX_SQRT_PRICE_IMPACT = sqrt_price_x96 // 100
            output = None
            delta_sqrt_price = None

            def _lr24():
                nonlocal delta_sqrt_price
                delta_sqrt_price = None
                if zero_for_one:

                    def _dr4():
                        nonlocal delta_sqrt_price, output
                        numerator = amount_after_fee * sqrt_price_x96
                        denominator = liquidity * Q96 + amount_after_fee * sqrt_price_x96

                        def _lr30():
                            nonlocal delta_sqrt_price, output
                            if denominator <= 0:
                                return 0
                            delta_sqrt_price = numerator * sqrt_price_x96 // denominator
                            if delta_sqrt_price > MAX_SQRT_PRICE_IMPACT:
                                return 0
                            output = liquidity * delta_sqrt_price // Q96
                            return _DR_UNSET
                        return _lr30()
                    _dr5 = _dr4()
                    if _dr5 is not _DR_UNSET:
                        return _dr5
                else:

                    def _lr17():
                        nonlocal delta_sqrt_price
                        delta_sqrt_price = amount_after_fee * Q96 // liquidity
                        if delta_sqrt_price > MAX_SQRT_PRICE_IMPACT:
                            return (1, 0)

                        def _lr14():
                            nonlocal output
                            new_sqrt_price = sqrt_price_x96 + delta_sqrt_price
                            if new_sqrt_price <= 0:
                                return (1, 0)
                            output = liquidity * Q96 * delta_sqrt_price // (sqrt_price_x96 * new_sqrt_price)
                            return (0, None)
                        _lrt15 = _lr14()
                        if _lrt15[0]:
                            return (1, _lrt15[1])
                        return (0, None)
                    _lrt18 = _lr17()
                    if _lrt18[0]:
                        return _lrt18[1]
                return max(0, output)
            return _lr24()
        find_best_pool = None

        def _lr20():
            nonlocal find_best_pool

            def find_best_pool(pool_states: dict[str, dict[str, Any]], token_in: str, token_out: str, amount_in: int) -> tuple[str, dict[str, Any], int] | None:
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
                best = candidates = min_liquidity = None

                def _lr21():
                    nonlocal best, candidates, min_liquidity
                    token_in_lower = token_in.lower()
                    token_out_lower = token_out.lower()
                    best = None

                    def _dr2():
                        nonlocal liquidity, pool, pool_addr, zero_for_one

                        def _dr8():
                            candidates: list[tuple[str, dict[str, Any], int, bool, int]] = []
                            return candidates
                        candidates = _dr8()
                        max_liquidity = None

                        def _lr26():
                            nonlocal liquidity, max_liquidity, pool, pool_addr
                            max_liquidity = 0
                            for pool_addr, pool in pool_states.items():
                                t0 = pool.get('token0', '').lower()

                                def _lr11():
                                    nonlocal zero_for_one
                                    t1 = pool.get('token1', '').lower()
                                    if t0 == token_in_lower and t1 == token_out_lower:
                                        zero_for_one = True
                                    elif t0 == token_out_lower and t1 == token_in_lower:
                                        zero_for_one = False
                                    else:
                                        return True
                                if _lr11():
                                    continue
                                liquidity = int(pool.get('liquidity', 0))

                                def _dr6():
                                    nonlocal max_liquidity
                                    max_liquidity = max(max_liquidity, liquidity)
                                    candidates.append((pool_addr, pool, liquidity, zero_for_one, int(pool.get('fee', 3000))))
                                _dr6()
                        _lr26()
                        min_liquidity = max_liquidity // 20
                        return (candidates, min_liquidity)
                    candidates, min_liquidity = _dr2()
                _lr21()
                for pool_addr, pool, liquidity, zero_for_one, fee in candidates:
                    if liquidity < min_liquidity:
                        continue

                    def _dr9():
                        nonlocal best
                        sqrt_price = int(pool.get('sqrtPriceX96', 0))
                        output = None

                        def _lr31():
                            nonlocal best, output
                            output = compute_v3_output(sqrt_price, liquidity, amount_in, zero_for_one, fee)
                            if output > 0 and (best is None or output > best[2]):
                                best = (pool_addr, pool, output)
                        _lr31()
                        return (output, sqrt_price)
                    output, sqrt_price = _dr9()
                return best
        _lr20()
        return (Any, Q96, compute_v3_output, find_best_pool, math)
    Any, Q96, compute_v3_output, find_best_pool, math = _dr7()
_lr19()

def find_best_route(pool_states, token_in, token_out, amount_in, intermediaries=None):
    best_output = None
    best_hops = None
    best_description = None

    def _dr1():
        nonlocal best_description, best_hops, best_output, intermediaries
        "Find the best route for a swap, including multi-hop paths.\n\n    Tries direct pools first, then two-hop routes through common\n    intermediary tokens (WETH, USDC by default).\n\n    Args:\n        pool_states: Pool states keyed by pool address (from RPC queries\n            or MarketSnapshot).\n        token_in: Input token address.\n        token_out: Output token address.\n        amount_in: Input amount in smallest unit.\n        intermediaries: Addresses to try as intermediate hops. These MUST be\n            chain-appropriate (e.g. the chain's WETH/USDC) — the caller is\n            responsible for resolving them per chain. When omitted, only\n            direct pools are considered (no multi-hop). A mainnet default here\n            would silently break multi-hop on every other chain.\n\n    Returns:\n        (output_amount, route_description, hops) or None.\n        Each hop is a dict with pool_addr, pool_state, fee, zero_for_one.\n    "
        direct = token_in_lower = token_out_lower = None

        def _lr10():
            nonlocal best_description, best_hops, best_output, direct, intermediaries, token_in_lower, token_out_lower
            if intermediaries is None:
                intermediaries = []
            token_in_lower = token_in.lower()
            token_out_lower = token_out.lower()
            best_output = 0
            best_description = ''
            best_hops = []
            direct = find_best_pool(pool_states, token_in, token_out, amount_in)
        _lr10()
        if direct is not None:
            addr, state, output = direct

            def _lr25():
                nonlocal best_description, best_hops, best_output
                fee = int(state.get('fee', 3000))
                best_output = output
                best_description = f'direct via {fee / 1000000:.2%} pool'
                best_hops = [{'pool_addr': addr, 'pool_state': state, 'fee': fee}]
            _lr25()
        return (token_in_lower, token_out_lower)
    token_in_lower, token_out_lower = _dr1()
    hop1 = hop2 = state1 = None
    _ = final_output = state2 = None

    def _lr22():
        for mid in intermediaries:

            def _lr16():
                nonlocal _, final_output, state2
                mid_lower = mid.lower()
                if mid_lower == token_in_lower or mid_lower == token_out_lower:
                    return True

                def _lr2():
                    nonlocal _, hop1, hop2, state1
                    hop1 = find_best_pool(pool_states, token_in, mid, amount_in)
                    if hop1 is None:
                        return True
                    _, state1, mid_amount = hop1
                    hop2 = find_best_pool(pool_states, mid, token_out, mid_amount)
                    if hop2 is None:
                        return True
                if _lr2():
                    return True
                _, state2, final_output = hop2
            if _lr16():
                continue
            if final_output > best_output:

                def _dr10():
                    nonlocal best_description, best_hops, best_output

                    def _dr3():
                        fee1 = int(state1.get('fee', 3000))
                        fee2 = int(state2.get('fee', 3000))
                        return (fee1, fee2)
                    fee1, fee2 = _dr3()
                    best_output = final_output

                    def _lr27():
                        nonlocal best_description, best_hops
                        best_description = f'2-hop via {fee1 / 1000000:.2%} + {fee2 / 1000000:.2%} pools'
                        best_hops = [{'pool_addr': hop1[0], 'pool_state': state1, 'fee': fee1}, {'pool_addr': hop2[0], 'pool_state': state2, 'fee': fee2}]
                    _lr27()
                    return _DR_UNSET
                _dr11 = _dr10()
                if _dr11 is not _DR_UNSET:
                    return _dr11
        if best_output <= 0:
            return None
        return (best_output, best_description, best_hops)
    return _lr22()
