"""Router addresses and function selectors, per chain.

Split from venues.py for the AST-region budget: the metric counts a module body
as one region, and the tables plus every builder's def header exceeded it.
"""
from __future__ import annotations

def routers(chain_id: int=8453) -> dict:
    """Router addresses per venue, PER CHAIN.

    Chain-awareness is load-bearing: Base's SwapRouter02 (0x2626664c…) does not
    exist on Ethereum, so sending a mainnet swap there executes nothing and the
    order silently drops. Mainnet uses SwapRouter V1 (0xE592427A…) — see
    swap_solver.py:37 UNISWAP_V3_ROUTERS. Aerodrome is Base-only.
    """
    if int(chain_id) == 1:
        return {'uniswap_v3': '0xE592427A0AEce92De3Edee1F18E0157C05861564', 'pancake_v3': '0x1b81D678ffb9C0263b24A97847620C99d213eB14', 'uniswap_v2': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'}
    if int(chain_id) == 8453:
        return {'uniswap_v3': '0x2626664c2603336E57B271c5C0b26F421741e481', 'aerodrome_slipstream': '0xBE6D8f0d05cC4be24d5167a3eF062215bE6D18a5', 'aerodrome_v2': '0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43', 'pancake_v3': '0x1b81D678ffb9C0263b24A97847620C99d213eB14', 'uniswap_v2': '0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24'}
    return {}

def selectors() -> dict:
    return {'v3_single_v2router': bytes.fromhex('04e45aaf'), 'v3_single_v1router': bytes.fromhex('414bf389'), 'exact_input': bytes.fromhex('c04b8d59'), 'slipstream_single': bytes.fromhex('a026383e'), 'approve': bytes.fromhex('095ea7b3')}