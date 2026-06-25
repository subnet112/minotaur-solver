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

import asyncio
import logging
import os
import time
from typing import Any

from minotaur_subnet.shared.types import (
    AppIntentDefinition,
    ExecutionPlan,
    Interaction,
    IntentState,
    QuoteResult,
)
from minotaur_subnet.sdk.intent_solver import IntentSolver, MarketSnapshot, SolverMetadata
from minotaur_subnet.sdk.processor_context import ProcessorContext
from strategies.dex_aggregator.swap_solver import SwapIntentProcessor
from minotaur_subnet.v3.contexts import build_typed_context
from minotaur_subnet.v3.manifest import manifest_from_definition, normalize_swap_intent_params

logger = logging.getLogger(__name__)


def _state_params(state: IntentState) -> dict[str, Any]:
    typed = getattr(state, "typed_context", None)
    if typed is not None:
        raw = getattr(typed, "raw_params", None)
        if isinstance(raw, dict):
            return raw
    return state.raw_params_view()


def _intent_function_from_state(state: IntentState, default: str = "swap") -> str:
    typed = getattr(state, "typed_context", None)
    params = _state_params(state)
    return (
        getattr(typed, "intent_function", "")
        or state.control_view().get("_intent_function")
        or params.get("intent_function")
        or default
    )


def _cross_chain_compat_params(state: IntentState) -> dict[str, Any]:
    """Return raw compatibility metadata that remains intentionally untyped."""
    return state.raw_params_view()


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

    if loop is not None and loop.is_running():
        # Already inside an event loop — create a new thread to run it
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


# ── Well-known pool addresses and ABIs ────────────────────────────────────

