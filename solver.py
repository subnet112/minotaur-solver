from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

from minotaur_subnet.sdk.intent_solver import IntentSolver, MarketSnapshot, SolverMetadata
from minotaur_subnet.shared.types import (
    AppIntentDefinition,
    ExecutionPlan,
    Interaction,
    IntentState,
    QuoteResult,
)


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
MSG_SENDER_SENTINEL = "0x0000000000000000000000000000000000000001"
MAX_UINT256 = (1 << 256) - 1
Q192 = 1 << 192

APP_RECIPIENT_SENTINEL = "app"

ERC20_APPROVE_SELECTOR = "095ea7b3"

DEX_UNISWAP_V3 = "uniswap_v3"
DEX_AERODROME_SLIPSTREAM = "aerodrome_slipstream"

# Uniswap V3 SwapRouter (Ethereum 0xE592...): deadline-bearing structs.
V3_EXACT_INPUT_SINGLE_SELECTOR = "414bf389"
V3_EXACT_INPUT_SELECTOR = "c04b8d59"

# Uniswap V3 SwapRouter02 (Base 0x2626...): exactInputSingle has no deadline;
# exactInput still uses the deadline-bearing V3 tuple selector.
V3_02_EXACT_INPUT_SINGLE_SELECTOR = "04e45aaf"
V3_02_EXACT_INPUT_SELECTOR = V3_EXACT_INPUT_SELECTOR

# Aerodrome Slipstream concentrated-liquidity router/factory on Base.
AERODROME_EXACT_INPUT_SINGLE_SELECTOR = "a026383e"
AERODROME_EXACT_INPUT_SELECTOR = V3_EXACT_INPUT_SELECTOR
AERODROME_FACTORY_GET_POOL_SELECTOR = "28af8d0b"

FACTORY_GET_POOL_SELECTOR = "1698ee82"
POOL_SLOT0_SELECTOR = "3850c7bd"
POOL_LIQUIDITY_SELECTOR = "1a686502"
POOL_TOKEN0_SELECTOR = "0dfe1681"
POOL_TOKEN1_SELECTOR = "d21220a7"
POOL_FEE_SELECTOR = "ddca3f43"
POOL_TICK_SPACING_SELECTOR = "d0c93a7c"

FEE_TIERS = (100, 500, 3000, 10000)
AERODROME_TICK_SPACINGS = (1, 50, 100, 200, 2000)


CHAIN_CONFIG: dict[int, dict[str, Any]] = {
    1: {
        "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
        "router": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        "router_kind": "v3",
        "tokens": {
            "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
            "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
            "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
        },
    },
    8453: {
        "factory": "0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
        "router": "0x2626664c2603336E57B271c5C0b26F421741e481",
        "router_kind": "v3_02",
        "aerodrome_factory": "0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A",
        "aerodrome_router": "0xBE6D8f0d05cC4be24d5167a3eF062215bE6D18a5",
        "tokens": {
            "WETH": "0x4200000000000000000000000000000000000006",
            "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "USDbC": "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA",
            "DAI": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb",
            "cbBTC": "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf",
            "cbETH": "0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22",
            "wstETH": "0xc1CBa3fCea344f92D9239c08C0568f6F2F0ee452",
            "BSWAP": "0x78a087d713Be963Bf307b18F2Ff8122EF9A63ae9",
            "HIGHER": "0x0578d8A44db98B23BF096A382e016e29a5Ce0ffe",
            "BRETT": "0x532f27101965dd16442E59d40670FaF5eBB142E4",
            "AERO": "0x940181a94A35A4569E4529A3CDfB74e38FD98631",
            "rETH": "0xB6fe221Fe9EeF5aBa221c348bA20A1Bf5e73624c",
            "weETH": "0x04C0599Ae5A44757c0af6F9eC3b93da8976c150A",
            "PRIME": "0xfA980cEd6895AC314E7dE34Ef1bFAE90a5AdD21b",
            "tBTC": "0x236aa50979D5f3De3Bd1Eeb40E81137F22ab794b",
            "wTAO": "0x77E06c9eCCf2E797fd462A92B6D7642EF85b0A44",
            "SNX": "0xdC46C1E93B71fF9209A0F8076a9951569DC35855",
        },
    },
    31337: {
        "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
        "router": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        "router_kind": "v3",
        "tokens": {
            "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
            "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
            "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
        },
    },
}

DECIMALS_BY_SYMBOL = {
    "WETH": 18,
    "ETH": 18,
    "USDC": 6,
    "USDT": 6,
    "USDbC": 6,
    "DAI": 18,
    "WBTC": 8,
    "cbBTC": 8,
}


