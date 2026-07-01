"""Lean concentrated-liquidity swap IntentSolver for Minotaur (v0.14.0).

Redesigned after the local bench showed that BREADTH is a liability: quoting 10
venues per plan made the solver too slow/flaky on real infra (timeouts, and
flaky quotes -> a suboptimal venue -> the swap reverts "Too little received").
The lean genesis (Uniswap V3 + Aerodrome Slipstream only, ~9 quotes) is fast,
reliable, and wins. So this matches that shape:

  CORE (hot path, parallel, retried): Uniswap V3 (4 fee tiers) + Aerodrome
  Slipstream (5 tickSpacings) — the two deep venues that hold ~all Base
  liquidity. ~9 concurrent quotes, well inside the 30s/intent budget.

  FALLBACK (only when the core finds no pool — a rare illiquid pair): via-WETH
  multi-hop on V3/Slipstream, then a single Uniswap V2 direct check.

Reliability: RPC calls retry (transient resets drop the best venue otherwise),
reads are pinned to one block, and the deadline is derived from block time —
so every validator builds the identical plan. Selection defaults to "relative"
(maximize delivered output — the subnet's incoming per-order adoption rule).

The module MUST export `SOLVER_CLASS`.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_hash.auto import keccak

from minotaur_subnet.sdk.intent_solver import IntentSolver, MarketSnapshot, SolverMetadata
from minotaur_subnet.shared.types import (
    AppIntentDefinition,
    ExecutionPlan,
    Interaction,
    IntentState,
)
from minotaur_subnet.v3.manifest import normalize_swap_intent_params

logger = logging.getLogger(__name__)

# Uniswap V3 (SwapRouter02, no deadline) + QuoterV2.
_V3_QUOTER_BY_CHAIN = {1: "0x61fFE014bA17989E743c5F6cB21bF9697530B21e", 8453: "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a"}
_V3_ROUTER_BY_CHAIN = {1: "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45", 8453: "0x2626664c2603336E57B271c5C0b26F421741e481"}
_V3_FEE_TIERS = [100, 500, 3000, 10000]
# Aerodrome Slipstream (Base) — concentrated, Base's deepest venue. Quoter takes
# int24 tickSpacing (not fee); router exactInputSingle has a deadline.
_SLIP_QUOTER_BY_CHAIN = {8453: "0x254cf9e1e6e233aa1ac962cb9b05b2cfeaae15b0"}
_SLIP_ROUTER_BY_CHAIN = {8453: "0xBE6D8f0d05cC4be24d5167a3eF062215bE6D18a5"}
_SLIP_TICK_SPACINGS = [1, 50, 100, 200, 2000]
# PancakeSwap V3 (Base) — 3rd concentrated venue the champion uses. QuoterV2 is
# Uniswap-identical; the SmartRouter swap is V1-style exactInputSingle w/ deadline.
_PANCAKE_QUOTER_BY_CHAIN = {8453: "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997"}
_PANCAKE_ROUTER_BY_CHAIN = {8453: "0x1b81D678ffb9C0263b24A97847620C99d213eB14"}
_PANCAKE_FEES = [100, 500, 2500, 10000]
# Uniswap V2 — fallback only (illiquid pairs the concentrated venues can't fill).
_V2_ROUTER_BY_CHAIN = {1: "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D", 8453: "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24"}
_V2_FACTORY_BY_CHAIN = {1: "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f", 8453: "0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6"}
_WETH_BY_CHAIN = {1: "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", 8453: "0x4200000000000000000000000000000000000006"}

_QUOTE_WORKERS = 10   # concurrent RPC quotes (core is ~9; one batch)
_CALL_RETRIES = 3     # retry transient RPC errors so the best venue is never dropped
_ZERO_ADDR = "0x0000000000000000000000000000000000000000"

# Score model (only used in "blended" mode). Gas measured on a Base fork.
_GAS_APPROVE, _GAS_V3, _GAS_SLIP, _GAS_EXTRA_HOP = 46_031, 135_367, 183_770, 60_000
_W_OUTPUT, _W_GAS, _W_ROUTE, _GAS_BASELINE, _GAS_BEST = 0.70, 0.20, 0.10, 250_000, 100_000
_DEFAULT_SELECTION_MODE = "relative"


def _selector(sig: str) -> bytes:
    return keccak(sig.encode())[:4]


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _state_params(state: IntentState) -> dict[str, Any]:
    typed = getattr(state, "typed_context", None)
    if typed is not None and isinstance(getattr(typed, "raw_params", None), dict):
        return typed.raw_params
    return state.raw_params_view()


def _pack_path(tokens: list[str], hops: list[int]) -> bytes:
    """token(20) + fee/tickSpacing(3) + ... for V3/Slipstream exactInput paths."""
    out = bytearray()
    for i, t in enumerate(tokens):
        out += bytes.fromhex(t[2:].zfill(40))
        if i < len(hops):
            out += (int(hops[i]) & 0xFFFFFF).to_bytes(3, "big")
    return bytes(out)


def get_amount_out(amount_in: int, reserve_in: int, reserve_out: int) -> int:
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return 0
    a = amount_in * 997
    return (a * reserve_out) // (reserve_in * 1000 + a)


def score_estimate(output: int, ref: int, gas: int, n_interactions: int) -> float:
    base = _W_OUTPUT * 0.6
    if ref > 0:
        out_score = base + _clamp((output - ref) / ref * 100.0 * 0.04, -base, _W_OUTPUT * 0.4)
    else:
        out_score = base
    gas_score = _clamp((_GAS_BASELINE - gas + _GAS_BEST) / _GAS_BASELINE, 0.0, 1.0) * _W_GAS
    route = _W_ROUTE if n_interactions <= 1 else (_W_ROUTE * 0.5 if n_interactions <= 3 else 0.0)
    return out_score + gas_score + route


class LeanConcentratedSolver(IntentSolver):
    """Uniswap V3 + Aerodrome Slipstream, parallel + retried. Lean = fast + robust."""

    def __init__(self) -> None:
        self._chain_ids: list[int] = []
        self._rpc_urls: dict[int, str] = {}
        self._w3_cache: dict[int, Any] = {}
        self._q_cache: dict[tuple, int] = {}     # per-batch quote cache
        self._pair_cache: dict[tuple, str] = {}  # permanent (V2 fallback)
        self._pool_cache: dict[tuple, tuple] = {}
        self._batch_active = False
        self._pin_block: int | None = None
        self._pin_ts: int | None = None
        self._mode = _DEFAULT_SELECTION_MODE

    # 1) setup ----------------------------------------------------------
    def initialize(self, config: dict[str, Any]) -> None:
        self._chain_ids = config.get("chain_ids", [1])
        self._rpc_urls = {int(k): v for k, v in (config.get("rpc_urls") or {}).items()}
        mode = (config.get("selection_mode") or os.environ.get("SOLVER_SELECTION_MODE") or _DEFAULT_SELECTION_MODE)
        self._mode = mode.lower() if mode.lower() in ("relative", "blended") else _DEFAULT_SELECTION_MODE

    def on_benchmark_start(self, intent_count: int) -> None:
        self._q_cache.clear()
        self._pool_cache.clear()
        self._batch_active = True

    def on_benchmark_end(self, results: list[dict]) -> None:
        self.on_benchmark_start(0)
        self._batch_active = False

    # concurrency + RPC -------------------------------------------------
    @staticmethod
    def _pmap(thunks: list) -> list:
        thunks = list(thunks)
        if len(thunks) <= 1:
            return [t() for t in thunks]
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(_QUOTE_WORKERS, len(thunks))) as ex:
            return list(ex.map(lambda t: t(), thunks))

    def _w3(self, chain_id: int):
        if chain_id in self._w3_cache:
            return self._w3_cache[chain_id]
        url = self._rpc_urls.get(chain_id)
        w3 = None
        if url:
            try:
                from web3 import Web3

                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 8}))
            except Exception as exc:
                logger.warning("web3 unavailable for chain %s: %s", chain_id, exc)
        self._w3_cache[chain_id] = w3
        return w3

    def _call(self, w3, to: str, data: bytes) -> bytes | None:
        from web3 import Web3

        tx = {"to": Web3.to_checksum_address(to), "data": "0x" + data.hex()}
        block = self._pin_block if self._pin_block is not None else "latest"
        for attempt in range(_CALL_RETRIES):
            try:
                return w3.eth.call(tx, block_identifier=block)
            except Exception:
                if attempt == _CALL_RETRIES - 1:
                    return None

    def _resolve_pin(self, chain_id: int, snapshot) -> None:
        bn = getattr(snapshot, "block_number", 0) or 0
        ts = getattr(snapshot, "timestamp", 0) or 0
        if bn > 0:
            self._pin_block, self._pin_ts = int(bn), (int(ts) or None)
            return
        w3 = self._w3(chain_id)
        if w3 is not None:
            try:
                self._pin_block = int(w3.eth.block_number)
                try:
                    self._pin_ts = int(w3.eth.get_block(self._pin_block)["timestamp"])
                except Exception:
                    self._pin_ts = None
                return
            except Exception:
                pass
        self._pin_block, self._pin_ts = None, None

    # quoting (cached) --------------------------------------------------
    def _v3_quote(self, w3, chain_id, quoter, ti, to, fee, amt) -> int:
        key = ("v3", chain_id, ti.lower(), to.lower(), fee, amt, self._pin_block)
        if key in self._q_cache:
            return self._q_cache[key]
        data = _selector("quoteExactInputSingle((address,address,uint256,uint24,uint160))") + abi_encode(
            ["(address,address,uint256,uint24,uint160)"], [(ti, to, amt, fee, 0)])
        out = self._call(w3, quoter, data)
        q = int(abi_decode(["uint256", "uint160", "uint32", "uint256"], out)[0]) if out else 0
        if self._batch_active:
            self._q_cache[key] = q
        return q

    def _slip_quote(self, w3, chain_id, quoter, ti, to, ts, amt) -> int:
        key = ("slip", chain_id, ti.lower(), to.lower(), ts, amt, self._pin_block)
        if key in self._q_cache:
            return self._q_cache[key]
        data = _selector("quoteExactInputSingle((address,address,uint256,int24,uint160))") + abi_encode(
            ["(address,address,uint256,int24,uint160)"], [(ti, to, amt, ts, 0)])
        out = self._call(w3, quoter, data)
        q = int(abi_decode(["uint256", "uint160", "uint32", "uint256"], out)[0]) if out else 0
        if self._batch_active:
            self._q_cache[key] = q
        return q

    def _best_v3(self, w3, chain_id, quoter, ti, to, amt) -> tuple[int, int]:
        qs = self._pmap([(lambda f=fee: (f, self._v3_quote(w3, chain_id, quoter, ti, to, f, amt))) for fee in _V3_FEE_TIERS])
        return max(qs, key=lambda fo: fo[1], default=(0, 0))  # (fee, out)

    def _best_slip(self, w3, chain_id, quoter, ti, to, amt) -> tuple[int, int]:
        qs = self._pmap([(lambda t=ts: (t, self._slip_quote(w3, chain_id, quoter, ti, to, t, amt))) for ts in _SLIP_TICK_SPACINGS])
        return max(qs, key=lambda to_: to_[1], default=(0, 0))  # (tickSpacing, out)

    def _pancake_quote(self, w3, chain_id, quoter, ti, to, fee, amt) -> int:
        key = ("pancake", chain_id, ti.lower(), to.lower(), fee, amt, self._pin_block)
        if key in self._q_cache:
            return self._q_cache[key]
        data = _selector("quoteExactInputSingle((address,address,uint256,uint24,uint160))") + abi_encode(
            ["(address,address,uint256,uint24,uint160)"], [(ti, to, amt, fee, 0)])
        out = self._call(w3, quoter, data)
        q = int(abi_decode(["uint256", "uint160", "uint32", "uint256"], out)[0]) if out else 0
        if self._batch_active:
            self._q_cache[key] = q
        return q

    def _best_pancake(self, w3, chain_id, quoter, ti, to, amt) -> tuple[int, int]:
        qs = self._pmap([(lambda f=fee: (f, self._pancake_quote(w3, chain_id, quoter, ti, to, f, amt))) for fee in _PANCAKE_FEES])
        return max(qs, key=lambda fo: fo[1], default=(0, 0))  # (fee, out)

    def _requote(self, w3, chain_id, v, ti, to, amt) -> int:
        """Re-quote one concentrated venue at a partial amount (for split probing)."""
        if v["venue"] == "slip":
            return self._slip_quote(w3, chain_id, v["quoter"], ti, to, v["param"], amt)
        if v["venue"] == "pancake":
            return self._pancake_quote(w3, chain_id, v["quoter"], ti, to, v["param"], amt)
        return self._v3_quote(w3, chain_id, v["quoter"], ti, to, v["param"], amt)

    def _try_cross_venue_split(self, w3, chain_id, conc, ti, to, amt, rcpt, dl):
        """Split across the top-2 concentrated venues if it beats the best single
        route. Champion-style: probe {1/3,1/2,2/3} (6 bounded quotes) only when the
        runner-up is within 2%; emit only on a >5 bps gain. Returns a candidate/None."""
        single_best = max(c["out"] for c in conc)
        if amt < 3 or single_best <= 0:
            return None
        top = sorted(conc, key=lambda c: c["out"], reverse=True)[:2]
        v1, v2 = top
        if v2["out"] < v1["out"] * 0.98:   # runner-up must be genuinely competitive
            return None
        # Only 2 extra quotes (a 50/50 split) — keeps latency inside the budget.
        half = amt // 2
        o1, o2 = self._pmap([
            lambda: self._requote(w3, chain_id, v1, ti, to, half),
            lambda: self._requote(w3, chain_id, v2, ti, to, amt - half),
        ])
        if o1 <= 0 or o2 <= 0 or o1 + o2 < int(single_best * 1.0005):
            return None
        legs = [(v1, half), (v2, amt - half)]
        return dict(venue=f"split:{v1['venue']}+{v2['venue']}", output=o1 + o2, n_inter=4,
                    gas=2 * (_GAS_APPROVE + _GAS_V3),
                    build=lambda: self._build_split(legs, ti, to, rcpt, chain_id, dl))

    # V2 fallback (only when concentrated venues are empty) -------------
    def _v2_direct(self, w3, chain_id, ti, to, amt) -> int:
        factory = _V2_FACTORY_BY_CHAIN.get(chain_id)
        if not factory:
            return 0
        lo, hi = sorted((ti.lower(), to.lower()))
        pk = (chain_id, lo, hi)
        if pk not in self._pair_cache:
            out = self._call(w3, factory, _selector("getPair(address,address)") + abi_encode(["address", "address"], [ti, to]))
            self._pair_cache[pk] = abi_decode(["address"], out)[0] if out else _ZERO_ADDR
        pair = self._pair_cache[pk]
        if pair == _ZERO_ADDR:
            return 0
        t0 = self._call(w3, pair, _selector("token0()"))
        res = self._call(w3, pair, _selector("getReserves()"))
        if not t0 or not res:
            return 0
        token0 = abi_decode(["address"], t0)[0]
        r0, r1, _ = abi_decode(["uint112", "uint112", "uint32"], res)
        rin, rout = (int(r0), int(r1)) if token0.lower() == ti.lower() else (int(r1), int(r0))
        return get_amount_out(amt, rin, rout)

    # plan builders -----------------------------------------------------
    @staticmethod
    def _approve(router, token_in, amount, chain_id):
        data = "0x" + (_selector("approve(address,uint256)") + abi_encode(["address", "uint256"], [router, amount])).hex()
        return Interaction(target=token_in, value="0", call_data=data, chain_id=chain_id)

    @classmethod
    def _build_v3(cls, router, ti, to, fee, amt, min_out, rcpt, chain_id, path=None):
        if path is None:  # single-hop exactInputSingle
            swap = "0x" + (_selector("exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))") + abi_encode(
                ["(address,address,uint24,address,uint256,uint256,uint160)"], [(ti, to, fee, rcpt, amt, min_out, 0)])).hex()
        else:  # multi-hop exactInput(packed path)
            swap = "0x" + (_selector("exactInput((bytes,address,uint256,uint256))") + abi_encode(
                ["(bytes,address,uint256,uint256)"], [(path, rcpt, amt, min_out)])).hex()
        return [cls._approve(router, ti, amt, chain_id), Interaction(target=router, value="0", call_data=swap, chain_id=chain_id)]

    @classmethod
    def _build_slip(cls, router, ti, to, ts, amt, min_out, rcpt, chain_id, dl, path=None):
        if path is None:  # single-hop exactInputSingle (int24 tickSpacing, WITH deadline)
            swap = "0x" + (_selector("exactInputSingle((address,address,int24,address,uint256,uint256,uint256,uint160))") + abi_encode(
                ["(address,address,int24,address,uint256,uint256,uint256,uint160)"], [(ti, to, ts, rcpt, dl, amt, min_out, 0)])).hex()
        else:  # multi-hop exactInput (WITH deadline)
            swap = "0x" + (_selector("exactInput((bytes,address,uint256,uint256,uint256))") + abi_encode(
                ["(bytes,address,uint256,uint256,uint256)"], [(path, rcpt, dl, amt, min_out)])).hex()
        return [cls._approve(router, ti, amt, chain_id), Interaction(target=router, value="0", call_data=swap, chain_id=chain_id)]

    @classmethod
    def _build_pancake(cls, router, ti, to, fee, amt, min_out, rcpt, chain_id, dl):
        # PancakeSwap V3 SmartRouter: V1-style exactInputSingle WITH deadline (0x414bf389).
        swap = "0x" + (bytes.fromhex("414bf389") + abi_encode(
            ["(address,address,uint24,address,uint256,uint256,uint256,uint160)"],
            [(ti, to, fee, rcpt, dl, amt, min_out, 0)])).hex()
        return [cls._approve(router, ti, amt, chain_id), Interaction(target=router, value="0", call_data=swap, chain_id=chain_id)]

    def _build_leg(self, v, ti, to, amt, rcpt, chain_id, dl):
        """One split leg (approve + swap) with amountOutMinimum=0 — the App
        contract enforces the overall min against the summed output."""
        if v["venue"] == "slip":
            return self._build_slip(v["router"], ti, to, v["param"], amt, 0, rcpt, chain_id, dl)
        if v["venue"] == "pancake":
            return self._build_pancake(v["router"], ti, to, v["param"], amt, 0, rcpt, chain_id, dl)
        return self._build_v3(v["router"], ti, to, v["param"], amt, 0, rcpt, chain_id)

    def _build_split(self, legs, ti, to, rcpt, chain_id, dl):
        interactions = []
        for v, amt in legs:
            interactions += self._build_leg(v, ti, to, amt, rcpt, chain_id, dl)
        return interactions

    @classmethod
    def _build_v2(cls, router, ti, to, amt, min_out, rcpt, chain_id, dl):
        swap = "0x" + (_selector("swapExactTokensForTokens(uint256,uint256,address[],address,uint256)") + abi_encode(
            ["uint256", "uint256", "address[]", "address", "uint256"], [amt, min_out, [ti, to], rcpt, dl])).hex()
        return [cls._approve(router, ti, amt, chain_id), Interaction(target=router, value="0", call_data=swap, chain_id=chain_id)]

    # 2) THE competition surface ---------------------------------------
    def generate_plan(self, intent, state, snapshot=None) -> ExecutionPlan | None:
        chain_id = state.chain_id or (self._chain_ids[0] if self._chain_ids else 1)
        v3_router = _V3_ROUTER_BY_CHAIN.get(chain_id)
        v3_quoter = _V3_QUOTER_BY_CHAIN.get(chain_id)
        slip_router = _SLIP_ROUTER_BY_CHAIN.get(chain_id)
        slip_quoter = _SLIP_QUOTER_BY_CHAIN.get(chain_id)
        pancake_router = _PANCAKE_ROUTER_BY_CHAIN.get(chain_id)
        pancake_quoter = _PANCAKE_QUOTER_BY_CHAIN.get(chain_id)
        if not v3_router or not v3_quoter:
            return None

        p = normalize_swap_intent_params(_state_params(state), receiver_default=state.contract_address or state.owner)
        ti, to = p["input_token"], p["output_token"]
        amt, min_out = int(p["input_amount"]), int(p["min_output_amount"])
        if not ti or not to or amt <= 0:
            return None
        rcpt = state.contract_address or state.owner
        weth = _WETH_BY_CHAIN.get(chain_id)
        self._resolve_pin(chain_id, snapshot)
        dl = (self._pin_ts + 300) if self._pin_ts else int(time.time()) + 300
        w3 = self._w3(chain_id)
        if w3 is None:
            return None

        # CORE: V3 + Slipstream + PancakeSwap V3 direct, one concurrent batch
        # (~13 quotes, retried) — the 3 concentrated venues that hold Base liquidity.
        (v3_fee, v3_out), (slip_ts, slip_out), (pk_fee, pk_out) = self._pmap([
            lambda: self._best_v3(w3, chain_id, v3_quoter, ti, to, amt),
            (lambda: self._best_slip(w3, chain_id, slip_quoter, ti, to, amt)) if slip_quoter else (lambda: (0, 0)),
            (lambda: self._best_pancake(w3, chain_id, pancake_quoter, ti, to, amt)) if pancake_quoter else (lambda: (0, 0)),
        ])
        candidates = []
        if v3_out > 0:
            candidates.append(dict(venue="v3", output=v3_out, n_inter=2, gas=_GAS_APPROVE + _GAS_V3,
                                   build=lambda: self._build_v3(v3_router, ti, to, v3_fee, amt, min_out, rcpt, chain_id)))
        if slip_out > 0 and slip_router:
            candidates.append(dict(venue="slip", output=slip_out, n_inter=2, gas=_GAS_APPROVE + _GAS_SLIP,
                                   build=lambda: self._build_slip(slip_router, ti, to, slip_ts, amt, min_out, rcpt, chain_id, dl)))
        if pk_out > 0 and pancake_router:
            candidates.append(dict(venue="pancake", output=pk_out, n_inter=2, gas=_GAS_APPROVE + _GAS_V3,
                                   build=lambda: self._build_pancake(pancake_router, ti, to, pk_fee, amt, min_out, rcpt, chain_id, dl)))

        # CROSS-VENUE SPLIT: on large orders, splitting across the top-2 concentrated
        # venues delivers more than any single route (convex price impact). Bounded,
        # runner-up-gated probe; only added if it beats the best single route.
        conc = []
        if v3_out > 0:
            conc.append({"venue": "v3", "param": v3_fee, "out": v3_out, "router": v3_router, "quoter": v3_quoter})
        if slip_out > 0 and slip_router:
            conc.append({"venue": "slip", "param": slip_ts, "out": slip_out, "router": slip_router, "quoter": slip_quoter})
        if pk_out > 0 and pancake_router:
            conc.append({"venue": "pancake", "param": pk_fee, "out": pk_out, "router": pancake_router, "quoter": pancake_quoter})
        if len(conc) >= 2:
            split = self._try_cross_venue_split(w3, chain_id, conc, ti, to, amt, rcpt, dl)
            if split:
                candidates.append(split)

        # FALLBACK (rare): concentrated multi-hop via WETH, then a V2 direct check.
        if not candidates and weth and weth.lower() not in (ti.lower(), to.lower()):
            (f1, w3out), (s1, sw_out) = self._pmap([
                lambda: self._best_v3(w3, chain_id, v3_quoter, ti, weth, amt),
                (lambda: self._best_slip(w3, chain_id, slip_quoter, ti, weth, amt)) if slip_quoter else (lambda: (0, 0)),
            ])
            if w3out > 0:  # V3 IN->WETH->OUT
                f2, out2 = self._best_v3(w3, chain_id, v3_quoter, weth, to, w3out)
                if out2 > 0:
                    path = _pack_path([ti, weth, to], [f1, f2])
                    candidates.append(dict(venue="v3-mh", output=out2, n_inter=2, gas=_GAS_APPROVE + _GAS_V3 + _GAS_EXTRA_HOP,
                                           build=lambda: self._build_v3(v3_router, ti, to, 0, amt, min_out, rcpt, chain_id, path=path)))
            if sw_out > 0 and slip_router:  # Slipstream IN->WETH->OUT
                s2, sout2 = self._best_slip(w3, chain_id, slip_quoter, weth, to, sw_out)
                if sout2 > 0:
                    path = _pack_path([ti, weth, to], [s1, s2])
                    candidates.append(dict(venue="slip-mh", output=sout2, n_inter=2, gas=_GAS_APPROVE + _GAS_SLIP + _GAS_EXTRA_HOP,
                                           build=lambda: self._build_slip(slip_router, ti, to, 0, amt, min_out, rcpt, chain_id, dl, path=path)))
        if not candidates:
            v2_out = self._v2_direct(w3, chain_id, ti, to, amt)
            v2_router = _V2_ROUTER_BY_CHAIN.get(chain_id)
            if v2_out > 0 and v2_router:
                candidates.append(dict(venue="v2", output=v2_out, n_inter=2, gas=_GAS_APPROVE + _GAS_V3,
                                       build=lambda: self._build_v2(v2_router, ti, to, amt, min_out, rcpt, chain_id, dl)))
        if not candidates:
            return None

        # SELECT — relative: max delivered output (never forfeit an order); break
        # exact ties toward fewer interactions / less gas. blended: old score.
        ref = max(c["output"] for c in candidates)
        for c in candidates:
            c["score"] = score_estimate(c["output"], ref, c["gas"], c["n_inter"])
        if self._mode == "blended":
            winner = max(candidates, key=lambda c: (c["score"], c["output"]))
        else:
            winner = max(candidates, key=lambda c: (c["output"], -c["n_inter"], -c["gas"]))

        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=winner["build"](),
            deadline=dl,
            nonce=state.nonce,
            metadata={
                "venue": winner["venue"], "min_out": min_out, "mode": self._mode,
                "pin_block": self._pin_block, "deadline": dl,
                "candidates": [{"venue": c["venue"], "output": c["output"], "score": round(c["score"], 4)} for c in candidates],
            },
        )

    # 3) identity -------------------------------------------------------
    def metadata(self) -> SolverMetadata:
        return SolverMetadata(
            name="uniswap-v2-solver",
            version="0.16.0",
            author="your-name",
            description=f"Lean concentrated solver ({self._mode}): Uniswap V3 + Aerodrome Slipstream + PancakeSwap V3 + cross-venue split, parallel+retried",
            supported_chains=self._chain_ids or [1, 8453],
            supported_intent_types=["swap"],
        )


SOLVER_CLASS = LeanConcentratedSolver
