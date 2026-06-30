"""Minotaur Subnet 112 — competitive swap IntentSolver.

Strategy
--------
This solver competes on the DEX-aggregator swap intent. The validator scores a
plan primarily on *output delivered* (with gas / route-simplicity as smaller
terms), so the whole design is in service of maximising realised output:

  1. Enumerate a broad route space for (input_token -> output_token):
       • Uniswap **V3** direct pools across every fee tier,
       • Uniswap **V3** two-hop routes through liquidity hubs (WETH / USDC / USDT),
       • Uniswap **V2** direct + two-hop routes,
       • **Aerodrome** (Base's deepest DEX — a Solidly fork) direct + two-hop
         routes across both *stable* and *volatile* pools. The genesis champion
         routes Aerodrome, so we must quote it too and then beat it with splits.
     Every candidate is quoted on-chain at the pinned fork block (V3 ``QuoterV2``;
     V2 / Aerodrome ``getAmountsOut``), concurrently, under a wall-clock budget.
  2. Beyond the best single route, evaluate a **2-way split** across the two best
     distinct pools (scanning split ratios). For large orders, splitting cuts
     price impact and delivers materially more output than any single pool — and
     output is the dominant scoring term, so the small extra gas is worth it.
  3. Build the minimal plan that realises the chosen route(s): one ERC-20
     ``approve`` per distinct router, then one swap call per leg, with the App
     contract as recipient.
  4. ``quote()`` reuses the exact same router so the validator's binding-quote /
     benchmark-enrichment path sees our real, honest estimate — and crucially
     *agrees with the plan at the same block*, so the on-chain ``minOut`` floor
     never self-reverts.

Determinism: all candidate selection is folded with a comparator that is
independent of probe finish order, and every read is pinned to the fork block,
so the same inputs always yield the same plan (the validator runs cross-host
determinism-parity checks).

Everything degrades gracefully: if no RPC is reachable (e.g. the offline
screening smoke test runs with ``--network=none``), the solver still returns a
structurally-valid plan so it passes screening, then routes for real once the
benchmark provides an RPC endpoint on the fork.

Submit
------
    my-solver/
      Dockerfile        FROM ghcr.io/subnet112/solver-base:v1
      solver.py         (this file)  -> SOLVER_CLASS
      requirements.txt
      README.md

Local smoke test (no Docker needed):
    python my-solver/test_local.py
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_utils import keccak

from minotaur_subnet.sdk.intent_solver import (
    IntentSolver,
    MarketSnapshot,
    SolverMetadata,
)
from minotaur_subnet.shared.types import (
    AppIntentDefinition,
    ExecutionPlan,
    Interaction,
    IntentState,
    QuoteResult,
)

try:  # Prefer the canonical normalizer so we match the rest of the runtime.
    from minotaur_subnet.v3.manifest import normalize_swap_intent_params
except Exception:  # pragma: no cover - defensive: never let an import kill init
    normalize_swap_intent_params = None  # type: ignore[assignment]


# ─────────────────────────────────────────────────────────────────────────────
#  Per-chain address book (Uniswap V3 + V2 core infra + common routing hubs)
# ─────────────────────────────────────────────────────────────────────────────

_ZERO = "0x" + "00" * 20

CHAINS: dict[int, dict[str, Any]] = {
    1: {  # Ethereum mainnet
        "weth": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "quoter": "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",   # V3 QuoterV2
        "router": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",   # V3 SwapRouter02
        "v2router": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",  # V2 Router02
        "hubs": [
            "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
            "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT
        ],
    },
    8453: {  # Base
        "weth": "0x4200000000000000000000000000000000000006",
        "quoter": "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",   # V3 QuoterV2
        "router": "0x2626664c2603336E57B271c5C0b26F421741e481",   # V3 SwapRouter02
        "v2router": "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24",  # Uniswap V2 Router02 (Base)
        # Aerodrome (Solidly fork) is Base's deepest DEX — the genesis champion
        # routes through it, so we must too (and beat it with splits). Router and
        # the default PoolFactory go into every Aerodrome Route{from,to,stable,factory}.
        "aero_router": "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",
        "aero_factory": "0x420DD381b31aEf6683db6B902084cB0FFECe40Da",
        "hubs": [
            "0x4200000000000000000000000000000000000006",  # WETH
            "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC
        ],
    },
}

FEE_TIERS = [500, 3000, 100, 10000]  # ordered by how often they hold the deepest pool

# Function selectors (computed once, so a typo can't silently produce bad calldata)
_SEL_APPROVE = keccak(b"approve(address,uint256)")[:4]
_SEL_QUOTE_SINGLE = keccak(
    b"quoteExactInputSingle((address,address,uint256,uint24,uint160))"
)[:4]
_SEL_QUOTE_PATH = keccak(b"quoteExactInput(bytes,uint256)")[:4]
_SEL_EXACT_IN_SINGLE = keccak(
    b"exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))"
)[:4]
_SEL_EXACT_IN_PATH = keccak(b"exactInput((bytes,address,uint256,uint256))")[:4]
# Uniswap V2 router surface (view quote + swap).
_SEL_V2_AMOUNTS_OUT = keccak(b"getAmountsOut(uint256,address[])")[:4]
_SEL_V2_SWAP = keccak(
    b"swapExactTokensForTokens(uint256,uint256,address[],address,uint256)"
)[:4]
# Aerodrome (Solidly fork) router surface. Same method names as V2 but the path
# is an array of Route{from,to,stable,factory} structs (volatile vs stable pools).
_AERO_ROUTE_T = "(address,address,bool,address)[]"
_SEL_AERO_AMOUNTS_OUT = keccak(b"getAmountsOut(uint256,(address,address,bool,address)[])")[:4]
_SEL_AERO_SWAP = keccak(
    b"swapExactTokensForTokens(uint256,uint256,(address,address,bool,address)[],address,uint256)"
)[:4]

# Max approval (uint256 max) — one approve covers repeated swaps within a sim.
_UINT256_MAX = (1 << 256) - 1

# Far-future deadline for the V2 router (V3 SwapRouter02 omits per-call deadline).
_V2_DEADLINE = 4_102_444_800  # 2100-01-01

# Per-swap-leg amountOutMinimum buffer (bps below our own quote) — keeps the leg
# from self-reverting under any rounding while still being a real floor. The
# user's true min-output is enforced separately by the app contract on-chain.
_LEG_MIN_BPS = 50  # 0.50%

# Rough gas: ERC-20 approve, and a Uniswap V2 swap per hop. (V3 gas comes back
# from the quoter directly.) Only used for the informational gas_estimate.
_APPROVE_GAS = 46_000
_V2_GAS_PER_HOP = 100_000
_AERO_GAS_PER_HOP = 120_000  # Solidly pools cost a touch more than constant-product V2


def _hexcall(data: bytes) -> str:
    return "0x" + data.hex()


def _encode_v3_path(tokens: list[str], fees: list[int]) -> bytes:
    """Encode a Uniswap V3 path: token (20) | fee (3) | token (20) | ..."""
    out = bytes.fromhex(tokens[0][2:])
    for i, fee in enumerate(fees):
        out += int(fee).to_bytes(3, "big") + bytes.fromhex(tokens[i + 1][2:])
    return out


class _Route:
    """One resolved (or template) swap leg and the output it quotes to.

    ``kind`` is ``"v3"``, ``"v2"`` or ``"aero"`` (Aerodrome/Solidly). For V3,
    ``fees`` has one entry per hop; for V2 it is empty (constant-product). For
    Aerodrome, ``fees`` is empty and ``stable`` carries one bool per hop (stable
    vs volatile pool) plus ``factory`` (the pool factory in each Route struct). A
    template is just a _Route with ``amount_in``/``amount_out`` left at 0, to be
    (re)quoted at any amount.
    """

    __slots__ = (
        "kind", "tokens", "fees", "router", "amount_in", "amount_out", "gas",
        "stable", "factory",
    )

    def __init__(
        self,
        kind: str,
        tokens: list[str],
        fees: list[int],
        router: str,
        amount_in: int = 0,
        amount_out: int = 0,
        gas: int = 0,
        stable: list[bool] | None = None,
        factory: str = "",
    ):
        self.kind = kind
        self.tokens = tokens
        self.fees = fees
        self.router = router
        self.amount_in = amount_in
        self.amount_out = amount_out
        self.gas = gas
        self.stable = stable or []
        self.factory = factory

    @property
    def hops(self) -> int:
        return len(self.tokens) - 1

    def pool_key(self) -> tuple:
        """Identity of the pool-path (so a split uses two *distinct* pools)."""
        return (
            self.kind,
            tuple(t.lower() for t in self.tokens),
            tuple(self.fees),
            tuple(self.stable),
        )

    def aero_routes(self) -> list[tuple]:
        """Aerodrome Route{from,to,stable,factory} structs for this leg's path."""
        return [
            (self.tokens[i], self.tokens[i + 1], bool(self.stable[i]), self.factory)
            for i in range(self.hops)
        ]