class Pool:
    def __init__(
        self,
        *,
        address: str,
        token0: str,
        token1: str,
        fee: int,
        sqrt_price_x96: int,
        liquidity: int,
        dex: str = DEX_UNISWAP_V3,
        tick_spacing: int | None = None,
    ) -> None:
        self.address = address
        self.token0 = token0
        self.token1 = token1
        self.fee = fee
        self.sqrt_price_x96 = sqrt_price_x96
        self.liquidity = liquidity
        self.dex = dex
        self.tick_spacing = tick_spacing

    def connects(self, token_a: str, token_b: str) -> bool:
        pair = {self.token0.lower(), self.token1.lower()}
        return token_a.lower() in pair and token_b.lower() in pair and token_a.lower() != token_b.lower()


class Leg:
    def __init__(self, pool: Pool, token_in: str, token_out: str) -> None:
        self.pool = pool
        self.token_in = token_in
        self.token_out = token_out


class Route:
    def __init__(
        self,
        *,
        legs: tuple[Leg, ...],
        amount_in: int,
        estimated_output: int,
        confidence_bps: int,
        amounts_out: tuple[int, ...],
    ) -> None:
        self.legs = legs
        self.amount_in = amount_in
        self.estimated_output = estimated_output
        self.confidence_bps = confidence_bps
        self.amounts_out = amounts_out

    @property
    def hops(self) -> int:
        return len(self.legs)

    @property
    def tokens(self) -> list[str]:
        if not self.legs:
            return []
        out = [self.legs[0].token_in]
        out.extend(leg.token_out for leg in self.legs)
        return out

    @property
    def fees(self) -> list[int]:
        return [leg.pool.fee for leg in self.legs]

    @property
    def dexes(self) -> list[str]:
        return [leg.pool.dex for leg in self.legs]

    @property
    def is_mixed_dex(self) -> bool:
        return len(set(self.dexes)) > 1