# Minimal Uniswap V3 pool ABI for slot0, liquidity, fee, token0, token1
_POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "fee",
        "outputs": [{"internalType": "uint24", "name": "", "type": "uint24"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# Uniswap V3 Factory ABI — getPool(address, address, uint24) -> address
_FACTORY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# Uniswap V3 Factory addresses per chain
_FACTORY_ADDRESSES: dict[int, str] = {
    1: "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    8453: "0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
    964: "0x20d0CdF9004bF56bCA52A25C9288AAD0eBB97D59",  # Astrid Bridge (formerly TaoFi) Uniswap V3 on BT EVM
}
_FACTORY_ADDRESSES[31337] = _FACTORY_ADDRESSES[1]  # Anvil = mainnet fork

# All Uniswap V3 fee tiers (hundredths of a bip)
_FEE_TIERS = [100, 500, 3000, 10000]

_ZERO_ADDRESS = "0x" + "0" * 40

# Well-known Uniswap V3 pools per chain (address → description)
_KNOWN_POOLS: dict[int, list[str]] = {
    1: [
        "0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8",  # USDC/WETH 0.3%
        "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640",  # USDC/WETH 0.05%
        "0x4e68Ccd3E89f51C3074ca5072bbAC773960dFa36",  # WETH/USDT 0.3%
        "0xCBCdF9626bC03E24f779434178A73a0B4bad62eD",  # WBTC/WETH 0.3%
        "0x6c6Bc977E13Df9b0de53b251522280BB72383700",  # DAI/USDC 0.05%
        "0xC2e9F25Be6257c210d7Adf0D4Cd6E3E881ba25f8",  # DAI/WETH 0.3%
    ],
    8453: [
        "0xd0b53D9277642d899DF5C87A3966A349A798F224",  # WETH/USDC 0.05%
    ],
    964: [
        "0x6647dcbeb030dc8E227D8B1A2Cb6A49F3C887E3c",  # WTAO/USDC 0.3% (Astrid Bridge, formerly TaoFi)
    ],
}

# Anvil/local forks share mainnet pool addresses
_KNOWN_POOLS[31337] = list(_KNOWN_POOLS[1])

# Seed tokens for factory-based discovery. The solver queries the Uniswap V3
# factory for all pairs among these tokens to find routable pools.
# This list is used by supported_tokens() for broader token discovery.
_DISCOVERY_SEED_TOKENS: dict[int, list[str]] = {
    8453: [  # Base
        "0x4200000000000000000000000000000000000006",  # WETH
        "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC
        "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb",  # DAI
        "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf",  # cbBTC
        "0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22",  # cbETH
        "0xc1CBa3fCea344f92D9239c08C0568f6F2F0ee452",  # wstETH
        "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA",  # USDbC
        "0x78a087d713Be963Bf307b18F2Ff8122EF9A63ae9",  # BSWAP
        "0x0578d8A44db98B23BF096A382e016e29a5Ce0ffe",  # HIGHER
        "0x532f27101965dd16442E59d40670FaF5eBB142E4",  # BRETT
        "0x940181a94A35A4569E4529A3CDfB74e38FD98631",  # AERO
        "0xB6fe221Fe9EeF5aBa221c348bA20A1Bf5e73624c",  # rETH
        "0x04C0599Ae5A44757c0af6F9eC3b93da8976c150A",  # weETH
        "0xfA980cEd6895AC314E7dE34Ef1bFAE90a5AdD21b",  # PRIME
        "0x236aa50979D5f3De3Bd1Eeb40E81137F22ab794b",  # tBTC
        "0x77E06c9eCCf2E797fd462A92B6D7642EF85b0A44",  # wTAO
        "0xdC46C1E93B71fF9209A0F8076a9951569DC35855",  # SNX
    ],
    1: [  # Ethereum mainnet
        "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
        "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT
        "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",  # WBTC
        "0x6B175474E89094C44Da98b954EedeAC495271d0F",  # DAI
        "0x77E06c9eCCf2E797fd462A92B6D7642EF85b0A44",  # wTAO
    ],
    964: [  # Bittensor EVM
        "0x9Dc08C6e2BF0F1eeD1E00670f80Df39145529F81",  # WTAO
        "0xB833E8137FEDf80de7E908dc6fea43a029142F20",  # USDC (Hyperlane)
    ],
}
_DISCOVERY_SEED_TOKENS[31337] = list(_DISCOVERY_SEED_TOKENS.get(1, []))

# Token symbols for known addresses (for price derivation)
_TOKEN_SYMBOLS: dict[str, str] = {
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH",
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC",
    "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "WBTC",
    "0x6b175474e89094c44da98b954eedeac495271d0f": "DAI",
    "0x77e06c9eccf2e797fd462a92b6d7642ef85b0a44": "wTAO",
    # BT EVM tokens
    "0x9dc08c6e2bf0f1eed1e00670f80df39145529f81": "WTAO",
    "0xb833e8137fedf80de7e908dc6fea43a029142f20": "USDC",
}


# Gas estimation for quoting.
# Measured on Anvil fork (March 2026):
#   1-hop direct swap: 508k-526k actual gas
#   2-hop multi-hop:   683k actual gas
# Base overhead covers: executeIntent(), EIP-712 signature verification,
# ephemeral proxy deployment, ERC-20 approve, output verification,
# fee capture, and token delivery.
_GAS_BASE_OVERHEAD = 400_000
_GAS_PER_HOP = 150_000

# Fallback gas prices in wei, used ONLY when live RPC query fails.
# These are deliberately conservative (≈ the chain's typical baseline) —
# the solver always prefers the live `eth_gasPrice` value. Hardcoding a
# single mainnet-style 20 gwei default produced $40+ fees on Base where
# actual gas prices are <0.01 gwei.
_FALLBACK_GAS_PRICE_WEI: dict[int, int] = {
    1:     25_000_000_000,   # Ethereum mainnet: 25 gwei
    8453:      20_000_000,   # Base: 0.02 gwei (typical L2 rate)
    42161:     10_000_000,   # Arbitrum: 0.01 gwei
    10:        10_000_000,   # Optimism: 0.01 gwei
    964:   25_000_000_000,   # Bittensor EVM: 25 gwei (similar to mainnet)
    31337:  1_000_000_000,   # Anvil/local: 1 gwei
}
_GENERIC_FALLBACK_GAS_PRICE_WEI = 1_000_000_000  # 1 gwei for unknown chains

_PLATFORM_FEE_MARGIN_BPS = 2000  # 20% margin above estimated gas cost


def _compute_platform_fee_wei(gas_units: int, gas_price_wei: int) -> int:
    """Estimate platform fee in native token wei (ETH/TAO).

    Fee = gas_units * gas_price_wei * (1 + margin).
    The caller is responsible for supplying a live or chain-appropriate
    gas_price_wei — see ``BaselineSwapSolver._get_gas_price_wei``.
    """
    gas_cost_wei = gas_units * int(gas_price_wei)
    margin = gas_cost_wei * _PLATFORM_FEE_MARGIN_BPS // 10000
    return gas_cost_wei + margin


class BaselineSwapSolver(IntentSolver):
    """Baseline v2 solver with RPC-first pool discovery.

    Queries real Uniswap V3 pool states via RPC for accurate quoting
    and plan generation. Falls back to MarketSnapshot when no RPC is
    available (tests, benchmarks).

    This solver exists to:
    1. Demonstrate RPC-first architecture for the Solving Engine
    2. Provide accurate quotes from real on-chain pool state
    3. Serve as the initial champion until miners submit better versions
    """

    def __init__(self) -> None:
        self._processor: SwapIntentProcessor | None = None
        self._config: dict[str, Any] = {}
        self._rpc_urls: dict[int, str] = {}
        self._web3_cache: dict[int, Any] = {}
        self._pool_cache: dict[int, dict[str, dict[str, Any]]] = {}
        self._pool_cache_time: dict[int, float] = {}
        self._pool_cache_ttl: float = 12.0  # Refresh every block (~12s)
        self._bridge_registry: Any = None
        # Factory-discovered pair cache: tracks which pairs have been queried
        self._pair_discovery_cache: dict[tuple[int, str, str], float] = {}

    def _normalized_swap_params(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
    ) -> dict[str, Any]:
        params = _state_params(state)
        receiver_default = state.contract_address or state.owner

        if getattr(state, "typed_context", None) is not None:
            typed = state.typed_context
            params = {
                **params,
                "input_token": getattr(typed, "input_token", params.get("input_token", "")),
                "output_token": getattr(typed, "output_token", params.get("output_token", "")),
                "input_amount": getattr(typed, "input_amount", params.get("input_amount", 0)),
                "min_output_amount": getattr(
                    typed,
                    "min_output_amount",
                    params.get("min_output_amount", params.get("output_amount", 0)),
                ),
                "receiver": getattr(typed, "receiver", receiver_default),
                "fee_tier": getattr(typed, "fee_tier", params.get("fee_tier", 3000)),
            }

        result = normalize_swap_intent_params(
            params,
            manifest=manifest_from_definition(intent),
            intent_name=_intent_function_from_state(state, "swap"),
            receiver_default=receiver_default,
            slippage_bps=self._processor.slippage_bps if self._processor else 50,
        )

        # Parse CAIP-10 interop addresses (eip155:chain:0xaddr) if present.
        # Extracts chain context from token addresses for cross-chain detection.
        for key, chain_key in [("input_token", "_input_chain"), ("output_token", "_output_chain")]:
            val = result.get(key, "")
            if val and val.startswith("eip155:"):
                try:
                    from minotaur_subnet.shared.interop_address import InteropAddress
                    ia = InteropAddress.parse(val, default_chain_id=state.chain_id)
                    result[key] = ia.address
                    if ia.chain_id is not None:
                        result[chain_key] = ia.chain_id
                except ValueError:
                    pass
            elif val:
                result[chain_key] = state.chain_id

        return result

    def _cross_chain_params(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
    ) -> dict[str, Any]:
        swap_params = self._normalized_swap_params(intent, state)
        extra = _cross_chain_compat_params(state)
        dest_chain_raw = extra.get("dest_chain_id")
        dest_chain_id = int(dest_chain_raw) if dest_chain_raw not in (None, "") else 0
        return {
            **swap_params,
            "dest_chain_id": dest_chain_id,
            "bridge_protocol": extra.get("bridge_protocol", "mock"),
            "dest_recipient": (
                extra.get("dest_recipient")
                or swap_params["receiver"]
                or state.owner
                or _ZERO_ADDRESS
            ),
            "dest_min_output_amount": int(
                extra.get("min_output", swap_params.get("min_output_amount", 0)) or 0
            ),
        }

    def _state_with_extra(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        *,
        chain_id: int,
        extra_updates: dict[str, Any],
    ) -> IntentState:
        raw_params = {**_cross_chain_compat_params(state), **extra_updates}
        cloned = IntentState(
            contract_address=state.contract_address,
            chain_id=chain_id,
            nonce=state.nonce,
            owner=state.owner,
            raw_params=raw_params,
            control=state.control_view(),
            context_version=state.context_version,
            policy_tier=state.policy_tier,
        )
        try:
            cloned.typed_context = build_typed_context(
                intent,
                state.control_view().get("_intent_function", _intent_function_from_state(state, "swap")),
                cloned,
            )
        except Exception:
            cloned.typed_context = None
        return cloned

    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize with RPC URLs and swap processor."""
        self._config = config
        # JSON serialization over the harness stdin protocol converts int
        # chain_id keys to strings. Coerce back to int so later int lookups
        # (self._rpc_urls.get(chain_id) with chain_id as int) succeed.
        raw_rpc_urls = config.get("rpc_urls", {}) or {}
        self._rpc_urls = {
            int(k): v for k, v in raw_rpc_urls.items() if v
        }
        self._bridge_registry = config.get("bridge_registry")
        self._processor = SwapIntentProcessor()
        logger.info(
            "BaselineSwapSolver initialized (chains=%s, rpc_chains=%s, bridge=%s)",
            config.get("chain_ids", [1]),
            list(self._rpc_urls.keys()) if self._rpc_urls else "none",
            self._bridge_registry is not None,
        )

    def _get_web3(self, chain_id: int) -> Any:
        """Get or create a cached Web3 instance for a chain."""
        if chain_id in self._web3_cache:
            return self._web3_cache[chain_id]

        rpc_url = self._rpc_urls.get(chain_id)
        if not rpc_url:
            return None

        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(rpc_url))
            if w3.is_connected():
                self._web3_cache[chain_id] = w3
                return w3
            logger.warning("Web3 not connected for chain %d at %s", chain_id, rpc_url)
        except Exception as exc:
            logger.warning("Failed to create Web3 for chain %d: %s", chain_id, exc)
        return None

    def _get_gas_price_wei(self, chain_id: int) -> int:
        """Return the live gas price in wei for a chain, cached briefly.

        Prefers the live `eth_gasPrice` via RPC. Falls back to a chain-
        specific default if RPC is unavailable. Cached for 30 seconds per
        chain to avoid spamming RPC on every quote.
        """
        now = time.time()
        cached = getattr(self, "_gas_price_cache", None)
        if cached is None:
            self._gas_price_cache: dict[int, tuple[int, float]] = {}
            cached = self._gas_price_cache

        entry = cached.get(chain_id)
        if entry is not None and now - entry[1] < 30.0:
            return entry[0]

        w3 = self._get_web3(chain_id)
        gas_price: int | None = None
        if w3 is not None:
            try:
                gas_price = int(w3.eth.gas_price)
            except Exception as exc:
                logger.warning("Failed to fetch gas price for chain %d: %s", chain_id, exc)

        if gas_price is None or gas_price <= 0:
            gas_price = _FALLBACK_GAS_PRICE_WEI.get(chain_id, _GENERIC_FALLBACK_GAS_PRICE_WEI)

        cached[chain_id] = (gas_price, now)
        return gas_price

    def _query_pool_state(self, w3: Any, pool_address: str) -> dict[str, Any] | None:
        """Query a Uniswap V3 pool's current state via RPC.

        The ``dex`` marker is set to ``uniswap_v3`` here. Aerodrome
        Slipstream discovery (``common/aerodrome.py``) reuses this same
        reader and overrides the marker to ``aerodrome_slipstream``.
        """
        try:
            pool = w3.eth.contract(
                address=w3.to_checksum_address(pool_address),
                abi=_POOL_ABI,
            )
            slot0 = pool.functions.slot0().call()
            liquidity = pool.functions.liquidity().call()
            fee = pool.functions.fee().call()
            token0 = pool.functions.token0().call()
            token1 = pool.functions.token1().call()

            return {
                "token0": token0,
                "token1": token1,
                "fee": fee,
                "sqrtPriceX96": str(slot0[0]),
                "tick": slot0[1],
                "liquidity": str(liquidity),
                "dex": "uniswap_v3",
            }
        except Exception as exc:
            logger.debug("Failed to query pool %s: %s", pool_address, exc)
            return None

    def _discover_pools(self, chain_id: int) -> dict[str, dict[str, Any]]:
        """Query known Uniswap V3 pools via RPC with caching.

        Returns pool_states dict keyed by pool address, compatible with
        pool_math functions.
        """
        now = time.time()
        if (
            chain_id in self._pool_cache
            and now - self._pool_cache_time.get(chain_id, 0) < self._pool_cache_ttl
        ):
            return self._pool_cache[chain_id]

        w3 = self._get_web3(chain_id)
        if w3 is None:
            return self._pool_cache.get(chain_id, {})

        pool_addrs = _KNOWN_POOLS.get(chain_id, [])
        pool_states: dict[str, dict[str, Any]] = {}

        for addr in pool_addrs:
            state = self._query_pool_state(w3, addr)
            if state is not None:
                pool_states[addr] = state

        if pool_states:
            self._pool_cache[chain_id] = pool_states
            self._pool_cache_time[chain_id] = now
            # This seed was just rebuilt from _KNOWN_POOLS only, dropping any
            # pools that prior factory discovery had merged into the cache.
            # Invalidate this chain's pair-discovery markers so the next
            # routing call re-discovers those pairs (with fresh state) instead
            # of being short-circuited by a now-stale "already discovered"
            # marker — otherwise factory-discovered (incl. multi-hop) pools
            # silently vanish until the pair TTL lapses.
            stale = [k for k in self._pair_discovery_cache if k[0] == chain_id]
            for k in stale:
                del self._pair_discovery_cache[k]
            logger.debug(
                "Discovered %d pools on chain %d via RPC",
                len(pool_states), chain_id,
            )

        return pool_states

    def _get_factory(self, chain_id: int) -> Any | None:
        """Get a Uniswap V3 Factory contract instance for a chain."""
        factory_addr = _FACTORY_ADDRESSES.get(chain_id)
        if not factory_addr:
            return None
        w3 = self._get_web3(chain_id)
        if w3 is None:
            return None
        return w3.eth.contract(
            address=w3.to_checksum_address(factory_addr),
            abi=_FACTORY_ABI,
        )

    def _discover_pools_for_pair(
        self,
        chain_id: int,
        token_a: str,
        token_b: str,
        pool_states: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Query Uniswap V3 Factory for all pools between two tokens.

        Checks all 4 fee tiers. For each non-zero pool found, queries
        on-chain state and merges into pool_states (mutated in-place).
        """
        now = time.time()
        a_lower, b_lower = token_a.lower(), token_b.lower()
        pair_key = (chain_id, min(a_lower, b_lower), max(a_lower, b_lower))

        if now - self._pair_discovery_cache.get(pair_key, 0) < self._pool_cache_ttl:
            return pool_states

        factory = self._get_factory(chain_id)
        if factory is None:
            return pool_states

        w3 = self._get_web3(chain_id)
        if w3 is None:
            return pool_states

        discovered = 0
        rpc_errors = 0
        for fee in _FEE_TIERS:
            try:
                pool_addr = factory.functions.getPool(
                    w3.to_checksum_address(token_a),
                    w3.to_checksum_address(token_b),
                    fee,
                ).call()
            except Exception as exc:
                logger.debug("Factory.getPool(%s, %s, %d) failed: %s",
                             token_a[:10], token_b[:10], fee, exc)
                rpc_errors += 1
                continue

            if not pool_addr or pool_addr == _ZERO_ADDRESS:
                continue

            # Skip if already in pool_states
            if pool_addr in pool_states or pool_addr.lower() in {k.lower() for k in pool_states}:
                continue

            state = self._query_pool_state(w3, pool_addr)
            if state is not None:
                pool_states[pool_addr] = state
                discovered += 1

        # Only cache if RPC calls succeeded — if all failed, don't cache
        # so the next call retries discovery instead of assuming no pools exist.
        if rpc_errors < len(_FEE_TIERS):
            self._pair_discovery_cache[pair_key] = now
        if discovered > 0:
            logger.debug("Factory: found %d new pools for %s/%s on chain %d",
                         discovered, token_a[:10], token_b[:10], chain_id)
        return pool_states

    def _intermediaries_for_chain(self, chain_id: int) -> list[str]:
        """Chain-appropriate multi-hop intermediary tokens (WETH + USDC).

        Sourced from the trusted SDK token registry so the addresses are
        always correct for the chain. A hardcoded mainnet list silently
        disables multi-hop on every other chain — the intermediary pools
        never resolve on the factory, so two-hop discovery and routing both
        come up empty (this was the Base/BT EVM multi-hop dead-spot).
        """
        from minotaur_subnet.blockchain.tokens import WRAPPED_NATIVE_TOKEN, TOKENS

        # Local Anvil forks mainnet, so reuse mainnet token addresses there.
        token_chain = 1 if chain_id == 31337 else chain_id
        mids: list[str] = []
        wnt = WRAPPED_NATIVE_TOKEN.get(chain_id)
        if wnt:
            mids.append(wnt)
        usdc = TOKENS.get(token_chain, {}).get("USDC")
        if usdc and usdc.lower() not in {m.lower() for m in mids}:
            mids.append(usdc)
        return mids

    def _ensure_pools_for_route(
        self,
        chain_id: int,
        pool_states: dict[str, dict[str, Any]],
        token_in: str,
        token_out: str,
    ) -> dict[str, dict[str, Any]]:
        """Discover pools needed for routing token_in -> token_out.

        Queries the Uniswap V3 Factory for the direct pair and
        intermediary pairs (for multi-hop routing via WETH, USDC).
        """
        if not self._rpc_urls.get(chain_id):
            return pool_states

        # Direct pair
        self._discover_pools_for_pair(chain_id, token_in, token_out, pool_states)

        # Intermediary pairs for multi-hop (chain-appropriate WETH/USDC)
        intermediaries = self._intermediaries_for_chain(chain_id)

        in_lower, out_lower = token_in.lower(), token_out.lower()
        for mid in intermediaries:
            mid_lower = mid.lower()
            if mid_lower == in_lower or mid_lower == out_lower:
                continue
            self._discover_pools_for_pair(chain_id, token_in, mid, pool_states)
            self._discover_pools_for_pair(chain_id, mid, token_out, pool_states)

        # Aerodrome Slipstream discovery on chains where it's deployed.
        # The Slipstream factory mirrors Uni V3 except getPool takes int24
        # tickSpacing, and pools come back tagged dex='aerodrome_slipstream'
        # so plan dispatch can route to the Slipstream SwapRouter.
        from strategies.dex_aggregator import aerodrome as _aero
        if chain_id in _aero.AERODROME_SLIPSTREAM_FACTORY:
            w3 = self._get_web3(chain_id)
            if w3 is not None:
                _aero.discover_pools_for_pair(
                    w3, chain_id, token_in, token_out, pool_states,
                    self._query_pool_state, self._pair_discovery_cache,
                    cache_ttl=self._pool_cache_ttl,
                )
                for mid in intermediaries:
                    mid_lower = mid.lower()
                    if mid_lower == in_lower or mid_lower == out_lower:
                        continue
                    _aero.discover_pools_for_pair(
                        w3, chain_id, token_in, mid, pool_states,
                        self._query_pool_state, self._pair_discovery_cache,
                        cache_ttl=self._pool_cache_ttl,
                    )
                    _aero.discover_pools_for_pair(
                        w3, chain_id, mid, token_out, pool_states,
                        self._query_pool_state, self._pair_discovery_cache,
                        cache_ttl=self._pool_cache_ttl,
                    )

        return pool_states

    def _derive_prices(
        self, pool_states: dict[str, dict[str, Any]], chain_id: int = 1,
    ) -> dict[str, float]:
        """Derive USD prices from pool sqrtPriceX96 values.

        Uses USDC-paired pools to extract USD prices. Simplified
        price derivation — production solvers would use multiple sources.
        """
        from minotaur_subnet.blockchain.tokens import TOKENS

        prices: dict[str, float] = {"USDC/USD": 1.0, "USDT/USD": 1.0, "DAI/USD": 1.0}
        token_chain = 1 if chain_id == 31337 else chain_id
        usdc_lower = TOKENS.get(token_chain, {}).get(
            "USDC", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        ).lower()

        for _pool_addr, state in pool_states.items():
            token0 = state.get("token0", "").lower()
            token1 = state.get("token1", "").lower()
            sqrt_price_raw = state.get("sqrtPriceX96")
            if not sqrt_price_raw:
                continue

            sqrt_price = int(sqrt_price_raw)
            if sqrt_price == 0:
                continue

            # Uniswap V3: price = (sqrtPriceX96 / 2^96)^2
            # This gives price of token0 in terms of token1
            price_ratio = (sqrt_price ** 2) / (2 ** 192)

            if token0 == usdc_lower:
                # price_ratio = token0(USDC) per token1
                # So token1 price in USDC = 1/price_ratio
                other_token = token1
                usd_price = 1.0 / price_ratio if price_ratio > 0 else 0
            elif token1 == usdc_lower:
                # price_ratio = token0 per token1(USDC)
                # So token0 price in USDC = price_ratio
                other_token = token0
                usd_price = price_ratio
            else:
                continue

            sym = _TOKEN_SYMBOLS.get(other_token, "")
            if sym:
                prices[f"{sym}/USD"] = usd_price

        return prices

    def _get_pool_states(
        self, chain_id: int, snapshot: MarketSnapshot | None,
    ) -> dict[str, dict[str, Any]]:
        """Get pool states: RPC first, then snapshot fallback."""
        if self._rpc_urls.get(chain_id):
            rpc_pools = self._discover_pools(chain_id)
            if rpc_pools:
                return rpc_pools

        if snapshot is not None and snapshot.pool_states:
            return snapshot.pool_states

        return {}

    def generate_plan(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        snapshot: MarketSnapshot | None = None,
    ) -> ExecutionPlan:
        """Generate a swap plan using route-aware plan generation.

        Discovers pools via RPC, finds the best route (direct or multi-hop),
        and builds the appropriate Uniswap V3 execution plan. Direct swaps
        use exactInputSingle; multi-hop swaps use exactInput with packed path.
        """
        if self._processor is None:
            raise RuntimeError("Solver not initialized — call initialize() first")

        chain_id = state.chain_id or (snapshot.chain_id if snapshot else 1)

        # Substrate-to-EVM: alpha token unstake + bridge + swap
        params = _state_params(state)
        if params.get("alpha_netuid") and params.get("owner_ss58"):
            return self._generate_substrate_to_evm_plan(intent, state, snapshot)

        # Yield rebalance: delegate to BaselineYieldStrategy
        intent_fn = _intent_function_from_state(state, "swap")
        if intent_fn == "rebalance":
            return self._generate_yield_plan(intent, state, snapshot)

        swap_params = self._normalized_swap_params(intent, state)

        # Cross-chain detection: from explicit dest_chain_id OR from
        # CAIP-10 token addresses (eip155:chain:0xaddr)
        dest_chain_id = _cross_chain_compat_params(state).get("dest_chain_id")
        if not dest_chain_id:
            # Auto-detect from interop token chain IDs
            output_chain = swap_params.get("_output_chain")
            input_chain = swap_params.get("_input_chain", chain_id)
            if output_chain and output_chain != input_chain:
                dest_chain_id = output_chain
                chain_id = input_chain  # source chain
        if dest_chain_id and int(dest_chain_id) != chain_id:
            return self._generate_cross_chain_plan(
                intent, state, snapshot, chain_id, int(dest_chain_id),
            )

        pool_states = self._get_pool_states(chain_id, snapshot)

        # Factory-based discovery for the requested pair
        input_token = swap_params.get("input_token", "")
        output_token = swap_params.get("output_token", "")
        if input_token and output_token:
            if snapshot is not None and snapshot.pool_states and pool_states is snapshot.pool_states:
                pool_states = dict(pool_states)
            self._ensure_pools_for_route(chain_id, pool_states, input_token, output_token)

        prices = self._derive_prices(pool_states, chain_id) if pool_states else {}

        context = ProcessorContext(
            chain_id=chain_id,
            timestamp=snapshot.timestamp if snapshot else int(time.time()),
            block_number=snapshot.block_number if snapshot else 0,
            rpc_url=self._rpc_urls.get(chain_id, ""),
            prices=prices,
            dex_config=snapshot.dex_config if snapshot else {},
        )

        # Route-aware plan generation: check if multi-hop is needed
        if input_token and output_token and pool_states:
            amount_in = swap_params.get("input_amount", 0)

            if amount_in > 0:
                route = self._find_best_executable_route(
                    pool_states, input_token, output_token, amount_in, chain_id,
                )
                if route is not None:
                    output_amount, route_desc, hops = route
                    hop_dex = self._dominant_dex(hops)
                    if len(hops) > 1:
                        if hop_dex == "aerodrome_slipstream":
                            return self._build_aerodrome_multihop_plan(
                                intent, state, context, hops,
                                input_token, output_token, amount_in,
                                output_amount, chain_id,
                            )
                        return self._build_multihop_plan(
                            intent, state, context, hops,
                            input_token, output_token, amount_in,
                            output_amount, chain_id,
                        )
                    elif len(hops) == 1:
                        if hop_dex == "aerodrome_slipstream":
                            return self._build_aerodrome_singlehop_plan(
                                intent, state, context, hops[0],
                                input_token, output_token, amount_in,
                                output_amount, chain_id,
                            )
                        # Uni V3 single-hop: pass the discovered fee tier
                        # to the processor so it doesn't override.
                        discovered_fee = hops[0].get("fee")
                        if discovered_fee and discovered_fee != self._processor.default_fee_tier:
                            state = self._state_with_extra(
                                intent,
                                state,
                                chain_id=state.chain_id,
                                extra_updates={"fee_tier": discovered_fee},
                            )

        # Direct pool or no route info — delegate to SwapIntentProcessor.
        # Falls back to direct pool.swap() on chains without a SwapRouter
        # (e.g., BT EVM where Astrid Bridge (formerly TaoFi) deployed pools but no router).
        try:
            plan = _run_coro(self._processor.generate_plan(intent, state, context))
            plan.metadata["chain_id"] = chain_id
            return plan
        except ValueError as exc:
            if "No Uniswap V3 router" not in str(exc):
                raise
            # No router — try direct pool swap
            return self._build_direct_pool_plan(
                intent, state, context, pool_states,
                input_token, output_token, chain_id,
            )

    def _build_direct_pool_plan(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        context: ProcessorContext,
        pool_states: dict[str, dict[str, Any]],
        input_token: str,
        output_token: str,
        chain_id: int,
    ) -> ExecutionPlan:
        """Build a plan that calls pool.swap() directly (no router needed).

        Used on chains like BT EVM where Uniswap V3 pools exist but no
        SwapRouter is deployed. Miners should improve on this by deploying
        their own router or using more sophisticated routing.
        """
        from eth_abi import encode as abi_encode

        swap_params = self._normalized_swap_params(intent, state)
        amount_in = swap_params.get("input_amount", 0)
        min_output = swap_params.get("min_output_amount", 0)
        recipient = state.contract_address or swap_params.get("receiver", state.owner)
        deadline = context.timestamp + (self._processor.deadline_offset if self._processor else 300)

        # Find the pool for this pair
        pool_address = None
        zero_for_one = True
        for addr, ps in pool_states.items():
            t0 = ps.get("token0", "").lower()
            t1 = ps.get("token1", "").lower()
            if t0 == input_token.lower() and t1 == output_token.lower():
                pool_address = addr
                zero_for_one = True
                break
            elif t1 == input_token.lower() and t0 == output_token.lower():
                pool_address = addr
                zero_for_one = False
                break

        if not pool_address:
            # Fallback: use the first known pool for this chain
            known = _KNOWN_POOLS.get(chain_id, [])
            if known:
                pool_address = known[0]
                # Query pool to determine direction
                try:
                    w3 = self._get_web3(chain_id)
                    pool_contract = w3.eth.contract(
                        address=w3.to_checksum_address(pool_address),
                        abi=_POOL_ABI,
                    )
                    t0 = pool_contract.functions.token0().call().lower()
                    zero_for_one = (t0 == input_token.lower())
                except Exception:
                    pass

        if not pool_address:
            raise ValueError(f"No pool found for {input_token}/{output_token} on chain {chain_id}")

        # sqrtPriceLimitX96: use min/max to accept any price
        # For zeroForOne=true: use MIN_SQRT_RATIO + 1
        # For zeroForOne=false: use MAX_SQRT_RATIO - 1
        MIN_SQRT_RATIO = 4295128739
        MAX_SQRT_RATIO = 1461446703485210103287273052203988822378723970342

        sqrt_price_limit = MIN_SQRT_RATIO + 1 if zero_for_one else MAX_SQRT_RATIO - 1

        # pool.swap(recipient, zeroForOne, amountSpecified, sqrtPriceLimitX96, data)
        # amountSpecified > 0 = exact input
        swap_selector = "128acb08"  # swap(address,bool,int256,uint160,bytes)
        callback_data = abi_encode(
            ["address", "address", "uint24"],
            [
                input_token if input_token.startswith("0x") else "0x" + "0" * 40,
                output_token if output_token.startswith("0x") else "0x" + "0" * 40,
                3000,
            ],
        )
        swap_calldata = (
            "0x" + swap_selector
            + recipient.replace("0x", "").lower().zfill(64)
            + ("01" if zero_for_one else "00").zfill(64)
            + hex(amount_in)[2:].zfill(64)
            + hex(sqrt_price_limit)[2:].zfill(64)
            + hex(160)[2:].zfill(64)  # offset to data
            + hex(len(callback_data))[2:].zfill(64)  # data length
            + callback_data.hex()
        )

        interactions = [
            # 1. Approve pool to spend input tokens
            Interaction(
                target=input_token,
                value="0",
                call_data="0x095ea7b3" + pool_address.replace("0x", "").lower().zfill(64) + hex(amount_in)[2:].zfill(64),
                chain_id=chain_id,
            ),
            # 2. Call pool.swap() directly
            Interaction(
                target=pool_address,
                value="0",
                call_data=swap_calldata,
                chain_id=chain_id,
            ),
        ]

        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=interactions,
            deadline=deadline,
            nonce=state.nonce,
            metadata={
                "route": "uniswap_v3_direct_pool",
                "pool": pool_address,
                "zero_for_one": zero_for_one,
                "input_token": input_token,
                "output_token": output_token,
                "input_amount": str(amount_in),
                "min_output_amount": str(min_output),
                "chain_id": chain_id,
            },
        )

    def _generate_yield_plan(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        snapshot: MarketSnapshot | None = None,
    ) -> ExecutionPlan:
        """Delegate to BaselineYieldStrategy for rebalance intents."""
        from draft.strategies.yield_optimizer.yield_solver import BaselineYieldStrategy
        strategy = BaselineYieldStrategy()
        strategy.APP_ID = intent.app_id
        plan = strategy.generate_plan(intent, state, snapshot)
        if plan is None:
            raise ValueError("Yield strategy returned no plan — check params (asset, amount)")
        return plan

    def _generate_substrate_to_evm_plan(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        snapshot: MarketSnapshot | None = None,
    ) -> ExecutionPlan:
        """Generate a 4-leg plan for Alpha → USDC (substrate + bridge + EVM).

        Leg 0 [substrate]: Unstake alpha → TAO via remove_stake
        Leg 1 [substrate]: Bridge deposit TAO to Tensorplex lock address
        Leg 2 [wait]:      Bridge finality (~30 min), handled by BridgeTracker
        Leg 3 [evm]:       Swap wTAO → output_token on Uniswap V3 (Ethereum)
        """
        from minotaur_subnet.shared.types import SubstrateAction

        params = _state_params(state)
        alpha_netuid = int(params["alpha_netuid"])
        owner_ss58 = params["owner_ss58"]
        hotkey_ss58 = params.get("hotkey_ss58", params.get("alpha_hotkey", ""))
        amount_rao = int(params.get("alpha_amount_rao", params.get("amount_rao", 0)))
        output_token = params.get("output_token", "")
        min_output = int(params.get("min_output_amount", 0))
        dest_chain_id = int(params.get("dest_chain_id", 1))  # Default: Ethereum
        receiver = params.get("recipient", params.get("receiver", state.owner))

        if amount_rao <= 0:
            raise ValueError("alpha_amount_rao must be positive")

        # Leg 0: Unstake alpha → TAO
        unstake_action = SubstrateAction(
            action="remove_stake",
            owner_ss58=owner_ss58,
            amount_rao=amount_rao,
            netuid=alpha_netuid,
            hotkey_ss58=hotkey_ss58,
        )

        # Leg 1: Bridge deposit — TAO → wTAO via Tensorplex
        # Use the bridge registry if available, otherwise hardcode Tensorplex
        bridge_fee_bps = 10  # Tensorplex: 0.1%
        bridge_fee = amount_rao * bridge_fee_bps // 10_000
        tao_after_bridge = amount_rao - bridge_fee

        from minotaur_subnet.bridge.tensorplex import _TENSORPLEX_LOCK_SS58
        bridge_action = SubstrateAction(
            action="bridge_deposit",
            owner_ss58=owner_ss58,
            amount_rao=amount_rao,
            dest_address=_TENSORPLEX_LOCK_SS58,
            metadata={
                "bridge": "tensorplex",
                "expected_output": tao_after_bridge,
                "fee": bridge_fee,
                "dst_chain_id": dest_chain_id,
            },
        )

        # Leg 3: EVM swap — wTAO → output_token on Ethereum
        # wTAO has 9 decimals. amount_rao maps to wTAO 1:1 (both use 9 decimals)
        wTAO = "0x77E06c9eCCf2E797fd462A92B6D7642EF85b0A44"
        evm_chain_id = dest_chain_id if dest_chain_id in (1, 31337) else 1

        # Build the EVM swap interactions using existing solver machinery
        evm_interactions = []
        if output_token and output_token.lower() != wTAO.lower():
            # Need to swap wTAO → output_token
            swap_state = IntentState(
                contract_address=state.contract_address,
                chain_id=evm_chain_id,
                nonce=state.nonce,
                owner=receiver,
                raw_params={
                    "input_token": wTAO,
                    "output_token": output_token,
                    "input_amount": str(tao_after_bridge),
                    "min_output_amount": str(min_output),
                    "receiver": receiver,
                },
                control={"_intent_function": "swap"},
            )
            try:
                evm_plan = self.generate_plan(intent, swap_state, snapshot)
                evm_interactions = evm_plan.interactions
            except Exception as exc:
                logger.warning("EVM swap leg generation failed: %s", exc)
                # Fallback: empty dest leg (user gets wTAO)

        deadline = int(time.time()) + 7200  # 2 hours (accounts for bridge delay)

        # Assemble the full plan
        all_interactions = list(evm_interactions)
        evm_indices = list(range(len(all_interactions)))

        legs = [
            {
                "leg_id": 0,
                "type": "source",
                "runtime": "substrate",
                "chain_id": 0,  # Bittensor substrate
                "interaction_indices": [],
                "substrate_actions": [unstake_action.to_dict()],
            },
            {
                "leg_id": 1,
                "type": "bridge",
                "runtime": "substrate",
                "chain_id": 0,
                "bridge_protocol": "tensorplex",
                "depends_on_leg": 0,
                "interaction_indices": [],
                "substrate_actions": [bridge_action.to_dict()],
                "estimated_duration_s": 1800,
                "estimated_output": str(tao_after_bridge),
                "fee": str(bridge_fee),
                "token_out": wTAO,
            },
            {
                "leg_id": 2,
                "type": "wait",
                "runtime": "none",
                "chain_id": 0,
                "depends_on_leg": 1,
                "interaction_indices": [],
            },
            {
                "leg_id": 3,
                "type": "destination",
                "runtime": "evm",
                "chain_id": evm_chain_id,
                "depends_on_leg": 2,
                "interaction_indices": evm_indices,
            },
        ]

        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=all_interactions,
            deadline=deadline,
            nonce=state.nonce,
            metadata={
                "cross_chain": True,
                "substrate_origin": True,
                "src_chain_id": 0,  # Bittensor substrate
                "dst_chain_id": evm_chain_id,
                # Use mock bridge for testnet (instant), tensorplex for production.
                "bridge_protocol": os.environ.get("BRIDGE_PROTOCOL", "mock"),
                "alpha_netuid": alpha_netuid,
                "owner_ss58": owner_ss58,
                "legs": legs,
                "route": "alpha_to_evm",
                "input_amount_rao": str(amount_rao),
                "output_token": output_token,
                "chain_id": evm_chain_id,
            },
        )

    def _build_multihop_plan(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        context: ProcessorContext,
        hops: list[dict[str, Any]],
        input_token: str,
        output_token: str,
        amount_in: int,
        expected_output: int,
        chain_id: int,
    ) -> ExecutionPlan:
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
        from strategies.dex_aggregator.v3_codec import (
            encode_exact_input,
            encode_swap_path,
        )
        from strategies.dex_aggregator.swap_solver import UNISWAP_V3_ROUTERS

        swap_params = self._normalized_swap_params(intent, state)

        # Build token sequence from hops
        tokens = [input_token]
        fees: list[int] = []
        for hop in hops:
            pool = hop["pool_state"]
            t0 = pool["token0"].lower()
            t1 = pool["token1"].lower()
            # The next token is whichever pool token is NOT the current tail
            if tokens[-1].lower() == t0:
                tokens.append(pool["token1"])
            else:
                tokens.append(pool["token0"])
            fees.append(hop["fee"])

        path = encode_swap_path(tokens, fees)

        router = UNISWAP_V3_ROUTERS.get(chain_id)
        if not router:
            raise ValueError(f"No Uniswap V3 router for chain {chain_id}")

        min_output = swap_params.get("min_output_amount", 0)
        if not min_output:
            # Apply slippage to the expected output (not the input amount,
            # which is in a different token denomination)
            slippage_bps = self._processor.slippage_bps
            min_output = expected_output * (10000 - slippage_bps) // 10000

        deadline = context.timestamp + self._processor.deadline_offset
        recipient = state.contract_address or swap_params.get("receiver", state.owner)

        interactions = [
            Interaction(
                target=input_token,
                value="0",
                call_data=encode_approve(router, amount_in),
                chain_id=chain_id,
            ),
            Interaction(
                target=router,
                value="0",
                call_data=encode_exact_input(
                    path=path,
                    recipient=recipient,
                    deadline=deadline,
                    amount_in=amount_in,
                    amount_out_minimum=min_output,
                ),
                chain_id=chain_id,
            ),
        ]

        logger.info(
            "Multi-hop plan: %d hops, path=%s, fees=%s",
            len(hops),
            " → ".join(t[:10] for t in tokens),
            fees,
        )

        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=interactions,
            deadline=deadline,
            nonce=state.nonce,
            metadata={
                "route": "uniswap_v3_multihop",
                "hops": len(hops),
                "tokens": tokens,
                "fees": fees,
                "input_token": input_token,
                "output_token": output_token,
                "input_amount": str(amount_in),
                "min_output_amount": str(min_output),
                "chain_id": chain_id,
            },
        )

    # ── Cross-DEX route selection ─────────────────────────────────────────

    @staticmethod
    def _hop_dex(hop: dict[str, Any]) -> str:
        """Return the DEX tag for a hop. Defaults to ``uniswap_v3`` for
        legacy/snapshot-sourced pools that predate the ``dex`` marker."""
        return (hop.get("pool_state") or {}).get("dex") or "uniswap_v3"

    @classmethod
    def _dominant_dex(cls, hops: list[dict[str, Any]]) -> str:
        """``aerodrome_slipstream`` if every hop is on Aerodrome, else
        ``uniswap_v3``. Used to pick the right router at plan time."""
        if all(cls._hop_dex(h) == "aerodrome_slipstream" for h in hops):
            return "aerodrome_slipstream"
        return "uniswap_v3"

    def _find_best_executable_route(
        self,
        pool_states: dict[str, dict[str, Any]],
        token_in: str,
        token_out: str,
        amount_in: int,
        chain_id: int,
    ) -> tuple[int, str, list[dict[str, Any]]] | None:
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
        unrestricted = find_best_route(
            pool_states, token_in, token_out, amount_in,
            intermediaries=intermediaries,
        )
        if unrestricted is None:
            return None

        _, _, hops = unrestricted
        if len(hops) <= 1:
            return unrestricted

        dexes = {self._hop_dex(h) for h in hops}
        if len(dexes) == 1:
            return unrestricted  # all-V3 or all-Aero — executable as-is

        # Mixed multi-hop: re-run on per-DEX subsets. Whichever yields the
        # best output wins; if neither produces a route, fall back to the
        # best direct (single-hop) pool from the unrestricted set.
        v3_only = {a: p for a, p in pool_states.items() if (p.get("dex") or "uniswap_v3") == "uniswap_v3"}
        aero_only = {a: p for a, p in pool_states.items() if p.get("dex") == "aerodrome_slipstream"}

        candidates = []
        for subset in (v3_only, aero_only):
            if not subset:
                continue
            r = find_best_route(
                subset, token_in, token_out, amount_in,
                intermediaries=intermediaries,
            )
            if r is not None:
                candidates.append(r)

        if candidates:
            return max(candidates, key=lambda r: r[0])

        # Nothing single-DEX viable — try direct only across all pools.
        from strategies.dex_aggregator.pool_math import find_best_pool
        direct = find_best_pool(pool_states, token_in, token_out, amount_in)
        if direct is not None:
            addr, state, output = direct
            return (
                output,
                f"direct via {(state.get('fee') or 0) / 1_000_000:.2%} pool",
                [{"pool_addr": addr, "pool_state": state, "fee": int(state.get("fee", 3000))}],
            )
        return None

    # ── Aerodrome plan builders ──────────────────────────────────────────

    def _build_aerodrome_singlehop_plan(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        context: ProcessorContext,
        hop: dict[str, Any],
        input_token: str,
        output_token: str,
        amount_in: int,
        expected_output: int,
        chain_id: int,
    ) -> ExecutionPlan:
        """Single-hop swap routed through Aerodrome's Slipstream router."""
        from strategies.dex_aggregator import aerodrome as _aero
        from common.abi_utils import encode_approve

        router = _aero.AERODROME_SLIPSTREAM_ROUTER.get(chain_id)
        if not router:
            raise ValueError(f"No Aerodrome Slipstream router for chain {chain_id}")

        swap_params = self._normalized_swap_params(intent, state)
        min_output = swap_params.get("min_output_amount", 0)
        if not min_output:
            slippage_bps = self._processor.slippage_bps
            min_output = expected_output * (10000 - slippage_bps) // 10000

        deadline = context.timestamp + self._processor.deadline_offset
        recipient = state.contract_address or swap_params.get("receiver", state.owner)
        tick_spacing = int(hop["pool_state"].get("tickSpacing", 0))

        interactions = [
            Interaction(
                target=input_token,
                value="0",
                call_data=encode_approve(router, amount_in),
                chain_id=chain_id,
            ),
            Interaction(
                target=router,
                value="0",
                call_data=_aero.encode_exact_input_single(
                    token_in=input_token,
                    token_out=output_token,
                    tick_spacing=tick_spacing,
                    recipient=recipient,
                    deadline=deadline,
                    amount_in=amount_in,
                    amount_out_minimum=min_output,
                ),
                chain_id=chain_id,
            ),
        ]

        logger.info(
            "Aerodrome single-hop plan: %s -> %s tickSpacing=%d expected_out=%d",
            input_token[:10], output_token[:10], tick_spacing, expected_output,
        )

        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=interactions,
            deadline=deadline,
            nonce=state.nonce,
            metadata={
                "route": "aerodrome_slipstream",
                "dex": "aerodrome",
                "router": router,
                "tick_spacing": tick_spacing,
                "input_token": input_token,
                "output_token": output_token,
                "input_amount": str(amount_in),
                "min_output_amount": str(min_output),
                "expected_output": str(expected_output),
                "chain_id": chain_id,
            },
        )

    def _build_aerodrome_multihop_plan(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        context: ProcessorContext,
        hops: list[dict[str, Any]],
        input_token: str,
        output_token: str,
        amount_in: int,
        expected_output: int,
        chain_id: int,
    ) -> ExecutionPlan:
        """Multi-hop swap routed entirely through Aerodrome's Slipstream
        router. Path is packed as ``token0 + ts0 + token1 + ts1 + ...``
        (3-byte tickSpacing per hop, mirroring the Uni V3 packed-fee path).
        """
        from strategies.dex_aggregator import aerodrome as _aero
        from common.abi_utils import encode_approve

        router = _aero.AERODROME_SLIPSTREAM_ROUTER.get(chain_id)
        if not router:
            raise ValueError(f"No Aerodrome Slipstream router for chain {chain_id}")

        swap_params = self._normalized_swap_params(intent, state)

        tokens = [input_token]
        tick_spacings: list[int] = []
        for hop in hops:
            pool = hop["pool_state"]
            t0 = pool["token0"].lower()
            if tokens[-1].lower() == t0:
                tokens.append(pool["token1"])
            else:
                tokens.append(pool["token0"])
            tick_spacings.append(int(pool.get("tickSpacing", 0)))

        path = _aero.encode_path(tokens, tick_spacings)

        min_output = swap_params.get("min_output_amount", 0)
        if not min_output:
            slippage_bps = self._processor.slippage_bps
            min_output = expected_output * (10000 - slippage_bps) // 10000

        deadline = context.timestamp + self._processor.deadline_offset
        recipient = state.contract_address or swap_params.get("receiver", state.owner)

        interactions = [
            Interaction(
                target=input_token,
                value="0",
                call_data=encode_approve(router, amount_in),
                chain_id=chain_id,
            ),
            Interaction(
                target=router,
                value="0",
                call_data=_aero.encode_exact_input(
                    path=path,
                    recipient=recipient,
                    deadline=deadline,
                    amount_in=amount_in,
                    amount_out_minimum=min_output,
                ),
                chain_id=chain_id,
            ),
        ]

        logger.info(
            "Aerodrome multi-hop plan: %d hops, path=%s, tickSpacings=%s",
            len(hops),
            " -> ".join(t[:10] for t in tokens),
            tick_spacings,
        )

        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=interactions,
            deadline=deadline,
            nonce=state.nonce,
            metadata={
                "route": "aerodrome_slipstream_multihop",
                "dex": "aerodrome",
                "router": router,
                "hops": len(hops),
                "tokens": tokens,
                "tick_spacings": tick_spacings,
                "input_token": input_token,
                "output_token": output_token,
                "input_amount": str(amount_in),
                "min_output_amount": str(min_output),
                "expected_output": str(expected_output),
                "chain_id": chain_id,
            },
        )

    def _generate_cross_chain_plan(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        snapshot: MarketSnapshot | None,
        src_chain: int,
        dst_chain: int,
    ) -> ExecutionPlan:
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
        from minotaur_subnet.shared.types import (
            BridgeRequest, ChainLeg, CrossChainPlan,
        )

        cross_chain_params = self._cross_chain_params(intent, state)
        input_token = cross_chain_params.get("input_token", "")
        output_token = cross_chain_params.get("output_token", "")
        input_amount = int(cross_chain_params.get("input_amount", 0))
        recipient = (
            cross_chain_params.get("dest_recipient")
            or state.owner
            or cross_chain_params.get("receiver")
            or _ZERO_ADDRESS
        )
        if recipient == state.contract_address and state.owner:
            recipient = state.owner

        # ── Detect direction: can input token be bridged directly? ────────
        bridge_token = input_token
        bridge_amount = input_amount
        needs_source_swap = True

        if self._bridge_registry is not None:
            try:
                direct_quote = _run_coro(self._bridge_registry.best_quote(
                    input_token, input_amount, src_chain, dst_chain,
                ))
                if direct_quote is not None:
                    needs_source_swap = False
                    logger.info(
                        "Cross-chain: direct bridge for %s (%s→%s) via %s",
                        input_token[:10], src_chain, dst_chain, direct_quote.protocol,
                    )
            except Exception:
                pass

        # ── Build chain legs (business logic only, NO bridge calldata) ────
        chain_legs: list[ChainLeg] = []
        bridge_requests: list[BridgeRequest] = []

        from eth_hash.auto import keccak as _kh
        bridge_sel = _kh(b"bridge(address,uint256,uint256,address)")[:4].hex()
        swap_sel = _kh(b"swap(address,address,uint256,uint256,address)")[:4].hex()

        if needs_source_swap:
            # Pattern B: swap on source, then bridge
            # Source leg: swap input_token → bridgeable_token
            source_interactions = self._build_source_swap_interactions(
                intent, state, snapshot, src_chain, input_token, output_token, input_amount,
                cross_chain_params,
            )
            chain_legs.append(ChainLeg(
                chain_id=src_chain,
                interactions=source_interactions,
                intent_selector=swap_sel,
                metadata={"type": "source_swap"},
            ))

            # Bridge: bridgeable_token from source → dest
            # Find which token to bridge (output of source swap)
            bridgeable_token = self._find_bridgeable_token(src_chain, dst_chain, input_token)
            if bridgeable_token:
                bridge_token = bridgeable_token
            bridge_requests.append(BridgeRequest(
                token=bridge_token,
                amount=bridge_amount,
                src_chain_id=src_chain,
                dst_chain_id=dst_chain,
                recipient=recipient,
                purpose=f"bridge {bridge_token[:10]}.. for dest action",
            ))

            # Dest leg: receive bridged token (may need further swap)
            dest_interactions = self._build_dest_swap_interactions(
                intent, state, snapshot, dst_chain, output_token, recipient,
            )
            chain_legs.append(ChainLeg(
                chain_id=dst_chain,
                interactions=dest_interactions,
                intent_selector=swap_sel,
                metadata={"type": "destination_action"},
            ))

        else:
            # Pattern A: bridge input directly, then swap on dest
            # Source leg: just approve (bridge calldata added by compiler)
            chain_legs.append(ChainLeg(
                chain_id=src_chain,
                interactions=[],  # Bridge interactions added by compiler
                intent_selector=bridge_sel,
                metadata={"type": "bridge_source"},
            ))

            bridge_requests.append(BridgeRequest(
                token=input_token,
                amount=input_amount,
                src_chain_id=src_chain,
                dst_chain_id=dst_chain,
                recipient=recipient,
                purpose=f"bridge {input_token[:10]}.. to dest chain",
            ))

            # Dest leg: swap bridged token → desired output
            dest_interactions = self._build_dest_swap_interactions(
                intent, state, snapshot, dst_chain, output_token, recipient,
            )
            chain_legs.append(ChainLeg(
                chain_id=dst_chain,
                interactions=dest_interactions,
                intent_selector=swap_sel,
                metadata={"type": "destination_swap"},
            ))

        cross_chain_plan = CrossChainPlan(
            legs=chain_legs,
            bridge_requests=bridge_requests,
        )

        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=[],  # Legs have the real interactions
            deadline=int(time.time()) + 7200,
            nonce=state.nonce,
            metadata={
                "cross_chain_plan": cross_chain_plan.to_dict(),
                "src_chain_id": src_chain,
                "dst_chain_id": dst_chain,
                "plan_type": "cross_chain",
            },
        )

    def _build_source_swap_interactions(
        self, intent, state, snapshot, src_chain, input_token, output_token,
        input_amount, cross_chain_params,
    ) -> list[Interaction]:
        """Build source chain swap interactions for cross-chain Pattern B."""
        try:
            source_state = self._state_with_extra(
                intent, state, chain_id=src_chain,
                extra_updates={
                    "input_token": input_token,
                    "output_token": output_token,
                    "input_amount": str(input_amount),
                    "receiver": cross_chain_params.get("receiver", state.owner or ""),
                    "min_output_amount": cross_chain_params.get("min_output_amount", 0),
                },
            )
            pool_states = self._get_pool_states(src_chain, snapshot)
            if input_token and output_token:
                if snapshot and snapshot.pool_states and pool_states is snapshot.pool_states:
                    pool_states = dict(pool_states)
                self._ensure_pools_for_route(src_chain, pool_states, input_token, output_token)

            prices = self._derive_prices(pool_states, src_chain) if pool_states else {}
            context = ProcessorContext(
                chain_id=src_chain, timestamp=int(time.time()),
                block_number=0, rpc_url=self._rpc_urls.get(src_chain, ""),
                prices=prices,
            )
            source_plan = _run_coro(
                self._processor.generate_plan(intent, source_state, context),
            )
            return source_plan.interactions
        except Exception as exc:
            logger.warning("Cross-chain source swap failed: %s", exc)
            return []

    def _build_dest_swap_interactions(
        self, intent, state, snapshot, dst_chain, output_token, recipient,
    ) -> list[Interaction]:
        """Build destination chain swap interactions."""
        # If the bridge output token IS the desired output, no swap needed
        # The compiler will fill in bridge details; we just need the swap
        try:
            pool_states = self._get_pool_states(dst_chain, snapshot)
            # Discovery seeds for dest chain
            seeds = _DISCOVERY_SEED_TOKENS.get(dst_chain, [])
            if output_token and seeds:
                for seed in seeds:
                    if seed.lower() != output_token.lower():
                        self._ensure_pools_for_route(dst_chain, pool_states, seed, output_token)

            if not pool_states:
                return []

            # Cross-chain destination-leg swap construction is not supported
            # in this single-chain build. The earlier implementation here
            # called a `_build_swap_interactions` helper that does not exist;
            # the broken reference was silently swallowed by the surrounding
            # `except`. Return no interactions explicitly until cross-chain
            # is reintroduced with a real builder.
            return []
        except Exception as exc:
            logger.warning("Cross-chain dest swap interactions failed: %s", exc)
            return []

    def _find_bridgeable_token(self, src_chain: int, dst_chain: int, exclude_token: str) -> str:
        """Find a token on src_chain that can be bridged to dst_chain."""
        if self._bridge_registry is None:
            return ""
        from minotaur_subnet.blockchain.tokens import TOKENS
        for symbol, addr in TOKENS.get(src_chain, {}).items():
            if addr.lower() == exclude_token.lower():
                continue
            adapters = self._bridge_registry.find_bridge(src_chain, dst_chain)
            for adapter in adapters:
                if hasattr(adapter, '_find_route'):
                    route = adapter._find_route(src_chain, dst_chain, addr)
                    if route:
                        return addr
        return ""

    def _build_dest_leg(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        dst_chain: int,
        bridge_quote_meta: dict,
        recipient: str,
    ) -> list[Interaction]:
        """Build destination leg interactions.

        If the bridged token (bridge_quote_meta["token_out"]) differs from
        the user's desired output_token, generate approve + swap on dest chain.
        Otherwise return an empty list (tokens arrive via bridge, no further action).
        """
        cross_chain_params = self._cross_chain_params(intent, state)
        output_token = cross_chain_params.get("output_token", "")
        bridge_token_out = bridge_quote_meta.get("token_out", "")
        bridge_estimated = bridge_quote_meta.get("estimated_output", 0)

        # If no bridge quote or bridge delivers the desired token → no dest swap
        if (
            not bridge_token_out
            or not output_token
            or bridge_token_out.lower() == output_token.lower()
        ):
            return []

        # Need a swap on dest chain: bridged_token → output_token
        try:
            dest_state = self._state_with_extra(
                intent,
                state,
                chain_id=dst_chain,
                extra_updates={
                    "input_token": bridge_token_out,
                    "output_token": output_token,
                    "input_amount": str(bridge_estimated),
                    "min_output_amount": str(cross_chain_params.get("dest_min_output_amount", 0)),
                    "receiver": recipient,
                },
            )
            context = ProcessorContext(
                chain_id=dst_chain,
                timestamp=int(time.time()),
                block_number=0,
                rpc_url=self._rpc_urls.get(dst_chain, ""),
            )
            dest_plan = _run_coro(
                self._processor.generate_plan(intent, dest_state, context),
            )
            return dest_plan.interactions
        except Exception as exc:
            logger.warning("Cross-chain dest plan failed: %s", exc)
            return []

    def quote(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        snapshot: MarketSnapshot | None = None,
    ) -> QuoteResult:
        """Compute a quote using RPC pool data (preferred) or snapshot fallback.

        Uses the shared normalized swap view (typed context first, raw
        compatibility payload second), routes through discovered pools,
        and returns estimated output.
        """
        from strategies.dex_aggregator.pool_math import find_best_route

        swap_params = self._normalized_swap_params(intent, state)
        input_token = swap_params.get("input_token", "")
        output_token = swap_params.get("output_token", "")
        amount_in = swap_params.get("input_amount", 0)

        if not input_token or not output_token:
            raise ValueError("input_token and output_token required in params")

        if amount_in <= 0:
            raise ValueError("input_amount must be positive")

        # Detect cross-chain from token chain IDs or dest_chain_id
        input_chain = swap_params.get("_input_chain", state.chain_id)
        output_chain = swap_params.get("_output_chain", state.chain_id)
        dest_chain_id = _cross_chain_compat_params(state).get("dest_chain_id")
        if dest_chain_id:
            output_chain = int(dest_chain_id)
        if input_chain and output_chain and input_chain != output_chain:
            return self._quote_cross_chain(
                intent, state, snapshot,
                input_token, output_token, amount_in,
                int(input_chain), int(output_chain),
            )

        chain_id = state.chain_id or (snapshot.chain_id if snapshot else 1)
        pool_states = self._get_pool_states(chain_id, snapshot)

        # Factory-based discovery for the requested pair
        if snapshot is not None and snapshot.pool_states and pool_states is snapshot.pool_states:
            pool_states = dict(pool_states)  # Shallow copy to avoid mutating snapshot
        self._ensure_pools_for_route(chain_id, pool_states, input_token, output_token)

        if not pool_states:
            raise ValueError(
                f"No pool data available for chain {chain_id} "
                f"(no RPC URL configured and no snapshot provided)"
            )

        # Use the executable route finder so quote estimates can't promise
        # a cross-DEX 2-hop the planner refuses to emit (the planner falls
        # back to single-DEX, leaving a quote/plan output mismatch).
        result = self._find_best_executable_route(
            pool_states, input_token, output_token, amount_in, chain_id,
        )
        if result is None:
            raise ValueError(
                f"No route found for {input_token} -> {output_token}"
            )

        output_amount, route_desc, hops = result

        # Determine data source for metadata
        data_source = "rpc" if self._rpc_urls.get(chain_id) else "snapshot"

        gas_estimate = _GAS_BASE_OVERHEAD + _GAS_PER_HOP * len(hops)
        # Query live gas price per chain — hardcoding a 20 gwei mainnet
        # default produced $40 fees on Base (real gas price <0.01 gwei).
        gas_price_wei = self._get_gas_price_wei(chain_id)
        fee_wei = _compute_platform_fee_wei(gas_estimate, gas_price_wei)

        from minotaur_subnet.blockchain.tokens import WRAPPED_NATIVE_TOKEN, WRAPPED_NATIVE_SYMBOL
        wnt_addr = WRAPPED_NATIVE_TOKEN.get(chain_id, "")
        wnt_symbol = WRAPPED_NATIVE_SYMBOL.get(chain_id, "ETH")

        # Per-hop and dominant-DEX labels. The dominant DEX is what the
        # planner will dispatch on (single-hop or all-same-DEX multi-hop);
        # ``protocols`` keeps the per-hop detail for diagnostics.
        per_hop_dex = [self._hop_dex(h) for h in hops]
        dominant = self._dominant_dex(hops)
        protocol_labels = {
            "uniswap_v3": "UniswapV3",
            "aerodrome_slipstream": "AerodromeSlipstream",
        }

        return QuoteResult(
            estimated_output=str(output_amount),
            route_summary=f"{input_token[:10]}..→{output_token[:10]}.. {route_desc}",
            gas_estimate=gas_estimate,
            metadata={
                "hops": len(hops),
                "pools": [h["pool_addr"] for h in hops],
                "fees": [h["fee"] for h in hops],
                "protocol": protocol_labels.get(dominant, dominant),
                "protocols": [protocol_labels.get(d, d) for d in per_hop_dex],
                "data_source": data_source,
            },
            platform_fee_wei=str(fee_wei),
            platform_fee_token=wnt_addr,
            platform_fee_symbol=wnt_symbol,
        )

    def _quote_cross_chain(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        snapshot: MarketSnapshot | None,
        input_token: str,
        output_token: str,
        amount_in: int,
        src_chain: int,
        dst_chain: int,
    ) -> QuoteResult:
        """Quote a cross-chain swap: bridge + swap (either order).

        Two directions:
        A) Bridge-first: input has a direct bridge route (e.g. USDC Base→BT EVM),
           then swap on destination (USDC→WTAO on BT EVM).
        B) Swap-first: no direct bridge for input token, swap on source chain
           to a bridgeable token, then bridge to destination
           (e.g. WTAO→USDC on BT EVM, then bridge USDC to Base).
        """
        from strategies.dex_aggregator.pool_math import find_best_route

        # Try direction A: bridge input_token first, then swap on dst
        bridge_quote_a = None
        if self._bridge_registry is not None:
            try:
                bridge_quote_a = _run_coro(
                    self._bridge_registry.best_quote(
                        input_token, amount_in, src_chain, dst_chain,
                    )
                )
            except Exception:
                pass

        if bridge_quote_a:
            # Direction A: bridge → swap on destination
            bridged_amount = bridge_quote_a.estimated_output
            bridge_token_out = bridge_quote_a.token_out
            bridge_fee = bridge_quote_a.fee

            dst_pool_states = self._get_pool_states(dst_chain, snapshot)
            self._ensure_pools_for_route(dst_chain, dst_pool_states, bridge_token_out, output_token)

            if bridge_token_out.lower() == output_token.lower():
                # Bridge output IS the desired token — no swap needed
                return QuoteResult(
                    estimated_output=str(bridged_amount),
                    route_summary=f"Cross-chain: bridge {src_chain}→{dst_chain} (direct)",
                    gas_estimate=_GAS_BASE_OVERHEAD * 2,
                    metadata={
                        "cross_chain": True, "direction": "bridge_only",
                        "src_chain": src_chain, "dst_chain": dst_chain,
                        "bridge_fee": bridge_fee, "protocol": "Hyperlane",
                    },
                    computed_params={"min_output_amount": str(bridged_amount)},
                )

            route = find_best_route(dst_pool_states, bridge_token_out, output_token, bridged_amount)
            if route:
                output_amount, route_desc, hops = route
                return QuoteResult(
                    estimated_output=str(output_amount),
                    route_summary=f"Cross-chain: bridge {src_chain}→{dst_chain} + {route_desc}",
                    gas_estimate=_GAS_BASE_OVERHEAD * 2 + _GAS_PER_HOP * len(hops),
                    metadata={
                        "cross_chain": True, "direction": "bridge_then_swap",
                        "src_chain": src_chain, "dst_chain": dst_chain,
                        "bridge_fee": bridge_fee, "bridged_amount": bridged_amount,
                        "hops": len(hops), "protocol": "UniswapV3 + Hyperlane",
                    },
                    computed_params={"min_output_amount": str(output_amount * 99 // 100)},
                )

        # Direction B: swap on source chain → bridge to destination
        # Find a bridgeable token from src→dst
        bridge_quote_b = None
        bridgeable_token = None
        if self._bridge_registry is not None:
            # Try common bridgeable tokens (USDC, etc.) on the source chain
            from minotaur_subnet.blockchain.tokens import TOKENS
            src_tokens = TOKENS.get(src_chain, {})
            # Also check discovery seeds as fallback
            if not src_tokens:
                for seed_addr in _DISCOVERY_SEED_TOKENS.get(src_chain, []):
                    src_tokens[seed_addr[:8]] = seed_addr
            # Check which tokens have bridge routes (no RPC needed)
            bridgeable_adapters = self._bridge_registry.find_bridge(src_chain, dst_chain)
            for symbol, addr in src_tokens.items():
                if addr.lower() == input_token.lower():
                    continue
                # Check if any adapter supports this token on this route
                for adapter in bridgeable_adapters:
                    has_fr = hasattr(adapter, '_find_route')
                    route = adapter._find_route(src_chain, dst_chain, addr) if has_fr else None
                    if route:
                        bridgeable_token = addr
                        break
                if bridgeable_token:
                    break

        if bridgeable_token:
            # Swap input_token → bridgeable_token on source chain
            src_pool_states = self._get_pool_states(src_chain, snapshot)
            self._ensure_pools_for_route(src_chain, src_pool_states, input_token, bridgeable_token)
            route = find_best_route(src_pool_states, input_token, bridgeable_token, amount_in)

            if route:
                swap_output, route_desc, hops = route

                # Bridge the swapped amount
                try:
                    bridge_quote_b = _run_coro(
                        self._bridge_registry.best_quote(
                            bridgeable_token, swap_output, src_chain, dst_chain,
                        )
                    )
                except Exception:
                    pass

                if bridge_quote_b:
                    final_output = bridge_quote_b.estimated_output
                    bridge_token_out = bridge_quote_b.token_out

                    # Check if bridge output matches desired output
                    if bridge_token_out.lower() == output_token.lower():
                        return QuoteResult(
                            estimated_output=str(final_output),
                            route_summary=f"Cross-chain: {route_desc} + bridge {src_chain}→{dst_chain}",
                            gas_estimate=_GAS_BASE_OVERHEAD * 2 + _GAS_PER_HOP * len(hops),
                            metadata={
                                "cross_chain": True, "direction": "swap_then_bridge",
                                "src_chain": src_chain, "dst_chain": dst_chain,
                                "bridge_fee": bridge_quote_b.fee,
                                "swap_output": swap_output,
                                "hops": len(hops), "protocol": "UniswapV3 + Hyperlane",
                            },
                            computed_params={"min_output_amount": str(final_output)},
                        )

        raise ValueError(
            f"No cross-chain route found for {input_token[:10]}.. ({src_chain}) → "
            f"{output_token[:10]}.. ({dst_chain})"
        )

    def check_trigger(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        snapshot: MarketSnapshot | None = None,
    ) -> bool:
        """Delegate trigger check to the wrapped processor."""
        if self._processor is None:
            return False

        chain_id = state.chain_id or (snapshot.chain_id if snapshot else 1)
        context = ProcessorContext(
            chain_id=chain_id,
            timestamp=snapshot.timestamp if snapshot else int(time.time()),
            block_number=snapshot.block_number if snapshot else 0,
            rpc_url=self._rpc_urls.get(chain_id, ""),
            prices={},
            dex_config={},
        )
        return _run_coro(self._processor.check_trigger(intent, state, context))

    _token_cache: dict[int, tuple[float, list[dict[str, Any]]]] = {}
    _token_cache_ttl: float = 300.0  # 5 minutes

    def supported_tokens(self, chain_id: int) -> list[dict[str, Any]]:
        """Return tokens the solver can route on the given chain.

        Extracts unique token addresses from all discovered pools,
        enriches with on-chain metadata (symbol, decimals) where possible.
        Results cached for 5 minutes to avoid repeated RPC queries.
        """
        # Return from cache if fresh
        cached = self._token_cache.get(chain_id)
        if cached and time.time() - cached[0] < self._token_cache_ttl:
            return cached[1]

        # Discover pools (uses cache if fresh)
        pool_states = self._get_pool_states(chain_id, snapshot=None)

        # Discover pools by querying factory for all pairs among seed tokens.
        # This finds pools the solver can route through.
        seed = _DISCOVERY_SEED_TOKENS.get(chain_id, [])
        for i, tok_a in enumerate(seed):
            for tok_b in seed[i + 1:]:
                try:
                    self._discover_pools_for_pair(chain_id, tok_a, tok_b, pool_states)
                except Exception:
                    pass

        # Also merge in the live pool cache — this includes pools discovered
        # during order processing (e.g. when a user pastes a custom token
        # and the solver successfully routes it). These tokens get promoted
        # to the public token list automatically.
        live_cache = self._pool_cache.get(chain_id, {})
        for addr, state in live_cache.items():
            if addr not in pool_states:
                pool_states[addr] = state

        # Extract unique token addresses
        tokens: dict[str, dict[str, Any]] = {}
        for pool in pool_states.values():
            for key in ("token0", "token1"):
                addr = pool.get(key, "")
                if addr and addr.lower() not in tokens:
                    tokens[addr.lower()] = {"address": addr}

        # Enrich with symbol/decimals — use cached symbols first, then RPC
        rpc_url = self._rpc_urls.get(chain_id, "")
        w3 = None
        if rpc_url:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(rpc_url))

        result = []
        for addr_lower, info in tokens.items():
            addr = info["address"]
            symbol = _TOKEN_SYMBOLS.get(addr_lower, "")
            decimals = 18  # default

            if w3 and not symbol:
                try:
                    # Query symbol() and decimals() on-chain
                    erc20 = w3.eth.contract(
                        address=w3.to_checksum_address(addr),
                        abi=[
                            {"inputs": [], "name": "symbol", "outputs": [{"type": "string"}], "stateMutability": "view", "type": "function"},
                            {"inputs": [], "name": "decimals", "outputs": [{"type": "uint8"}], "stateMutability": "view", "type": "function"},
                        ],
                    )
                    symbol = erc20.functions.symbol().call()
                    decimals = erc20.functions.decimals().call()
                except Exception:
                    symbol = addr_lower[:8] + "..."

            if not symbol:
                symbol = addr_lower[:8] + "..."

            if w3 and decimals == 18:
                try:
                    erc20 = w3.eth.contract(
                        address=w3.to_checksum_address(addr),
                        abi=[{"inputs": [], "name": "decimals", "outputs": [{"type": "uint8"}], "stateMutability": "view", "type": "function"}],
                    )
                    decimals = erc20.functions.decimals().call()
                except Exception:
                    pass

            # Estimate liquidity rank from pool count
            pool_count = sum(
                1 for p in pool_states.values()
                if p.get("token0", "").lower() == addr_lower or p.get("token1", "").lower() == addr_lower
            )

            result.append({
                "address": w3.to_checksum_address(addr) if w3 else addr,
                "symbol": symbol,
                "decimals": decimals,
                "pool_count": pool_count,
            })

        # Sort by pool count (most connected tokens first)
        result.sort(key=lambda t: -t["pool_count"])

        # Cache the result
        self._token_cache[chain_id] = (time.time(), result)
        return result

    def metadata(self) -> SolverMetadata:
        """Return baseline solver metadata."""
        return SolverMetadata(
            name="baseline-swap-solver",
            version="2.0.0",
            author="minotaur-subnet",
            description=(
                "Baseline v2 solver with RPC-first pool discovery. "
                "Queries real Uniswap V3 pool states for accurate "
                "pricing. Falls back to snapshot when no RPC available."
            ),
            supported_chains=[1, 8453],
            supported_intent_types=["swap"],
        )


# Module-level attribute required by the solver loader (harness/runner.py)
SOLVER_CLASS = BaselineSwapSolver
