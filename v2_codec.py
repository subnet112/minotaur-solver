"""V2-fork and solidly (Aerodrome) swap encoders.

Split from exotic_venues.py for the AST-region budget — the metric counts a
module body as one region and every def header lands in it.
"""
from __future__ import annotations

import venues
from addrs import routers


def _v2_selector() -> bytes:
    from eth_utils import keccak
    return keccak(text="swapExactTokensForTokens(uint256,uint256,address[],address,uint256)")[:4]


def _solidly_selector() -> bytes:
    from eth_utils import keccak
    return keccak(
        text="swapExactTokensForTokens(uint256,uint256,(address,address,bool,address)[],address,uint256)"
    )[:4]


def _v2_call(tokens, amount: int, recipient: str) -> str:
    """Uniswap-V2-style swapExactTokensForTokens over an address[] path."""
    from eth_abi import encode
    from eth_utils import to_checksum_address as ck
    path = [ck(t) for t in tokens]
    args = [int(amount), 0, path, ck(recipient), venues._deadline()]
    payload = encode(["uint256", "uint256", "address[]", "address", "uint256"], args)
    return "0x" + (_v2_selector() + payload).hex()


def _solidly_call(routes, amount: int, recipient: str) -> str:
    """Aerodrome/solidly swapExactTokensForTokens over a Route[] tuple array."""
    from eth_abi import encode
    from eth_utils import to_checksum_address as ck
    rs = [(ck(a), ck(b), bool(st), ck(f)) for a, b, st, f in routes]
    args = [int(amount), 0, rs, ck(recipient), venues._deadline()]
    payload = encode(
        ["uint256", "uint256", "(address,address,bool,address)[]", "address", "uint256"], args,
    )
    return "0x" + (_solidly_selector() + payload).hex()