class TopMinerRouterSolver(IntentSolver):
    """DexAggregator-focused CPU solver.

    The route search is intentionally conservative. It prefers execution
    reliability over speculative output and shares one route engine between
    quote() and generate_plan() so benchmark quote enrichment and plan execution
    cannot diverge.
    """

    def __init__(self) -> None:
        self.rpc_urls: dict[int, str] = {}
        self.chain_ids: list[int] = [1, 8453]
        self._pool_cache: dict[tuple[Any, ...], Pool | None] = {}
        self._batch_route_cache: dict[tuple[int, str, str, int, str], Route | None] = {}
        self._last_results: list[dict[str, Any]] = []

    def initialize(self, config: dict[str, Any]) -> None:
        self.chain_ids = [int(c) for c in config.get("chain_ids", [1, 8453])]
        raw_rpc = config.get("rpc_urls", {}) or {}
        self.rpc_urls = {}
        for key, value in raw_rpc.items():
            try:
                self.rpc_urls[int(key)] = str(value)
            except (TypeError, ValueError):
                continue
        self._pool_cache.clear()
        self._batch_route_cache.clear()

    def on_benchmark_start(self, intent_count: int) -> None:
        self._batch_route_cache.clear()

    def on_benchmark_end(self, results: list[dict[str, Any]]) -> None:
        self._last_results = list(results or [])

    def metadata(self) -> SolverMetadata:
        return SolverMetadata(
            name="top-miner-router",
            version="0.1.0",
            author="local-miner",
            description=(
                "DexAggregator Uniswap V3 and Aerodrome Slipstream router with "
                "shared quote and execution planning"
            ),
            supported_chains=[1, 8453, 31337],
            supported_intent_types=["swap", "limit_order"],
        )

    def quote(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        snapshot: MarketSnapshot | None = None,
    ) -> QuoteResult:
        params = _swap_params(state)
        route = self._best_route(state.chain_id or _snapshot_chain(snapshot), params, snapshot)
        if route is None or route.estimated_output <= 0:
            return QuoteResult(
                estimated_output="0",
                route_summary="no-route",
                gas_estimate=0,
                metadata={"reason": "no executable route found"},
            )

        fee_wei = self._platform_fee_wei(route.estimated_output, params["output_token"], state.chain_id)
        return QuoteResult(
            estimated_output=str(route.estimated_output),
            computed_params={
                "quoted_output": str(route.estimated_output),
                "min_output_amount": str(_apply_bps(route.estimated_output, route.confidence_bps)),
            },
            route_summary=_route_summary(route),
            gas_estimate=_gas_estimate(route),
            metadata={
                "router": self._router_for_chain(state.chain_id),
                "hops": route.hops,
                "tokens": route.tokens,
                "fees": route.fees,
                "dexes": route.dexes,
                "confidence_bps": route.confidence_bps,
                "solver": "top-miner-router",
            },
            platform_fee_wei=str(fee_wei),
            platform_fee_token=_wrapped_native(state.chain_id),
            platform_fee_symbol="ETH",
        )

    def generate_plan(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        snapshot: MarketSnapshot | None = None,
    ) -> ExecutionPlan:
        params = _swap_params(state)
        chain_id = state.chain_id or _snapshot_chain(snapshot)
        route = self._best_route(chain_id, params, snapshot)

        if route is None:
            return self._fallback_plan(intent, state, snapshot, params, "no-route")

        recipient = state.contract_address or params.get("receiver") or state.owner or ZERO_ADDRESS
        deadline = _deadline(snapshot)
        amount_in = params["input_amount"]
        min_output = self._execution_min_output(params, route)

        if route.is_mixed_dex:
            interactions = self._encode_sequential_route(route, recipient, deadline, min_output, chain_id)
            router = "mixed"
        else:
            router = self._router_for_route(route, chain_id)
            interactions = [
                Interaction(
                    target=params["input_token"],
                    value="0",
                    call_data=_encode_approve(router, amount_in),
                    chain_id=chain_id,
                ),
                Interaction(
                    target=router,
                    value="0",
                    call_data=self._encode_swap(route, recipient, deadline, min_output, chain_id),
                    chain_id=chain_id,
                ),
            ]

        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=interactions,
            deadline=deadline,
            nonce=state.nonce,
            metadata={
                "solver": "top-miner-router",
                "route": _route_summary(route),
                "estimated_output": str(route.estimated_output),
                "min_output": str(min_output),
                "min_output_amount": str(min_output),
                "output_token": params["output_token"],
                "hops": route.hops,
                "tokens": route.tokens,
                "fees": route.fees,
                "dexes": route.dexes,
                "chain_id": chain_id,
                "router": router,
            },
        )

    def check_trigger(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        snapshot: MarketSnapshot | None = None,
    ) -> bool:
        params = _swap_params(state)
        route = self._best_route(state.chain_id or _snapshot_chain(snapshot), params, snapshot)
        if route is None:
            return False
        target_price = _to_float(params.get("target_price"))
        if target_price is None:
            return route.estimated_output >= max(1, params["min_output_amount"])
        input_amount = max(1, params["input_amount"])
        implied = route.estimated_output / input_amount
        return implied >= target_price

    def serialize_state(self) -> bytes:
        return json.dumps({"last_results": self._last_results[-50:]}).encode("utf-8")

    def restore_state(self, data: bytes) -> None:
        if not data:
            return
        try:
            parsed = json.loads(data.decode("utf-8"))
            self._last_results = list(parsed.get("last_results", []))
        except Exception:
            self._last_results = []

    def _best_route(
        self,
        chain_id: int,
        params: dict[str, Any],
        snapshot: MarketSnapshot | None,
    ) -> Route | None:
        token_in = _addr(params["input_token"])
        token_out = _addr(params["output_token"])
        amount_in = int(params["input_amount"])
        block_hint = str(getattr(snapshot, "block_number", 0) if snapshot else 0)
        key = (chain_id, token_in.lower(), token_out.lower(), amount_in, block_hint)
        if key in self._batch_route_cache:
            return self._batch_route_cache[key]

        pools = self._collect_pools(chain_id, token_in, token_out, snapshot)
        candidates: list[Route] = []

        for pool in pools:
            route = _simulate_route((Leg(pool, token_in, token_out),), amount_in)
            if route is not None and self._is_executable_route(route, chain_id):
                candidates.append(route)

        for mid in self._intermediaries(chain_id, token_in, token_out):
            first_pools = self._collect_pools(chain_id, token_in, mid, snapshot)
            second_pools = self._collect_pools(chain_id, mid, token_out, snapshot)
            for p1 in first_pools:
                first = _simulate_route((Leg(p1, token_in, mid),), amount_in)
                if first is None or first.estimated_output <= 0:
                    continue
                for p2 in second_pools:
                    route = _simulate_route(
                        (Leg(p1, token_in, mid), Leg(p2, mid, token_out)),
                        amount_in,
                    )
                    if route is not None and self._is_executable_route(route, chain_id):
                        candidates.append(route)

        if not candidates:
            self._batch_route_cache[key] = None
            return None

        min_out = int(params.get("min_output_amount") or 0)

        def rank(route: Route) -> tuple[int, int, int]:
            pass_floor = 1 if route.estimated_output >= min_out else 0
            gas_penalty = _gas_estimate(route)
            return (pass_floor, route.estimated_output - gas_penalty, -route.hops)

        best = max(candidates, key=rank)
        self._batch_route_cache[key] = best
        return best

    def _collect_pools(
        self,
        chain_id: int,
        token_a: str,
        token_b: str,
        snapshot: MarketSnapshot | None,
    ) -> list[Pool]:
        pools: list[Pool] = []
        seen: set[tuple[str, str, int, int | None]] = set()

        if snapshot is not None:
            for address, raw in (snapshot.pool_states or {}).items():
                pool = _pool_from_snapshot(address, raw)
                if pool and pool.connects(token_a, token_b):
                    ident = (pool.dex, pool.address.lower(), pool.fee, pool.tick_spacing)
                    if ident not in seen:
                        pools.append(pool)
                        seen.add(ident)

        if len(pools) < 4 and self.rpc_urls.get(chain_id):
            for fee in FEE_TIERS:
                pool = self._discover_pool_rpc(chain_id, token_a, token_b, fee)
                if pool:
                    ident = (pool.dex, pool.address.lower(), pool.fee, pool.tick_spacing)
                    if ident not in seen:
                        pools.append(pool)
                        seen.add(ident)
            for tick_spacing in AERODROME_TICK_SPACINGS:
                pool = self._discover_aerodrome_pool_rpc(chain_id, token_a, token_b, tick_spacing)
                if pool:
                    ident = (pool.dex, pool.address.lower(), pool.fee, pool.tick_spacing)
                    if ident not in seen:
                        pools.append(pool)
                        seen.add(ident)

        pools.sort(key=lambda p: (p.liquidity, -p.fee), reverse=True)
        return pools[:4]

    def _discover_pool_rpc(self, chain_id: int, token_a: str, token_b: str, fee: int) -> Pool | None:
        cache_key = (chain_id, token_a.lower(), token_b.lower(), fee)
        if cache_key in self._pool_cache:
            return self._pool_cache[cache_key]

        factory = CHAIN_CONFIG.get(chain_id, CHAIN_CONFIG[1]).get("factory")
        rpc_url = self.rpc_urls.get(chain_id)
        if not factory or not rpc_url:
            self._pool_cache[cache_key] = None
            return None

        try:
            calldata = "0x" + FACTORY_GET_POOL_SELECTOR + _encode_address(token_a) + _encode_address(token_b) + _encode_uint(fee)
            raw = _eth_call(rpc_url, factory, calldata)
            pool_addr = _decode_address_word(raw)
            if not pool_addr or pool_addr == ZERO_ADDRESS:
                self._pool_cache[cache_key] = None
                return None

            slot0 = _eth_call(rpc_url, pool_addr, "0x" + POOL_SLOT0_SELECTOR)
            liquidity = _eth_call(rpc_url, pool_addr, "0x" + POOL_LIQUIDITY_SELECTOR)
            token0 = _decode_address_word(_eth_call(rpc_url, pool_addr, "0x" + POOL_TOKEN0_SELECTOR))
            token1 = _decode_address_word(_eth_call(rpc_url, pool_addr, "0x" + POOL_TOKEN1_SELECTOR))
            sqrt_price = int(_strip_0x(slot0)[:64], 16)
            liq = int(_strip_0x(liquidity)[:64] or "0", 16)
            pool = Pool(
                address=pool_addr,
                token0=_addr(token0),
                token1=_addr(token1),
                fee=fee,
                sqrt_price_x96=sqrt_price,
                liquidity=liq,
            )
            self._pool_cache[cache_key] = pool if pool.connects(token_a, token_b) else None
            return self._pool_cache[cache_key]
        except Exception:
            self._pool_cache[cache_key] = None
            return None

    def _discover_aerodrome_pool_rpc(
        self,
        chain_id: int,
        token_a: str,
        token_b: str,
        tick_spacing: int,
    ) -> Pool | None:
        cache_key = (DEX_AERODROME_SLIPSTREAM, chain_id, token_a.lower(), token_b.lower(), tick_spacing)
        if cache_key in self._pool_cache:
            return self._pool_cache[cache_key]

        cfg = CHAIN_CONFIG.get(chain_id, {})
        factory = cfg.get("aerodrome_factory")
        rpc_url = self.rpc_urls.get(chain_id)
        if not factory or not rpc_url:
            self._pool_cache[cache_key] = None
            return None

        try:
            calldata = (
                "0x"
                + AERODROME_FACTORY_GET_POOL_SELECTOR
                + _encode_address(token_a)
                + _encode_address(token_b)
                + _encode_int(tick_spacing)
            )
            raw = _eth_call(rpc_url, factory, calldata)
            pool_addr = _decode_address_word(raw)
            if not pool_addr or pool_addr == ZERO_ADDRESS:
                self._pool_cache[cache_key] = None
                return None

            slot0 = _eth_call(rpc_url, pool_addr, "0x" + POOL_SLOT0_SELECTOR)
            liquidity = _eth_call(rpc_url, pool_addr, "0x" + POOL_LIQUIDITY_SELECTOR)
            token0 = _decode_address_word(_eth_call(rpc_url, pool_addr, "0x" + POOL_TOKEN0_SELECTOR))
            token1 = _decode_address_word(_eth_call(rpc_url, pool_addr, "0x" + POOL_TOKEN1_SELECTOR))
            fee_raw = _eth_call(rpc_url, pool_addr, "0x" + POOL_FEE_SELECTOR)
            spacing_raw = _eth_call(rpc_url, pool_addr, "0x" + POOL_TICK_SPACING_SELECTOR)
            sqrt_price = int(_strip_0x(slot0)[:64], 16)
            liq = int(_strip_0x(liquidity)[:64] or "0", 16)
            fee_hex = _strip_0x(fee_raw)[:64]
            spacing_hex = _strip_0x(spacing_raw)[:64]
            fee = int(fee_hex or "0", 16)
            spacing = int(spacing_hex, 16) if spacing_hex else tick_spacing
            pool = Pool(
                address=pool_addr,
                token0=_addr(token0),
                token1=_addr(token1),
                fee=fee or 3000,
                sqrt_price_x96=sqrt_price,
                liquidity=liq,
                dex=DEX_AERODROME_SLIPSTREAM,
                tick_spacing=spacing or tick_spacing,
            )
            self._pool_cache[cache_key] = pool if pool.connects(token_a, token_b) else None
            return self._pool_cache[cache_key]
        except Exception:
            self._pool_cache[cache_key] = None
            return None

    def _intermediaries(self, chain_id: int, token_in: str, token_out: str) -> list[str]:
        cfg = CHAIN_CONFIG.get(chain_id, CHAIN_CONFIG[1])
        tokens = [_addr(v) for v in cfg.get("tokens", {}).values()]
        priority_symbols = ("WETH", "USDC", "USDbC", "USDT", "DAI")
        priority = [_addr(cfg["tokens"][s]) for s in priority_symbols if s in cfg.get("tokens", {})]
        out: list[str] = []
        for token in priority + tokens:
            if token.lower() in (token_in.lower(), token_out.lower()):
                continue
            if token.lower() not in {t.lower() for t in out}:
                out.append(token)
        return out[:5]

    def _router_for_chain(self, chain_id: int) -> str:
        return _addr(CHAIN_CONFIG.get(chain_id, CHAIN_CONFIG[1])["router"])

    def _aerodrome_router_for_chain(self, chain_id: int) -> str:
        return _addr(CHAIN_CONFIG.get(chain_id, {}).get("aerodrome_router") or ZERO_ADDRESS)

    def _router_for_leg(self, leg: Leg, chain_id: int) -> str:
        if leg.pool.dex == DEX_AERODROME_SLIPSTREAM:
            return self._aerodrome_router_for_chain(chain_id)
        return self._router_for_chain(chain_id)

    def _router_for_route(self, route: Route, chain_id: int) -> str:
        if route.legs and all(leg.pool.dex == DEX_AERODROME_SLIPSTREAM for leg in route.legs):
            return self._aerodrome_router_for_chain(chain_id)
        return self._router_for_chain(chain_id)

    def _router_kind(self, chain_id: int) -> str:
        return str(CHAIN_CONFIG.get(chain_id, CHAIN_CONFIG[1]).get("router_kind", "v3"))

    def _is_executable_route(self, route: Route, chain_id: int) -> bool:
        if not route.legs:
            return False
        if not route.is_mixed_dex:
            return True
        if chain_id != 8453:
            return False
        # SwapRouter02 can send intermediate output back to msg.sender via the
        # address(1) recipient sentinel. Aerodrome final hops are then executable
        # as a separate interaction from the same proxy.
        return all(leg.pool.dex == DEX_UNISWAP_V3 for leg in route.legs[:-1])

    def _encode_sequential_route(
        self,
        route: Route,
        final_recipient: str,
        deadline: int,
        final_min_output: int,
        chain_id: int,
    ) -> list[Interaction]:
        interactions: list[Interaction] = []
        amount_in = route.amount_in
        for idx, leg in enumerate(route.legs):
            router = self._router_for_leg(leg, chain_id)
            is_final = idx == len(route.legs) - 1
            recipient = final_recipient if is_final else MSG_SENDER_SENTINEL
            min_output = final_min_output if is_final else 0
            interactions.append(
                Interaction(
                    target=leg.token_in,
                    value="0",
                    call_data=_encode_approve(router, amount_in),
                    chain_id=chain_id,
                )
            )
            interactions.append(
                Interaction(
                    target=router,
                    value="0",
                    call_data=self._encode_single_leg_swap(
                        leg,
                        amount_in=amount_in,
                        recipient=recipient,
                        deadline=deadline,
                        min_output=min_output,
                        chain_id=chain_id,
                    ),
                    chain_id=chain_id,
                )
            )
            if idx < len(route.amounts_out):
                amount_in = route.amounts_out[idx]
        return interactions

    def _encode_swap(self, route: Route, recipient: str, deadline: int, min_output: int, chain_id: int) -> str:
        if route.is_mixed_dex:
            raise ValueError("mixed routes must be encoded as sequential interactions")
        if route.legs and all(leg.pool.dex == DEX_AERODROME_SLIPSTREAM for leg in route.legs):
            if route.hops == 1:
                return self._encode_single_leg_swap(
                    route.legs[0],
                    amount_in=route.amount_in,
                    recipient=recipient,
                    deadline=deadline,
                    min_output=min_output,
                    chain_id=chain_id,
                )
            return "0x" + AERODROME_EXACT_INPUT_SELECTOR + _encode_dynamic_tuple(
                [
                    ("bytes", _encode_path(route)),
                    ("address", recipient),
                    ("uint256", deadline),
                    ("uint256", route.amount_in),
                    ("uint256", min_output),
                ]
            )

        kind = self._router_kind(chain_id)
        if route.hops == 1:
            return self._encode_single_leg_swap(
                route.legs[0],
                amount_in=route.amount_in,
                recipient=recipient,
                deadline=deadline,
                min_output=min_output,
                chain_id=chain_id,
            )

        path = _encode_path(route)
        if kind == "v3_02":
            return "0x" + V3_02_EXACT_INPUT_SELECTOR + _encode_dynamic_tuple(
                [
                    ("bytes", path),
                    ("address", recipient),
                    ("uint256", route.amount_in),
                    ("uint256", min_output),
                ]
            )
        return "0x" + V3_EXACT_INPUT_SELECTOR + _encode_dynamic_tuple(
            [
                ("bytes", path),
                ("address", recipient),
                ("uint256", deadline),
                ("uint256", route.amount_in),
                ("uint256", min_output),
            ]
        )

    def _encode_single_leg_swap(
        self,
        leg: Leg,
        *,
        amount_in: int,
        recipient: str,
        deadline: int,
        min_output: int,
        chain_id: int,
    ) -> str:
        if leg.pool.dex == DEX_AERODROME_SLIPSTREAM:
            tick_spacing = int(leg.pool.tick_spacing or leg.pool.fee)
            return (
                "0x"
                + AERODROME_EXACT_INPUT_SINGLE_SELECTOR
                + _encode_address(leg.token_in)
                + _encode_address(leg.token_out)
                + _encode_int(tick_spacing)
                + _encode_address(recipient)
                + _encode_uint(deadline)
                + _encode_uint(amount_in)
                + _encode_uint(min_output)
                + _encode_uint(0)
            )

        kind = self._router_kind(chain_id)
        if kind == "v3_02":
            return (
                "0x"
                + V3_02_EXACT_INPUT_SINGLE_SELECTOR
                + _encode_address(leg.token_in)
                + _encode_address(leg.token_out)
                + _encode_uint(leg.pool.fee)
                + _encode_address(recipient)
                + _encode_uint(amount_in)
                + _encode_uint(min_output)
                + _encode_uint(0)
            )
        return (
            "0x"
            + V3_EXACT_INPUT_SINGLE_SELECTOR
            + _encode_address(leg.token_in)
            + _encode_address(leg.token_out)
            + _encode_uint(leg.pool.fee)
            + _encode_address(recipient)
            + _encode_uint(deadline)
            + _encode_uint(amount_in)
            + _encode_uint(min_output)
            + _encode_uint(0)
        )

    def _execution_min_output(self, params: dict[str, Any], route: Route) -> int:
        requested_min = int(params.get("min_output_amount") or 0)
        quoted_output = int(params.get("quoted_output") or 0)
        if quoted_output > 0:
            quote_floor = _apply_bps(quoted_output, min(9900, route.confidence_bps))
            if requested_min <= 0:
                return quote_floor
            return min(requested_min, quote_floor)
        if requested_min > 0:
            return requested_min
        return _apply_bps(route.estimated_output, min(9900, route.confidence_bps))

    def _fallback_plan(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        snapshot: MarketSnapshot | None,
        params: dict[str, Any],
        reason: str,
    ) -> ExecutionPlan:
        deadline = _deadline(snapshot)
        chain_id = state.chain_id or _snapshot_chain(snapshot)
        token = params.get("input_token") or ZERO_ADDRESS
        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=[
                Interaction(
                    target=token,
                    value="0",
                    call_data=_encode_approve(self._router_for_chain(chain_id), 0),
                    chain_id=chain_id,
                )
            ],
            deadline=deadline,
            nonce=state.nonce,
            metadata={"solver": "top-miner-router", "reason": reason, "chain_id": chain_id},
        )

    def _platform_fee_wei(self, output_amount: int, output_token: str, chain_id: int) -> int:
        # Keep this advisory and small. Binding production fee is recalculated by
        # the API; returning zero avoids fee-token mismatch on non-WETH outputs.
        return 0


