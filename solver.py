"""Minotaur SN112 DEX-aggregator solver — king-iris MAX-OUTPUT multi-venue router (v20).

v20 change: the subnet is shipping RELATIVE per-order scoring (#394-#399) that
compares challenger vs champion on RAW DELIVERED OUTPUT (gas term / quote anchor /
clamp all removed), adopting iff no order regresses and >=1 strictly wins. The
incumbent (score-aware-router) DOWN-ROUTES output for gas under the old absolute
scorer — every such trade is a REGRESSION under the relative rule. v20 sets the
venue-selection gas weight to 0 (``SOLVER_GAS_WEIGHT``), so it picks the MAX-OUTPUT
single-hop on every order: it never regresses and strictly out-delivers a
gas-sacrificing champion on every down-routed order -> a clean relative dethrone,
while keeping the exact-quote multi-venue coverage + robustness below. The original
score-aware design notes follow.

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

SOLVER_NAME = os.environ.get("MINOTAUR_SOLVER_NAME", "king-minotaur-solver")
SOLVER_VERSION = os.environ.get("MINOTAUR_SOLVER_VERSION", "21.0.0")
SOLVER_AUTHOR = os.environ.get("MINOTAUR_SOLVER_AUTHOR", "king")

# v20: weight of the gas term in single-hop venue selection. The incumbent
# score-aware build used 0.2 (the live 0.8*output + 0.2*gas absolute scorer),
# which DOWN-ROUTES to a leaner-gas venue even when another venue delivers MORE
# output. The subnet is shipping RELATIVE per-order scoring (#394-#399), which
# compares challenger vs champion on RAW DELIVERED OUTPUT (gas term, quote anchor
# and clamp all removed) and adopts iff NO order regresses and >=1 strictly wins.
# Against that rule, any gas-for-output trade is a REGRESSION. v20 sets the gas
# weight to 0 -> pure MAX OUTPUT on every order: it never regresses and strictly
# out-delivers a gas-sacrificing champion on every down-routed order -> a clean
# relative dethrone. (Set SOLVER_GAS_WEIGHT=0.2 to restore the absolute-regime
# gas-aware behaviour.) Output coverage + robustness layers are unchanged.
_GAS_WEIGHT = float(os.environ.get("SOLVER_GAS_WEIGHT", "0.0"))

# Base (chain 8453) only — the whole live order book is Base.
_BASE = 8453

# On-chain quoters (view eth_call; never sends a tx).
_UNI_QUOTER = "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a"   # Uniswap V3 QuoterV2
_AERO_QUOTER = "0x254cf9e1e6e233aa1ac962cb9b05b2cfeaae15b0"  # Aerodrome Slipstream Quoter
_UNI_FEES = (100, 500, 3000, 10000)
_AERO_TICK_SPACINGS = (1, 50, 100, 200, 2000)

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
_SELECT_BUDGET_S = float(os.environ.get("SOLVER_SELECT_BUDGET_S", "7.0"))
# Per-venue quoter eth_calls are fired concurrently; cap the pool so a slow RPC
# can't spawn unbounded threads. 9 venues (4 Uni fee tiers + 5 Aero spacings).
_QUOTER_MAX_WORKERS = int(os.environ.get("SOLVER_QUOTER_MAX_WORKERS", "9"))

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

    @staticmethod
    def _is_multihop_plan(plan):
        """True if the plan ships a multi-hop exactInput — the route family that
        reverts CallFailed(index=1) on the cbBTC->WETH phantom 2-hop and drops the
        order. Detected by the route metadata (set pre-slim) and, as a backstop,
        the swap selector (0xb858183f / 0xc04b8d59 = exactInput; single-hop
        exactInputSingle is 0x04e45aaf / 0x414bf389 / 0xa026383e)."""
        if plan is None:
            return False
        try:
            m = plan.metadata or {}
            route = str(m.get("route") or "").lower()
            if ("multi" in route) or ("hop" in route) or int(m.get("hops", 1) or 1) > 1:
                return True
            for ix in (getattr(plan, "interactions", None) or []):
                if (ix.call_data or "")[:10].lower() in ("0xb858183f", "0xc04b8d59"):
                    return True
        except Exception:
            return False
        return False

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

        # Robustness net for the select-timeout path: never DEFAULT to an
        # unvalidated multi-hop. When selection timed out (enhanced is None) and
        # the baseline handed us a multi-hop — the cbBTC->WETH phantom "0.00% +
        # 0.01%" 2-hop that reverts CallFailed(index=1) and DROPS the order — make
        # one more bounded attempt at a real single-hop fill (base_plan=None makes
        # _score_aware_singlehop build the max-output single-hop directly). The
        # gas-tilted champion serves this order via single-hop; so can we.
        if enhanced is None and self._is_multihop_plan(plan):
            sh = self._bounded_call(
                self._score_aware_singlehop, (intent, state, snapshot, None),
                timeout=_SELECT_BUDGET_S)
            if sh is not None and not self._is_multihop_plan(sh):
                plan = sh

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
        aero_sel = _kk(text="quoteExactInputSingle((address,address,uint256,int24,uint160))")[:4]

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

        jobs = [(_quote_uni, f) for f in _UNI_FEES] + [(_quote_aero, t) for t in _AERO_TICK_SPACINGS]
        cands: list[dict[str, Any]] = []
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=_QUOTER_MAX_WORKERS) as ex:
                futs = [ex.submit(fn, arg) for fn, arg in jobs]
                for fu in concurrent.futures.as_completed(futs):
                    try:
                        c = fu.result()
                    except Exception:
                        c = None
                    if c is not None:
                        cands.append(c)
        except Exception:
            # Thread-pool/runtime failure: fall back to a sequential sweep so we
            # never lose the candidates entirely.
            logger.exception("[solver] concurrent quoter enumeration failed; sequential fallback")
            for fn, arg in jobs:
                c = fn(arg)
                if c is not None:
                    cands.append(c)
        return cands

    def _score_aware_singlehop(self, intent, state, snapshot, base_plan):
        """Pick the finalScore-optimal single-hop route across Uniswap +
        Aerodrome and build its plan. Falls back to base_plan on anything."""
        try:
            params = self._normalized_swap_params(intent, state)
            tin = str(params.get("input_token", "") or "")
            tout = str(params.get("output_token", "") or "")
            amount_in = int(params.get("input_amount", 0) or 0)
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
                # v20: gas weight defaults to 0 -> pure MAX OUTPUT (relative regime).
                return 0.4 * (out / ref) - _GAS_WEIGHT * (gas_model / 1e6)

            # Only consider single-hops that clear the order min — a single-hop
            # below min would revert (e.g. the THIN direct WETH/DAI pool delivers
            # ~150 DAI vs the 354 DAI min, while the real route is the multi-hop
            # WETH->USDC->DAI). If NO single-hop clears the min, keep the baseline
            # plan (its multi-hop route + the V2 calldata fix execute it).
            usable = [c for c in cands if min_out <= 0 or c["out"] >= min_out]
            if not usable:
                return base_plan
            # Primary key: score proxy; tie-break: lower quoter gasEstimate.
            best = max(usable, key=lambda c: (round(score(c["out"], c["gas_model"]), 9), -c["gas_est"]))

            # Don't regress a baseline route that scores higher — BUT only honor a
            # SINGLE-HOP baseline here. A multi-hop baseline's expected_output is
            # route-math that is frequently a PHANTOM-pool fantasy: e.g. cbBTC->WETH
            # picks a "0.00% + 0.01%" 2-hop quoting 0.527 WETH that reverts
            # CallFailed(index=1) on execution -> delivers 0 -> a DROPPED order the
            # gas-tilted champion fills via a real single-hop (0.3806 WETH). We only
            # reach this line when a usable single-hop CLEARS the order min (the
            # `usable` gate above already ships the baseline when NO single-hop
            # fills — the legit thin-pool multi-hop case), so a real single-hop fill
            # is always in hand. Never trade it for an unvalidated multi-hop's
            # modeled output: under max-output (gas weight 0) the fantasy always
            # "wins" the score proxy and silently drops the order.
            if base_plan is not None and bp_out > 0 and (min_out <= 0 or bp_out >= min_out):
                m = (base_plan.metadata or {})
                route = str(m.get("route") or "").lower()
                is_multihop = (("multi" in route) or ("hop" in route)
                               or int(m.get("hops", 1) or 1) > 1)
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

        if cand["venue"] == "aerodrome_slipstream":
            from strategies.dex_aggregator import aerodrome as _aero
            router = _aero.AERODROME_SLIPSTREAM_ROUTER.get(chain_id)
            if not router:
                raise ValueError("no aerodrome router")
            call = _aero.encode_exact_input_single(
                token_in=tin, token_out=tout, tick_spacing=int(cand["param"]),
                recipient=recipient, deadline=deadline, amount_in=amount_in,
                amount_out_minimum=0)
            route_tag = "aerodrome_slipstream"
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
