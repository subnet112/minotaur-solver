"""Static venue/token tables for the labyrinth fill-only-empty layer.

Covers ONLY what the champion stack leaves blind:
  - chain 8453 (Base): the champion's general blindfill is gated chain_id==1,
    so Base orders the engine leaves empty are never swept. We sweep them
    across UniV3 (singles + wide-hub 2-hop), Aerodrome classic (vAMM/sAMM),
    and UniV2-family routers.
  - chain 1: the champion already sweeps V3 singles, PCS V3, UniV2/Sushi and
    Curve-all-pools with WETH/USDC hubs. Our marginal add is V3 2-hop through
    the hubs it does NOT try (USDT/DAI/WBTC) and V2 3-hop paths.

All 4-byte selectors are derived from signature strings at import time —
nothing hand-copied. Router addresses for V3 come from the champion's own
production tables (strategies/dex_aggregator/swap_solver.py).
"""
from __future__ import annotations

from eth_utils import keccak


def sel(sig: str) -> bytes:
    """4-byte selector from a canonical signature string."""
    return keccak(sig.encode())[:4]


MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"

SEL_AGG3 = sel("aggregate3((address,bool,bytes)[])")
SEL_V3_QUOTE_PATH = sel("quoteExactInput(bytes,uint256)")
SEL_V2_AMOUNTS = sel("getAmountsOut(uint256,address[])")
SEL_AERO_AMOUNTS = sel("getAmountsOut(uint256,(address,address,bool,address)[])")
SEL_V2_SWAP = sel("swapExactTokensForTokens(uint256,uint256,address[],address,uint256)")
SEL_AERO_SWAP = sel(
    "swapExactTokensForTokens(uint256,uint256,(address,address,bool,address)[],address,uint256)"
)
SEL_V3_EXACT_INPUT_02 = sel("exactInput((bytes,address,uint256,uint256))")

# --- chain 1 tokens ---
WETH1 = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
USDC1 = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
USDT1 = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
DAI1 = "0x6B175474E89094C44Da98b954EedeAC495271d0F"
WBTC1 = "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"

# --- chain 8453 (Base) tokens ---
WETH8 = "0x4200000000000000000000000000000000000006"
USDC8 = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDBC8 = "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA"
DAI8 = "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb"
CBBTC8 = "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf"
AERO8 = "0x940181a94A35A4569E4529A3CDfB74e38FD98631"

CH: dict[int, dict] = {
    1: {
        # champion sweeps V3 singles + WETH/USDC-hub 2-hop already; add the
        # hubs it never tries.
        "v3_quoter": "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",
        "v3_router": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        "v3_single_fees": (),
        "v3_hubs": (USDT1, DAI1, WBTC1),
        "v3_hub_fees": (500, 3000),
        "v2_routers": (
            "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",  # UniV2 Router02
            "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F",  # Sushi Router
        ),
        # champion's V2 sweep is direct-path; add 3-hop mid pairs.
        "v2_hubs": (),
        "v2_three_hop": (
            (WETH1, USDC1),
            (USDC1, WETH1),
            (WETH1, DAI1),
            (WETH1, USDT1),
            (DAI1, USDC1),
            (USDC1, USDT1),
        ),
        "aero_router": None,
        "aero_factory": None,
        "aero_hubs": (),
    },
    8453: {
        "v3_quoter": "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",  # QuoterV2
        "v3_router": "0x2626664c2603336E57B271c5C0b26F421741e481",  # SwapRouter02
        "v3_single_fees": (100, 500, 3000, 10000),
        "v3_hubs": (WETH8, USDC8, USDBC8, CBBTC8, DAI8, AERO8),
        "v3_hub_fees": (500, 3000),
        "v2_routers": (
            "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24",  # UniV2 Router02 (Base)
            "0x327Df1E6de05895d2ab08513aaDD9313Fe505d86",  # BaseSwap
        ),
        "v2_hubs": (WETH8, USDC8),
        "v2_three_hop": (
            (WETH8, USDC8),
            (USDC8, WETH8),
        ),
        "aero_router": "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",
        "aero_factory": "0x420DD381b31aEf6683db6B902084cB0FFECe40Da",
        "aero_hubs": (WETH8, USDC8, USDBC8),
    },
}