def _swap_params(state: IntentState) -> dict[str, Any]:
    typed = getattr(state, "typed_context", None)
    if typed is not None and getattr(typed, "input_token", ""):
        raw = dict(getattr(typed, "raw_params", {}) or {})
        raw.update(
            input_token=getattr(typed, "input_token"),
            output_token=getattr(typed, "output_token"),
            input_amount=str(getattr(typed, "input_amount", 0)),
            min_output_amount=str(getattr(typed, "min_output_amount", 0)),
            receiver=getattr(typed, "receiver", ""),
        )
    else:
        raw = dict(state.raw_params_view())

    input_token = _addr(raw.get("input_token") or raw.get("token_in") or raw.get("from_token") or ZERO_ADDRESS)
    output_token = _addr(raw.get("output_token") or raw.get("token_out") or raw.get("to_token") or ZERO_ADDRESS)
    input_amount = _to_int(raw.get("input_amount") or raw.get("amount_in") or raw.get("amount") or 0)
    min_output = _to_int(raw.get("min_output_amount") or raw.get("min_output") or raw.get("output_amount") or 0)
    return {
        **raw,
        "input_token": input_token,
        "output_token": output_token,
        "input_amount": max(0, input_amount),
        "min_output_amount": max(0, min_output),
        "receiver": raw.get("receiver") or raw.get("recipient") or "",
    }


