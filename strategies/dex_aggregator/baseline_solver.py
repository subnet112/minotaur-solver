"""Baseline IntentSolver (v2) — RPC-first pool discovery and routing.

The default solver that ships with the SDK. Queries real on-chain pool
states via RPC (Anvil fork, Alchemy, etc.) for accurate pricing and
routing. Falls back to MarketSnapshot data when RPC is unavailable
(e.g. offline tests, benchmarks).

Architecture:
    1. initialize() stores rpc_urls, creates Web3 instances on demand
    2. quote()/generate_plan() query live pool states via RPC
    3. If no RPC → fall back to snapshot.pool_states
    4. Route through pools using pool_math (direct + multi-hop)

Miners are expected to surpass this baseline with better strategies:
    - More pools/DEXes discovered via factory events
    - Cross-DEX aggregation
    - MEV protection
    - ML-based parameter tuning

Usage::

    from strategies.dex_aggregator.baseline_solver import BaselineSwapSolver

    solver = BaselineSwapSolver()
    solver.initialize({
        "chain_ids": [1, 31337],
        "rpc_urls": {1: "http://localhost:8545", 31337: "http://localhost:8545"},
    })
    quote = solver.quote(intent, state)  # queries real pools via RPC
"""
from __future__ import annotations

def _mw1():
    global _lr114, _BaselineSwapSolverDR1DR49LR119, _BaselineSwapSolverDR1DR49, _BaselineSwapSolverDR1LR28, _BaselineSwapSolverDR1LR201, _BaselineSwapSolverDR1, _BaselineSwapSolverDR2DR30, _BaselineSwapSolverDR2DR31LR47, _BaselineSwapSolverDR2DR31LR202, _BaselineSwapSolverDR2DR31, _BaselineSwapSolverDR2DR88, _BaselineSwapSolverDR2LR39, _BaselineSwapSolverDR2LR159, _BaselineSwapSolverDR2, _BaselineSwapSolverDR31, _BaselineSwapSolverDR34LR49, _BaselineSwapSolverDR34LR246, _BaselineSwapSolverDR34

    def _lr114():
        global Any, AppIntentDefinition, ExecutionPlan, IntentState, Interaction, QuoteResult, _DR_UNSET, _compute_platform_fee_wei, _lr18, asyncio, logging, os, time
        _DR_UNSET = object()
        import asyncio
        import logging
        import os
        import time
        from typing import Any
        from minotaur_subnet.shared.types import AppIntentDefinition, ExecutionPlan, Interaction, IntentState, QuoteResult

        def _lr18():
            global IntentSolver, MarketSnapshot, ProcessorContext, SolverMetadata, SwapIntentProcessor, _DISCOVERY_SEED_TOKENS, _FACTORY_ABI, _FACTORY_ADDRESSES, _FALLBACK_GAS_PRICE_WEI, _FEE_TIERS, _GAS_BASE_OVERHEAD, _GAS_PER_HOP, _GENERIC_FALLBACK_GAS_PRICE_WEI, _KNOWN_POOLS, _PLATFORM_FEE_MARGIN_BPS, _POOL_ABI, _TOKEN_SYMBOLS, _ZERO_ADDRESS, _cross_chain_compat_params, _dr81, _intent_function_from_state, _run_coro, _state_params, build_typed_context, logger, manifest_from_definition, normalize_swap_intent_params
            from minotaur_subnet.sdk.intent_solver import IntentSolver, MarketSnapshot, SolverMetadata
            from minotaur_subnet.sdk.processor_context import ProcessorContext
            from strategies.dex_aggregator.swap_solver import SwapIntentProcessor
            from minotaur_subnet.v3.contexts import build_typed_context
            from minotaur_subnet.v3.manifest import manifest_from_definition, normalize_swap_intent_params

            def _dr81():
                logger = logging.getLogger(__name__)

                def _dr40():

                    def _state_params(state: IntentState) -> dict[str, Any]:
                        typed = getattr(state, 'typed_context', None)
                        if typed is not None:
                            raw = getattr(typed, 'raw_params', None)
                            if isinstance(raw, dict):
                                return raw
                        return state.raw_params_view()

                    def _dr9():

                        def _dr57():

                            def _intent_function_from_state(state: IntentState, default: str='swap') -> str:
                                typed = getattr(state, 'typed_context', None)
                                params = _state_params(state)
                                return getattr(typed, 'intent_function', '') or state.control_view().get('_intent_function') or params.get('intent_function') or default

                            def _cross_chain_compat_params(state: IntentState) -> dict[str, Any]:
                                """Return raw compatibility metadata that remains intentionally untyped."""
                                return state.raw_params_view()
                            return (_cross_chain_compat_params, _intent_function_from_state)
                        _cross_chain_compat_params, _intent_function_from_state = _dr57()

                        def _run_coro(coro):
                            """Run a coroutine from sync code, handling nested event loops.

    BaselineSwapSolver (sync IntentSolver interface) delegates to
    SwapIntentProcessor (async IntentProcessor interface). When called
    from the validator's async block loop, we're already inside an event
    loop, so we run the coroutine in a separate thread.
    """
                            try:
                                loop = asyncio.get_running_loop()
                            except RuntimeError:
                                loop = None

                            def _lr211():
                                nonlocal loop
                                if loop is not None and loop.is_running():

                                    def _lr135():
                                        import concurrent.futures
                                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                                            return (1, pool.submit(asyncio.run, coro).result())
                                        return (0, None)
                                    _lrt136 = _lr135()
                                    if _lrt136[0]:
                                        return _lrt136[1]
                                else:
                                    loop = asyncio.new_event_loop()
                                    try:
                                        return loop.run_until_complete(coro)
                                    finally:
                                        loop.close()
                            return _lr211()

                        def _lr6():

                            def _lr250():
                                return {'inputs': [], 'name': 'slot0'}

                            def _lr251():
                                return {'outputs': [{'internalType': 'uint160', 'name': 'sqrtPriceX96', 'type': 'uint160'}, {'internalType': 'int24', 'name': 'tick', 'type': 'int24'}, {'internalType': 'uint16', 'name': 'observationIndex', 'type': 'uint16'}, {'internalType': 'uint16', 'name': 'observationCardinality', 'type': 'uint16'}, {'internalType': 'uint16', 'name': 'observationCardinalityNext', 'type': 'uint16'}, {'internalType': 'uint8', 'name': 'feeProtocol', 'type': 'uint8'}, {'internalType': 'bool', 'name': 'unlocked', 'type': 'bool'}]}

                            def _lr252():
                                return {'stateMutability': 'view', 'type': 'function'}
                            return [{**_lr250(), **_lr251(), **_lr252()}]

                        def _lr7():
                            return [{'inputs': [], 'name': 'liquidity', 'outputs': [{'internalType': 'uint128', 'name': '', 'type': 'uint128'}], 'stateMutability': 'view', 'type': 'function'}, {'inputs': [], 'name': 'fee', 'outputs': [{'internalType': 'uint24', 'name': '', 'type': 'uint24'}], 'stateMutability': 'view', 'type': 'function'}]

                        def _lr8():
                            return [{'inputs': [], 'name': 'token0', 'outputs': [{'internalType': 'address', 'name': '', 'type': 'address'}], 'stateMutability': 'view', 'type': 'function'}, {'inputs': [], 'name': 'token1', 'outputs': [{'internalType': 'address', 'name': '', 'type': 'address'}], 'stateMutability': 'view', 'type': 'function'}]
                        _POOL_ABI = [*_lr6(), *_lr7(), *_lr8()]
                        return (_POOL_ABI, _cross_chain_compat_params, _intent_function_from_state, _run_coro)
                    _POOL_ABI, _cross_chain_compat_params, _intent_function_from_state, _run_coro = _dr9()
                    _FACTORY_ABI = None

                    def _lr177():
                        nonlocal _FACTORY_ABI
                        _FACTORY_ABI = None

                        def _lr56():
                            nonlocal _FACTORY_ABI
                            _FACTORY_ABI = [{'inputs': [{'internalType': 'address', 'name': 'tokenA', 'type': 'address'}, {'internalType': 'address', 'name': 'tokenB', 'type': 'address'}, {'internalType': 'uint24', 'name': 'fee', 'type': 'uint24'}], 'name': 'getPool', 'outputs': [{'internalType': 'address', 'name': 'pool', 'type': 'address'}], 'stateMutability': 'view', 'type': 'function'}]
                        _lr56()
                        _FACTORY_ADDRESSES: dict[int, str] = {1: '0x1F98431c8aD98523631AE4a59f267346ea31F984', 8453: '0x33128a8fC17869897dcE68Ed026d694621f6FDfD', 964: '0x20d0CdF9004bF56bCA52A25C9288AAD0eBB97D59'}
                        return (_FACTORY_ABI, _FACTORY_ADDRESSES, _POOL_ABI, _cross_chain_compat_params, _intent_function_from_state, _run_coro, _state_params)
                    return _lr177()
                _FACTORY_ABI, _FACTORY_ADDRESSES, _POOL_ABI, _cross_chain_compat_params, _intent_function_from_state, _run_coro, _state_params = _dr40()
                _DISCOVERY_SEED_TOKENS = None

                def _lr117():
                    nonlocal _DISCOVERY_SEED_TOKENS

                    def _dr1():
                        _FACTORY_ADDRESSES[31337] = _FACTORY_ADDRESSES[1]
                        _FEE_TIERS = [100, 500, 3000, 10000]
                        _ZERO_ADDRESS = '0x' + '0' * 40
                        _DISCOVERY_SEED_TOKENS = None

                        def _lr130():
                            nonlocal _DISCOVERY_SEED_TOKENS

                            def _dr56():
                                _DISCOVERY_SEED_TOKENS = _KNOWN_POOLS = None

                                def _lr143():
                                    nonlocal _DISCOVERY_SEED_TOKENS, _KNOWN_POOLS
                                    _KNOWN_POOLS = {1: ['0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8', '0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640', '0x4e68Ccd3E89f51C3074ca5072bbAC773960dFa36', '0xCBCdF9626bC03E24f779434178A73a0B4bad62eD', '0x6c6Bc977E13Df9b0de53b251522280BB72383700', '0xC2e9F25Be6257c210d7Adf0D4Cd6E3E881ba25f8'], 8453: ['0xd0b53D9277642d899DF5C87A3966A349A798F224'], 964: ['0x6647dcbeb030dc8E227D8B1A2Cb6A49F3C887E3c']}
                                    _KNOWN_POOLS[31337] = list(_KNOWN_POOLS[1])
                                    _DISCOVERY_SEED_TOKENS = None
                                _lr143()

                                def _lr24():
                                    nonlocal _DISCOVERY_SEED_TOKENS
                                    _DISCOVERY_SEED_TOKENS = {8453: ['0x4200000000000000000000000000000000000006', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913', '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb', '0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf', '0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22', '0xc1CBa3fCea344f92D9239c08C0568f6F2F0ee452', '0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA', '0x78a087d713Be963Bf307b18F2Ff8122EF9A63ae9', '0x0578d8A44db98B23BF096A382e016e29a5Ce0ffe', '0x532f27101965dd16442E59d40670FaF5eBB142E4', '0x940181a94A35A4569E4529A3CDfB74e38FD98631', '0xB6fe221Fe9EeF5aBa221c348bA20A1Bf5e73624c', '0x04C0599Ae5A44757c0af6F9eC3b93da8976c150A', '0xfA980cEd6895AC314E7dE34Ef1bFAE90a5AdD21b', '0x236aa50979D5f3De3Bd1Eeb40E81137F22ab794b', '0x77E06c9eCCf2E797fd462A92B6D7642EF85b0A44', '0xdC46C1E93B71fF9209A0F8076a9951569DC35855'], 1: ['0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', '0xdAC17F958D2ee523a2206206994597C13D831ec7', '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599', '0x6B175474E89094C44Da98b954EedeAC495271d0F', '0x77E06c9eCCf2E797fd462A92B6D7642EF85b0A44'], 964: ['0x9Dc08C6e2BF0F1eeD1E00670f80Df39145529F81', '0xB833E8137FEDf80de7E908dc6fea43a029142F20']}
                                _lr24()
                                _DISCOVERY_SEED_TOKENS[31337] = list(_DISCOVERY_SEED_TOKENS.get(1, []))
                                return (_DISCOVERY_SEED_TOKENS, _KNOWN_POOLS)
                            _DISCOVERY_SEED_TOKENS, _KNOWN_POOLS = _dr56()
                            _TOKEN_SYMBOLS: dict[str, str] = {'0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2': 'WETH', '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48': 'USDC', '0xdac17f958d2ee523a2206206994597c13d831ec7': 'USDT', '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599': 'WBTC', '0x6b175474e89094c44da98b954eedeac495271d0f': 'DAI', '0x77e06c9eccf2e797fd462a92b6d7642ef85b0a44': 'wTAO', '0x9dc08c6e2bf0f1eed1e00670f80df39145529f81': 'WTAO', '0xb833e8137fedf80de7e908dc6fea43a029142f20': 'USDC'}
                            return (_DISCOVERY_SEED_TOKENS, _FEE_TIERS, _KNOWN_POOLS, _TOKEN_SYMBOLS, _ZERO_ADDRESS)
                        return _lr130()
                    _DISCOVERY_SEED_TOKENS, _FEE_TIERS, _KNOWN_POOLS, _TOKEN_SYMBOLS, _ZERO_ADDRESS = _dr1()
                    _GAS_BASE_OVERHEAD = 400000
                    _GAS_PER_HOP = 150000
                    _FALLBACK_GAS_PRICE_WEI: dict[int, int] = {1: 25000000000, 8453: 20000000, 42161: 10000000, 10: 10000000, 964: 25000000000, 31337: 1000000000}

                    def _lr23():
                        _GENERIC_FALLBACK_GAS_PRICE_WEI = 1000000000
                        return (_DISCOVERY_SEED_TOKENS, _FACTORY_ABI, _FACTORY_ADDRESSES, _FALLBACK_GAS_PRICE_WEI, _FEE_TIERS, _GAS_BASE_OVERHEAD, _GAS_PER_HOP, _GENERIC_FALLBACK_GAS_PRICE_WEI, _KNOWN_POOLS, _POOL_ABI, _TOKEN_SYMBOLS, _ZERO_ADDRESS, _cross_chain_compat_params, _intent_function_from_state, _run_coro, _state_params, logger)
                    return _lr23()
                return _lr117()
            _DISCOVERY_SEED_TOKENS, _FACTORY_ABI, _FACTORY_ADDRESSES, _FALLBACK_GAS_PRICE_WEI, _FEE_TIERS, _GAS_BASE_OVERHEAD, _GAS_PER_HOP, _GENERIC_FALLBACK_GAS_PRICE_WEI, _KNOWN_POOLS, _POOL_ABI, _TOKEN_SYMBOLS, _ZERO_ADDRESS, _cross_chain_compat_params, _intent_function_from_state, _run_coro, _state_params, logger = _dr81()
            _PLATFORM_FEE_MARGIN_BPS = 2000
        _lr18()

        def _compute_platform_fee_wei(gas_units: int, gas_price_wei: int) -> int:
            """Estimate platform fee in native token wei (ETH/TAO).

    Fee = gas_units * gas_price_wei * (1 + margin).
    The caller is responsible for supplying a live or chain-appropriate
    gas_price_wei — see ``BaselineSwapSolver._get_gas_price_wei``.
    """
            gas_cost_wei = gas_units * int(gas_price_wei)
            margin = gas_cost_wei * _PLATFORM_FEE_MARGIN_BPS // 10000
            return gas_cost_wei + margin
    _lr114()

    class _BaselineSwapSolverDR1DR49LR119(IntentSolver):

        def _discover_pools(self, chain_id: int) -> dict[str, dict[str, Any]]:
            """Query known Uniswap V3 pools via RPC with caching.

        Returns pool_states dict keyed by pool address, compatible with
        pool_math functions.
        """
            now = time.time()
            w3 = None

            def _lr128():
                nonlocal w3
                if chain_id in self._pool_cache and now - self._pool_cache_time.get(chain_id, 0) < self._pool_cache_ttl:
                    return (1, self._pool_cache[chain_id])
                w3 = self._get_web3(chain_id)
                return (0, None)
            _lrt129 = _lr128()
            if _lrt129[0]:
                return _lrt129[1]
            pool_states = None

            def _lr42():
                nonlocal pool_states
                if w3 is None:
                    return (1, self._pool_cache.get(chain_id, {}))
                pool_addrs = _KNOWN_POOLS.get(chain_id, [])
                pool_states = {}

                def _dr44():
                    for addr in pool_addrs:
                        state = self._query_pool_state(w3, addr)
                        if state is not None:
                            pool_states[addr] = state
                    if pool_states:

                        def _lr82():
                            self._pool_cache[chain_id] = pool_states
                            self._pool_cache_time[chain_id] = now
                            stale = [k for k in self._pair_discovery_cache if k[0] == chain_id]
                            for k in stale:
                                del self._pair_discovery_cache[k]
                        _lr82()
                        logger.debug('Discovered %d pools on chain %d via RPC', len(pool_states), chain_id)
                _dr44()
                return (0, None)
            _lrt43 = _lr42()
            if _lrt43[0]:
                return _lrt43[1]
            return pool_states

        def _get_factory(self, chain_id: int) -> Any | None:
            """Get a Uniswap V3 Factory contract instance for a chain."""
            factory_addr = _FACTORY_ADDRESSES.get(chain_id)
            if not factory_addr:
                return None
            w3 = self._get_web3(chain_id)
            if w3 is None:
                return None
            return w3.eth.contract(address=w3.to_checksum_address(factory_addr), abi=_FACTORY_ABI)

    class _BaselineSwapSolverDR1DR49(_BaselineSwapSolverDR1DR49LR119):

        def initialize(self, config: dict[str, Any]) -> None:
            """Initialize with RPC URLs and swap processor."""

            def _lr81():
                self._config = config
                raw_rpc_urls = config.get('rpc_urls', {}) or {}
                self._rpc_urls = {int(k): v for k, v in raw_rpc_urls.items() if v}
                self._bridge_registry = config.get('bridge_registry')
            _lr81()
            self._processor = SwapIntentProcessor()
            logger.info('BaselineSwapSolver initialized (chains=%s, rpc_chains=%s, bridge=%s)', config.get('chain_ids', [1]), list(self._rpc_urls.keys()) if self._rpc_urls else 'none', self._bridge_registry is not None)

        def _get_web3(self, chain_id: int) -> Any:
            """Get or create a cached Web3 instance for a chain."""
            if chain_id in self._web3_cache:
                return self._web3_cache[chain_id]

            def _lr179():
                rpc_url = self._rpc_urls.get(chain_id)
                if not rpc_url:
                    return None
                try:

                    def _lr94():
                        from web3 import Web3
                        w3 = Web3(Web3.HTTPProvider(rpc_url))
                        if w3.is_connected():
                            self._web3_cache[chain_id] = w3
                            return (1, w3)
                        logger.warning('Web3 not connected for chain %d at %s', chain_id, rpc_url)
                        return (0, None)
                    _lrt95 = _lr94()
                    if _lrt95[0]:
                        return _lrt95[1]
                except Exception as exc:
                    logger.warning('Failed to create Web3 for chain %d: %s', chain_id, exc)
                return None
            return _lr179()

        def _get_gas_price_wei(self, chain_id: int) -> int:
            """Return the live gas price in wei for a chain, cached briefly.

        Prefers the live `eth_gasPrice` via RPC. Falls back to a chain-
        specific default if RPC is unavailable. Cached for 30 seconds per
        chain to avoid spamming RPC on every quote.
        """
            now = time.time()
            cached = entry = None

            def _lr131():
                nonlocal cached, entry
                cached = getattr(self, '_gas_price_cache', None)
                if cached is None:
                    self._gas_price_cache: dict[int, tuple[int, float]] = {}
                    cached = self._gas_price_cache
                entry = cached.get(chain_id)
            _lr131()

            def _dr60():
                if entry is not None and now - entry[1] < 30.0:
                    return entry[0]
                gas_price = None

                def _lr245():
                    nonlocal gas_price
                    w3 = self._get_web3(chain_id)
                    gas_price = None

                    def _lr38():
                        nonlocal gas_price
                        if w3 is not None:
                            try:
                                gas_price = int(w3.eth.gas_price)
                            except Exception as exc:
                                logger.warning('Failed to fetch gas price for chain %d: %s', chain_id, exc)
                        if gas_price is None or gas_price <= 0:
                            gas_price = _FALLBACK_GAS_PRICE_WEI.get(chain_id, _GENERIC_FALLBACK_GAS_PRICE_WEI)
                    _lr38()
                    cached[chain_id] = (gas_price, now)
                    return gas_price
                    return _DR_UNSET
                return _lr245()
            _dr61 = _dr60()
            if _dr61 is not _DR_UNSET:
                return _dr61

        def _query_pool_state(self, w3: Any, pool_address: str) -> dict[str, Any] | None:
            """Query a Uniswap V3 pool's current state via RPC.

        The ``dex`` marker is set to ``uniswap_v3`` here. Aerodrome
        Slipstream discovery (``common/aerodrome.py``) reuses this same
        reader and overrides the marker to ``aerodrome_slipstream``.
        """
            try:

                def _dr103():
                    pool = w3.eth.contract(address=w3.to_checksum_address(pool_address), abi=_POOL_ABI)

                    def _lr157():
                        slot0 = pool.functions.slot0().call()
                        liquidity = pool.functions.liquidity().call()
                        fee = pool.functions.fee().call()
                        token0 = pool.functions.token0().call()

                        def _lr34():
                            token1 = pool.functions.token1().call()
                            return {'token0': token0, 'token1': token1, 'fee': fee, 'sqrtPriceX96': str(slot0[0]), 'tick': slot0[1], 'liquidity': str(liquidity), 'dex': 'uniswap_v3'}
                            return _DR_UNSET
                        return _lr34()
                    return _lr157()
                _dr104 = _dr103()
                if _dr104 is not _DR_UNSET:
                    return _dr104
            except Exception as exc:
                logger.debug('Failed to query pool %s: %s', pool_address, exc)
                return None

    class _BaselineSwapSolverDR1LR28(_BaselineSwapSolverDR1DR49):

        def _discover_pools_for_pair(self, chain_id: int, token_a: str, token_b: str, pool_states: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:

            def _dr90():
                """Query Uniswap V3 Factory for all pools between two tokens.

        Checks all 4 fee tiers. For each non-zero pool found, queries
        on-chain state and merges into pool_states (mutated in-place).
        """
                now = time.time()
                a_lower, b_lower = (token_a.lower(), token_b.lower())
                pair_key = (chain_id, min(a_lower, b_lower), max(a_lower, b_lower))
                return (now, pair_key)
            now, pair_key = _dr90()
            if now - self._pair_discovery_cache.get(pair_key, 0) < self._pool_cache_ttl:
                return pool_states
            discovered = None

            def _lr200():
                nonlocal discovered
                factory = self._get_factory(chain_id)
                if factory is None:
                    return pool_states
                w3 = self._get_web3(chain_id)
                discovered = None

                def _lr57():
                    nonlocal discovered
                    if w3 is None:
                        return pool_states

                    def _dr27():
                        discovered = 0

                        def _dr93():
                            rpc_errors = 0
                            for fee in _FEE_TIERS:
                                try:
                                    pool_addr = factory.functions.getPool(w3.to_checksum_address(token_a), w3.to_checksum_address(token_b), fee).call()
                                except Exception as exc:

                                    def _lr155():
                                        nonlocal rpc_errors
                                        logger.debug('Factory.getPool(%s, %s, %d) failed: %s', token_a[:10], token_b[:10], fee, exc)
                                        rpc_errors += 1
                                    _lr155()
                                    continue

                                def _lr29():
                                    if not pool_addr or pool_addr == _ZERO_ADDRESS:
                                        return
                                    if pool_addr in pool_states or pool_addr.lower() in {k.lower() for k in pool_states}:
                                        return

                                    def _dr79():
                                        nonlocal discovered
                                        state = self._query_pool_state(w3, pool_addr)
                                        if state is not None:
                                            pool_states[pool_addr] = state
                                            discovered += 1
                                        return state
                                    state = _dr79()
                                _lr29()
                            return rpc_errors
                        rpc_errors = _dr93()
                        if rpc_errors < len(_FEE_TIERS):
                            self._pair_discovery_cache[pair_key] = now
                        return discovered
                    discovered = _dr27()
                    if discovered > 0:
                        logger.debug('Factory: found %d new pools for %s/%s on chain %d', discovered, token_a[:10], token_b[:10], chain_id)
                    return pool_states
                return _lr57()
            return _lr200()

    class _BaselineSwapSolverDR1LR201(_BaselineSwapSolverDR1LR28):

        def _cross_chain_params(self, intent: AppIntentDefinition, state: IntentState) -> dict[str, Any]:
            swap_params = self._normalized_swap_params(intent, state)
            extra = _cross_chain_compat_params(state)
            dest_chain_raw = extra.get('dest_chain_id')
            dest_chain_id = int(dest_chain_raw) if dest_chain_raw not in (None, '') else 0

            def _lr96():
                return {**swap_params, 'dest_chain_id': dest_chain_id, 'bridge_protocol': extra.get('bridge_protocol', 'mock'), 'dest_recipient': extra.get('dest_recipient') or swap_params['receiver'] or state.owner or _ZERO_ADDRESS, 'dest_min_output_amount': int(extra.get('min_output', swap_params.get('min_output_amount', 0)) or 0)}
            return _lr96()

    class _BaselineSwapSolverDR1(_BaselineSwapSolverDR1LR201):

        def _normalized_swap_params(self, intent: AppIntentDefinition, state: IntentState) -> dict[str, Any]:
            params = _state_params(state)
            result = None

            def _lr213():
                nonlocal result
                receiver_default = state.contract_address or state.owner

                def _dr33():
                    nonlocal params

                    def _lr77():
                        return {**params, 'input_token': getattr(typed, 'input_token', params.get('input_token', '')), 'output_token': getattr(typed, 'output_token', params.get('output_token', '')), 'input_amount': getattr(typed, 'input_amount', params.get('input_amount', 0))}

                    def _lr78():
                        return {'min_output_amount': getattr(typed, 'min_output_amount', params.get('min_output_amount', params.get('output_amount', 0))), 'receiver': getattr(typed, 'receiver', receiver_default), 'fee_tier': getattr(typed, 'fee_tier', params.get('fee_tier', 3000))}
                    if getattr(state, 'typed_context', None) is not None:
                        typed = state.typed_context
                        params = {**_lr77(), **_lr78()}
                _dr33()
                result = normalize_swap_intent_params(params, manifest=manifest_from_definition(intent), intent_name=_intent_function_from_state(state, 'swap'), receiver_default=receiver_default, slippage_bps=self._processor.slippage_bps if self._processor else 50)
            _lr213()

            def _dr80():
                InteropAddress = ia = None
                _lr87 = val = None
                for key, chain_key in [('input_token', '_input_chain'), ('output_token', '_output_chain')]:

                    def _lr253():
                        nonlocal _lr87, val
                        val = result.get(key, '')
                        if val and val.startswith('eip155:'):

                            def _lr87():
                                nonlocal InteropAddress, ia
                                try:
                                    from minotaur_subnet.shared.interop_address import InteropAddress
                                    ia = InteropAddress.parse(val, default_chain_id=state.chain_id)
                                    result[key] = ia.address
                                    if ia.chain_id is not None:
                                        result[chain_key] = ia.chain_id
                                except ValueError:
                                    pass
                            _lr87()
                        elif val:
                            result[chain_key] = state.chain_id
                    _lr253()
            _dr80()
            return result

        def _state_with_extra(self, intent: AppIntentDefinition, state: IntentState, *, chain_id: int, extra_updates: dict[str, Any]) -> IntentState:
            cloned = None

            def _lr110():
                nonlocal cloned
                raw_params = {**_cross_chain_compat_params(state), **extra_updates}
                cloned = IntentState(contract_address=state.contract_address, chain_id=chain_id, nonce=state.nonce, owner=state.owner, raw_params=raw_params, control=state.control_view(), context_version=state.context_version, policy_tier=state.policy_tier)
            _lr110()
            try:
                cloned.typed_context = build_typed_context(intent, state.control_view().get('_intent_function', _intent_function_from_state(state, 'swap')), cloned)
            except Exception:
                cloned.typed_context = None
            return cloned

        def _intermediaries_for_chain(self, chain_id: int) -> list[str]:
            """Chain-appropriate multi-hop intermediary tokens (WETH + USDC).

        Sourced from the trusted SDK token registry so the addresses are
        always correct for the chain. A hardcoded mainnet list silently
        disables multi-hop on every other chain — the intermediary pools
        never resolve on the factory, so two-hop discovery and routing both
        come up empty (this was the Base/BT EVM multi-hop dead-spot).
        """
            from minotaur_subnet.blockchain.tokens import WRAPPED_NATIVE_TOKEN, TOKENS
            token_chain = 1 if chain_id == 31337 else chain_id
            mids: list[str] = []
            wnt = WRAPPED_NATIVE_TOKEN.get(chain_id)

            def _lr108():
                if wnt:
                    mids.append(wnt)
                usdc = TOKENS.get(token_chain, {}).get('USDC')
                if usdc and usdc.lower() not in {m.lower() for m in mids}:
                    mids.append(usdc)
            _lr108()
            return mids

    class _BaselineSwapSolverDR2DR30(_BaselineSwapSolverDR1):

        def generate_plan(self, intent: AppIntentDefinition, state: IntentState, snapshot: MarketSnapshot | None=None) -> ExecutionPlan:
            """Generate a swap plan using route-aware plan generation.

        Discovers pools via RPC, finds the best route (direct or multi-hop),
        and builds the appropriate Uniswap V3 execution plan. Direct swaps
        use exactInputSingle; multi-hop swaps use exactInput with packed path.
        """
            if self._processor is None:
                raise RuntimeError('Solver not initialized — call initialize() first')
            chain_id = None

            def _lr214():
                nonlocal chain_id
                chain_id = state.chain_id or (snapshot.chain_id if snapshot else 1)
                params = _state_params(state)
                if params.get('alpha_netuid') and params.get('owner_ss58'):
                    return self._generate_substrate_to_evm_plan(intent, state, snapshot)

                def _lr63():
                    intent_fn = _intent_function_from_state(state, 'swap')
                    if intent_fn == 'rebalance':
                        return self._generate_yield_plan(intent, state, snapshot)

                    def _dr46():
                        nonlocal chain_id
                        swap_params = self._normalized_swap_params(intent, state)
                        dest_chain_id = None

                        def _lr25():
                            nonlocal chain_id, dest_chain_id
                            dest_chain_id = _cross_chain_compat_params(state).get('dest_chain_id')
                            if not dest_chain_id:
                                output_chain = swap_params.get('_output_chain')
                                input_chain = swap_params.get('_input_chain', chain_id)
                                if output_chain and output_chain != input_chain:
                                    dest_chain_id = output_chain
                                    chain_id = input_chain

                        def _lr178():
                            _lr25()
                            if dest_chain_id and int(dest_chain_id) != chain_id:
                                return self._generate_cross_chain_plan(intent, state, snapshot, chain_id, int(dest_chain_id))

                            def _dr23():

                                def _dr15():

                                    def _dr83():
                                        pool_states = self._get_pool_states(chain_id, snapshot)

                                        def _lr254():
                                            input_token = swap_params.get('input_token', '')
                                            output_token = swap_params.get('output_token', '')

                                            def _lr79():
                                                nonlocal pool_states
                                                if input_token and output_token:
                                                    if snapshot is not None and snapshot.pool_states and (pool_states is snapshot.pool_states):
                                                        pool_states = dict(pool_states)
                                                    self._ensure_pools_for_route(chain_id, pool_states, input_token, output_token)
                                            _lr79()
                                            prices = self._derive_prices(pool_states, chain_id) if pool_states else {}
                                            return (input_token, output_token, pool_states, prices)
                                        return _lr254()
                                    input_token, output_token, pool_states, prices = _dr83()
                                    context = None

                                    def _lr137():
                                        nonlocal context
                                        context = ProcessorContext(chain_id=chain_id, timestamp=snapshot.timestamp if snapshot else int(time.time()), block_number=snapshot.block_number if snapshot else 0, rpc_url=self._rpc_urls.get(chain_id, ''), prices=prices, dex_config=snapshot.dex_config if snapshot else {})
                                    _lr137()
                                    return (context, input_token, output_token, pool_states)
                                context, input_token, output_token, pool_states = _dr15()
                                _dr92 = None

                                def _lr190():
                                    nonlocal _dr92
                                    if input_token and output_token and pool_states:
                                        amount_in = swap_params.get('input_amount', 0)

                                        def _lr91():
                                            if amount_in > 0:
                                                route = self._find_best_executable_route(pool_states, input_token, output_token, amount_in, chain_id)
                                                if route is not None:

                                                    def _dr3():
                                                        nonlocal state
                                                        output_amount, route_desc, hops = route
                                                        hop_dex = self._dominant_dex(hops)

                                                        def _lr219():
                                                            if len(hops) > 1:

                                                                def _dr67():
                                                                    if hop_dex == 'aerodrome_slipstream':
                                                                        return self._build_aerodrome_multihop_plan(intent, state, context, hops, input_token, output_token, amount_in, output_amount, chain_id)
                                                                    return self._build_multihop_plan(intent, state, context, hops, input_token, output_token, amount_in, output_amount, chain_id)
                                                                    return _DR_UNSET
                                                                _dr68 = _dr67()
                                                                if _dr68 is not _DR_UNSET:
                                                                    return _dr68
                                                            else:

                                                                def _lr132():
                                                                    if len(hops) == 1:

                                                                        def _dr98():
                                                                            if hop_dex == 'aerodrome_slipstream':
                                                                                return self._build_aerodrome_singlehop_plan(intent, state, context, hops[0], input_token, output_token, amount_in, output_amount, chain_id)
                                                                            return _DR_UNSET
                                                                        _dr99 = _dr98()
                                                                        if _dr99 is not _DR_UNSET:
                                                                            return (1, _dr99)

                                                                        def _lr20():
                                                                            nonlocal state
                                                                            discovered_fee = hops[0].get('fee')
                                                                            if discovered_fee and discovered_fee != self._processor.default_fee_tier:
                                                                                state = self._state_with_extra(intent, state, chain_id=state.chain_id, extra_updates={'fee_tier': discovered_fee})
                                                                        _lr20()
                                                                    return (0, None)
                                                                _lrt133 = _lr132()
                                                                if _lrt133[0]:
                                                                    return _lrt133[1]
                                                            return _DR_UNSET
                                                        return _lr219()
                                                    _dr4 = _dr3()
                                                    if _dr4 is not _DR_UNSET:
                                                        return (1, _dr4)
                                            return (0, None)
                                        _lrt92 = _lr91()
                                        if _lrt92[0]:
                                            return (1, _lrt92[1])

                                    def _dr91():
                                        plan = None
                                        try:

                                            def _lr220():
                                                nonlocal plan
                                                plan = _run_coro(self._processor.generate_plan(intent, state, context))
                                                plan.metadata['chain_id'] = chain_id
                                            _lr220()
                                            return plan
                                        except ValueError as exc:
                                            if 'No Uniswap V3 router' not in str(exc):
                                                raise
                                            return self._build_direct_pool_plan(intent, state, context, pool_states, input_token, output_token, chain_id)
                                        return _DR_UNSET
                                        return _DR_UNSET
                                    _dr92 = _dr91()
                                    return (0, None)
                                _lrt191 = _lr190()
                                if _lrt191[0]:
                                    return _lrt191[1]
                                if _dr92 is not _DR_UNSET:
                                    return _dr92
                                return _DR_UNSET
                            _dr24 = _dr23()
                            if _dr24 is not _DR_UNSET:
                                return _dr24
                            return _DR_UNSET
                        return _lr178()
                    _dr47 = _dr46()
                    if _dr47 is not _DR_UNSET:
                        return _dr47
                return _lr63()
            return _lr214()

    class _BaselineSwapSolverDR2DR31LR47(_BaselineSwapSolverDR2DR30):

        def _build_multihop_plan(self, intent: AppIntentDefinition, state: IntentState, context: ProcessorContext, hops: list[dict[str, Any]], input_token: str, output_token: str, amount_in: int, expected_output: int, chain_id: int) -> ExecutionPlan:
            """Build a multi-hop swap plan using Uniswap V3 exactInput.

        Constructs the packed path from discovered pool hops and generates
        approve + exactInput interactions.

        Args:
            hops: Route hops from ``pool_math.find_best_route()``. Each hop
                is a dict with ``pool_state`` (dict with ``token0``,
                ``token1``), ``fee`` (int), and ``pool_addr`` (str).
            expected_output: Estimated output from route math, used for
                slippage fallback when ``min_output_amount`` is not set.
        """
            from common.abi_utils import encode_approve
            from strategies.dex_aggregator.v3_codec import encode_exact_input, encode_swap_path
            from strategies.dex_aggregator.swap_solver import UNISWAP_V3_ROUTERS
            swap_params = self._normalized_swap_params(intent, state)
            tokens = [input_token]
            fees: list[int] = []

            def _dr48():
                path = None

                def _lr145():
                    nonlocal path
                    for hop in hops:
                        pool = hop['pool_state']
                        t0 = pool['token0'].lower()

                        def _lr31():
                            t1 = pool['token1'].lower()
                            if tokens[-1].lower() == t0:
                                tokens.append(pool['token1'])
                            else:
                                tokens.append(pool['token0'])
                        _lr31()
                        fees.append(hop['fee'])
                    path = encode_swap_path(tokens, fees)
                _lr145()
                router = UNISWAP_V3_ROUTERS.get(chain_id)
                if not router:
                    raise ValueError(f'No Uniswap V3 router for chain {chain_id}')
                return (path, router)
            path, router = _dr48()

            def _lr80():
                min_output = swap_params.get('min_output_amount', 0)
                if not min_output:
                    slippage_bps = self._processor.slippage_bps
                    min_output = expected_output * (10000 - slippage_bps) // 10000

                def _dr20():

                    def _dr76():
                        deadline = context.timestamp + self._processor.deadline_offset
                        recipient = state.contract_address or swap_params.get('receiver', state.owner)
                        interactions = None

                        def _lr147():
                            nonlocal interactions
                            interactions = None

                            def _lr32():
                                nonlocal interactions
                                interactions = [Interaction(target=input_token, value='0', call_data=encode_approve(router, amount_in), chain_id=chain_id), Interaction(target=router, value='0', call_data=encode_exact_input(path=path, recipient=recipient, deadline=deadline, amount_in=amount_in, amount_out_minimum=0), chain_id=chain_id)]
                            _lr32()
                            logger.info('Multi-hop plan: %d hops, path=%s, fees=%s', len(hops), ' → '.join((t[:10] for t in tokens)), fees)
                            return (deadline, interactions)
                        return _lr147()
                    deadline, interactions = _dr76()

                    def _lr225():
                        return ExecutionPlan(intent_id=intent.app_id, interactions=interactions, deadline=deadline, nonce=state.nonce, metadata={'route': 'uniswap_v3_multihop', 'hops': len(hops), 'tokens': tokens, 'fees': fees, 'input_token': input_token, 'output_token': output_token, 'input_amount': str(amount_in), 'min_output_amount': str(min_output), 'chain_id': chain_id})
                    return _lr225()
                    return _DR_UNSET
                _dr21 = _dr20()
                if _dr21 is not _DR_UNSET:
                    return _dr21
            return _lr80()

    class _BaselineSwapSolverDR2DR31LR202(_BaselineSwapSolverDR2DR31LR47):

        def _generate_substrate_to_evm_plan(self, intent: AppIntentDefinition, state: IntentState, snapshot: MarketSnapshot | None=None) -> ExecutionPlan:
            """Generate a 4-leg plan for Alpha → USDC (substrate + bridge + EVM).

        Leg 0 [substrate]: Unstake alpha → TAO via remove_stake
        Leg 1 [substrate]: Bridge deposit TAO to Tensorplex lock address
        Leg 2 [wait]:      Bridge finality (~30 min), handled by BridgeTracker
        Leg 3 [evm]:       Swap wTAO → output_token on Uniswap V3 (Ethereum)
        """
            from minotaur_subnet.shared.types import SubstrateAction
            params = _state_params(state)
            alpha_netuid = int(params['alpha_netuid'])
            _dr12 = None

            def _lr118():
                nonlocal _dr12
                owner_ss58 = params['owner_ss58']
                hotkey_ss58 = params.get('hotkey_ss58', params.get('alpha_hotkey', ''))
                amount_rao = int(params.get('alpha_amount_rao', params.get('amount_rao', 0)))

                def _dr51():
                    output_token = params.get('output_token', '')
                    _lr30 = None

                    def _lr226():
                        nonlocal _lr30
                        min_output = int(params.get('min_output_amount', 0))
                        dest_chain_id = int(params.get('dest_chain_id', 1))
                        receiver = params.get('recipient', params.get('receiver', state.owner))
                        if amount_rao <= 0:
                            raise ValueError('alpha_amount_rao must be positive')

                        def _lr30():
                            unstake_action = SubstrateAction(action='remove_stake', owner_ss58=owner_ss58, amount_rao=amount_rao, netuid=alpha_netuid, hotkey_ss58=hotkey_ss58)
                            bridge_fee_bps = 10
                            bridge_fee = amount_rao * bridge_fee_bps // 10000
                            tao_after_bridge = amount_rao - bridge_fee
                            from minotaur_subnet.bridge.tensorplex import _TENSORPLEX_LOCK_SS58

                            def _dr19():
                                bridge_action = evm_chain_id = evm_interactions = wTAO = None

                                def _lr203():
                                    nonlocal bridge_action, evm_chain_id, evm_interactions, wTAO
                                    bridge_action = SubstrateAction(action='bridge_deposit', owner_ss58=owner_ss58, amount_rao=amount_rao, dest_address=_TENSORPLEX_LOCK_SS58, metadata={'bridge': 'tensorplex', 'expected_output': tao_after_bridge, 'fee': bridge_fee, 'dst_chain_id': dest_chain_id})
                                    wTAO = '0x77E06c9eCCf2E797fd462A92B6D7642EF85b0A44'
                                    evm_chain_id = dest_chain_id if dest_chain_id in (1, 31337) else 1
                                    evm_interactions = []
                                _lr203()

                                def _dr63():
                                    nonlocal evm_interactions
                                    swap_state = None

                                    def _lr158():
                                        nonlocal evm_interactions
                                        if output_token and output_token.lower() != wTAO.lower():

                                            def _lr50():
                                                nonlocal swap_state
                                                swap_state = IntentState(contract_address=state.contract_address, chain_id=evm_chain_id, nonce=state.nonce, owner=receiver, raw_params={'input_token': wTAO, 'output_token': output_token, 'input_amount': str(tao_after_bridge), 'min_output_amount': str(min_output), 'receiver': receiver}, control={'_intent_function': 'swap'})
                                            _lr50()
                                            try:
                                                evm_plan = self.generate_plan(intent, swap_state, snapshot)
                                                evm_interactions = evm_plan.interactions
                                            except Exception as exc:
                                                logger.warning('EVM swap leg generation failed: %s', exc)
                                    _lr158()
                                    deadline = int(time.time()) + 7200
                                    return deadline
                                deadline = _dr63()
                                all_interactions = list(evm_interactions)

                                def _dr11():

                                    def _dr77():
                                        evm_indices = list(range(len(all_interactions)))

                                        def _lr65():
                                            return [{'leg_id': 0, 'type': 'source', 'runtime': 'substrate', 'chain_id': 0, 'interaction_indices': [], 'substrate_actions': [unstake_action.to_dict()]}]

                                        def _lr66():
                                            return [{'leg_id': 1, 'type': 'bridge', 'runtime': 'substrate', 'chain_id': 0, 'bridge_protocol': 'tensorplex', 'depends_on_leg': 0, 'interaction_indices': [], 'substrate_actions': [bridge_action.to_dict()], 'estimated_duration_s': 1800, 'estimated_output': str(tao_after_bridge), 'fee': str(bridge_fee), 'token_out': wTAO}]

                                        def _lr67():
                                            return [{'leg_id': 2, 'type': 'wait', 'runtime': 'none', 'chain_id': 0, 'depends_on_leg': 1, 'interaction_indices': []}, {'leg_id': 3, 'type': 'destination', 'runtime': 'evm', 'chain_id': evm_chain_id, 'depends_on_leg': 2, 'interaction_indices': evm_indices}]
                                        legs = [*_lr65(), *_lr66(), *_lr67()]
                                        return legs
                                    legs = _dr77()

                                    def _lr204():
                                        return {'cross_chain': True, 'substrate_origin': True, 'src_chain_id': 0, 'dst_chain_id': evm_chain_id, 'bridge_protocol': os.environ.get('BRIDGE_PROTOCOL', 'mock'), 'alpha_netuid': alpha_netuid, 'owner_ss58': owner_ss58, 'legs': legs, 'route': 'alpha_to_evm', 'input_amount_rao': str(amount_rao), 'output_token': output_token, 'chain_id': evm_chain_id}
                                    return ExecutionPlan(intent_id=intent.app_id, interactions=all_interactions, deadline=deadline, nonce=state.nonce, metadata={**_lr204()})
                                    return _DR_UNSET
                                return _dr11
                            _dr11 = _dr19()
                            return _dr11
                    _lr226()
                    return _lr30()
                _dr11 = _dr51()
                _dr12 = _dr11()
            _lr118()
            if _dr12 is not _DR_UNSET:
                return _dr12

    class _BaselineSwapSolverDR2DR31(_BaselineSwapSolverDR2DR31LR202):

        def _generate_yield_plan(self, intent: AppIntentDefinition, state: IntentState, snapshot: MarketSnapshot | None=None) -> ExecutionPlan:
            """Delegate to BaselineYieldStrategy for rebalance intents."""
            from draft.strategies.yield_optimizer.yield_solver import BaselineYieldStrategy
            strategy = BaselineYieldStrategy()
            strategy.APP_ID = intent.app_id
            plan = strategy.generate_plan(intent, state, snapshot)
            if plan is None:
                raise ValueError('Yield strategy returned no plan — check params (asset, amount)')
            return plan

        @staticmethod
        def _hop_dex(hop: dict[str, Any]) -> str:
            """Return the DEX tag for a hop. Defaults to ``uniswap_v3`` for
        legacy/snapshot-sourced pools that predate the ``dex`` marker."""
            return (hop.get('pool_state') or {}).get('dex') or 'uniswap_v3'

        @classmethod
        def _dominant_dex(cls, hops: list[dict[str, Any]]) -> str:
            """``aerodrome_slipstream`` if every hop is on Aerodrome, else
        ``uniswap_v3``. Used to pick the right router at plan time."""
            if all((cls._hop_dex(h) == 'aerodrome_slipstream' for h in hops)):
                return 'aerodrome_slipstream'
            return 'uniswap_v3'

    class _BaselineSwapSolverDR2DR88(_BaselineSwapSolverDR2DR31):

        def _derive_prices(self, pool_states: dict[str, dict[str, Any]], chain_id: int=1) -> dict[str, float]:

            def _dr50():
                """Derive USD prices from pool sqrtPriceX96 values.

        Uses USDC-paired pools to extract USD prices. Simplified
        price derivation — production solvers would use multiple sources.
        """
                from minotaur_subnet.blockchain.tokens import TOKENS

                def _lr258():
                    prices: dict[str, float] = {'USDC/USD': 1.0, 'USDT/USD': 1.0, 'DAI/USD': 1.0}
                    token_chain = 1 if chain_id == 31337 else chain_id
                    usdc_lower = TOKENS.get(token_chain, {}).get('USDC', '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48').lower()
                    return (prices, usdc_lower)
                return _lr258()
            prices, usdc_lower = _dr50()
            other_token = usd_price = None
            price_ratio = token0 = token1 = None
            for _pool_addr, state in pool_states.items():

                def _lr120():
                    nonlocal price_ratio, token0, token1

                    def _dr82():
                        token0 = state.get('token0', '').lower()
                        token1 = state.get('token1', '').lower()
                        sqrt_price_raw = state.get('sqrtPriceX96')
                        return (sqrt_price_raw, token0, token1)
                    sqrt_price_raw, token0, token1 = _dr82()
                    if not sqrt_price_raw:
                        return
                    sqrt_price = int(sqrt_price_raw)
                    if sqrt_price == 0:
                        return
                    price_ratio = sqrt_price ** 2 / 2 ** 192

                    def _lr19():
                        nonlocal other_token, usd_price
                        if token0 == usdc_lower:
                            other_token = token1
                            usd_price = 1.0 / price_ratio if price_ratio > 0 else 0
                        elif token1 == usdc_lower:
                            other_token = token0
                            usd_price = price_ratio
                        else:
                            return

                        def _dr96():
                            sym = _TOKEN_SYMBOLS.get(other_token, '')
                            if sym:
                                prices[f'{sym}/USD'] = usd_price
                            return sym
                        sym = _dr96()
                    _lr19()
                _lr120()
            return prices

    class _BaselineSwapSolverDR2LR39(_BaselineSwapSolverDR2DR88):

        def _build_direct_pool_plan(self, intent: AppIntentDefinition, state: IntentState, context: ProcessorContext, pool_states: dict[str, dict[str, Any]], input_token: str, output_token: str, chain_id: int) -> ExecutionPlan:
            """Build a plan that calls pool.swap() directly (no router needed).

        Used on chains like BT EVM where Uniswap V3 pools exist but no
        SwapRouter is deployed. Miners should improve on this by deploying
        their own router or using more sophisticated routing.
        """
            from eth_abi import encode as abi_encode
            swap_params = self._normalized_swap_params(intent, state)
            _dr85 = pool_address = t0 = zero_for_one = None

            def _lr148():
                nonlocal _dr85, pool_address, t0, zero_for_one

                def _dr18():

                    def _eh2():
                        return t1 == input_token.lower() and t0 == output_token.lower()

                    def _eh1():
                        return t0 == input_token.lower() and t1 == output_token.lower()
                    nonlocal pool_address, t0, zero_for_one

                    def _dr65():
                        nonlocal pool_address, zero_for_one
                        amount_in = swap_params.get('input_amount', 0)
                        deadline = min_output = recipient = None

                        def _lr156():
                            nonlocal deadline, min_output, pool_address, recipient, zero_for_one
                            min_output = swap_params.get('min_output_amount', 0)
                            recipient = state.contract_address or swap_params.get('receiver', state.owner)
                            deadline = context.timestamp + (self._processor.deadline_offset if self._processor else 300)
                            pool_address = None
                            zero_for_one = True
                        _lr156()
                        return (amount_in, deadline, min_output, recipient)
                    amount_in, deadline, min_output, recipient = _dr65()
                    t1 = None

                    def _lr2():
                        nonlocal pool_address, zero_for_one
                        for addr, ps in pool_states.items():

                            def _lr21():
                                nonlocal t0, t1
                                t0 = ps.get('token0', '').lower()
                                t1 = ps.get('token1', '').lower()
                            _lr21()
                            if _eh1():
                                pool_address = addr
                                zero_for_one = True
                                break
                            elif _eh2():
                                pool_address = addr
                                zero_for_one = False
                                break
                    _lr2()

                    def _lr268():
                        return (amount_in, deadline, min_output, recipient)
                    return _lr268()
                amount_in, deadline, min_output, recipient = _dr18()
                pool_address = t0 = zero_for_one = None
                if not pool_address:
                    known = _KNOWN_POOLS.get(chain_id, [])

                    def _lr48():
                        nonlocal pool_address, t0, zero_for_one
                        if known:
                            pool_address = known[0]
                            try:

                                def _dr100():
                                    w3 = self._get_web3(chain_id)
                                    pool_contract = w3.eth.contract(address=w3.to_checksum_address(pool_address), abi=_POOL_ABI)
                                    return pool_contract
                                pool_contract = _dr100()
                                t0 = pool_contract.functions.token0().call().lower()
                                zero_for_one = t0 == input_token.lower()
                            except Exception:
                                pass
                    _lr48()

                def _dr84():
                    if not pool_address:
                        raise ValueError(f'No pool found for {input_token}/{output_token} on chain {chain_id}')

                    def _dr35():

                        def _eh3():
                            return [Interaction(target=input_token, value='0', call_data='0x095ea7b3' + pool_address.replace('0x', '').lower().zfill(64) + hex(amount_in)[2:].zfill(64), chain_id=chain_id), Interaction(target=pool_address, value='0', call_data=swap_calldata, chain_id=chain_id)]

                        def _dr8():
                            MIN_SQRT_RATIO = 4295128739
                            MAX_SQRT_RATIO = 1461446703485210103287273052203988822378723970342
                            sqrt_price_limit = MIN_SQRT_RATIO + 1 if zero_for_one else MAX_SQRT_RATIO - 1
                            swap_selector = '128acb08'

                            def _lr134():
                                callback_data = abi_encode(['address', 'address', 'uint24'], [input_token if input_token.startswith('0x') else '0x' + '0' * 40, output_token if output_token.startswith('0x') else '0x' + '0' * 40, 3000])

                                def _dr64():

                                    def _lr83():
                                        return '0x' + swap_selector + recipient.replace('0x', '').lower().zfill(64) + ('01' if zero_for_one else '00').zfill(64) + hex(amount_in)[2:].zfill(64)

                                    def _lr84():
                                        return _lr83() + hex(sqrt_price_limit)[2:].zfill(64) + hex(160)[2:].zfill(64) + hex(len(callback_data))[2:].zfill(64)

                                    def _lr85():
                                        return _lr84() + callback_data.hex()
                                    swap_calldata = _lr85()
                                    return swap_calldata
                                swap_calldata = _dr64()
                                return swap_calldata
                            return _lr134()
                        swap_calldata = _dr8()
                        interactions = _eh3()

                        def _lr26():
                            return ExecutionPlan(intent_id=intent.app_id, interactions=interactions, deadline=deadline, nonce=state.nonce, metadata={'route': 'uniswap_v3_direct_pool', 'pool': pool_address, 'zero_for_one': zero_for_one, 'input_token': input_token, 'output_token': output_token, 'input_amount': str(amount_in), 'min_output_amount': str(min_output), 'chain_id': chain_id})
                            return _DR_UNSET
                        return _lr26()
                    _dr36 = _dr35()
                    if _dr36 is not _DR_UNSET:
                        return _dr36
                    return _DR_UNSET
                _dr85 = _dr84()
            _lr148()
            if _dr85 is not _DR_UNSET:
                return _dr85

    class _BaselineSwapSolverDR2LR159(_BaselineSwapSolverDR2LR39):

        def _get_pool_states(self, chain_id: int, snapshot: MarketSnapshot | None) -> dict[str, dict[str, Any]]:
            """Get pool states: RPC first, then snapshot fallback."""
            if self._rpc_urls.get(chain_id):
                rpc_pools = self._discover_pools(chain_id)
                if rpc_pools:
                    return rpc_pools
            if snapshot is not None and snapshot.pool_states:
                return snapshot.pool_states
            return {}

    class _BaselineSwapSolverDR2(_BaselineSwapSolverDR2LR159):

        def _ensure_pools_for_route(self, chain_id: int, pool_states: dict[str, dict[str, Any]], token_in: str, token_out: str) -> dict[str, dict[str, Any]]:
            """Discover pools needed for routing token_in -> token_out.

        Queries the Uniswap V3 Factory for the direct pair and
        intermediary pairs (for multi-hop routing via WETH, USDC).
        """
            if not self._rpc_urls.get(chain_id):
                return pool_states
            mid = mid_lower = None

            def _lr215():
                nonlocal mid, mid_lower

                def _dr97():
                    self._discover_pools_for_pair(chain_id, token_in, token_out, pool_states)
                    intermediaries = self._intermediaries_for_chain(chain_id)
                    in_lower, out_lower = (token_in.lower(), token_out.lower())
                    return (in_lower, intermediaries, out_lower)
                in_lower, intermediaries, out_lower = _dr97()
                mid = mid_lower = None

                def _lr51():
                    nonlocal mid, mid_lower
                    for mid in intermediaries:
                        mid_lower = mid.lower()
                        if mid_lower == in_lower or mid_lower == out_lower:
                            continue
                        self._discover_pools_for_pair(chain_id, token_in, mid, pool_states)
                        self._discover_pools_for_pair(chain_id, mid, token_out, pool_states)
                _lr51()
                from strategies.dex_aggregator import aerodrome as _aero
                if chain_id in _aero.AERODROME_SLIPSTREAM_FACTORY:
                    w3 = self._get_web3(chain_id)

                    def _dr37():
                        nonlocal mid, mid_lower
                        if w3 is not None:
                            _aero.discover_pools_for_pair(w3, chain_id, token_in, token_out, pool_states, self._query_pool_state, self._pair_discovery_cache, cache_ttl=self._pool_cache_ttl)

                            def _lr243():
                                nonlocal mid, mid_lower
                                for mid in intermediaries:
                                    mid_lower = mid.lower()
                                    if mid_lower == in_lower or mid_lower == out_lower:
                                        continue

                                    def _lr35():
                                        _aero.discover_pools_for_pair(w3, chain_id, token_in, mid, pool_states, self._query_pool_state, self._pair_discovery_cache, cache_ttl=self._pool_cache_ttl)
                                        _aero.discover_pools_for_pair(w3, chain_id, mid, token_out, pool_states, self._query_pool_state, self._pair_discovery_cache, cache_ttl=self._pool_cache_ttl)
                                    _lr35()
                            _lr243()
                    _dr37()
                return pool_states
            return _lr215()

    class _BaselineSwapSolverDR31(_BaselineSwapSolverDR2):

        def quote(self, intent: AppIntentDefinition, state: IntentState, snapshot: MarketSnapshot | None=None) -> QuoteResult:
            """Compute a quote using RPC pool data (preferred) or snapshot fallback.

        Uses the shared normalized swap view (typed context first, raw
        compatibility payload second), routes through discovered pools,
        and returns estimated output.
        """
            from strategies.dex_aggregator.pool_math import find_best_route
            swap_params = self._normalized_swap_params(intent, state)
            input_token = swap_params.get('input_token', '')
            output_token = swap_params.get('output_token', '')

            def _lr121():
                amount_in = swap_params.get('input_amount', 0)

                def _dr58():
                    if not input_token or not output_token:
                        raise ValueError('input_token and output_token required in params')
                    output_chain = None

                    def _lr244():
                        nonlocal output_chain
                        if amount_in <= 0:
                            raise ValueError('input_amount must be positive')
                        input_chain = swap_params.get('_input_chain', state.chain_id)
                        output_chain = swap_params.get('_output_chain', state.chain_id)
                        dest_chain_id = _cross_chain_compat_params(state).get('dest_chain_id')

                        def _lr44():
                            nonlocal output_chain
                            if dest_chain_id:
                                output_chain = int(dest_chain_id)
                            if input_chain and output_chain and (input_chain != output_chain):
                                return self._quote_cross_chain(intent, state, snapshot, input_token, output_token, amount_in, int(input_chain), int(output_chain))
                            return _DR_UNSET
                        return _lr44()
                    return _lr244()
                _dr59 = _dr58()
                if _dr59 is not _DR_UNSET:
                    return _dr59

                def _dr22():
                    chain_id = pool_states = None

                    def _lr248():
                        nonlocal chain_id, pool_states
                        chain_id = state.chain_id or (snapshot.chain_id if snapshot else 1)
                        pool_states = self._get_pool_states(chain_id, snapshot)
                        if snapshot is not None and snapshot.pool_states and (pool_states is snapshot.pool_states):
                            pool_states = dict(pool_states)
                    _lr248()

                    def _dr66():
                        self._ensure_pools_for_route(chain_id, pool_states, input_token, output_token)

                        def _lr227():
                            if not pool_states:
                                raise ValueError(f'No pool data available for chain {chain_id} (no RPC URL configured and no snapshot provided)')
                            result = self._find_best_executable_route(pool_states, input_token, output_token, amount_in, chain_id)
                            if result is None:
                                raise ValueError(f'No route found for {input_token} -> {output_token}')

                            def _lr36():
                                output_amount, route_desc, hops = result
                                data_source = 'rpc' if self._rpc_urls.get(chain_id) else 'snapshot'
                                gas_estimate = _GAS_BASE_OVERHEAD + _GAS_PER_HOP * len(hops)
                                gas_price_wei = self._get_gas_price_wei(chain_id)

                                def _dr13():
                                    fee_wei = _compute_platform_fee_wei(gas_estimate, gas_price_wei)
                                    from minotaur_subnet.blockchain.tokens import WRAPPED_NATIVE_TOKEN, WRAPPED_NATIVE_SYMBOL
                                    wnt_addr = WRAPPED_NATIVE_TOKEN.get(chain_id, '')

                                    def _lr146():
                                        wnt_symbol = WRAPPED_NATIVE_SYMBOL.get(chain_id, 'ETH')
                                        per_hop_dex = [self._hop_dex(h) for h in hops]
                                        dominant = self._dominant_dex(hops)

                                        def _dr69():
                                            protocol_labels = {'uniswap_v3': 'UniswapV3', 'aerodrome_slipstream': 'AerodromeSlipstream'}

                                            def _lr40():
                                                return {'hops': len(hops), 'pools': [h['pool_addr'] for h in hops], 'fees': [h['fee'] for h in hops], 'protocol': protocol_labels.get(dominant, dominant)}

                                            def _lr41():
                                                return {'protocols': [protocol_labels.get(d, d) for d in per_hop_dex], 'data_source': data_source}

                                            def _lr238():
                                                return QuoteResult(estimated_output=str(output_amount), route_summary=f'{input_token[:10]}..→{output_token[:10]}.. {route_desc}', gas_estimate=gas_estimate, metadata={**_lr40(), **_lr41()}, platform_fee_wei=str(fee_wei), platform_fee_token=wnt_addr, platform_fee_symbol=wnt_symbol)
                                            return _lr238()
                                            return _DR_UNSET
                                            return _DR_UNSET
                                        _dr70 = _dr69()
                                        if _dr70 is not _DR_UNSET:
                                            return _dr70
                                        return _DR_UNSET
                                    return _lr146()
                                return _dr13
                            return _lr36()
                        return _lr227()
                    _dr13 = _dr66()
                    return _dr13
                _dr13 = _dr22()
                _dr14 = _dr13()
                if _dr14 is not _DR_UNSET:
                    return _dr14
            return _lr121()

    class _BaselineSwapSolverDR34LR49(_BaselineSwapSolverDR31):

        def _quote_cross_chain(self, intent: AppIntentDefinition, state: IntentState, snapshot: MarketSnapshot | None, input_token: str, output_token: str, amount_in: int, src_chain: int, dst_chain: int) -> QuoteResult:
            bridge_token_out = find_best_route = None

            def _lr209():
                nonlocal bridge_token_out, find_best_route

                def _dr45():
                    """Quote a cross-chain swap: bridge + swap (either order).

        Two directions:
        A) Bridge-first: input has a direct bridge route (e.g. USDC Base→BT EVM),
           then swap on destination (USDC→WTAO on BT EVM).
        B) Swap-first: no direct bridge for input token, swap on source chain
           to a bridgeable token, then bridge to destination
           (e.g. WTAO→USDC on BT EVM, then bridge USDC to Base).
        """
                    from strategies.dex_aggregator.pool_math import find_best_route
                    bridge_quote_a = None
                    if self._bridge_registry is not None:
                        try:
                            bridge_quote_a = _run_coro(self._bridge_registry.best_quote(input_token, amount_in, src_chain, dst_chain))
                        except Exception:
                            pass
                    return (bridge_quote_a, find_best_route)
                bridge_quote_a, find_best_route = _dr45()
                if bridge_quote_a:
                    bridged_amount = bridge_quote_a.estimated_output
                    bridge_token_out = bridge_quote_a.token_out

                    def _dr38():
                        bridge_fee = bridge_quote_a.fee
                        dst_pool_states = self._get_pool_states(dst_chain, snapshot)
                        self._ensure_pools_for_route(dst_chain, dst_pool_states, bridge_token_out, output_token)

                        def _dr5():
                            nonlocal hops, route, route_desc
                            if bridge_token_out.lower() == output_token.lower():

                                def _lr239():
                                    return (1, QuoteResult(estimated_output=str(bridged_amount), route_summary=f'Cross-chain: bridge {src_chain}→{dst_chain} (direct)', gas_estimate=_GAS_BASE_OVERHEAD * 2, metadata={'cross_chain': True, 'direction': 'bridge_only', 'src_chain': src_chain, 'dst_chain': dst_chain, 'bridge_fee': bridge_fee, 'protocol': 'Hyperlane'}, computed_params={'min_output_amount': str(bridged_amount)}))
                                    return (0, None)
                                _lrt240 = _lr239()
                                if _lrt240[0]:
                                    return _lrt240[1]

                            def _lr55():
                                nonlocal hops, route, route_desc
                                route = find_best_route(dst_pool_states, bridge_token_out, output_token, bridged_amount)
                                if route:
                                    output_amount, route_desc, hops = route

                                    def _dr74():

                                        def _lr138():
                                            return (str(output_amount), f'Cross-chain: bridge {src_chain}→{dst_chain} + {route_desc}', _GAS_BASE_OVERHEAD * 2 + _GAS_PER_HOP * len(hops))
                                        _lrt139 = _lr138()

                                        def _lr216():
                                            return (_lrt139[0], _lrt139[1], _lrt139[2], {'cross_chain': True, 'direction': 'bridge_then_swap', 'src_chain': src_chain, 'dst_chain': dst_chain, 'bridge_fee': bridge_fee, 'bridged_amount': bridged_amount, 'hops': len(hops), 'protocol': 'UniswapV3 + Hyperlane'})
                                        _lrt217 = _lr216()
                                        return QuoteResult(estimated_output=_lrt217[0], route_summary=_lrt217[1], gas_estimate=_lrt217[2], metadata=_lrt217[3], computed_params={'min_output_amount': str(output_amount * 99 // 100)})
                                        return _DR_UNSET
                                    _dr75 = _dr74()
                                    if _dr75 is not _DR_UNSET:
                                        return _dr75
                                return _DR_UNSET
                            return _lr55()
                        _dr6 = _dr5()
                        if _dr6 is not _DR_UNSET:
                            return _dr6
                        return _DR_UNSET
                    _dr39 = _dr38()
                    if _dr39 is not _DR_UNSET:
                        return (1, _dr39)
                return (0, None)
            _lrt210 = _lr209()
            if _lrt210[0]:
                return _lrt210[1]

            def _dr16():
                nonlocal bridge_quote_b, route
                bridge_quote_b = None
                bridgeable_token = None
                adapter = has_fr = None
                if self._bridge_registry is not None:

                    def _dr95():
                        bridgeable_adapters = src_tokens = None

                        def _lr256():
                            nonlocal bridgeable_adapters, src_tokens
                            from minotaur_subnet.blockchain.tokens import TOKENS
                            src_tokens = TOKENS.get(src_chain, {})
                            if not src_tokens:
                                for seed_addr in _DISCOVERY_SEED_TOKENS.get(src_chain, []):
                                    src_tokens[seed_addr[:8]] = seed_addr
                            bridgeable_adapters = self._bridge_registry.find_bridge(src_chain, dst_chain)
                        _lr256()
                        return (bridgeable_adapters, src_tokens)
                    bridgeable_adapters, src_tokens = _dr95()
                    for symbol, addr in src_tokens.items():

                        def _lr93():
                            nonlocal adapter, bridgeable_token, has_fr, route
                            if addr.lower() == input_token.lower():
                                return True
                            for adapter in bridgeable_adapters:
                                has_fr = hasattr(adapter, '_find_route')
                                route = adapter._find_route(src_chain, dst_chain, addr) if has_fr else None
                                if route:
                                    bridgeable_token = addr
                                    break
                        if _lr93():
                            continue
                        if bridgeable_token:
                            break
                return bridgeable_token
            bridgeable_token = _dr16()
            _dr26 = bridge_quote_b = hops = route_desc = None
            route = None

            def _lr54():
                nonlocal route
                if bridgeable_token:

                    def _dr87():
                        src_pool_states = self._get_pool_states(src_chain, snapshot)
                        self._ensure_pools_for_route(src_chain, src_pool_states, input_token, bridgeable_token)
                        return src_pool_states
                    src_pool_states = _dr87()
                    route = find_best_route(src_pool_states, input_token, bridgeable_token, amount_in)
                    if route:

                        def _lr17():
                            nonlocal _dr26, bridge_quote_b, hops, route_desc
                            swap_output, route_desc, hops = route
                            try:
                                bridge_quote_b = _run_coro(self._bridge_registry.best_quote(bridgeable_token, swap_output, src_chain, dst_chain))
                            except Exception:
                                pass

                            def _dr25():
                                nonlocal bridge_token_out
                                if bridge_quote_b:
                                    final_output = bridge_quote_b.estimated_output
                                    bridge_token_out = bridge_quote_b.token_out
                                    if bridge_token_out.lower() == output_token.lower():

                                        def _lr75():
                                            return (str(final_output), f'Cross-chain: {route_desc} + bridge {src_chain}→{dst_chain}', _GAS_BASE_OVERHEAD * 2 + _GAS_PER_HOP * len(hops))
                                        _lrt76 = _lr75()

                                        def _lr105():
                                            return QuoteResult(estimated_output=_lrt76[0], route_summary=_lrt76[1], gas_estimate=_lrt76[2], metadata={'cross_chain': True, 'direction': 'swap_then_bridge', 'src_chain': src_chain, 'dst_chain': dst_chain, 'bridge_fee': bridge_quote_b.fee, 'swap_output': swap_output, 'hops': len(hops), 'protocol': 'UniswapV3 + Hyperlane'}, computed_params={'min_output_amount': str(final_output)})
                                        return _lr105()
                                return _DR_UNSET
                            _dr26 = _dr25()
                        _lr17()
                        if _dr26 is not _DR_UNSET:
                            return _dr26

                def _dr62():
                    raise ValueError(f'No cross-chain route found for {input_token[:10]}.. ({src_chain}) → {output_token[:10]}.. ({dst_chain})')
                _dr62()
            return _lr54()

        def check_trigger(self, intent: AppIntentDefinition, state: IntentState, snapshot: MarketSnapshot | None=None) -> bool:
            """Delegate trigger check to the wrapped processor."""
            if self._processor is None:
                return False
            chain_id = state.chain_id or (snapshot.chain_id if snapshot else 1)
            context = None

            def _lr109():
                nonlocal context
                context = ProcessorContext(chain_id=chain_id, timestamp=snapshot.timestamp if snapshot else int(time.time()), block_number=snapshot.block_number if snapshot else 0, rpc_url=self._rpc_urls.get(chain_id, ''), prices={}, dex_config={})
            _lr109()
            return _run_coro(self._processor.check_trigger(intent, state, context))

    class _BaselineSwapSolverDR34LR246(_BaselineSwapSolverDR34LR49):

        def _find_bridgeable_token(self, src_chain: int, dst_chain: int, exclude_token: str) -> str:
            """Find a token on src_chain that can be bridged to dst_chain."""
            if self._bridge_registry is None:
                return ''
            from minotaur_subnet.blockchain.tokens import TOKENS
            adapter = route = None

            def _lr212():
                for symbol, addr in TOKENS.get(src_chain, {}).items():
                    if addr.lower() == exclude_token.lower():
                        continue

                    def _lr111():
                        nonlocal adapter, route
                        adapters = self._bridge_registry.find_bridge(src_chain, dst_chain)
                        for adapter in adapters:
                            if hasattr(adapter, '_find_route'):
                                route = adapter._find_route(src_chain, dst_chain, addr)
                                if route:
                                    return (1, addr)
                        return (0, None)
                    _lrt112 = _lr111()
                    if _lrt112[0]:
                        return _lrt112[1]
                return ''
            return _lr212()

    class _BaselineSwapSolverDR34(_BaselineSwapSolverDR34LR246):

        def _generate_cross_chain_plan(self, intent: AppIntentDefinition, state: IntentState, snapshot: MarketSnapshot | None, src_chain: int, dst_chain: int) -> ExecutionPlan:
            """Generate a cross-chain plan using the CrossChainPlan primitive.

        The solver provides business-logic legs (swaps, stakes, etc.) and
        bridge requests. The platform's CrossChainCompiler handles all
        bridge mechanics, escrow, rollback, and simulation mocking.

        Two patterns:
        A) Bridge-first: input token has direct bridge route
           → Leg 0 (src): bridge input token
           → Leg 1 (dst): swap bridged token → desired output
        B) Swap-first: input token has no bridge route
           → Leg 0 (src): swap input → bridgeable token
           → Leg 1 (dst): receive bridged token (or swap further)
        """
            from minotaur_subnet.shared.types import BridgeRequest, ChainLeg, CrossChainPlan

            def _dr86():
                cross_chain_params = self._cross_chain_params(intent, state)
                input_token = cross_chain_params.get('input_token', '')
                output_token = cross_chain_params.get('output_token', '')
                input_amount = int(cross_chain_params.get('input_amount', 0))
                needs_source_swap = None

                def _lr115():
                    nonlocal needs_source_swap

                    def _dr10():
                        nonlocal bridge_token
                        recipient = cross_chain_params.get('dest_recipient') or state.owner or cross_chain_params.get('receiver') or _ZERO_ADDRESS
                        if recipient == state.contract_address and state.owner:
                            recipient = state.owner
                        bridge_token = input_token
                        needs_source_swap = None

                        def _lr88():
                            nonlocal needs_source_swap
                            bridge_amount = input_amount

                            def _dr54():
                                needs_source_swap = True
                                if self._bridge_registry is not None:

                                    def _lr45():
                                        nonlocal needs_source_swap
                                        try:
                                            direct_quote = _run_coro(self._bridge_registry.best_quote(input_token, input_amount, src_chain, dst_chain))
                                            if direct_quote is not None:
                                                needs_source_swap = False
                                                logger.info('Cross-chain: direct bridge for %s (%s→%s) via %s', input_token[:10], src_chain, dst_chain, direct_quote.protocol)
                                        except Exception:
                                            pass
                                    _lr45()

                                def _lr247():
                                    chain_legs: list[ChainLeg] = []
                                    bridge_requests: list[BridgeRequest] = []
                                    from eth_hash.auto import keccak as _kh
                                    bridge_sel = _kh(b'bridge(address,uint256,uint256,address)')[:4].hex()
                                    return (_kh, bridge_requests, bridge_sel, chain_legs, needs_source_swap)
                                return _lr247()
                            _kh, bridge_requests, bridge_sel, chain_legs, needs_source_swap = _dr54()
                            swap_sel = _kh(b'swap(address,address,uint256,uint256,address)')[:4].hex()
                            return (bridge_amount, bridge_requests, bridge_sel, chain_legs, needs_source_swap, recipient, swap_sel)
                        return _lr88()
                    bridge_amount, bridge_requests, bridge_sel, chain_legs, needs_source_swap, recipient, swap_sel = _dr10()
                    return (bridge_amount, bridge_requests, bridge_sel, chain_legs, cross_chain_params, input_amount, input_token, needs_source_swap, output_token, recipient, swap_sel)
                return _lr115()
            bridge_amount, bridge_requests, bridge_sel, chain_legs, cross_chain_params, input_amount, input_token, needs_source_swap, output_token, recipient, swap_sel = _dr86()
            bridge_token = dest_interactions = None

            def _lr144():
                nonlocal bridge_token, dest_interactions
                bridge_token = dest_interactions = None
                if needs_source_swap:

                    def _dr30():

                        def _lr257():
                            source_interactions = self._build_source_swap_interactions(intent, state, snapshot, src_chain, input_token, output_token, input_amount, cross_chain_params)
                            chain_legs.append(ChainLeg(chain_id=src_chain, interactions=source_interactions, intent_selector=swap_sel, metadata={'type': 'source_swap'}))
                        _lr257()
                        bridgeable_token = self._find_bridgeable_token(src_chain, dst_chain, input_token)
                        return bridgeable_token
                    bridgeable_token = _dr30()

                    def _lr22():
                        nonlocal bridge_token, dest_interactions
                        if bridgeable_token:
                            bridge_token = bridgeable_token

                        def _dr55():
                            bridge_requests.append(BridgeRequest(token=bridge_token, amount=bridge_amount, src_chain_id=src_chain, dst_chain_id=dst_chain, recipient=recipient, purpose=f'bridge {bridge_token[:10]}.. for dest action'))
                        _dr55()
                        dest_interactions = self._build_dest_swap_interactions(intent, state, snapshot, dst_chain, output_token, recipient)
                        chain_legs.append(ChainLeg(chain_id=dst_chain, interactions=dest_interactions, intent_selector=swap_sel, metadata={'type': 'destination_action'}))
                    _lr22()
                else:

                    def _dr17():
                        nonlocal dest_interactions

                        def _lr106():
                            chain_legs.append(ChainLeg(chain_id=src_chain, interactions=[], intent_selector=bridge_sel, metadata={'type': 'bridge_source'}))
                            bridge_requests.append(BridgeRequest(token=input_token, amount=input_amount, src_chain_id=src_chain, dst_chain_id=dst_chain, recipient=recipient, purpose=f'bridge {input_token[:10]}.. to dest chain'))
                        _lr106()
                        dest_interactions = self._build_dest_swap_interactions(intent, state, snapshot, dst_chain, output_token, recipient)
                        chain_legs.append(ChainLeg(chain_id=dst_chain, interactions=dest_interactions, intent_selector=swap_sel, metadata={'type': 'destination_swap'}))
                    _dr17()

                def _dr41():
                    cross_chain_plan = CrossChainPlan(legs=chain_legs, bridge_requests=bridge_requests)
                    return ExecutionPlan(intent_id=intent.app_id, interactions=[], deadline=int(time.time()) + 7200, nonce=state.nonce, metadata={'cross_chain_plan': cross_chain_plan.to_dict(), 'src_chain_id': src_chain, 'dst_chain_id': dst_chain, 'plan_type': 'cross_chain'})
                    return _DR_UNSET
                _dr42 = _dr41()
                if _dr42 is not _DR_UNSET:
                    return _dr42
            return _lr144()

        def _build_source_swap_interactions(self, intent, state, snapshot, src_chain, input_token, output_token, input_amount, cross_chain_params) -> list[Interaction]:
            """Build source chain swap interactions for cross-chain Pattern B."""
            source_state = None
            try:

                def _lr107():
                    nonlocal source_state
                    source_state = self._state_with_extra(intent, state, chain_id=src_chain, extra_updates={'input_token': input_token, 'output_token': output_token, 'input_amount': str(input_amount), 'receiver': cross_chain_params.get('receiver', state.owner or ''), 'min_output_amount': cross_chain_params.get('min_output_amount', 0)})
                _lr107()
                pool_states = self._get_pool_states(src_chain, snapshot)

                def _dr52():
                    nonlocal pool_states

                    def _lr154():
                        nonlocal pool_states
                        if input_token and output_token:
                            if snapshot and snapshot.pool_states and (pool_states is snapshot.pool_states):
                                pool_states = dict(pool_states)
                            self._ensure_pools_for_route(src_chain, pool_states, input_token, output_token)
                    _lr154()
                    prices = self._derive_prices(pool_states, src_chain) if pool_states else {}
                    source_plan = None

                    def _lr33():
                        nonlocal source_plan
                        context = ProcessorContext(chain_id=src_chain, timestamp=int(time.time()), block_number=0, rpc_url=self._rpc_urls.get(src_chain, ''), prices=prices)
                        source_plan = _run_coro(self._processor.generate_plan(intent, source_state, context))
                    _lr33()
                    return source_plan.interactions
                    return _DR_UNSET
                _dr53 = _dr52()
                if _dr53 is not _DR_UNSET:
                    return _dr53
            except Exception as exc:
                logger.warning('Cross-chain source swap failed: %s', exc)
                return []

        def _build_dest_swap_interactions(self, intent, state, snapshot, dst_chain, output_token, recipient) -> list[Interaction]:
            """Build destination chain swap interactions."""
            try:
                pool_states = self._get_pool_states(dst_chain, snapshot)

                def _lr116():
                    seeds = _DISCOVERY_SEED_TOKENS.get(dst_chain, [])
                    if output_token and seeds:
                        for seed in seeds:
                            if seed.lower() != output_token.lower():
                                self._ensure_pools_for_route(dst_chain, pool_states, seed, output_token)
                _lr116()
                if not pool_states:
                    return []
                return []
            except Exception as exc:
                logger.warning('Cross-chain dest swap interactions failed: %s', exc)
                return []

def _mw2():
    global _BaselineSwapSolverDR89, _BaselineSwapSolverLR53, _BaselineSwapSolverLR249, BaselineSwapSolver, SOLVER_CLASS

    class _BaselineSwapSolverDR89(_BaselineSwapSolverDR34):

        def _build_aerodrome_singlehop_plan(self, intent: AppIntentDefinition, state: IntentState, context: ProcessorContext, hop: dict[str, Any], input_token: str, output_token: str, amount_in: int, expected_output: int, chain_id: int) -> ExecutionPlan:
            """Single-hop swap routed through Aerodrome's Slipstream router."""
            deadline = interactions = min_output = router = tick_spacing = None

            def _lr113():
                nonlocal deadline, interactions, min_output, router, tick_spacing
                from strategies.dex_aggregator import aerodrome as _aero
                from common.abi_utils import encode_approve
                router = _aero.AERODROME_SLIPSTREAM_ROUTER.get(chain_id)

                def _dr73():
                    if not router:
                        raise ValueError(f'No Aerodrome Slipstream router for chain {chain_id}')
                    _dr32 = deadline = min_output = tick_spacing = None

                    def _lr241():
                        nonlocal _dr32, deadline, min_output, tick_spacing
                        _dr32 = min_output = None

                        def _lr58():
                            nonlocal _dr32, min_output
                            swap_params = self._normalized_swap_params(intent, state)
                            min_output = swap_params.get('min_output_amount', 0)
                            if not min_output:
                                slippage_bps = self._processor.slippage_bps
                                min_output = expected_output * (10000 - slippage_bps) // 10000

                            def _dr32():
                                deadline = recipient = tick_spacing = None

                                def _lr46():
                                    nonlocal deadline, recipient, tick_spacing
                                    deadline = context.timestamp + self._processor.deadline_offset
                                    recipient = state.contract_address or swap_params.get('receiver', state.owner)
                                    tick_spacing = int(hop['pool_state'].get('tickSpacing', 0))
                                _lr46()

                                def _lr142():
                                    return [Interaction(target=input_token, value='0', call_data=encode_approve(router, amount_in), chain_id=chain_id), Interaction(target=router, value='0', call_data=_aero.encode_exact_input_single(token_in=input_token, token_out=output_token, tick_spacing=tick_spacing, recipient=recipient, deadline=deadline, amount_in=amount_in, amount_out_minimum=0), chain_id=chain_id)]
                                interactions = _lr142()
                                return (deadline, interactions, tick_spacing)
                        _lr58()
                        deadline, interactions, tick_spacing = _dr32()
                        logger.info('Aerodrome single-hop plan: %s -> %s tickSpacing=%d expected_out=%d', input_token[:10], output_token[:10], tick_spacing, expected_output)
                        return (deadline, interactions, min_output, tick_spacing)
                    return _lr241()
                deadline, interactions, min_output, tick_spacing = _dr73()
            _lr113()

            def _lr163():
                return ExecutionPlan(intent_id=intent.app_id, interactions=interactions, deadline=deadline, nonce=state.nonce, metadata={'route': 'aerodrome_slipstream', 'dex': 'aerodrome', 'router': router, 'tick_spacing': tick_spacing, 'input_token': input_token, 'output_token': output_token, 'input_amount': str(amount_in), 'min_output_amount': str(min_output), 'expected_output': str(expected_output), 'chain_id': chain_id})
            return _lr163()

    class _BaselineSwapSolverLR53(_BaselineSwapSolverDR89):

        def _build_aerodrome_multihop_plan(self, intent: AppIntentDefinition, state: IntentState, context: ProcessorContext, hops: list[dict[str, Any]], input_token: str, output_token: str, amount_in: int, expected_output: int, chain_id: int) -> ExecutionPlan:
            """Multi-hop swap routed entirely through Aerodrome's Slipstream
        router. Path is packed as ``token0 + ts0 + token1 + ts1 + ...``
        (3-byte tickSpacing per hop, mirroring the Uni V3 packed-fee path).
        """
            from strategies.dex_aggregator import aerodrome as _aero
            from common.abi_utils import encode_approve
            _dr2 = min_output = None

            def _lr164():
                nonlocal _dr2, min_output
                router = _aero.AERODROME_SLIPSTREAM_ROUTER.get(chain_id)
                if not router:
                    raise ValueError(f'No Aerodrome Slipstream router for chain {chain_id}')
                swap_params = self._normalized_swap_params(intent, state)
                tokens = [input_token]
                _dr2 = min_output = None

                def _lr27():
                    nonlocal _dr2, min_output

                    def _dr43():
                        nonlocal min_output
                        tick_spacings: list[int] = []
                        pool = None

                        def _lr242():
                            nonlocal min_output
                            for hop in hops:

                                def _lr52():
                                    nonlocal pool
                                    pool = hop['pool_state']
                                    t0 = pool['token0'].lower()
                                    if tokens[-1].lower() == t0:
                                        tokens.append(pool['token1'])
                                    else:
                                        tokens.append(pool['token0'])
                                _lr52()
                                tick_spacings.append(int(pool.get('tickSpacing', 0)))
                            path = _aero.encode_path(tokens, tick_spacings)
                            min_output = swap_params.get('min_output_amount', 0)
                            return (path, tick_spacings)
                        return _lr242()
                    path, tick_spacings = _dr43()
                    if not min_output:
                        slippage_bps = self._processor.slippage_bps
                        min_output = expected_output * (10000 - slippage_bps) // 10000
                    deadline = context.timestamp + self._processor.deadline_offset

                    def _dr2():

                        def _dr78():
                            recipient = state.contract_address or swap_params.get('receiver', state.owner)
                            interactions = None

                            def _lr259():
                                nonlocal interactions
                                interactions = None

                                def _lr86():
                                    nonlocal interactions
                                    interactions = [Interaction(target=input_token, value='0', call_data=encode_approve(router, amount_in), chain_id=chain_id), Interaction(target=router, value='0', call_data=_aero.encode_exact_input(path=path, recipient=recipient, deadline=deadline, amount_in=amount_in, amount_out_minimum=0), chain_id=chain_id)]
                                _lr86()
                                logger.info('Aerodrome multi-hop plan: %d hops, path=%s, tickSpacings=%s', len(hops), ' -> '.join((t[:10] for t in tokens)), tick_spacings)
                                return interactions
                            return _lr259()
                        interactions = _dr78()

                        def _lr165():
                            return {'route': 'aerodrome_slipstream_multihop', 'dex': 'aerodrome', 'router': router, 'hops': len(hops), 'tokens': tokens, 'tick_spacings': tick_spacings, 'input_token': input_token, 'output_token': output_token, 'input_amount': str(amount_in), 'min_output_amount': str(min_output), 'expected_output': str(expected_output), 'chain_id': chain_id}
                        return ExecutionPlan(intent_id=intent.app_id, interactions=interactions, deadline=deadline, nonce=state.nonce, metadata={**_lr165()})
                        return _DR_UNSET
                _lr27()
            _lr164()
            _dr7 = _dr2()
            if _dr7 is not _DR_UNSET:
                return _dr7

        def metadata(self) -> SolverMetadata:
            """Return baseline solver metadata."""
            return SolverMetadata(name='baseline-swap-solver', version='2.0.0', author='minotaur-subnet', description='Baseline v2 solver with RPC-first pool discovery. Queries real Uniswap V3 pool states for accurate pricing. Falls back to snapshot when no RPC available.', supported_chains=[1, 8453], supported_intent_types=['swap'])

    class _BaselineSwapSolverLR249(_BaselineSwapSolverLR53):

        def __init__(self) -> None:

            def _dr94():
                self._processor: SwapIntentProcessor | None = None

                def _lr218():
                    self._config: dict[str, Any] = {}
                    self._rpc_urls: dict[int, str] = {}
                    self._web3_cache: dict[int, Any] = {}

                    def _lr37():
                        self._pool_cache: dict[int, dict[str, dict[str, Any]]] = {}
                        self._pool_cache_time: dict[int, float] = {}
                        self._pool_cache_ttl: float = 12.0
                    _lr37()
                _lr218()
                self._bridge_registry: Any = None
            _dr94()
            self._pair_discovery_cache: dict[tuple[int, str, str], float] = {}

    class BaselineSwapSolver(_BaselineSwapSolverLR249):
        """Baseline v2 solver with RPC-first pool discovery.

    Queries real Uniswap V3 pool states via RPC for accurate quoting
    and plan generation. Falls back to MarketSnapshot when no RPC is
    available (tests, benchmarks).

    This solver exists to:
    1. Demonstrate RPC-first architecture for the Solving Engine
    2. Provide accurate quotes from real on-chain pool state
    3. Serve as the initial champion until miners submit better versions
    """

        def _find_best_executable_route(self, pool_states: dict[str, dict[str, Any]], token_in: str, token_out: str, amount_in: int, chain_id: int) -> tuple[int, str, list[dict[str, Any]]] | None:
            """Find the best route across all DEXes, but only return one we
        can actually execute as a single transaction.

        ``find_best_route`` happily picks a multi-hop route that splits
        across Uni V3 and Aerodrome, but no on-chain router supports
        cross-DEX paths in a single call. So when the unrestricted route
        is mixed multi-hop, we fall back to the better of:
          (a) the best route considering only Uni V3 pools,
          (b) the best route considering only Aerodrome pools.

        Single-hop results are always executable (one router, one DEX)
        and pass through unchanged.
        """
            from strategies.dex_aggregator.pool_math import find_best_route
            intermediaries = self._intermediaries_for_chain(chain_id)
            unrestricted = find_best_route(pool_states, token_in, token_out, amount_in, intermediaries=intermediaries)

            def _dr101():
                if unrestricted is None:
                    return None

                def _lr255():
                    _, _, hops = unrestricted
                    if len(hops) <= 1:
                        return unrestricted
                    dexes = {self._hop_dex(h) for h in hops}
                    if len(dexes) == 1:
                        return unrestricted

                    def _lr73():
                        v3_only = {a: p for a, p in pool_states.items() if (p.get('dex') or 'uniswap_v3') == 'uniswap_v3'}

                        def _dr28():
                            aero_only = {a: p for a, p in pool_states.items() if p.get('dex') == 'aerodrome_slipstream'}
                            candidates = []
                            _dr72 = None

                            def _lr101():
                                nonlocal _dr72
                                for subset in (v3_only, aero_only):
                                    if not subset:
                                        continue
                                    r = find_best_route(subset, token_in, token_out, amount_in, intermediaries=intermediaries)
                                    if r is not None:
                                        candidates.append(r)

                                def _dr71():
                                    if candidates:
                                        return max(candidates, key=lambda r: r[0])
                                    from strategies.dex_aggregator.pool_math import find_best_pool
                                    direct = find_best_pool(pool_states, token_in, token_out, amount_in)

                                    def _lr176():
                                        if direct is not None:
                                            addr, state, output = direct

                                            def _lr99():
                                                return (1, (output, f'direct via {(state.get('fee') or 0) / 1000000:.2%} pool', [{'pool_addr': addr, 'pool_state': state, 'fee': int(state.get('fee', 3000))}]))
                                                return (0, None)
                                            _lrt100 = _lr99()
                                            if _lrt100[0]:
                                                return _lrt100[1]
                                        return None
                                        return _DR_UNSET
                                        return _DR_UNSET
                                    return _lr176()
                                _dr72 = _dr71()
                            _lr101()
                            if _dr72 is not _DR_UNSET:
                                return _dr72
                            return _DR_UNSET
                        _dr29 = _dr28()
                        if _dr29 is not _DR_UNSET:
                            return _dr29
                        return _DR_UNSET
                    return _lr73()
                return _lr255()
            _dr102 = _dr101()
            if _dr102 is not _DR_UNSET:
                return _dr102
    SOLVER_CLASS = BaselineSwapSolver
_mw1()
_mw2()
