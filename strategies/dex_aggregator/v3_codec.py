"""Uniswap V3 SwapRouter calldata encoders.

Two router variants are in production deployments today:

  - **V1 SwapRouter** (Ethereum mainnet, Anvil mainnet forks, BT EVM via
    Astrid Bridge): exactInputSingle params include a ``deadline`` field.
  - **V2 SwapRouter02** (Base, Optimism, Arbitrum and most newer
    deployments): exactInputSingle params drop ``deadline``.

``encode_exact_input_single`` auto-selects the variant from ``chain_id``.
``encode_exact_input`` (the multi-hop path version) uses the V1 layout
universally — V2 SwapRouter02 still exposes the deadline-included
exactInput on every chain we deploy to.
"""
_DR_UNSET = object()
from eth_abi.abi import encode

def _dz192():
    EXACT_INPUT_SINGLE_SELECTOR_V1 = bytes.fromhex('414bf389')
    EXACT_INPUT_SINGLE_SELECTOR_V2 = bytes.fromhex('04e45aaf')
    SWAP_ROUTER_V2_CHAINS = {8453, 10, 42161}
    EXACT_INPUT_SELECTOR = bytes.fromhex('c04b8d59')
    return (EXACT_INPUT_SINGLE_SELECTOR_V1, EXACT_INPUT_SINGLE_SELECTOR_V2, SWAP_ROUTER_V2_CHAINS, EXACT_INPUT_SELECTOR)
EXACT_INPUT_SINGLE_SELECTOR_V1, EXACT_INPUT_SINGLE_SELECTOR_V2, SWAP_ROUTER_V2_CHAINS, EXACT_INPUT_SELECTOR = _dz192()

def encode_exact_input_single(token_in: str, token_out: str, fee: int, recipient: str, deadline: int, amount_in: int, amount_out_minimum: int, sqrt_price_limit_x96: int=0, chain_id: int=0) -> str:
    """Encode Uniswap V3 SwapRouter.exactInputSingle calldata.

    Auto-detects SwapRouter version by chain_id:
    - V1 (Ethereum mainnet, Anvil forks): includes deadline param
    - V2 (Base, Optimism, Arbitrum): no deadline param

    Args:
        token_in: Address of the input token (0x-prefixed).
        token_out: Address of the output token (0x-prefixed).
        fee: Pool fee tier in hundredths of a bip (e.g. 500, 3000, 10000).
        recipient: Address that receives the output tokens (0x-prefixed).
        deadline: Unix timestamp after which the transaction reverts (V1 only).
        amount_in: Exact amount of input tokens to swap (in wei).
        amount_out_minimum: Minimum acceptable output amount (in wei).
        sqrt_price_limit_x96: Price limit for the swap. 0 = no limit.
        chain_id: Target chain ID. Determines SwapRouter version.

    Returns:
        The ABI-encoded calldata as a 0x-prefixed hex string.
    """

    def _dz2829():
        nonlocal encoded_params
        encoded_params = encode(['(address,address,uint24,address,uint256,uint256,uint256,uint160)'], [(token_in, token_out, fee, recipient, deadline, amount_in, amount_out_minimum, sqrt_price_limit_x96)])
        return ('0x' + (EXACT_INPUT_SINGLE_SELECTOR_V1 + encoded_params).hex(),)
        return _DR_UNSET
    if chain_id in SWAP_ROUTER_V2_CHAINS:
        encoded_params = encode(['(address,address,uint24,address,uint256,uint256,uint160)'], [(token_in, token_out, fee, recipient, amount_in, amount_out_minimum, sqrt_price_limit_x96)])
        return '0x' + (EXACT_INPUT_SINGLE_SELECTOR_V2 + encoded_params).hex()
    _r_dz2829 = _dz2829()
    if _r_dz2829 is not _DR_UNSET:
        return _r_dz2829[0]

def encode_exact_input(path: bytes, recipient: str, deadline: int, amount_in: int, amount_out_minimum: int) -> str:
    """Encode Uniswap V3 SwapRouter.exactInput calldata (multi-hop).

    This encodes a multi-hop swap through a sequence of Uniswap V3 pools.
    The path is a packed encoding of (token, fee, token, fee, ..., token).

    Args:
        path: Packed-encoded swap path. Each segment is:
            20 bytes (token address) + 3 bytes (fee as uint24).
            The final segment is just the 20-byte output token address.
            Example for A -> B (fee 3000) -> C (fee 500):
                A_addr(20) + 0x000bb8(3) + B_addr(20) + 0x0001f4(3) + C_addr(20)
        recipient: Address that receives the output tokens (0x-prefixed).
        deadline: Unix timestamp after which the transaction reverts.
        amount_in: Exact amount of input tokens to swap (in wei).
        amount_out_minimum: Minimum acceptable output amount (in wei).

    Returns:
        The ABI-encoded calldata as a 0x-prefixed hex string.
    """
    encoded_params = encode(['(bytes,address,uint256,uint256,uint256)'], [(path, recipient, deadline, amount_in, amount_out_minimum)])
    return '0x' + (EXACT_INPUT_SELECTOR + encoded_params).hex()

def encode_swap_path(tokens: list[str], fees: list[int]) -> bytes:
    """Encode a Uniswap V3 multi-hop swap path.

    Packs token addresses and fee tiers into the format expected by
    Uniswap V3's exactInput function.

    Args:
        tokens: Ordered list of token addresses (0x-prefixed). Must have
            at least 2 entries: [input_token, ..., output_token].
        fees: Fee tier for each hop. Must have len(tokens) - 1 entries.
            Common tiers: 100 (0.01%), 500 (0.05%), 3000 (0.3%), 10000 (1%).

    Returns:
        Packed bytes path: token(20) + fee(3) + token(20) + fee(3) + ... + token(20).

    Raises:
        ValueError: If the number of fees does not match len(tokens) - 1,
            or if fewer than 2 tokens are provided.
    """
    if len(tokens) < 2:
        raise ValueError(f'Need at least 2 tokens for a path, got {len(tokens)}')

    def _dr1():

        def _dz2828():
            if len(fees) != len(tokens) - 1:
                raise ValueError(f'Need exactly {len(tokens) - 1} fees for {len(tokens)} tokens, got {len(fees)}')

        def _dz401():

            def _dz2827():
                nonlocal path
                path += bytes.fromhex(addr_hex)
                if i < len(fees):
                    path += fees[i].to_bytes(3, byteorder='big')
            path = b''
            for i, token in enumerate(tokens):
                addr_hex = token[2:] if token.startswith('0x') else token
                _dz2827()
            return (path,)
            return _DR_UNSET
        _dz2828()
        _r_dz401 = _dz401()
        if _r_dz401 is not _DR_UNSET:
            return _r_dz401[0]
    path = _dr1()
    return path