def _pool_from_snapshot(address: str, raw: dict[str, Any]) -> Pool | None:
    try:
        token0 = _addr(raw.get("token0"))
        token1 = _addr(raw.get("token1"))
        fee = int(raw.get("fee", 3000))
        raw_dex = str(raw.get("dex") or raw.get("protocol") or raw.get("source") or DEX_UNISWAP_V3).lower()
        dex = DEX_AERODROME_SLIPSTREAM if "aerodrome" in raw_dex else DEX_UNISWAP_V3
        tick_spacing = raw.get("tickSpacing") or raw.get("tick_spacing")
        if tick_spacing is None and dex == DEX_AERODROME_SLIPSTREAM:
            tick_spacing = raw.get("spacing") or raw.get("fee")
        sqrt_price = int(raw.get("sqrtPriceX96") or raw.get("sqrt_price_x96") or 0)
        liquidity = int(raw.get("liquidity") or 0)
        if not token0 or not token1 or sqrt_price <= 0:
            return None
        return Pool(
            address=_addr(address),
            token0=token0,
            token1=token1,
            fee=fee,
            sqrt_price_x96=sqrt_price,
            liquidity=max(1, liquidity),
            dex=dex,
            tick_spacing=int(tick_spacing) if tick_spacing is not None else None,
        )
    except Exception:
        return None


