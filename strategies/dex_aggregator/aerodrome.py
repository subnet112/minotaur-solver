"""Aerodrome Slipstream (concentrated liquidity) integration.

Aerodrome's CL pools are a Uniswap V3 fork. Pool state has the same
shape (sqrtPriceX96, liquidity, tick, fee) so `pool_math.compute_v3_output`
works directly. The differences live at the edges:

  - Pool factory uses ``getPool(t0, t1, tickSpacing)`` (int24) instead of
    Uni V3's ``getPool(t0, t1, fee)`` (uint24).
  - SwapRouter uses ``tickSpacing`` (int24) where Uni V3's uses ``fee``
    (uint24) in both ``exactInputSingle`` and the packed ``exactInput`` path.

We discover pools across all live tickSpacings, tag the resulting pool
states with ``dex='aerodrome_slipstream'`` so route execution can dispatch
to the correct router, and provide encoders for the Slipstream router's
swap calldata.
"""
from __future__ import annotations
_DR_UNSET = object()
import logging
import time
from typing import Any, Callable
from eth_abi.abi import encode as abi_encode
def _aero_c():
    logger = logging.getLogger(__name__)
    AERODROME_SLIPSTREAM_FACTORY: dict[int, str] = {8453: '0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A'}
    AERODROME_SLIPSTREAM_ROUTER: dict[int, str] = {8453: '0xBE6D8f0d05cC4be24d5167a3eF062215bE6D18a5'}
    AERODROME_TICK_SPACINGS: tuple[int, ...] = (1, 50, 100, 200, 2000)
    globals().update(locals())
_aero_c()

