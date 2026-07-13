"""Shared Uniswap V3 helpers for miner strategies."""

from __future__ import annotations

import time

from strategies.dex_aggregator.v3_codec import (
    encode_approve,
    encode_exact_input,
    encode_exact_input_single,
    encode_swap_path,
)
from minotaur_subnet.sdk.intent_solver import MarketSnapshot
from minotaur_subnet.shared.types import Interaction

UNISWAP_V3_ROUTER: dict[int, str] = {
    1: "0xE592427A0AEce92De3Edee1F18E0157C05861564",
    8453: "0x2626664c2603336E57B271c5C0b26F421741e481",
    31337: "0xE592427A0AEce92De3Edee1F18E0157C05861564",
}

WETH_ADDRESS: dict[int, str] = {
    1: "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    8453: "0x4200000000000000000000000000000000000006",
    31337: "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
}

FEE_TIERS = [3000, 500, 10000, 100]
DEFAULT_FEE = 3000
DEADLINE_BUFFER = 300


def is_valid_address(addr: object) -> bool:
    """Return whether a value looks like a 20-byte EVM address."""
    return isinstance(addr, str) and addr.startswith("0x") and len(addr) == 42


def compute_deadline(
    snapshot: MarketSnapshot | None,
    *,
    buffer_seconds: int = DEADLINE_BUFFER,
) -> int:
    """Compute a deadline from the market snapshot or wall clock."""
    if snapshot is not None and snapshot.timestamp > 0:
        return snapshot.timestamp + buffer_seconds
    return int(time.time()) + buffer_seconds


def get_uniswap_v3_router(
    chain_id: int,
    snapshot: MarketSnapshot | None,
) -> str:
    """Resolve the router from live snapshot config or static chain defaults."""
    if snapshot is not None and snapshot.dex_config:
        router = snapshot.dex_config.get("router")
        if router and is_valid_address(router):
            return router
    return UNISWAP_V3_ROUTER.get(chain_id, UNISWAP_V3_ROUTER[1])


def get_weth_address(chain_id: int) -> str:
    """Resolve the canonical wrapped native token address for a chain."""
    return WETH_ADDRESS.get(chain_id, WETH_ADDRESS[1])


def find_best_fee(
    token_in: str,
    token_out: str,
    snapshot: MarketSnapshot | None,
    *,
    fallback_fee: int | None = DEFAULT_FEE,
) -> int | None:
    """Select the direct-pool fee tier with the best observed liquidity."""
    if snapshot is None or not snapshot.pool_states:
        return fallback_fee

    in_lower = token_in.lower()
    out_lower = token_out.lower()
    best_fee: int | None = None
    best_liquidity = -1

    for pool in snapshot.pool_states.values():
        token0 = pool.get("token0", "").lower()
        token1 = pool.get("token1", "").lower()
        if (token0 == in_lower and token1 == out_lower) or (
            token0 == out_lower and token1 == in_lower
        ):
            fee = int(pool.get("fee", DEFAULT_FEE))
            liquidity = int(pool.get("liquidity", "0"))
            if liquidity > best_liquidity:
                best_liquidity = liquidity
                best_fee = fee

    if best_fee is not None:
        return best_fee
    return fallback_fee


def build_approval_interaction(
    token_address: str,
    router: str,
    amount: int,
    chain_id: int,
) -> Interaction:
    """Build an ERC-20 approval interaction for a router."""
    return Interaction(
        target=token_address,
        value="0",
        call_data=encode_approve(router, amount),
        chain_id=chain_id,
    )


def build_single_hop_swap_interaction(
    *,
    token_in: str,
    token_out: str,
    fee: int,
    recipient: str,
    deadline: int,
    amount_in: int,
    amount_out_minimum: int,
    router: str,
    chain_id: int,
    sqrt_price_limit_x96: int = 0,
) -> Interaction:
    """Build a single-hop `exactInputSingle` router interaction."""
    return Interaction(
        target=router,
        value="0",
        call_data=encode_exact_input_single(
            token_in=token_in,
            token_out=token_out,
            fee=fee,
            recipient=recipient,
            deadline=deadline,
            amount_in=amount_in,
            amount_out_minimum=amount_out_minimum,
            sqrt_price_limit_x96=sqrt_price_limit_x96,
        ),
        chain_id=chain_id,
    )


def build_multi_hop_swap_interaction(
    *,
    tokens: list[str],
    fees: list[int],
    recipient: str,
    deadline: int,
    amount_in: int,
    amount_out_minimum: int,
    router: str,
    chain_id: int,
) -> Interaction:
    """Build a multi-hop `exactInput` router interaction."""
    return Interaction(
        target=router,
        value="0",
        call_data=encode_exact_input(
            path=encode_swap_path(tokens=tokens, fees=fees),
            recipient=recipient,
            deadline=deadline,
            amount_in=amount_in,
            amount_out_minimum=amount_out_minimum,
        ),
        chain_id=chain_id,
    )
