"""ABI encoding utilities for ERC-20 interactions.

Generic, app-agnostic helpers. App-specific encoders (e.g. Uniswap V3
SwapRouter calldata) live alongside their strategy module — for the DEX
aggregator, see ``strategies/dex_aggregator/v3_codec.py``.

Function selectors (first 4 bytes of keccak256 of the signature):
    approve(address,uint256)  ->  0x095ea7b3
"""

from eth_abi.abi import encode

# ---- Function selectors (pre-computed keccak256 of canonical signatures) ----

# ERC-20 approve(address,uint256)
APPROVE_SELECTOR = bytes.fromhex("095ea7b3")


def encode_approve(spender: str, amount: int) -> str:
    """Encode ERC-20 approve(spender, amount) calldata.

    Args:
        spender: The address being approved to spend tokens (0x-prefixed).
        amount: The token amount to approve, in the token's smallest unit (wei).

    Returns:
        The ABI-encoded calldata as a 0x-prefixed hex string.
    """
    encoded_params = encode(
        ["address", "uint256"],
        [spender, amount],
    )
    return "0x" + (APPROVE_SELECTOR + encoded_params).hex()
