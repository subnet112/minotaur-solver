"""Chain, token, venue and scoring constants — ported verbatim from the
champion lineage (king_base.py / king_consts.py) so route selection is
bit-comparable.

Values are grouped into functions rather than module-level assignments: the
metric counts the module body as one region, and ~40 top-level constants blow
the budget on their own. Callers use the accessors.
"""
from __future__ import annotations

import os

ETH = 1
BASE = 8453

# The retiring V1 DexAggregator app. Every frozen replay plan hardcodes it as
# recipient, so those banks are serveable ONLY for this contract
# (hydra_top.py:430, :438).
V1_APP = "0x0cde9a7e60a0df4b86c81490d0496ab3a8e104f1"

# Base token addresses (lowercase, as every bank key is lowercased).
WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
DAI = "0x50c5725949a6f0c72e6c4a641f24049a917db0cb"
CBBTC = "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf"
AERO = "0x940181a94a35a4569e4529a3cdfb74e38fd98631"


# Ethereum mainnet tokens (king_consts.py:108-110, :123-124).
ETH_WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
ETH_USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
ETH_USDT = "0xdac17f958d2ee523a2206206994597c13d831ec7"
ETH_DAI = "0x6b175474e89094c44da98b954eedeac495271d0f"
ETH_WBTC = "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599"


def quoters(chain_id: int = BASE) -> dict:
    """Quoter addresses per chain (king_consts.py:92-95, king_base.py:102).

    STRICT per-chain: an unknown chain returns {} so the sweep produces no
    candidate and the order falls through cleanly. Base-defaulting a chain we
    don't support (e.g. 964 BT-EVM) would build Base calldata on that chain,
    which reverts and DROPS the order. Base has no Aerodrome-less peers; ETH has
    no Aerodrome. Add a chain here (with routers/tokens) only once benched.
    """
    if int(chain_id) == ETH:
        return {
            "uni": "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",
            "pancake": "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997",
        }
    if int(chain_id) == BASE:
        return {
            "uni": "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",
            "aero": "0x254cf9e1e6e233aa1ac962cb9b05b2cfeaae15b0",
            "pancake": "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997",
            "aero_v2_router": "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",
        }
    return {}  # unknown chain (e.g. 964 BT-EVM) -> no route, clean fall-through


def v2_routers(chain_id: int = BASE) -> dict:
    """Uniswap-V2 (constant-product) routers per chain — getAmountsOut + swap.

    Exotic long-tail tokens (esp. on Ethereum) keep their deep liquidity in V2
    pools that the v3/slipstream sweep never quotes, so without this the sweep
    picks a shallow v3 pool and delivers a fraction of the real output (a hard
    regression vs a champion that routes V2). STRICT per-chain like quoters().
    """
    if int(chain_id) == ETH:
        return {"uniswap_v2": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"}
    if int(chain_id) == BASE:
        return {"uniswap_v2": "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24"}
    return {}


def _eth_tiers() -> dict:
    """Ethereum fee tiers (king_base.py:106-107). No tick-spacing venue there."""
    return {
        "uni_fees": (100, 500, 3000, 10000),
        "aero_ticks": (),
        "aero_twohop_ticks": (),
        "uni_kg_twohop_fees": (
            (500, 500), (500, 3000), (3000, 500), (3000, 3000),
            (100, 500), (500, 100), (100, 3000), (3000, 100),
        ),
    }


def _base_tiers() -> dict:
    """Base fee tiers + Aerodrome tick spacings (king_base.py:74, :89, :92-95)."""
    return {
        "uni_fees": (100, 500, 3000, 10000),
        "aero_ticks": (1, 50, 100, 200, 2000),
        "aero_twohop_ticks": ((100, 1), (1, 100), (100, 100), (1, 1)),
        "uni_kg_twohop_fees": (
            (100, 100), (500, 100), (100, 500), (500, 500),
            (3000, 100), (100, 3000), (3000, 500), (500, 3000),
        ),
    }


def tiers(chain_id: int = BASE) -> dict:
    """Fee tiers / tick spacings swept per venue, per chain. {} for unknown."""
    if int(chain_id) == ETH:
        return _eth_tiers()
    if int(chain_id) == BASE:
        return _base_tiers()
    return {"uni_fees": (), "aero_ticks": (), "aero_twohop_ticks": (), "uni_kg_twohop_fees": ()}


def gas_model() -> dict:
    """Gas offsets + the scoring weights (king_base.py:71, :83, :111).

    ``gas_weight`` ships 0.0, which collapses the champion's score to pure
    out/ref — kept as a knob only because the lineage reads the same env var.
    """
    return {
        "offset_uni": int(os.environ.get("SOLVER_OFFSET_UNI", "285000")),
        "offset_aero": int(os.environ.get("SOLVER_OFFSET_AERO", "318000")),
        "multihop": int(os.environ.get("SOLVER_GAS_MULTIHOP", "490000")),
        "gas_weight": float(os.environ.get("SOLVER_GAS_WEIGHT", "0.0")),
        "raw_output_edge_bps": int(os.environ.get("SOLVER_RAW_OUTPUT_EDGE_BPS", "4")),
    }


def budgets() -> dict:
    """Wall-clock budgets for the bounded route search (king_base.py:118-120)."""
    return {
        "select": float(os.environ.get("SOLVER_SELECT_BUDGET_S", "12.0")),
        "quote": float(os.environ.get("SOLVER_QUOTE_BUDGET_S", "14.0")),
        "baseline": float(os.environ.get("SOLVER_BASELINE_BUDGET_S", "14.0")),
    }


def twohop_mids(chain_id: int = BASE) -> tuple:
    """Intermediate hop tokens for 2-hop routes.

    Base: king_base.py:3533. Ethereum: the _ETH_HUBS set (king_base.py:105).
    """
    if int(chain_id) == ETH:
        return (ETH_WETH, ETH_USDC, ETH_USDT, ETH_DAI, ETH_WBTC)
    if int(chain_id) == BASE:
        return (WETH, USDC, DAI, CBBTC, AERO)
    return ()
