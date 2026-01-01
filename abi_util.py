"""ABI plumbing shared by the quoters — selectors, packed paths, eth_call.

Split out of quotes.py for the AST-region budget (the metric counts a module
body as one region and every def header lands in it).
"""
from __future__ import annotations


def _selectors() -> dict:
    from eth_utils import keccak
    return {
        "uni": keccak(text="quoteExactInputSingle((address,address,uint256,uint24,uint160))")[:4],
        "uni_path": keccak(text="quoteExactInput(bytes,uint256)")[:4],
        "aero": keccak(text="quoteExactInputSingle((address,address,uint256,int24,uint160))")[:4],
        "aero_v2": keccak(text="getAmountsOut(uint256,(address,address,bool,address)[])")[:4],
        "uni_v2": keccak(text="getAmountsOut(uint256,address[])")[:4],
    }


def encode_path(tokens, params, width: int = 3) -> bytes:
    """Uniswap/Aerodrome packed path: token (20b) [+ param (3b)] token ...

    Aerodrome masks tickSpacing to 24 bits so negative ticks wrap the same way
    the lineage does (king_base.py:3373).
    """
    path = b""
    for i, token in enumerate(tokens):
        addr = str(token)
        path += bytes.fromhex(addr[2:] if addr.startswith("0x") else addr)
        if i < len(params):
            path += (int(params[i]) & 0xFFFFFF).to_bytes(width, byteorder="big")
    return path


def _call(w3, to: str, data: bytes):
    from eth_utils import to_checksum_address
    return w3.eth.call({"to": to_checksum_address(to), "data": "0x" + data.hex()})