def _dr4():
    def _fw2():
        _FACTORY_ABI = [{'inputs': [{'internalType': 'address', 'name': 'tokenA', 'type': 'address'}, {'internalType': 'address', 'name': 'tokenB', 'type': 'address'}, {'internalType': 'int24', 'name': 'tickSpacing', 'type': 'int24'}], 'name': 'getPool', 'outputs': [{'internalType': 'address', 'name': 'pool', 'type': 'address'}], 'stateMutability': 'view', 'type': 'function'}]
        return (_FACTORY_ABI,)
    _FACTORY_ABI, = _fw2()

    def _dr2():
        discover_pools_for_pair = None

        def _dr11():
            nonlocal discover_pools_for_pair
            def _fh1():
                return [{'inputs': [], 'name': 'slot0', 'outputs': [{'internalType': 'uint160', 'name': 'sqrtPriceX96', 'type': 'uint160'}, {'internalType': 'int24', 'name': 'tick', 'type': 'int24'}, {'internalType': 'uint16', 'name': 'observationIndex', 'type': 'uint16'}, {'internalType': 'uint16', 'name': 'observationCardinality', 'type': 'uint16'}, {'internalType': 'uint16', 'name': 'observationCardinalityNext', 'type': 'uint16'}, {'internalType': 'bool', 'name': 'unlocked', 'type': 'bool'}], 'stateMutability': 'view', 'type': 'function'}, {'inputs': [], 'name': 'liquidity', 'outputs': [{'internalType': 'uint128', 'name': '', 'type': 'uint128'}], 'stateMutability': 'view', 'type': 'function'}, {'inputs': [], 'name': 'fee', 'outputs': [{'internalType': 'uint24', 'name': '', 'type': 'uint24'}], 'stateMutability': 'view', 'type': 'function'}]
            def _fh2():
                return [{'inputs': [], 'name': 'token0', 'outputs': [{'internalType': 'address', 'name': '', 'type': 'address'}], 'stateMutability': 'view', 'type': 'function'}, {'inputs': [], 'name': 'token1', 'outputs': [{'internalType': 'address', 'name': '', 'type': 'address'}], 'stateMutability': 'view', 'type': 'function'}, {'inputs': [], 'name': 'tickSpacing', 'outputs': [{'internalType': 'int24', 'name': '', 'type': 'int24'}], 'stateMutability': 'view', 'type': 'function'}]
            _POOL_ABI = _fh1() + _fh2()

            def _dr1():
                _ZERO_ADDRESS = '0x' + '0' * 40

                def _is_supported_chain(chain_id: int) -> bool:
                    return chain_id in AERODROME_SLIPSTREAM_FACTORY

                def _query_slipstream_pool_state(w3: Any, pool_address: str, base_query_pool_state: Callable[[Any, str], dict[str, Any] | None] | None=None) -> dict[str, Any] | None:
                    """Read a Slipstream pool's state via the Slipstream-specific ABI.

    Cannot reuse the Uni V3 reader because Slipstream's ``slot0`` drops
    the ``uint8 feeProtocol`` byte present in Uni V3 — the V3 ABI fails
    to decode.

    ``base_query_pool_state`` is accepted for symmetry with the original
    plumbing but is unused; kept so callers don't have to branch.
    """
                    del base_query_pool_state
                    try:

                        def _dr9():
                            pool = w3.eth.contract(address=w3.to_checksum_address(pool_address), abi=_POOL_ABI)
                            slot0 = pool.functions.slot0().call()
                            def _fw3():
                                liquidity = pool.functions.liquidity().call()
                                fee = pool.functions.fee().call()
                                token0 = pool.functions.token0().call()
                                token1 = pool.functions.token1().call()
                                tick_spacing = pool.functions.tickSpacing().call()
                                return ((fee, liquidity, slot0, tick_spacing, token0, token1),)
                            _fwr3 = _fw3()
                            if _fwr3 is not None:
                                return _fwr3[0]
                        fee, liquidity, slot0, tick_spacing, token0, token1 = _dr9()
                    except Exception as exc:
                        logger.debug('Slipstream pool query failed for %s: %s', pool_address, exc)
                        return None
                    return {'token0': token0, 'token1': token1, 'fee': int(fee), 'tickSpacing': int(tick_spacing), 'sqrtPriceX96': str(slot0[0]), 'tick': int(slot0[1]), 'liquidity': str(liquidity), 'dex': 'aerodrome_slipstream'}

                def _dr7():

                    def discover_pools_for_pair(w3, chain_id, token_a, token_b, pool_states, base_query_pool_state, discovery_cache=None, cache_ttl=60.0):
                        """Discover Aerodrome Slipstream pools for a token pair.

    Mirrors ``BaselineSwapSolver._discover_pools_for_pair`` but uses the
    Slipstream factory's ``getPool(address, address, int24)`` signature,
    iterating through ``AERODROME_TICK_SPACINGS``.

    The discovered pool states are merged into ``pool_states`` (mutated
    in place) with the ``dex='aerodrome_slipstream'`` marker.
    """
                        if not _is_supported_chain(chain_id):
                            return pool_states
                        factory_addr = AERODROME_SLIPSTREAM_FACTORY[chain_id]
                        if w3 is None or w3.eth.get_code(w3.to_checksum_address(factory_addr)) == b'':
                            return pool_states
                        a_lower, b_lower = (token_a.lower(), token_b.lower())

                        def _dr5():
                            cache_key = (chain_id, 'aero_slip', min(a_lower, b_lower), max(a_lower, b_lower))
                            now = time.time()
                            if discovery_cache is not None:
                                if now - discovery_cache.get(cache_key, 0) < cache_ttl:
                                    return pool_states
                            factory = w3.eth.contract(address=w3.to_checksum_address(factory_addr), abi=_FACTORY_ABI)

                            def _dr3():
                                discovered = 0

                                def _dr10():
                                    rpc_errors = 0
                                    for ts in AERODROME_TICK_SPACINGS:
                                        try:
                                            pool_addr = factory.functions.getPool(w3.to_checksum_address(token_a), w3.to_checksum_address(token_b), ts).call()
                                        except Exception as exc:
                                            logger.debug('Aerodrome factory.getPool(%s, %s, ts=%d) failed: %s', token_a[:10], token_b[:10], ts, exc)
                                            rpc_errors += 1
                                            continue
                                        def _fw3():
                                            if not pool_addr or pool_addr == _ZERO_ADDRESS:
                                                return ('c',)
                                            if pool_addr in pool_states or pool_addr.lower() in {k.lower() for k in pool_states}:
                                                return ('c',)
                                        if _fw3() is not None:
                                            continue

                                        def _dr8():
                                            nonlocal discovered
                                            state = _query_slipstream_pool_state(w3, pool_addr, base_query_pool_state)
                                            if state is not None:
                                                pool_states[pool_addr] = state
                                                discovered += 1
                                            return state
                                        state = _dr8()
                                    return rpc_errors
                                rpc_errors = _dr10()
                                if discovery_cache is not None and rpc_errors < len(AERODROME_TICK_SPACINGS):
                                    discovery_cache[cache_key] = now
                                return discovered
                            def _fw1():
                                discovered = _dr3()
                                if discovered > 0:
                                    logger.debug('Aerodrome: %d pools for %s/%s on chain %d', discovered, token_a[:10], token_b[:10], chain_id)
                                return (discovered,)
                            discovered, = _fw1()
                            return pool_states
                            return _DR_UNSET
                        _dr6 = _dr5()
                        if _dr6 is not _DR_UNSET:
                            return _dr6
                    return discover_pools_for_pair
                discover_pools_for_pair = _dr7()
                return discover_pools_for_pair
            discover_pools_for_pair = _dr1()
            return _DR_UNSET
        _dr12 = _dr11()
        if _dr12 is not _DR_UNSET:
            return _dr12
        _EXACT_INPUT_SINGLE_SELECTOR = bytes.fromhex('a026383e')
        return (_EXACT_INPUT_SINGLE_SELECTOR, discover_pools_for_pair)
    _EXACT_INPUT_SINGLE_SELECTOR, discover_pools_for_pair = _dr2()
    _EXACT_INPUT_SELECTOR = bytes.fromhex('c04b8d59')

    def encode_exact_input_single(token_in: str, token_out: str, tick_spacing: int, recipient: str, deadline: int, amount_in: int, amount_out_minimum: int, sqrt_price_limit_x96: int=0) -> str:
        """Encode Slipstream SwapRouter.exactInputSingle calldata."""
        encoded = abi_encode(['(address,address,int24,address,uint256,uint256,uint256,uint160)'], [(token_in, token_out, int(tick_spacing), recipient, int(deadline), int(amount_in), int(amount_out_minimum), int(sqrt_price_limit_x96))])
        return '0x' + (_EXACT_INPUT_SINGLE_SELECTOR + encoded).hex()

    def encode_path(tokens: list[str], tick_spacings: list[int]) -> bytes:
        """Pack tokens + tickSpacings into the Slipstream exactInput path.

    Layout: token0 (20B) + ts0 (3B int24) + token1 (20B) + ts1 (3B) + …

    The 3-byte tickSpacing is two's-complement big-endian, matching how
    Uniswap V3 packs its 3-byte fee field.
    """
        if len(tokens) < 2 or len(tick_spacings) != len(tokens) - 1:
            raise ValueError('encode_path: need len(tokens) == len(tick_spacings) + 1')
        def _fw1():
            out = bytearray()
            for i, tok in enumerate(tokens):
                addr_hex = tok[2:] if tok.startswith('0x') else tok
                out.extend(bytes.fromhex(addr_hex.zfill(40)))
                if i < len(tick_spacings):
                    ts = int(tick_spacings[i])
                    out.extend((ts & 16777215).to_bytes(3, 'big'))
            return (out,)
        out, = _fw1()
        return bytes(out)
    return (_EXACT_INPUT_SELECTOR, discover_pools_for_pair, encode_exact_input_single, encode_path)
_EXACT_INPUT_SELECTOR, discover_pools_for_pair, encode_exact_input_single, encode_path = _dr4()

def encode_exact_input(path: bytes, recipient: str, deadline: int, amount_in: int, amount_out_minimum: int) -> str:
    """Encode Slipstream SwapRouter.exactInput calldata."""
    encoded = abi_encode(['(bytes,address,uint256,uint256,uint256)'], [(path, recipient, int(deadline), int(amount_in), int(amount_out_minimum))])
    return '0x' + (_EXACT_INPUT_SELECTOR + encoded).hex()