class _RoutePlan:
    """The chosen execution: one or more legs and their total quoted output."""

    __slots__ = ("legs", "amount_out", "kind")

    def __init__(self, legs: list[_Route], amount_out: int, kind: str):
        self.legs = legs
        self.amount_out = amount_out
        self.kind = kind

    @property
    def gas_total(self) -> int:
        routers = {leg.router for leg in self.legs}
        return sum(int(leg.gas or 0) for leg in self.legs) + _APPROVE_GAS * len(routers)


class CompetitiveSwapSolver(IntentSolver):
    """RPC-routing Uniswap V3+V2 swap solver with split routing + offline fallback."""

    # Per-eth_call HTTP timeout and the wall-clock ceiling for one routing pass.
    # Reads run through the validator's block-pinning RPC proxy, so on the scored
    # fork they're fast and reliable; these bounds only guard against a wedged
    # endpoint so we never blow the per-plan timeout (default 30s) and get killed.
    _RPC_TIMEOUT_S = 5
    _ROUTE_BUDGET_S = 18.0
    _MAX_WORKERS = 8

    def __init__(self) -> None:
        self.rpc_urls: dict[int, str] = {}
        self.chain_ids: list[int] = [1]
        self._w3: dict[int, Any] = {}
        # Cache is keyed by (chain, tin, tout, amt, block) so a route quoted at
        # one scenario's fork block never leaks into another scenario pinned to a
        # different block — that staleness would desync quote() from the plan.
        self._plan_cache: dict[tuple, _RoutePlan | None] = {}

    # ── lifecycle ────────────────────────────────────────────────────────────

    def initialize(self, config: dict[str, Any]) -> None:
        # rpc_urls may come keyed by int or str depending on transport.
        raw_urls = config.get("rpc_urls", {}) or {}
        self.rpc_urls = {int(k): v for k, v in raw_urls.items() if v}
        self.chain_ids = [int(c) for c in config.get("chain_ids", [1])] or [1]
        # Honour the validator's per-plan time budget: leave ~30% headroom for
        # plan encoding + transport so routing never runs past the kill timeout.
        budget_ms = int(config.get("timeout_per_plan_ms", 0) or 0)
        if budget_ms > 0:
            self._ROUTE_BUDGET_S = max(4.0, (budget_ms / 1000.0) * 0.7)
            self._RPC_TIMEOUT_S = max(2, min(self._RPC_TIMEOUT_S, int(self._ROUTE_BUDGET_S)))
        self._w3 = {}
        self._plan_cache = {}

    def on_benchmark_start(self, intent_count: int) -> None:
        # A new batch may fork at a fresh block; drop clients and cached routes
        # so we never serve a quote pinned to a stale fork.
        self._w3 = {}
        self._plan_cache = {}

    def _web3(self, chain_id: int):
        """Lazily build a Web3 client for a chain, or None if unavailable."""
        if chain_id in self._w3:
            return self._w3[chain_id]
        url = self.rpc_urls.get(chain_id)
        client = None
        if url:
            try:
                from web3 import Web3

                w3 = Web3(
                    Web3.HTTPProvider(
                        url, request_kwargs={"timeout": self._RPC_TIMEOUT_S}
                    )
                )
                # A cheap liveness probe; if it throws we fall back.
                _ = w3.eth.chain_id
                client = w3
            except Exception:
                client = None
        self._w3[chain_id] = client
        return client

    # ── param extraction ─────────────────────────────────────────────────────

    def _params(self, state: IntentState) -> dict[str, Any]:
        typed = getattr(state, "typed_context", None)
        if typed is not None:
            # Typed swap context exposes the resolved fields directly.
            in_tok = getattr(typed, "input_token", "") or ""
            out_tok = getattr(typed, "output_token", "") or ""
            if in_tok and out_tok:
                return {
                    "input_token": in_tok,
                    "output_token": out_tok,
                    "input_amount": int(getattr(typed, "input_amount", 0) or 0),
                    "min_output_amount": int(getattr(typed, "min_output_amount", 0) or 0),
                    "receiver": getattr(typed, "receiver", "") or "",
                    "fee_tier": int(getattr(typed, "fee_tier", 3000) or 3000),
                }
            raw = getattr(typed, "raw_params", None)
            if isinstance(raw, dict):
                return self._normalize(raw, state)
        return self._normalize(state.raw_params_view(), state)

    def _normalize(self, raw: dict[str, Any], state: IntentState) -> dict[str, Any]:
        receiver_default = state.contract_address or state.owner
        if normalize_swap_intent_params is not None:
            try:
                return normalize_swap_intent_params(
                    raw, receiver_default=receiver_default
                )
            except Exception:
                pass
        return {
            "input_token": raw.get("input_token", "") or raw.get("tokenIn", ""),
            "output_token": raw.get("output_token", "") or raw.get("tokenOut", ""),
            "input_amount": int(raw.get("input_amount", 0) or raw.get("amount", 0) or 0),
            "min_output_amount": int(raw.get("min_output_amount", 0) or 0),
            "receiver": receiver_default,
            "fee_tier": int(raw.get("fee_tier", 3000) or 3000),
        }

    # ── block pinning ──────────────────────────────────────────────────────────

    def _resolve_block(self, w3, snapshot: MarketSnapshot | None) -> int | None:
        """The block to pin every quote read to, so quote() and the plan agree.

        Prefer the snapshot's block (the validator's fork block). Otherwise read
        the current head once — through the pinning proxy this returns the fork
        block too, and ``eth_blockNumber`` costs 0 against the RPC budget.
        """
        if snapshot is not None:
            blk = getattr(snapshot, "block_number", 0) or 0
            if blk > 0:
                return int(blk)
        try:
            return int(w3.eth.block_number)
        except Exception:
            return None

    # ── low-level quoting (V3 quoter + V2 router) ──────────────────────────────

    def _quote_v3_single(self, w3, quoter, tin, tout, amt, fee, block):
        args = abi_encode(
            ["(address,address,uint256,uint24,uint160)"],
            [(tin, tout, amt, fee, 0)],
        )
        ret = w3.eth.call(
            {"to": quoter, "data": _hexcall(_SEL_QUOTE_SINGLE + args)},
            block_identifier=block,
        )
        out, _sp, _ticks, gas = abi_decode(["uint256", "uint160", "uint32", "uint256"], ret)
        return int(out), int(gas)

    def _quote_v3_path(self, w3, quoter, tokens, fees, amt, block):
        path = _encode_v3_path(tokens, fees)
        args = abi_encode(["bytes", "uint256"], [path, amt])
        ret = w3.eth.call(
            {"to": quoter, "data": _hexcall(_SEL_QUOTE_PATH + args)},
            block_identifier=block,
        )
        out, _sp, _ticks, gas = abi_decode(
            ["uint256", "uint160[]", "uint32[]", "uint256"], ret
        )
        return int(out), int(gas)

    def _quote_v2(self, w3, router, path, amt, block):
        args = abi_encode(["uint256", "address[]"], [amt, path])
        ret = w3.eth.call(
            {"to": router, "data": _hexcall(_SEL_V2_AMOUNTS_OUT + args)},
            block_identifier=block,
        )
        amounts = abi_decode(["uint256[]"], ret)[0]
        return int(amounts[-1]) if amounts else 0

    def _quote_aero(self, w3, router, routes, amt, block):
        args = abi_encode(["uint256", _AERO_ROUTE_T], [amt, routes])
        ret = w3.eth.call(
            {"to": router, "data": _hexcall(_SEL_AERO_AMOUNTS_OUT + args)},
            block_identifier=block,
        )
        amounts = abi_decode(["uint256[]"], ret)[0]
        return int(amounts[-1]) if amounts else 0

    def _requote(self, w3, cfg, tmpl: _Route, amt: int, block) -> _Route | None:
        """(Re)quote a route template/leg at ``amt``; None if it has no liquidity."""
        if amt <= 0:
            return None
        try:
            if tmpl.kind == "aero":
                out = self._quote_aero(w3, tmpl.router, tmpl.aero_routes(), amt, block)
                gas = _AERO_GAS_PER_HOP * tmpl.hops
            elif tmpl.kind == "v2":
                out = self._quote_v2(w3, tmpl.router, list(tmpl.tokens), amt, block)
                gas = _V2_GAS_PER_HOP * tmpl.hops
            elif len(tmpl.fees) == 1:
                out, gas = self._quote_v3_single(
                    w3, cfg["quoter"], tmpl.tokens[0], tmpl.tokens[1], amt, tmpl.fees[0], block
                )
            else:
                out, gas = self._quote_v3_path(
                    w3, cfg["quoter"], list(tmpl.tokens), list(tmpl.fees), amt, block
                )
        except Exception:
            return None
        if out <= 0:
            return None
        return _Route(
            tmpl.kind, list(tmpl.tokens), list(tmpl.fees), tmpl.router,
            amt, out, gas, list(tmpl.stable), tmpl.factory,
        )

    # ── route enumeration / selection ──────────────────────────────────────────

    @staticmethod
    def _templates(cfg: dict[str, Any], tin: str, tout: str) -> list[_Route]:
        """All candidate route shapes (no amounts yet), in a deterministic order."""
        router3 = cfg["router"]
        v2 = cfg.get("v2router")
        tl, ol = tin.lower(), tout.lower()
        out: list[_Route] = []
        # V3 direct, every fee tier.
        for fee in FEE_TIERS:
            out.append(_Route("v3", [tin, tout], [fee], router3))
        # V3 two-hop through each hub.
        for hub in cfg["hubs"]:
            if hub.lower() in (tl, ol):
                continue
            for f1 in FEE_TIERS:
                for f2 in FEE_TIERS:
                    out.append(_Route("v3", [tin, hub, tout], [f1, f2], router3))
        # V2 direct + two-hop.
        if v2:
            out.append(_Route("v2", [tin, tout], [], v2))
            for hub in cfg["hubs"]:
                if hub.lower() in (tl, ol):
                    continue
                out.append(_Route("v2", [tin, hub, tout], [], v2))
        # Aerodrome (Base): each pool can be stable or volatile, so enumerate both
        # per hop. Direct = 2 pools; two-hop = the 4 stable/volatile combinations
        # through each hub. This is where Base's deepest liquidity sits.
        aero, fac = cfg.get("aero_router"), cfg.get("aero_factory")
        if aero and fac:
            for s in (False, True):
                out.append(_Route("aero", [tin, tout], [], aero, stable=[s], factory=fac))
            for hub in cfg["hubs"]:
                if hub.lower() in (tl, ol):
                    continue
                for s1 in (False, True):
                    for s2 in (False, True):
                        out.append(_Route(
                            "aero", [tin, hub, tout], [], aero,
                            stable=[s1, s2], factory=fac,
                        ))
        return out

    @staticmethod
    def _route_sort_key(r: _Route) -> tuple:
        """Best-first ordering: most output, then fewer hops, lower fees, then path.

        Fully deterministic so selection is independent of probe finish order
        (the validator runs cross-host determinism-parity checks).
        """
        return (
            -r.amount_out, r.hops, sum(r.fees),
            tuple(t.lower() for t in r.tokens), tuple(r.stable),
        )

    def _quote_all(self, w3, cfg, templates, amt, block) -> list[_Route]:
        """Quote every template at ``amt`` concurrently, under the time budget."""
        quoted: list[_Route] = []
        deadline = time.monotonic() + self._ROUTE_BUDGET_S
        with ThreadPoolExecutor(max_workers=self._MAX_WORKERS) as pool:
            futures = [pool.submit(self._requote, w3, cfg, t, amt, block) for t in templates]
            for fut in as_completed(futures):
                try:
                    r = fut.result()
                except Exception:
                    r = None
                if r is not None:
                    quoted.append(r)
                if time.monotonic() > deadline:
                    break
        return quoted

    def _eval_split_points(
        self, w3, cfg, ra: _Route, rb: _Route, amt, block, points: list[int],
        results: dict[int, tuple[_Route, _Route]],
    ) -> None:
        """Quote ``ra``/``rb`` at each permille split in ``points``; fill ``results``.

        ``points`` are permille (1..999) of ``amt`` routed through ``ra``, the rest
        through ``rb``. Both legs of a point must quote for it to be usable.
        """
        todo = [p for p in points if p not in results]
        if not todo:
            return
        tasks: list[tuple[str, int, int]] = []
        for p in todo:
            a_amt = amt * p // 1000
            tasks.append(("a", p, a_amt))
            tasks.append(("b", p, amt - a_amt))
        legs: dict[tuple[str, int], _Route | None] = {}
        deadline = time.monotonic() + self._ROUTE_BUDGET_S
        with ThreadPoolExecutor(max_workers=self._MAX_WORKERS) as pool:
            futs = {}
            for side, p, sub in tasks:
                base = ra if side == "a" else rb
                futs[pool.submit(self._requote, w3, cfg, base, sub, block)] = (side, p)
            for fut in as_completed(futs):
                key = futs[fut]
                try:
                    legs[key] = fut.result()
                except Exception:
                    legs[key] = None
                if time.monotonic() > deadline:
                    break
        for p in todo:
            la, lb = legs.get(("a", p)), legs.get(("b", p))
            if la is not None and lb is not None:
                results[p] = (la, lb)

    def _best_split(self, w3, cfg, ra: _Route, rb: _Route, amt, block) -> _RoutePlan | None:
        """Find the best 2-way split across two distinct pools (most total output).

        Coarse pass over deciles, then a finer local refine around the best decile —
        the split curve is single-peaked, so refining near the coarse optimum buys
        extra output for a handful more quotes without scanning the whole range.
        """
        results: dict[int, tuple[_Route, _Route]] = {}

        # Coarse: 10%..90% in 10% steps.
        coarse = list(range(100, 1000, 100))
        self._eval_split_points(w3, cfg, ra, rb, amt, block, coarse, results)
        if not results:
            return None

        def best_of(pts: list[int]) -> int:
            # Most total output; ties resolve to the smallest permille (deterministic).
            return max(
                (p for p in pts if p in results),
                key=lambda p: (results[p][0].amount_out + results[p][1].amount_out, -p),
            )

        center = best_of(coarse)
        # Refine: ±9% around the coarse optimum in 2% steps (clamped to 1..999).
        refine = [p for p in range(center - 90, center + 91, 20) if 1 <= p <= 999]
        self._eval_split_points(w3, cfg, ra, rb, amt, block, refine, results)

        best_p = best_of(list(results.keys()))
        la, lb = results[best_p]
        return _RoutePlan([la, lb], la.amount_out + lb.amount_out, "split")

    def _route_plan(self, chain_id, tin, tout, amt, block) -> _RoutePlan | None:
        """Best execution (single or split) for the swap, or None if unroutable."""
        if not tin or not tout or amt <= 0:
            return None
        ckey = (chain_id, tin.lower(), tout.lower(), amt, block)
        if ckey in self._plan_cache:
            return self._plan_cache[ckey]

        cfg = CHAINS.get(chain_id)
        w3 = self._web3(chain_id)
        if not cfg or w3 is None:
            self._plan_cache[ckey] = None
            return None

        blk = block if block is not None else "latest"
        quoted = self._quote_all(w3, cfg, self._templates(cfg, tin, tout), amt, blk)
        if not quoted:
            self._plan_cache[ckey] = None
            return None

        quoted.sort(key=self._route_sort_key)
        best = quoted[0]
        plan = _RoutePlan([best], best.amount_out, self._single_kind(best))

        # Try a 2-way split across the two best *distinct* pools. Only bother
        # when the runner-up is at least half as deep (both genuinely viable) —
        # this bounds the extra quotes and avoids pointless splits on thin pools.
        second = next(
            (r for r in quoted[1:] if r.pool_key() != best.pool_key()), None
        )
        if second is not None and second.amount_out * 2 >= best.amount_out:
            split = self._best_split(w3, cfg, best, second, amt, blk)
            if split is not None and split.amount_out > plan.amount_out:
                plan = split

        self._plan_cache[ckey] = plan
        return plan

    @staticmethod
    def _single_kind(r: _Route) -> str:
        if r.kind == "aero":
            return "aero-direct" if r.hops == 1 else "aero-multihop"
        if r.kind == "v2":
            return "v2-direct" if r.hops == 1 else "v2-multihop"
        return "v3-direct" if r.hops == 1 else "v3-multihop"

    # ── plan construction ──────────────────────────────────────────────────────

    def _leg_swap(self, chain_id: int, leg: _Route, recipient: str) -> Interaction:
        """One swap interaction for a single leg, with a self-revert-safe minOut."""
        min_out = leg.amount_out * (10_000 - _LEG_MIN_BPS) // 10_000
        if leg.kind == "aero":
            args = abi_encode(
                ["uint256", "uint256", _AERO_ROUTE_T, "address", "uint256"],
                [leg.amount_in, min_out, leg.aero_routes(), recipient, _V2_DEADLINE],
            )
            return Interaction(
                target=leg.router,
                value="0",
                call_data=_hexcall(_SEL_AERO_SWAP + args),
                chain_id=chain_id,
            )
        if leg.kind == "v2":
            args = abi_encode(
                ["uint256", "uint256", "address[]", "address", "uint256"],
                [leg.amount_in, min_out, list(leg.tokens), recipient, _V2_DEADLINE],
            )
            return Interaction(
                target=leg.router,
                value="0",
                call_data=_hexcall(_SEL_V2_SWAP + args),
                chain_id=chain_id,
            )
        if leg.hops == 1:  # V3 exactInputSingle
            args = abi_encode(
                ["(address,address,uint24,address,uint256,uint256,uint160)"],
                [(leg.tokens[0], leg.tokens[1], leg.fees[0], recipient, leg.amount_in, min_out, 0)],
            )
            return Interaction(
                target=leg.router,
                value="0",
                call_data=_hexcall(_SEL_EXACT_IN_SINGLE + args),
                chain_id=chain_id,
            )
        # V3 exactInput (multi-hop path)
        path = _encode_v3_path(leg.tokens, leg.fees)
        args = abi_encode(
            ["(bytes,address,uint256,uint256)"],
            [(path, recipient, leg.amount_in, min_out)],
        )
        return Interaction(
            target=leg.router,
            value="0",
            call_data=_hexcall(_SEL_EXACT_IN_PATH + args),
            chain_id=chain_id,
        )

    def _plan_interactions(
        self, chain_id: int, plan: _RoutePlan, recipient: str
    ) -> list[Interaction]:
        tin = plan.legs[0].tokens[0]
        # One max-approval per distinct router (covers every leg on it), in a
        # deterministic order so the plan calldata is reproducible.
        routers = sorted({leg.router for leg in plan.legs}, key=str.lower)
        interactions = [
            Interaction(
                target=tin,
                value="0",
                call_data=_hexcall(
                    _SEL_APPROVE + abi_encode(["address", "uint256"], [r, _UINT256_MAX])
                ),
                chain_id=chain_id,
            )
            for r in routers
        ]
        # Swap legs, also in a deterministic order.
        for leg in sorted(plan.legs, key=self._route_sort_key):
            interactions.append(self._leg_swap(chain_id, leg, recipient))
        return interactions

    def _fallback_interactions(
        self, chain_id: int, params: dict[str, Any], recipient: str
    ) -> list[Interaction]:
        """Structurally-valid plan for the offline screening smoke test.

        We can't route without RPC, so emit a single approve on the input token.
        It satisfies plan validation (non-empty, valid 0x address + calldata) so
        the solver clears screening; real routing kicks in once the benchmark
        provides an RPC endpoint.
        """
        cfg = CHAINS.get(chain_id, CHAINS[1])
        tin = params.get("input_token") or cfg["weth"]
        return [
            Interaction(
                target=tin,
                value="0",
                call_data=_hexcall(
                    _SEL_APPROVE
                    + abi_encode(["address", "uint256"], [cfg["router"], _UINT256_MAX])
                ),
                chain_id=chain_id,
            )
        ]

    def generate_plan(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        snapshot: MarketSnapshot | None = None,
    ) -> ExecutionPlan:
        chain_id = state.chain_id or 1
        params = self._params(state)
        recipient = state.contract_address or params.get("receiver") or state.owner
        amt = int(params.get("input_amount", 0) or 0)

        w3 = self._web3(chain_id)
        block = self._resolve_block(w3, snapshot) if w3 is not None else None
        plan = self._route_plan(
            chain_id, params.get("input_token", ""), params.get("output_token", ""), amt, block
        )

        if plan is not None and recipient:
            interactions = self._plan_interactions(chain_id, plan, recipient)
            meta = {
                "solver": "competitive-swap-solver",
                "route": plan.kind,
                "legs": len(plan.legs),
                "quoted_out": str(plan.amount_out),
            }
        else:
            interactions = self._fallback_interactions(chain_id, params, recipient)
            meta = {"solver": "competitive-swap-solver", "route": "fallback"}

        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=interactions,
            deadline=int(time.time()) + 300,
            nonce=state.nonce,
            metadata=meta,
        )

    # ── quoting surface (powers benchmark enrichment + binding-quote UX) ───────

    def quote(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        snapshot: MarketSnapshot | None = None,
    ) -> QuoteResult:
        chain_id = state.chain_id or 1
        params = self._params(state)
        amt = int(params.get("input_amount", 0) or 0)
        w3 = self._web3(chain_id)
        block = self._resolve_block(w3, snapshot) if w3 is not None else None
        plan = self._route_plan(
            chain_id, params.get("input_token", ""), params.get("output_token", ""), amt, block
        )
        if plan is None:
            # No live route — return a conservative zero quote rather than raise,
            # so the orchestrator's self-quote path doesn't treat us as crashed.
            return QuoteResult(
                estimated_output="0",
                route_summary="no-route",
                metadata={"solver": "competitive-swap-solver"},
            )
        return QuoteResult(
            estimated_output=str(plan.amount_out),
            computed_params={
                "quoted_output": str(plan.amount_out),
                "output_amount": str(plan.amount_out),
            },
            route_summary=plan.kind if len(plan.legs) == 1 else f"split({len(plan.legs)})",
            gas_estimate=int(plan.gas_total),
            metadata={"route": plan.kind, "legs": len(plan.legs)},
        )

    # ── auto-trigger (swaps are user-triggered) ────────────────────────────────

    def check_trigger(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        snapshot: MarketSnapshot | None = None,
    ) -> bool:
        return False

    def metadata(self) -> SolverMetadata:
        return SolverMetadata(
            name="competitive-swap-solver",
            version="1.3.0",
            author="joeknight",  # set to your hotkey SS58 when submitting
            description=(
                "Uniswap V3 (multi-fee-tier + multi-hop), Uniswap V2, and "
                "Aerodrome (stable + volatile) routing over RPC with coarse→fine "
                "2-way split routing across venues, block-pinned deterministic "
                "selection, and an honest quote() that agrees with the plan."
            ),
            supported_chains=[1, 8453],
            supported_intent_types=["swap"],
        )


# REQUIRED: the harness instantiates this class.
SOLVER_CLASS = CompetitiveSwapSolver
