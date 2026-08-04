"""Selectors, fee tiers, venue addresses and per-chain config.

A module top level is itself a region and every top-level assignment counts in
it, so the constant block lives here rather than inflating the venue module.
"""
from __future__ import annotations

DEADLINE = 9999999999
BUDGET_S = 6.0
_SEARCH_DEADLINE = [0.0]   # mutable cell: set by best_route, read by eth_call

# ---- selectors ----
S_APPROVE = "095ea7b3"
S_V3_SINGLE_V1 = "414bf389"   # mainnet SwapRouter exactInputSingle (8-field, deadline)
S_V3_SINGLE_02 = "04e45aaf"   # SwapRouter02 exactInputSingle (7-field, no deadline)
S_V3_PATH_V1 = "c04b8d59"     # mainnet exactInput (path,recipient,deadline,amountIn,min)
S_V3_PATH_02 = "b858183f"     # SwapRouter02 exactInput (path,recipient,amountIn,min)
S_V2_SWAP = "38ed1739"        # swapExactTokensForTokens
S_QUOTE_SINGLE = "c6a5026a"   # QuoterV2 quoteExactInputSingle((address,address,uint256,uint24,uint160))
S_QUOTE_PATH = "cdca1753"     # QuoterV2 quoteExactInput(bytes,uint256)
S_V2_AMOUNTS = "d06ca61f"     # getAmountsOut(uint256,address[])
S_CURVE_FIND = "a87df06c"     # MetaRegistry find_pool_for_coins(address,address)
S_CURVE_IDX = "eb85226d"      # MetaRegistry get_coin_indices(address,address,address)
S_CURVE_GETDY = "5e0d443f"    # pool get_dy(int128,int128,uint256)
S_CURVE_EXCH = "3df02124"     # pool exchange(int128,int128,uint256,uint256)
S_CURVE_EXCH_RECV = "ddc1f59d" # pool exchange(int128,int128,uint256,uint256,address) -> pays receiver
S_TRANSFER = "a9059cbb"       # ERC20 transfer
S_AERO_GAO = "5509a1ac"       # Aerodrome Router getAmountsOut(uint256,(address,address,bool,address)[])
S_AERO_SWAP = "cac88ea9"      # swapExactTokensForTokens(uint256,uint256,(address,address,bool,address)[],address,uint256)

FEES = (100, 500, 3000, 10000)

# Aerodrome (Base 8453) — the dominant Base DEX (Solidly fork). Verified on-fork:
# Router + PoolFactory hold most Base liquidity that Uniswap-on-Base misses.
AERO_ROUTER = "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43"
AERO_FACTORY = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"

# Per-chain venue config. Built by functions rather than one module-level literal:
# data literals count into their ENCLOSING region, so a big top-level dict inflates
# the module region — and the finalist tie-break ranks by ascending max_region_nodes
# ("VIA SIMPLER CODE" on the dashboard). Same keys/values as the previous literal.

def _cfg_eth():
    return {
        "quoter": "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",
        "v3router": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        "v3sel_single": S_V3_SINGLE_V1, "v3sel_path": S_V3_PATH_V1, "v3_deadline": True,
        "v2routers": ["0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",   # Uniswap V2
                      "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F"],  # Sushi V2
        # Wider hub set: the chain-1 corpus tail (wstETH, stETH, PYUSD, CRV, LINK,
        # crvUSD...) frequently routes through USDT/DAI/WBTC rather than WETH/USDC,
        # so a WETH+USDC-only hub list silently misses those blind spots.
        "hubs": ["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",       # WETH
                 "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",       # USDC
                 "0xdAC17F958D2ee523a2206206994597C13D831ec7",       # USDT
                 "0x6B175474E89094C44Da98b954EedeAC495271d0F",       # DAI
                 "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"],      # WBTC
        "curve_metareg": "0xF98B45FA17DE75FB1aD0e7aFD971b0ca00e379fC",
    }


def _cfg_base():
    return {
        "quoter": "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",
        "v3router": "0x2626664c2603336E57B271c5C0b26F421741e481",
        "v3sel_single": S_V3_SINGLE_02, "v3sel_path": S_V3_PATH_02, "v3_deadline": False,
        "v2routers": ["0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24"],  # Uniswap V2 (Base)
        "hubs": ["0x4200000000000000000000000000000000000006",        # WETH
                 "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"],       # USDC
        "curve_metareg": None,
    }


CHAINS = {1: _cfg_eth(), 8453: _cfg_base()}