def _simulate_route(legs: tuple[Leg, ...], amount_in: int) -> Route | None:
    amount = amount_in
    amounts_out: list[int] = []
    min_conf = 9950
    for leg in legs:
        amount = _pool_output(leg.pool, leg.token_in, leg.token_out, amount)
        if amount <= 0:
            return None
        amounts_out.append(amount)
        liq = max(1, leg.pool.liquidity)
        if amount_in > liq // 25:
            min_conf = min(min_conf, 9700)
        if leg.pool.fee >= 10000:
            min_conf = min(min_conf, 9850)
    if len(legs) > 1:
        min_conf = min(min_conf, 9900)
    return Route(
        legs=legs,
        amount_in=amount_in,
        estimated_output=amount,
        confidence_bps=min_conf,
        amounts_out=tuple(amounts_out),
    )


def _pool_output(pool: Pool, token_in: str, token_out: str, amount_in: int) -> int:
    if amount_in <= 0 or not pool.connects(token_in, token_out):
        return 0
    fee_adj = 1_000_000 - int(pool.fee)
    sqrt = pool.sqrt_price_x96
    if sqrt <= 0:
        return 0

    if token_in.lower() == pool.token0.lower() and token_out.lower() == pool.token1.lower():
        numerator = amount_in * sqrt * sqrt * fee_adj
        return max(0, numerator // Q192 // 1_000_000)
    if token_in.lower() == pool.token1.lower() and token_out.lower() == pool.token0.lower():
        numerator = amount_in * Q192 * fee_adj
        denominator = sqrt * sqrt * 1_000_000
        return max(0, numerator // denominator)
    return 0


def _encode_approve(spender: str, amount: int) -> str:
    return "0x" + ERC20_APPROVE_SELECTOR + _encode_address(spender) + _encode_uint(amount)


def _encode_path(route: Route) -> bytes:
    parts = bytearray()
    parts.extend(bytes.fromhex(_strip_0x(route.legs[0].token_in)))
    for leg in route.legs:
        if leg.pool.dex == DEX_AERODROME_SLIPSTREAM:
            parts.extend(int(leg.pool.tick_spacing or leg.pool.fee).to_bytes(3, "big", signed=True))
        else:
            parts.extend(int(leg.pool.fee).to_bytes(3, "big"))
        parts.extend(bytes.fromhex(_strip_0x(leg.token_out)))
    return bytes(parts)


def _encode_dynamic_tuple(values: list[tuple[str, Any]]) -> str:
    # One dynamic tuple parameter: top-level offset points to the tuple body.
    head_words: list[str] = []
    tails: list[bytes] = []
    static_count = len(values)
    dynamic_offset = 32 * static_count

    for value_type, value in values:
        if value_type == "bytes":
            blob = bytes(value)
            head_words.append(_encode_uint(dynamic_offset))
            padded_len = ((len(blob) + 31) // 32) * 32
            tail = int(len(blob)).to_bytes(32, "big") + blob + (b"\x00" * (padded_len - len(blob)))
            tails.append(tail)
            dynamic_offset += len(tail)
        elif value_type == "address":
            head_words.append(_encode_address(str(value)))
        else:
            head_words.append(_encode_uint(int(value)))

    return _encode_uint(32) + "".join(head_words) + b"".join(tails).hex()


def _encode_address(value: str) -> str:
    raw = _strip_0x(_addr(value))
    return ("0" * 24) + raw.lower()


def _encode_uint(value: int) -> str:
    return int(value).to_bytes(32, "big").hex()


def _encode_int(value: int) -> str:
    value = int(value)
    if value < 0:
        value = (1 << 256) + value
    return value.to_bytes(32, "big").hex()


def _decode_address_word(hex_data: str) -> str:
    raw = _strip_0x(hex_data)
    if len(raw) < 64:
        return ZERO_ADDRESS
    return _addr("0x" + raw[24:64])


def _eth_call(rpc_url: str, to: str, data: str) -> str:
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [{"to": _addr(to), "data": data}, "latest"],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        rpc_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=3) as resp:
        parsed = json.loads(resp.read().decode("utf-8"))
    if parsed.get("error"):
        raise RuntimeError(parsed["error"])
    return parsed.get("result", "0x")


def _route_summary(route: Route) -> str:
    legs = ",".join(f"{leg.pool.dex}:{leg.pool.tick_spacing or leg.pool.fee}" for leg in route.legs)
    return " -> ".join(_short_addr(t) for t in route.tokens) + " / " + legs


def _gas_estimate(route: Route) -> int:
    if route.is_mixed_dex:
        return 110_000 + 115_000 * max(1, route.hops)
    return 95_000 + 75_000 * max(1, route.hops)


def _apply_bps(value: int, bps: int) -> int:
    return max(0, int(value) * int(bps) // 10_000)


def _deadline(snapshot: MarketSnapshot | None) -> int:
    base = int(getattr(snapshot, "timestamp", 0) or time.time())
    return base + 300


def _snapshot_chain(snapshot: MarketSnapshot | None) -> int:
    return int(getattr(snapshot, "chain_id", 1) or 1)


def _wrapped_native(chain_id: int) -> str:
    return CHAIN_CONFIG.get(chain_id, CHAIN_CONFIG[1]).get("tokens", {}).get("WETH", "")


def _addr(value: Any) -> str:
    if not isinstance(value, str):
        return ZERO_ADDRESS
    value = value.strip()
    if not value.startswith("0x"):
        return ZERO_ADDRESS
    raw = value[2:]
    if len(raw) > 40:
        raw = raw[-40:]
    if len(raw) < 40:
        raw = raw.rjust(40, "0")
    try:
        int(raw, 16)
    except ValueError:
        return ZERO_ADDRESS
    return "0x" + raw.lower()


def _strip_0x(value: str) -> str:
    return value[2:] if isinstance(value, str) and value.startswith("0x") else str(value or "")


def _short_addr(value: str) -> str:
    value = _addr(value)
    return value[:6] + "..." + value[-4:]


def _to_int(value: Any) -> int:
    try:
        if isinstance(value, str) and value.startswith("0x"):
            return int(value, 16)
        return int(value)
    except Exception:
        return 0


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


SOLVER_CLASS = TopMinerRouterSolver
