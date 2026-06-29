"""Minotaur SN112 DEX-aggregator solver — score-aware multi-venue router.

Design (validated on the fork-scoring oracle, run_oracle_delta.py)
------------------------------------------------------------------
Under the live "reference-bar" scoring every challenger is anchored on the
CHAMPION's quote, so for the deep canonical book (USDC<->WETH ~80% of orders)
the output term is PINNED at outputScore≈0.505 for everyone who delivers the
true market output — the champion sandbags its own quote ~1%, so ratio≈1.010
no matter what. That makes:

    finalScore = 0.8*outputScore + 0.2*gasScore

a GAS race on the canonical book, and an OUTPUT race only on the long-tail
(exotic pairs where ratio<1). This solver optimizes the actual finalScore
directly instead of "max output then maybe reroute for gas":

  1. Build the baseline plan (bounded; offline-snapshot fallback if RPC is slow)
     so we always have a valid plan in hand.
  2. SCORE-AWARE SELECTION: exact-quote every single-hop venue for the pair —
     Uniswap V3 (fee tiers 100/500/3000/10000) AND Aerodrome Slipstream
     (tickSpacings 1/50/100/200/2000) — via their on-chain QuoterV2 (output +
     gasEstimate), then pick the route that maximizes a faithful score proxy
        score ~= 0.4*(out/best_out) - 0.2*(model_gas/1e6)
     i.e. take the leaner-gas Uniswap single-hop when it delivers within the
     gas-justified margin of Aerodrome (the canonical-book gas win), and take
     whatever delivers the MOST output when ratio<1 (the long-tail output win,
     output being 4x the gas weight). Always require out >= the order min so the
     swap clears the on-chain veto — never a zero.
  3. The selected single-hop also COVERS the champion's blind spots for free:
     a direct Uniswap WETH/DAI single-hop fills WETH->DAI (which the champion's
     multi-hop reverts on), and a working Uniswap tier fills the tiny WETH->USDC
     case the champion's Aerodrome route reverts on.
  4. Never crash / never return None: a top-level try/except guard on BOTH
     generate_plan and quote (so even an undefined-variable bug — the exact way
     the live king died — degrades to a fallback instead of crashing the
     process), bounded calls under the harness 30s/15s kills, an offline
     snapshot fallback, a best-effort default-fee single-hop, and a final
     structurally-valid empty plan together guarantee 0 crashes and 0 nulls.

No quote sandbagging. ``quote()`` reports the honest baseline estimate (the
old _QUOTE_FACTOR under-report is neutralized by the validator's reference-bar
fix, so it is removed — dead weight and risk).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from strategies.dex_aggregator.baseline_solver import BaselineSwapSolver
from minotaur_subnet.sdk.intent_solver import SolverMetadata
from minotaur_subnet.shared.types import ExecutionPlan, Interaction

logger = logging.getLogger(__name__)

SOLVER_NAME = os.environ.get("MINOTAUR_SOLVER_NAME", "top-miner-router")
SOLVER_VERSION = os.environ.get("MINOTAUR_SOLVER_VERSION", "0.23.0")
SOLVER_AUTHOR = os.environ.get("MINOTAUR_SOLVER_AUTHOR", "Xayaan")

# Base (chain 8453) only — the whole live order book is Base.
_BASE = 8453
_WETH = "0x4200000000000000000000000000000000000006"
_USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
_CBBTC = "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf"
_AERO = "0x940181a94a35a4569e4529a3cdfb74e38fd98631"
_DAI = "0x50c5725949a6f0c72e6c4a641f24049a917db0cb"
_USDBC = "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca"
_ZERO = "0x0000000000000000000000000000000000000000"

# Relative scoring compares raw delivered output, so the incumbent v21
# max-output route is the baseline to preserve. The one narrow extension here is
# fee-aware sizing for WETH-input orders: the benchmark scorer funds exactly
# input_amount of WETH, while the app contract may reserve platform_fee_wei
# before the swap leg. Swapping the full input then leaves no WETH for the
# locked fee and produces a zero on tiny rejected orders. Only WETH-input orders
# with an explicit fee use the net amount; every other order stays incumbent-like.
_GAS_WEIGHT = float(os.environ.get("SOLVER_GAS_WEIGHT", "0.0"))
_NET_WETH_PLATFORM_FEE = os.environ.get("SOLVER_NET_WETH_PLATFORM_FEE", "0").lower() in {"1", "true", "yes"}

# On-chain quoters (view eth_call; never sends a tx).
_UNI_QUOTER = "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a"   # Uniswap V3 QuoterV2
_AERO_QUOTER = "0x254cf9e1e6e233aa1ac962cb9b05b2cfeaae15b0"  # Aerodrome Slipstream Quoter
_AERO_V2_ROUTER = "0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43"  # Aerodrome Router
_UNI_FEES = (100, 500, 3000, 10000)
_UNI_WETH_DAI_PATH_FEES = ((3000, 100), (500, 100), (100, 100), (10000, 100))
_UNI_TWOHOP_FEES = ((500, 500), (100, 100), (500, 100), (100, 500))
_AERO_TICK_SPACINGS = (1, 50, 100, 200, 2000)
_AERO_TWOHOP_TICKS = ((100, 1), (1, 100), (100, 100), (1, 1))

# Score-proxy gas model: actual executeIntent gas ≈ fixed harness/proxy
# overhead (per venue) + the route's tick-crossing cost, which the on-chain
# QuoterV2 returns as ``gasEstimate``. So model_gas = OFFSET[venue] + gas_est.
# Measured floors on the fork: Uniswap single-hop ~385k (OFFSET≈285k + ~100k
# quoter gas), Aerodrome single-hop ~428k (OFFSET≈318k). This makes selection
# (a) prefer the leaner Uniswap venue over Aerodrome unless Aerodrome delivers
# enough more output to fund its extra gas, AND (b) prefer the lower-tick-
# crossing fee tier WITHIN a venue when outputs are close (the 406k-vs-380k gap).
_OFFSET_UNI = int(os.environ.get("SOLVER_OFFSET_UNI", "285000"))
_OFFSET_AERO = int(os.environ.get("SOLVER_OFFSET_AERO", "318000"))
_GAS_MULTIHOP = int(os.environ.get("SOLVER_GAS_MULTIHOP", "490000"))

# Per-eth_call socket timeout so no single RPC can hang the plan.
_RPC_TIMEOUT_S = float(os.environ.get("SOLVER_RPC_TIMEOUT_S", "2.0"))
# Wall-clock bounds. Harness kills generate_plan at 30s and quote at 15s
# (minotaur_subnet.harness.protocol.TIMEOUTS). Every bound below leaves margin
# under those kills so we ALWAYS return a value before the harness aborts us —
# a hard kill is an uncovered zero (the assasin failure mode).
#
#  * quote: 14s lets a legitimate live RPC quote (~10s of Base/Aero pool reads)
#    finish; only a genuinely-overbudget quote is truncated to the offline
#    fallback, and we still return ~1s before the 15s kill.
#  * generate_plan worst case = baseline(14) + select(7) = 21s < 30s. The
#    concurrent quoter enumeration makes the select step ~2-3s in practice.
_QUOTE_BUDGET_S = float(os.environ.get("SOLVER_QUOTE_BUDGET_S", "14.0"))
_BASELINE_BUDGET_S = float(os.environ.get("SOLVER_BASELINE_BUDGET_S", "14.0"))
_SELECT_BUDGET_S = float(os.environ.get("SOLVER_SELECT_BUDGET_S", "10.0"))
# Per-venue quoter eth_calls are fired concurrently; cap the pool so a slow RPC
# can't spawn unbounded threads. 9 venues (4 Uni fee tiers + 5 Aero spacings).
_QUOTER_MAX_WORKERS = int(os.environ.get("SOLVER_QUOTER_MAX_WORKERS", "32"))

# V1/V2 exactInput selectors for the multi-hop SwapRouter02 repair (insurance).
_V1_EXACT_INPUT = "0xc04b8d59"
_V2_EXACT_INPUT = "0xb858183f"


class MinerSolver(BaselineSwapSolver):
    """Baseline routing + score-aware multi-venue single-hop selection."""

    # ── bounded Web3 so no eth_call can hang the plan/quote ──────────────────
    def _get_web3(self, chain_id):  # type: ignore[override]
        cid = int(chain_id)
        if cid in self._web3_cache:
            return self._web3_cache[cid]
        rpc_url = self._rpc_urls.get(cid)
        if not rpc_url:
            return None
        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": _RPC_TIMEOUT_S}))
            if w3.is_connected():
                self._web3_cache[cid] = w3
                return w3
        except Exception:
            logger.warning("[solver] bounded web3 create failed for chain %d", cid, exc_info=True)
        return None

    @staticmethod
    def _bounded_call(fn, args=(), *, timeout):
        """Run ``fn(*args)`` in a daemon thread; return None if it overruns
        ``timeout`` (so the caller falls back) — a hung RPC can never block."""
        import threading
        box: dict[str, Any] = {}

        def _run():
            try:
                box["v"] = fn(*args)
            except Exception:
                logger.exception("[solver] bounded_call raised; -> fallback")
                box["v"] = None

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            logger.warning("[solver] bounded_call timed out (%.1fs) -> fallback", timeout)
            return None
        return box.get("v")

    @staticmethod
    def _effective_swap_amount(params: dict[str, Any], tin: str, amount_in: int) -> int:
        """Amount the router can safely spend after the locked WETH fee.

        The benchmark scorer funds the user with ``input_amount`` of the input
        token. For WETH-input orders the app can reserve ``platform_fee_wei``
        from that same WETH balance before our router leg runs. Spending the
        gross amount then drops the order; spending the net amount can still
        clear the order min and covers the incumbent's tiny-fee blind spots.
        """
        if not _NET_WETH_PLATFORM_FEE or amount_in <= 0 or str(tin).lower() != _WETH:
            return amount_in
        try:
            fee = int(params.get("platform_fee_wei", 0) or 0)
        except (TypeError, ValueError):
            fee = 0
        if fee <= 0:
            return amount_in
        fee_token = str(params.get("platform_fee_token", "") or "").lower()
        if fee_token and fee_token != _WETH:
            return amount_in
        return max(0, amount_in - fee)

    @staticmethod
    def _fee_params(state, params: dict[str, Any]) -> dict[str, Any]:
        """Merge raw state fee fields back into normalized swap params."""
        merged = dict(params or {})
        try:
            raw = state.raw_params_view() if hasattr(state, "raw_params_view") else getattr(state, "raw_params", {})
            if isinstance(raw, dict):
                for key in ("platform_fee_wei", "platform_fee_token"):
                    if key in raw:
                        merged[key] = raw[key]
        except Exception:
            pass
        return merged

    # ── honest quote (bounded + offline fallback; NO sandbag) ────────────────
    def quote(self, intent, state, snapshot=None):  # type: ignore[override]
        """Never raises: every path is guarded so a quote failure degrades to a
        structurally-valid QuoteResult instead of crashing the solver process."""
        from minotaur_subnet.shared.types import QuoteResult
        try:
            def _live():
                return super(MinerSolver, self).quote(intent, state, snapshot)
            q = self._bounded_call(_live, timeout=_QUOTE_BUDGET_S)
            if q is None:
                q = self._offline_fallback_quote(intent, state, snapshot)
            if q is None:
                return QuoteResult(estimated_output="0", route_summary="offline-empty", gas_estimate=0)
            return q
        except Exception:
            logger.exception("[solver] quote top-level guard caught; returning empty quote")
            return QuoteResult(estimated_output="0", route_summary="guard-empty", gas_estimate=0)

    def _offline_fallback_quote(self, intent, state, snapshot):
        """RPC-free honest quote from the snapshot pools (single-tick V3 math)."""
        try:
            from minotaur_subnet.shared.types import QuoteResult
            from strategies.dex_aggregator import pool_math
            params = self._normalized_swap_params(intent, state)
            tin = str(params.get("input_token", "") or "")
            tout = str(params.get("output_token", "") or "")
            amount_in = int(params.get("input_amount", 0) or 0)
            amount_in = self._effective_swap_amount(self._fee_params(state, params), tin, amount_in)
            if not tin or not tout or amount_in <= 0:
                return None
            if tin.startswith("eip155:") or tout.startswith("eip155:"):
                return None
            chain_id = int(state.chain_id or (snapshot.chain_id if snapshot else 0) or 0)
            pool_states = (snapshot.pool_states if snapshot and snapshot.pool_states else {}) or {}
            if not pool_states:
                return None
            try:
                mids = self._intermediaries_for_chain(chain_id) if chain_id else []
            except Exception:
                mids = []
            route = pool_math.find_best_route(pool_states, tin, tout, amount_in, intermediaries=mids)
            if route is None:
                return None
            output_amount, route_desc, hops = route
            if output_amount <= 0:
                return None
            return QuoteResult(
                estimated_output=str(output_amount),
                route_summary=f"{tin[:10]}..->{tout[:10]}.. {route_desc} (offline)",
                gas_estimate=400_000 + 150_000 * len(hops),
                metadata={"hops": len(hops), "data_source": "snapshot-offline"})
        except Exception:
            logger.exception("[solver] offline fallback quote failed")
            return None

    # ── plan: bounded baseline -> score-aware selection -> never-null ────────
    def generate_plan(self, intent, state, snapshot=None):  # type: ignore[override]
        """Top-level crash guard: NOTHING escapes this method. Even an
        undefined-variable / typo bug (the exact way the live king died) is
        caught here and degraded to a best-effort plan rather than a process
        crash + uncovered zero."""
        try:
            plan = self._generate_plan_impl(intent, state, snapshot)
        except Exception:
            logger.exception("[solver] generate_plan top-level guard caught; last-resort plan")
            plan = self._last_resort_plan(intent, state, snapshot)
        return self._slim_plan_metadata(plan, state)

    @staticmethod
    def _slim_plan_metadata(plan, state):
        """Strip the SHIPPED plan's metadata to the functional minimum.

        ``plan.metadata`` is JSON-serialized into the on-chain ``scoreIntent``
        CALLDATA (16 gas per non-zero byte). Our verbose keys
        (``solver``/``route``/``venue_param``/``expected_output``) cost
        ~2.0k gas per swap (MEASURED: 125-byte metadata = +2024 gas vs empty,
        = +0.0004 gasScore js) for ZERO scoring benefit — they are read only
        off the *internal candidate* plans during venue selection
        (``_score_aware_singlehop``), never off the shipped plan. The scorer
        and the simulator's scoreIntent path read output/route/chain from the
        intent_order + interactions, NOT from plan.metadata; the harness even
        re-adds ``chain_id`` itself. We keep ``chain_id`` only (the irreducible
        floor the multichain simulator needs to pick a backend). On-chain
        OUTPUT and validity are unchanged — only calldata bytes shrink."""
        if plan is None:
            return plan
        try:
            old = plan.metadata or {}
            cid = old.get("chain_id")
            if cid is None:
                cid = getattr(state, "chain_id", None)
            if cid is None and getattr(plan, "interactions", None):
                cid = getattr(plan.interactions[0], "chain_id", None)
            plan.metadata = {"chain_id": int(cid)} if cid is not None else {}
        except Exception:
            logger.exception("[solver] metadata slim skipped; leaving plan metadata as-is")
        return plan

    def _generate_plan_impl(self, intent, state, snapshot=None):
        def _baseline():
            return BaselineSwapSolver.generate_plan(self, intent, state, snapshot)
        base_plan = self._bounded_call(_baseline, timeout=_BASELINE_BUDGET_S)
        if base_plan is None:
            base_plan = self._offline_fallback_plan(intent, state, snapshot)

        # The edge: pick the score-optimal single-hop venue (bounded; falls
        # back to base_plan on anything). This both wins the gas race on the
        # canonical book and covers the champion's blind spots. It is also an
        # INDEPENDENT plan source: when the baseline times out/returns None it
        # can still build a fill straight from the live RPC quoters.
        enhanced = self._bounded_call(
            self._score_aware_singlehop, (intent, state, snapshot, base_plan),
            timeout=_SELECT_BUDGET_S)
        plan = enhanced if enhanced is not None else base_plan

        plan = self._fix_multihop_v2(plan)
        if plan is None:
            logger.warning("[solver] no plan from baseline/selection — last-resort plan")
            plan = self._last_resort_plan(intent, state, snapshot)
        return plan

    def _last_resort_plan(self, intent, state, snapshot=None):
        """Best-effort, never-raising plan for when every primary path failed.

        Order: (1) the RPC-free offline snapshot plan, (2) a structurally-valid
        default-fee Uniswap single-hop for the requested pair (may or may not
        fill, but is a real approve+swap — strictly better than an empty plan
        for both screening structure checks and live coverage), (3) a final
        structurally-empty plan only when the pair is genuinely unroutable on
        this chain (e.g. Ethereum-mainnet token addresses on a Base book)."""
        try:
            fb = self._offline_fallback_plan(intent, state, snapshot)
            if fb is not None:
                return fb
        except Exception:
            logger.exception("[solver] last-resort: offline fallback raised")
        try:
            bep = self._best_effort_singlehop_plan(intent, state, snapshot)
            if bep is not None:
                return bep
        except Exception:
            logger.exception("[solver] last-resort: best-effort single-hop raised")
        return self._empty_plan(intent, state)

    def _best_effort_singlehop_plan(self, intent, state, snapshot):
        """Build a default-fee Uniswap V3 approve+exactInputSingle for the pair
        WITHOUT any RPC verification. Returns None if params are unusable
        (missing tokens, non-positive amount, cross-chain eip155 address, or no
        router for the chain)."""
        params = self._normalized_swap_params(intent, state)
        tin = str(params.get("input_token", "") or "")
        tout = str(params.get("output_token", "") or "")
        try:
            amount_in = int(params.get("input_amount", 0) or 0)
            amount_in = self._effective_swap_amount(self._fee_params(state, params), tin, amount_in)
        except (TypeError, ValueError):
            amount_in = 0
        if (not tin or not tout or amount_in <= 0
                or tin.startswith("eip155:") or tout.startswith("eip155:")
                or not tin.startswith("0x") or not tout.startswith("0x")):
            return None
        try:
            chain_id = int(state.chain_id or (snapshot.chain_id if snapshot else 0) or 0)
        except (TypeError, ValueError):
            chain_id = 0
        from strategies.dex_aggregator.swap_solver import UNISWAP_V3_ROUTERS
        from strategies.dex_aggregator.v3_codec import encode_exact_input_single
        from common.abi_utils import encode_approve
        router = UNISWAP_V3_ROUTERS.get(chain_id)
        if not router:
            return None
        recipient = state.contract_address or params.get("receiver") or state.owner
        ts = getattr(snapshot, "timestamp", None) if snapshot else None
        deadline = int(ts or time.time()) + 300
        interactions = [
            Interaction(target=tin, value="0",
                        call_data=encode_approve(router, amount_in), chain_id=chain_id),
            Interaction(target=router, value="0",
                        call_data=encode_exact_input_single(
                            token_in=tin, token_out=tout, fee=3000, recipient=recipient,
                            deadline=deadline, amount_in=amount_in, amount_out_minimum=0,
                            chain_id=chain_id), chain_id=chain_id),
        ]
        return ExecutionPlan(
            intent_id=getattr(intent, "app_id", "") or "", interactions=interactions,
            deadline=deadline, nonce=int(getattr(state, "nonce", 0) or 0),
            metadata={"solver": "best-effort", "route": "uniswap_v3", "fee_tier": 3000,
                      "chain_id": chain_id})

    @staticmethod
    def _empty_plan(intent, state):
        """Structurally-valid (non-null) empty plan — the absolute last resort
        for a genuinely unroutable pair. Never raises."""
        return ExecutionPlan(
            intent_id=getattr(intent, "app_id", "") or "", interactions=[],
            deadline=int(time.time()) + 300, nonce=int(getattr(state, "nonce", 0) or 0),
            metadata={"route": "last_resort_empty"})

    # ── score-aware multi-venue single-hop selection (the edge) ──────────────
    def _enumerate_singlehop_quotes(self, chain_id, tin, tout, amount_in):
        """Exact-quote every single-hop venue CONCURRENTLY. Returns list of
        {venue, param, out, gas_est, gas_model}.

        All 9 quoter eth_calls (4 Uniswap fee tiers + 5 Aerodrome tickSpacings)
        are fired in parallel, each socket-bounded by _get_web3's request
        timeout. Sequential, these would serialize to ~9*2s=18s under a slow
        RPC and blow the select budget (losing the score edge to the timeout);
        fanned out they finish in ~one round-trip, so a transient slow read
        costs at most one venue, not the whole selection. A reverting venue
        (can't fill) returns 0 and is skipped — never raises."""
        w3 = self._get_web3(int(chain_id))
        if w3 is None:
            return []
        import concurrent.futures
        from eth_abi import encode as _enc, decode as _dec
        from eth_utils import keccak as _kk, to_checksum_address as _ck

        uni_sel = _kk(text="quoteExactInputSingle((address,address,uint256,uint24,uint160))")[:4]
        uni_exact_sel = _kk(text="quoteExactInput(bytes,uint256)")[:4]
        aero_sel = _kk(text="quoteExactInputSingle((address,address,uint256,int24,uint160))")[:4]
        aero_v2_sel = _kk(text="getAmountsOut(uint256,(address,address,bool,address)[])")[:4]

        def _uni_path(tokens, fees):
            path = b""
            for i, token in enumerate(tokens):
                addr = str(token)
                path += bytes.fromhex(addr[2:] if addr.startswith("0x") else addr)
                if i < len(fees):
                    path += int(fees[i]).to_bytes(3, byteorder="big")
            return path

        def _aero_path(tokens, tick_spacings):
            path = b""
            for i, token in enumerate(tokens):
                addr = str(token)
                path += bytes.fromhex(addr[2:] if addr.startswith("0x") else addr)
                if i < len(tick_spacings):
                    path += (int(tick_spacings[i]) & 0xFFFFFF).to_bytes(3, byteorder="big")
            return path

        def _quote_uni(fee):
            try:
                p = _enc(["(address,address,uint256,uint24,uint160)"],
                         [(_ck(tin), _ck(tout), int(amount_in), int(fee), 0)])
                r = w3.eth.call({"to": _ck(_UNI_QUOTER), "data": "0x" + (uni_sel + p).hex()})
                out, _a, _t, gas_est = _dec(["uint256", "uint160", "uint32", "uint256"], r)
                if int(out) > 0:
                    return {"venue": "uniswap_v3", "param": int(fee), "out": int(out),
                            "gas_est": int(gas_est), "gas_model": _OFFSET_UNI + int(gas_est)}
            except Exception:
                return None
            return None

        def _quote_aero(ts):
            try:
                p = _enc(["(address,address,uint256,int24,uint160)"],
                         [(_ck(tin), _ck(tout), int(amount_in), int(ts), 0)])
                r = w3.eth.call({"to": _ck(_AERO_QUOTER), "data": "0x" + (aero_sel + p).hex()})
                out, _a, _t, gas_est = _dec(["uint256", "uint160", "uint32", "uint256"], r)
                if int(out) > 0:
                    return {"venue": "aerodrome_slipstream", "param": int(ts), "out": int(out),
                            "gas_est": int(gas_est), "gas_model": _OFFSET_AERO + int(gas_est)}
            except Exception:
                return None
            return None

        def _quote_uni_multihop(route):
            try:
                tokens, fees = route
                path = _uni_path(tokens, fees)
                p = _enc(["bytes", "uint256"], [path, int(amount_in)])
                r = w3.eth.call({"to": _ck(_UNI_QUOTER), "data": "0x" + (uni_exact_sel + p).hex()})
                out, _a, _t, gas_est = _dec(["uint256", "uint160[]", "uint32[]", "uint256"], r)
                if int(out) > 0:
                    return {"venue": "uniswap_v3_multihop", "param": tuple(int(f) for f in fees),
                            "tokens": tuple(tokens), "fees": tuple(int(f) for f in fees),
                            "out": int(out), "gas_est": int(gas_est),
                            "gas_model": _GAS_MULTIHOP + int(gas_est)}
            except Exception:
                return None
            return None

        def _quote_aero_multihop(route):
            try:
                tokens, tick_spacings = route
                path = _aero_path(tokens, tick_spacings)
                p = _enc(["bytes", "uint256"], [path, int(amount_in)])
                r = w3.eth.call({"to": _ck(_AERO_QUOTER), "data": "0x" + (uni_exact_sel + p).hex()})
                out, _a, _t, gas_est = _dec(["uint256", "uint160[]", "uint32[]", "uint256"], r)
                if int(out) > 0:
                    ticks = tuple(int(t) for t in tick_spacings)
                    return {"venue": "aerodrome_slipstream_multihop", "param": ticks,
                            "tokens": tuple(tokens), "tick_spacings": ticks,
                            "out": int(out), "gas_est": int(gas_est),
                            "gas_model": _GAS_MULTIHOP + int(gas_est)}
            except Exception:
                return None
            return None

        def _quote_aero_v2(routes):
            try:
                normalized = [
                    (_ck(a), _ck(b), bool(stable), _ck(factory))
                    for a, b, stable, factory in routes
                ]
                p = _enc(["uint256", "(address,address,bool,address)[]"],
                         [int(amount_in), normalized])
                r = w3.eth.call({"to": _ck(_AERO_V2_ROUTER), "data": "0x" + (aero_v2_sel + p).hex()})
                amounts = _dec(["uint256[]"], r)[0]
                if amounts:
                    out = int(amounts[-1])
                    if out > 0:
                        return {"venue": "aerodrome_v2", "param": tuple(route[2] for route in routes),
                                "routes": routes, "out": out,
                                "gas_est": 145000 * max(1, len(routes)),
                                "gas_model": 350000 + 145000 * max(1, len(routes))}
            except Exception:
                return None
            return None

        def _twohop_mids():
            tin_l, tout_l = str(tin).lower(), str(tout).lower()
            majors = {_WETH, _USDC, _DAI, _CBBTC, _USDBC}
            mids: list[str] = []

            def add(token):
                t = str(token).lower()
                if t not in (tin_l, tout_l) and t not in mids:
                    mids.append(t)

            # Current live gaps are concentrated here: cbBTC gives better
            # WETH/USDC execution at retail+ sizes; USDbC is the deep DAI/USDC
            # bridge; WETH/AERO cover the long-tail Base tokens.
            if {tin_l, tout_l} == {_WETH, _USDC}:
                for token in (_CBBTC, _DAI, _USDBC):
                    add(token)
            if tin_l == _DAI and tout_l == _USDC:
                for token in (_USDBC, _WETH):
                    add(token)
            if tin_l == _CBBTC and tout_l in {_WETH, _USDC}:
                add(_USDC)
                add(_WETH)
            if tin_l == _WETH and tout_l == _DAI:
                for token in (_USDC, _USDBC):
                    add(token)
            if tin_l not in majors or tout_l not in majors:
                for token in (_WETH, _USDC, _AERO, _DAI):
                    add(token)
            if tin_l == _USDC and tout_l in {_DAI, _USDBC, _AERO}:
                for token in (_WETH, _USDBC, _DAI):
                    add(token)
            return mids

        twohop_mids = _twohop_mids()

        core_v2_routes = []
        extra_v2_routes = []
        if not (str(tin).lower() == _WETH and str(tout).lower() == _DAI):
            for stable in (False, True):
                core_v2_routes.append(((tin, tout, stable, _ZERO),))
            for mid in (_WETH, _USDC, _AERO):
                if mid.lower() in (str(tin).lower(), str(tout).lower()):
                    continue
                for stable_a in (False, True):
                    for stable_b in (False, True):
                        core_v2_routes.append(((tin, mid, stable_a, _ZERO), (mid, tout, stable_b, _ZERO)))
            for mid in (_DAI, _USDBC, _CBBTC):
                if mid.lower() in (str(tin).lower(), str(tout).lower()):
                    continue
                for stable_a in (False, True):
                    for stable_b in (False, True):
                        extra_v2_routes.append(((tin, mid, stable_a, _ZERO), (mid, tout, stable_b, _ZERO)))

        core_jobs = (
            [(_quote_uni, f) for f in _UNI_FEES]
            + [(_quote_aero, t) for t in _AERO_TICK_SPACINGS]
            + [(_quote_aero_v2, r) for r in core_v2_routes]
        )
        uni_routes = []
        if str(tin).lower() == _WETH and str(tout).lower() == _DAI:
            uni_routes.extend([((tin, _USDC, tout), fees) for fees in _UNI_WETH_DAI_PATH_FEES])
        for mid in twohop_mids:
            uni_routes.extend([((tin, mid, tout), fees) for fees in _UNI_TWOHOP_FEES])

        aero_routes = []
        for mid in twohop_mids:
            # Slipstream multihop had the best current-preview edges for
            # USDC/WETH via cbBTC and USDC->long-tail via WETH.
            if mid in {_CBBTC, _WETH, _USDC, _AERO}:
                aero_routes.extend([((tin, mid, tout), ticks) for ticks in _AERO_TWOHOP_TICKS])

        extra_jobs = (
            [(_quote_aero_v2, r) for r in extra_v2_routes]
            + [(_quote_uni_multihop, r) for r in uni_routes]
            + [(_quote_aero_multihop, r) for r in aero_routes]
        )

        def _run_jobs(jobs):
            out: list[dict[str, Any]] = []
            if not jobs:
                return out
            workers = max(1, min(_QUOTER_MAX_WORKERS, len(jobs)))
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                    futs = [ex.submit(fn, arg) for fn, arg in jobs]
                    for fu in concurrent.futures.as_completed(futs):
                        try:
                            c = fu.result()
                        except Exception:
                            c = None
                        if c is not None:
                            out.append(c)
            except Exception:
                # Thread-pool/runtime failure: fall back to a sequential sweep so we
                # never lose the candidates entirely.
                logger.exception("[solver] concurrent quoter enumeration failed; sequential fallback")
                for fn, arg in jobs:
                    c = fn(arg)
                    if c is not None:
                        out.append(c)
            return out

        # Preserve incumbent behavior first. Extra probes run afterwards and can
        # only add candidates; transient extra-RPC failures cannot hide the old
        # best direct route.
        cands: list[dict[str, Any]] = _run_jobs(core_jobs)
        if extra_jobs:
            extra_cands = _run_jobs(extra_jobs)
            for cand in extra_cands:
                cand["extra_route"] = True
            cands.extend(extra_cands)
        return cands

    def _score_aware_singlehop(self, intent, state, snapshot, base_plan):
        """Pick the finalScore-optimal single-hop route across Uniswap +
        Aerodrome and build its plan. Falls back to base_plan on anything."""
        try:
            params = self._normalized_swap_params(intent, state)
            tin = str(params.get("input_token", "") or "")
            tout = str(params.get("output_token", "") or "")
            amount_in = int(params.get("input_amount", 0) or 0)
            amount_in = self._effective_swap_amount(self._fee_params(state, params), tin, amount_in)
            min_out = int(params.get("min_output_amount", 0) or 0)
            chain_id = int(state.chain_id or (snapshot.chain_id if snapshot else 0) or 0)
            if chain_id != _BASE or amount_in <= 0 or not tin or not tout:
                return base_plan
            if tin.startswith("eip155:") or tout.startswith("eip155:"):
                return base_plan

            cands = self._enumerate_singlehop_quotes(chain_id, tin, tout, amount_in)
            if not cands:
                return base_plan

            best_out = max(c["out"] for c in cands)
            bp_out = 0
            if base_plan is not None:
                try:
                    bp_out = int((base_plan.metadata or {}).get("expected_output", 0) or 0)
                except (TypeError, ValueError):
                    bp_out = 0
            ref = max(best_out, bp_out, 1)

            def score(out, gas_model):
                return 0.4 * (out / ref) - _GAS_WEIGHT * (gas_model / 1e6)

            # Only consider single-hops that clear the order min — a single-hop
            # below min would revert (e.g. the THIN direct WETH/DAI pool delivers
            # ~150 DAI vs the 354 DAI min, while the real route is the multi-hop
            # WETH->USDC->DAI). If NO single-hop clears the min, keep the baseline
            # plan (its multi-hop route + the V2 calldata fix execute it).
            usable = [c for c in cands if min_out <= 0 or c["out"] >= min_out]
            if not usable:
                return base_plan
            core_usable = [c for c in usable if not c.get("extra_route")]
            if core_usable:
                core_best_out = max(c["out"] for c in core_usable)
                usable = core_usable + [
                    c for c in usable
                    if c.get("extra_route") and c["out"] * 10000 > core_best_out * 10010
                ]
            # Primary key: score proxy; tie-break: lower quoter gasEstimate.
            best = max(usable, key=lambda c: (round(score(c["out"], c["gas_model"]), 9), -c["gas_est"]))
            # Don't regress a baseline route that scores higher — BUT only honor
            # a SINGLE-HOP baseline here. A multi-hop baseline's expected_output
            # is sometimes a phantom route that reverts at execution time.
            if base_plan is not None and bp_out > 0 and (min_out <= 0 or bp_out >= min_out):
                m = (base_plan.metadata or {})
                route = str(m.get("route") or "").lower()
                is_multihop = (("multi" in route) or ("hop" in route)
                               or int(m.get("hops", 1) or 1) > 1)
                if is_multihop and tin.lower() == _WETH and tout.lower() == _DAI:
                    if bp_out >= best["out"]:
                        return base_plan
                if not is_multihop:
                    bp_gas = (_OFFSET_AERO + 110000 if "aero" in route
                              else _OFFSET_UNI + 100000)
                    if score(bp_out, bp_gas) >= score(best["out"], best["gas_model"]):
                        return base_plan

            return self._build_singlehop_plan(
                intent, state, snapshot, best, tin, tout, amount_in, chain_id)
        except Exception:
            logger.exception("[solver] score-aware selection failed; keeping base plan")
            return base_plan

    def _build_singlehop_plan(self, intent, state, snapshot, cand, tin, tout, amount_in, chain_id):
        """Build approve + exactInputSingle for the chosen venue.

        amount_out_minimum is left at 0 on the swap leg (the harness enforces
        the order's min_output invariant at the intent level); the venue was
        already verified to deliver >= min via the quoter, so this only removes
        spurious per-swap slippage reverts."""
        from common.abi_utils import encode_approve
        params = self._normalized_swap_params(intent, state)
        recipient = state.contract_address or params.get("receiver") or state.owner
        ts = getattr(snapshot, "timestamp", None) if snapshot else None
        deadline = int(ts or time.time()) + 300

        if cand["venue"] == "aerodrome_v2":
            from eth_abi import encode as _abi_encode
            from eth_utils import keccak as _keccak, to_checksum_address as _ck
            router = _AERO_V2_ROUTER
            routes = [
                (_ck(a), _ck(b), bool(stable), _ck(factory))
                for a, b, stable, factory in cand.get("routes", ())
            ]
            if not routes:
                raise ValueError("no aerodrome v2 routes")
            selector = _keccak(
                text="swapExactTokensForTokens(uint256,uint256,(address,address,bool,address)[],address,uint256)"
            )[:4]
            call = "0x" + (selector + _abi_encode(
                ["uint256", "uint256", "(address,address,bool,address)[]", "address", "uint256"],
                [int(amount_in), 0, routes, _ck(recipient), int(deadline)],
            )).hex()
            route_tag = "aerodrome_v2"
        elif cand["venue"] == "uniswap_v3_multihop":
            from strategies.dex_aggregator.swap_solver import UNISWAP_V3_ROUTERS
            from strategies.dex_aggregator.v3_codec import encode_exact_input, encode_swap_path
            router = UNISWAP_V3_ROUTERS.get(chain_id)
            if not router:
                raise ValueError("no uniswap router")
            path = encode_swap_path(list(cand["tokens"]), list(cand["fees"]))
            call = encode_exact_input(
                path=path, recipient=recipient, deadline=deadline,
                amount_in=amount_in, amount_out_minimum=0)
            route_tag = "uniswap_v3_multihop"
        elif cand["venue"] == "aerodrome_slipstream":
            from strategies.dex_aggregator import aerodrome as _aero
            router = _aero.AERODROME_SLIPSTREAM_ROUTER.get(chain_id)
            if not router:
                raise ValueError("no aerodrome router")
            call = _aero.encode_exact_input_single(
                token_in=tin, token_out=tout, tick_spacing=int(cand["param"]),
                recipient=recipient, deadline=deadline, amount_in=amount_in,
                amount_out_minimum=0)
            route_tag = "aerodrome_slipstream"
        elif cand["venue"] == "aerodrome_slipstream_multihop":
            from strategies.dex_aggregator import aerodrome as _aero
            router = _aero.AERODROME_SLIPSTREAM_ROUTER.get(chain_id)
            if not router:
                raise ValueError("no aerodrome router")
            path = _aero.encode_path(list(cand["tokens"]), list(cand["tick_spacings"]))
            call = _aero.encode_exact_input(
                path=path, recipient=recipient, deadline=deadline,
                amount_in=amount_in, amount_out_minimum=0)
            route_tag = "aerodrome_slipstream_multihop"
        else:
            from strategies.dex_aggregator.swap_solver import UNISWAP_V3_ROUTERS
            from strategies.dex_aggregator.v3_codec import encode_exact_input_single
            router = UNISWAP_V3_ROUTERS.get(chain_id)
            if not router:
                raise ValueError("no uniswap router")
            call = encode_exact_input_single(
                token_in=tin, token_out=tout, fee=int(cand["param"]), recipient=recipient,
                deadline=deadline, amount_in=amount_in, amount_out_minimum=0, chain_id=chain_id)
            route_tag = "uniswap_v3"

        interactions = [
            Interaction(target=tin, value="0",
                        call_data=encode_approve(router, amount_in), chain_id=chain_id),
            Interaction(target=router, value="0", call_data=call, chain_id=chain_id),
        ]
        logger.info("[solver] score-aware %s param=%s out=%d gas_model=%d",
                    route_tag, cand["param"], cand["out"], cand["gas_model"])
        return ExecutionPlan(
            intent_id=intent.app_id, interactions=interactions, deadline=deadline,
            nonce=state.nonce,
            metadata={"solver": "score-aware-router", "route": route_tag,
                      "venue_param": cand["param"], "expected_output": str(cand["out"]),
                      "chain_id": chain_id})

    # ── offline RPC-free plan (safety net when baseline yields nothing) ──────
    def _offline_fallback_plan(self, intent, state, snapshot):
        try:
            params = self._normalized_swap_params(intent, state)
            tin = str(params.get("input_token", "") or "")
            tout = str(params.get("output_token", "") or "")
            amount_in = int(params.get("input_amount", 0) or 0)
            amount_in = self._effective_swap_amount(self._fee_params(state, params), tin, amount_in)
            if (not tin or not tout or amount_in <= 0
                    or tin.startswith("eip155:") or tout.startswith("eip155:")):
                return None
            chain_id = int(state.chain_id or (snapshot.chain_id if snapshot else 0) or 0)
            from strategies.dex_aggregator.swap_solver import UNISWAP_V3_ROUTERS
            router = UNISWAP_V3_ROUTERS.get(chain_id)
            if not router:
                return None
            pool_states = (snapshot.pool_states if snapshot and snapshot.pool_states else {}) or {}
            a, b = tin.lower(), tout.lower()
            best = None
            for p in pool_states.values():
                if {str(p.get("token0", "")).lower(), str(p.get("token1", "")).lower()} != {a, b}:
                    continue
                dex = str(p.get("dex") or "").lower()
                if dex and "uniswap" not in dex:
                    continue
                liq = int(p.get("liquidity", "0") or 0)
                if liq <= 0:
                    continue
                if best is None or liq > best[0]:
                    best = (liq, int(p.get("fee", 3000) or 3000))
            if best is None:
                return None
            recipient = state.contract_address or params.get("receiver") or state.owner
            ts = getattr(snapshot, "timestamp", None) if snapshot else None
            deadline = int(ts or time.time()) + 300
            from common.abi_utils import encode_approve
            from strategies.dex_aggregator.v3_codec import encode_exact_input_single
            interactions = [
                Interaction(target=tin, value="0",
                            call_data=encode_approve(router, amount_in), chain_id=chain_id),
                Interaction(target=router, value="0",
                            call_data=encode_exact_input_single(
                                token_in=tin, token_out=tout, fee=best[1], recipient=recipient,
                                deadline=deadline, amount_in=amount_in, amount_out_minimum=0,
                                chain_id=chain_id), chain_id=chain_id),
            ]
            return ExecutionPlan(
                intent_id=intent.app_id, interactions=interactions, deadline=deadline,
                nonce=state.nonce,
                metadata={"solver": "offline-fallback", "route": "uniswap_v3", "fee_tier": best[1]})
        except Exception:
            logger.exception("[solver] offline fallback plan failed")
            return None

    # ── multi-hop SwapRouter02 calldata repair (insurance) ───────────────────
    def _fix_multihop_v2(self, plan):
        if plan is None:
            return plan
        try:
            from strategies.dex_aggregator.v3_codec import SWAP_ROUTER_V2_CHAINS
            from strategies.dex_aggregator.swap_solver import UNISWAP_V3_ROUTERS
            from eth_abi import encode as _abi_encode, decode as _abi_decode
        except Exception:
            return plan
        v1 = bytes.fromhex(_V1_EXACT_INPUT[2:])
        v2 = bytes.fromhex(_V2_EXACT_INPUT[2:])
        changed = False
        for ix in (plan.interactions or []):
            try:
                if int(getattr(ix, "chain_id", 0) or 0) not in SWAP_ROUTER_V2_CHAINS:
                    continue
                uni_router = str(UNISWAP_V3_ROUTERS.get(int(ix.chain_id)) or "").lower()
                if uni_router and str(getattr(ix, "target", "") or "").lower() != uni_router:
                    continue
                cd = ix.call_data or ""
                raw = bytes.fromhex(cd[2:] if cd.startswith("0x") else cd)
                if raw[:4] != v1:
                    continue
                path, recipient, _deadline, amt_in, amt_min = _abi_decode(
                    ["(bytes,address,uint256,uint256,uint256)"], raw[4:])[0]
                ix.call_data = "0x" + (v2 + _abi_encode(
                    ["(bytes,address,uint256,uint256)"],
                    [(path, recipient, amt_in, amt_min)])).hex()
                changed = True
            except Exception:
                continue
        if changed:
            logger.info("[solver] multihop fix: rewrote V1 exactInput -> V2 (SwapRouter02)")
        return plan

    def metadata(self) -> SolverMetadata:
        base = super().metadata()
        return SolverMetadata(
            name=SOLVER_NAME, version=SOLVER_VERSION, author=SOLVER_AUTHOR,
            description=("Baseline routing + score-aware multi-venue single-hop "
                         "selection (Uniswap V3 tiers + Aerodrome Slipstream), "
                         "honest quoting, 0-zero coverage"),
            supported_chains=base.supported_chains,
            supported_intent_types=base.supported_intent_types)


SOLVER_CLASS = MinerSolver
