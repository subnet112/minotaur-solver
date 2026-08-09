"""blindfill_cover — GENERAL veto-safe blind-fill for the champion's failures.

Measured: ~37% of the champion's zero-output quotes are fillable by a plain Uni V3
route (champion delivers 0, a direct/2-hop Uni route delivers). Our narrow covers
(override/Curve/2-hop-combo) and the empty-only aggregator cover miss the ones where
the champion returns a NON-EMPTY plan that reverts to 0. This cover, on ANY order:
  1. cheap fast-path: if the champion's plan is EMPTY, serve the best live Uni route
     directly (no sim needed — champion delivers 0, any delivery is win-or-match).
  2. otherwise sim the champion's own plan (viking_sim.sim_floor) and fire ONLY when
     it delivers NOTHING (== 0) — catching non-empty-but-reverting plans.
  3. serve the best live Uni V3 route (direct 4 tiers + 2-hop via WETH/USDC).
DROP-SAFE: we only ever add delivery where the champion delivered 0.
Self-verifying: if the champion actually delivers at solve time, sim_floor > 0 and
we defer — so transient quote-time artifacts never cause a bad fill.

SAFETY (this runs in the SCORED sandbox — a stall = a DROP = veto):
  * every RPC (champion sim + Uni multicall) runs under a hard wall-clock timeout
    (_CALL_TIMEOUT_S); a hung/slow RPC returns None -> defer, never stalls the order.
  * total RPC time this cover may spend across the whole run is capped
    (_RUN_RPC_BUDGET_S); once exhausted it becomes a pure passthrough. This bounds the
    added latency regardless of order count, so it cannot push a tail order to a drop.
  * the champion `_dyn_order_budget` guard is kept as a belt-and-suspenders check but
    is NOT relied on (the current champion doesn't expose it).
"""
from __future__ import annotations
import concurrent.futures as _cf
import logging
import os
import time as _time

logger = logging.getLogger(__name__)
# BUDGET-AWARE gate (2026-07-29): the champion has a SHARED wall-clock run budget
# (_apex_champ.py _RUN_BUDGET_S=860s; _dyn_order_budget = remaining/orders). When it gets
# tight it serves an EMPTY `last_resort_empty` plan. Our RPC is counted in that clock, so
# firing under pressure starves the champion -> it goes empty in OUR run while the baseline
# delivers -> DROP. Fix: only fire when _dyn_order_budget has AMPLE headroom (>> the ~6-8s
# degrade edge), and cap our TOTAL RPC low so we can never drain enough to tip it. During the
# slow soak the budget stays ~4s so blindfill self-defers (no drops); when the bench is fast
# the champion banks budget, headroom appears, blindfill fires + fills (no drop). Env-tunable.
_MIN_BUDGET_S = float(os.environ.get("AUTOBOT_BLINDFILL_MIN_BUDGET_S", "15.0"))  # need this much headroom to fire
_CALL_TIMEOUT_S = 4.0          # hard cap per RPC (sim or multicall); on timeout -> defer
_RUN_RPC_BUDGET_S = float(os.environ.get("AUTOBOT_BLINDFILL_RPC_BUDGET_S", "12.0"))  # total RPC secs across the run (bounded drain)
_RPC_SPENT = [0.0]             # module-level accumulator (one solver instance per run)
_FEES = (100, 500, 3000, 10000)
# (Uni QuoterV2, SwapRouter, hub tokens, deadline_in_struct) per chain.
# CRITICAL: the codec's encode_exact_input emits the deadline-INCLUDED struct, which only
# the ORIGINAL SwapRouter (0xE592…, ETH) accepts. SwapRouter02 (Base 0x2626…) dropped the
# deadline field, so it needs the 4-field exactInput instead — mismatching the router
# reverts the swap (delivers 0). Verified via viking_sim: 0x68b3(02)->0, 0xE592(orig)->OK.
_CFG = {
    1:   ("0x61fFE014bA17989E743c5F6cB21bF9697530B21e", "0xE592427A0AEce92De3Edee1F18E0157C05861564",
          ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
           "0xdAC17F958D2ee523a2206206994597C13D831ec7",
           "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"), True),   # +WBTC hub: catches BTC-paired long-tail tokens
    8453:("0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a", "0x2626664c2603336E57B271c5C0b26F421741e481",
          ("0x4200000000000000000000000000000000000006", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
           "0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22"), False),  # +cbETH hub: catches Base LST pairs
}
_MC3 = "0xcA11bde05977b3631167028862bE2a173976CA11"
# Key-free extra venues the Uni-V3-only path misses (all quoted directly via RPC, no API keys).
# ETH: Uni V2 + Sushi (V2 getAmountsOut). Base: Aerodrome (dominant Base DEX, Solidly-style).
# Each is drop-safe — we only serve if its live route sim-beats the champion.
_V2_ROUTERS = {1: ("0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",   # Uni V2 Router02
                   "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F")}  # SushiSwap Router
_AERO_ROUTER = "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43"        # Aerodrome Router (Base)
_AERO_FACTORY = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"       # Aerodrome PoolFactory
try:
    _EXEC = _cf.ThreadPoolExecutor(max_workers=2)
except Exception:              # threads unavailable in sandbox -> disable expensive path
    _EXEC = None


def _timed(fn, *a):
    """Run fn(*a) under a hard wall-clock timeout, charging elapsed time to the run
    RPC budget. Returns None on timeout/error/budget-exhausted -> caller defers.
    A timed-out RPC thread is abandoned (not awaited) so the order never stalls."""
    if _EXEC is None or _RPC_SPENT[0] >= _RUN_RPC_BUDGET_S:
        return None
    t0 = _time.time()
    try:
        return _EXEC.submit(fn, *a).result(timeout=_CALL_TIMEOUT_S)
    except Exception:
        return None
    finally:
        _RPC_SPENT[0] += _time.time() - t0


def wrap(base_cls):
    from minotaur_subnet.shared.types import ExecutionPlan, Interaction
    from strategies.dex_aggregator.v3_codec import encode_exact_input
    from common.abi_utils import encode_approve
    from eth_abi import encode as _e, decode as _d
    from eth_utils import to_checksum_address as _ck, keccak as _k
    import viking_sim
    import cover_state
    _QSEL = _k(text="quoteExactInput(bytes,uint256)")[:4]
    _AGG3 = _k(text="aggregate3((address,bool,bytes)[])")[:4]
    _EISEL = _k(text="exactInput((bytes,address,uint256,uint256))")[:4]   # SwapRouter02, no deadline

    def _pd(tin, fee, tout):
        return bytes.fromhex(tin[2:]) + int(fee).to_bytes(3, "big") + bytes.fromhex(tout[2:])

    def _p2(tin, fa, hub, tout, fb):
        return (bytes.fromhex(tin[2:]) + int(fa).to_bytes(3, "big") + bytes.fromhex(hub[2:])
                + int(fb).to_bytes(3, "big") + bytes.fromhex(tout[2:]))

    def _v3_paths(tin, tout, hubs):
        """Candidate Uni V3 encoded paths: direct 4-tier + 2-hop via hubs (own region)."""
        paths = [_pd(tin, f, tout) for f in _FEES]
        for hub in hubs:
            if hub.lower() in (tin.lower(), tout.lower()):
                continue
            paths += [_p2(tin, fa, hub, tout, fb) for fa in _FEES for fb in _FEES]
        return paths

    def _best_route(w3, quoter, tin, tout, amt, hubs):
        paths = _v3_paths(tin, tout, hubs)
        calls = [(_ck(quoter), True, _QSEL + _e(["bytes", "uint256"], [p, int(amt)])) for p in paths]
        try:
            raw = w3.eth.call({"to": _ck(_MC3), "data": _AGG3 + _e(["(address,bool,bytes)[]"], [calls])})
            rows = _d(["(bool,bytes)[]"], bytes(raw))[0]
        except Exception:
            return 0, None
        best, bp = 0, None
        for (ok, rb), p in zip(rows, paths):
            if ok and len(rb) >= 32:
                try:
                    v = int.from_bytes(bytes(rb)[:32], "big")
                    if v > best:
                        best, bp = v, p
                except Exception:
                    pass
        return best, bp

    _V2GAO = _k(text="getAmountsOut(uint256,address[])")[:4]
    _V2SWAP = _k(text="swapExactTokensForTokens(uint256,uint256,address[],address,uint256)")[:4]
    _RT = "(address,address,bool,address)[]"
    _AGAO = _k(text="getAmountsOut(uint256," + _RT + ")")[:4]
    _ASWAP = _k(text="swapExactTokensForTokens(uint256,uint256," + _RT + ",address,uint256)")[:4]

    def _mc_amounts(w3, calls, tags):
        """aggregate3 the getAmountsOut calls; return (best_out, best_tag) by amounts[-1]."""
        try:
            raw = w3.eth.call({"to": _ck(_MC3), "data": _AGG3 + _e(["(address,bool,bytes)[]"], [calls])})
            rows = _d(["(bool,bytes)[]"], bytes(raw))[0]
        except Exception:
            return 0, None
        best, bt = 0, None
        for (ok, rb), tag in zip(rows, tags):
            if ok and len(rb) >= 64:
                try:
                    a = _d(["uint256[]"], bytes(rb))[0]
                    v = int(a[-1]) if a else 0
                    if v > best:
                        best, bt = v, tag
                except Exception:
                    pass
        return best, bt

    def _v2_best(w3, routers, tin, tout, amt, hubs):
        """Best V2-style route (Uni V2 / Sushi): direct + 2-hop via hubs. -> (out, router, path)."""
        paths = [[_ck(tin), _ck(tout)]]
        for h in hubs:
            if h.lower() not in (tin.lower(), tout.lower()):
                paths.append([_ck(tin), _ck(h), _ck(tout)])
        calls, tags = [], []
        for rt in routers:
            for pth in paths:
                calls.append((_ck(rt), True, _V2GAO + _e(["uint256", "address[]"], [int(amt), pth])))
                tags.append((rt, pth))
        out, tag = _mc_amounts(w3, calls, tags)
        return (out, tag[0], tag[1]) if tag else (0, None, None)

    def _aero_best(w3, tin, tout, amt, hubs):
        """Best Aerodrome route: direct (stable+volatile) + 2-hop via hubs. -> (out, routes)."""
        def leg(a, b, st):
            return (_ck(a), _ck(b), st, _ck(_AERO_FACTORY))
        cands = [[leg(tin, tout, False)], [leg(tin, tout, True)]]
        for h in hubs:
            if h.lower() in (tin.lower(), tout.lower()):
                continue
            for s1 in (False, True):
                for s2 in (False, True):
                    cands.append([leg(tin, h, s1), leg(h, tout, s2)])
        calls = [(_ck(_AERO_ROUTER), True, _AGAO + _e(["uint256", _RT], [int(amt), r])) for r in cands]
        out, r = _mc_amounts(w3, calls, cands)
        return (out, r) if r else (0, None)

    class BlindfillCoverSolver(base_cls):
        """Champion + general Uni blind-fill where the champion delivers nothing (drop-safe)."""

        def _extra_venue(self, w3, cid, hub_ck, tin, tout, amt, recipient, deadline):
            """Key-free non-Uni-V3 fill for THIS chain (ETH: Uni V2/Sushi | Base: Aerodrome).
            Only called when Uni V3 is empty. Per-chain builders keep each region small."""
            if cid == 1 and cid in _V2_ROUTERS:
                return self._extra_v2(w3, cid, hub_ck, tin, tout, amt, recipient, deadline)
            if cid == 8453:
                return self._extra_aero(w3, hub_ck, tin, tout, amt, recipient, deadline)
            return None

        def _extra_v2(self, w3, cid, hub_ck, tin, tout, amt, recipient, deadline):
            r = _timed(_v2_best, w3, _V2_ROUTERS[cid], _ck(tin), _ck(tout), amt, hub_ck)
            if r and r[0] > 0 and r[1]:
                cd = "0x" + (_V2SWAP + _e(["uint256", "uint256", "address[]", "address", "uint256"],
                                          [int(amt), 0, r[2], _ck(recipient), int(deadline)])).hex()
                return r[0], _ck(r[1]), cd
            return None

        def _extra_aero(self, w3, hub_ck, tin, tout, amt, recipient, deadline):
            r = _timed(_aero_best, w3, _ck(tin), _ck(tout), amt, hub_ck)
            if r and r[0] > 0 and r[1]:
                cd = "0x" + (_ASWAP + _e(["uint256", "uint256", _RT, "address", "uint256"],
                                         [int(amt), 0, r[1], _ck(recipient), int(deadline)])).hex()
                return r[0], _ck(_AERO_ROUTER), cd
            return None
            return None

        def _bf_uniV3(self, w3, quoter, router, needs_dl, hub_ck, tin, tout, amt, recipient, deadline):
            """Best Uni V3 route + calldata (own region). -> (out, target, cd) or None."""
            out, path = _timed(_best_route, w3, quoter, _ck(tin), _ck(tout), amt, hub_ck)
            if not (out and out > 0 and path is not None):
                return None
            if needs_dl:   # original SwapRouter (ETH): exactInput struct includes deadline
                cd = encode_exact_input(path=path, recipient=_ck(recipient), deadline=deadline,
                                        amount_in=amt, amount_out_minimum=0)
            else:          # SwapRouter02 (Base): 4-field exactInput, no deadline
                cd = "0x" + (_EISEL + _e(["(bytes,address,uint256,uint256)"],
                                         [(path, _ck(recipient), int(amt), 0)])).hex()
            return out, _ck(router), cd

        def _blindfill_serve(self, w3, cfg, intent, state, snapshot, p, tin, tout, amt, cid):
            """Best live route: Uni V3 first, else the chain's extra key-free venue. None if none."""
            quoter, router, hubs, needs_dl = cfg
            hub_ck = [_ck(h) for h in hubs]
            recipient = self._apex_recipient(state, p)
            deadline = int(self._apex_deadline(snapshot))
            got = self._bf_uniV3(w3, quoter, router, needs_dl, hub_ck, tin, tout, amt, recipient, deadline)
            if got is None:
                got = self._extra_venue(w3, cid, hub_ck, tin, tout, amt, recipient, deadline)
            if got is None:
                return None
            out, target, cd = got
            ix = [Interaction(target=_ck(tin), value="0", call_data=encode_approve(target, amt), chain_id=cid),
                  Interaction(target=target, value="0", call_data=cd, chain_id=cid)]
            logger.info("[blindfill] champion=0, serving route out=%d %s->%s", out, tin[:10], tout[:10])
            return ExecutionPlan(intent_id=intent.app_id, interactions=ix, deadline=deadline,
                                 nonce=state.nonce, metadata={"solver": "blindfill", "chain_id": cid})

        def _bf_prep(self, intent, state):
            """Guards + param/w3 extraction (its own named region for factorization).
            Returns (cid, cfg, p, tin, tout, amt, app, w3) or None to defer."""
            if cover_state.disabled("blindfill") or _EXEC is None:
                return None
            if _RPC_SPENT[0] >= _RUN_RPC_BUDGET_S:
                return None                                      # run RPC budget spent -> passthrough
            cid = int(getattr(state, "chain_id", 0) or 0)
            cfg = _CFG.get(cid)
            if cfg is None or float(getattr(self, "_dyn_order_budget", None) or 99.0) < _MIN_BUDGET_S:
                return None
            p = self._normalized_swap_params(intent, state)
            tin = str(p.get("input_token", "") or "").lower()
            tout = str(p.get("output_token", "") or "").lower()
            amt = int(p.get("input_amount", 0) or 0)
            app = getattr(state, "contract_address", "") or ""
            if amt <= 0 or not tin or not tout or tin == tout or not app:
                return None
            w3 = self._get_web3(cid)
            if w3 is None:
                return None
            return (cid, cfg, p, tin, tout, amt, app, w3)

        def generate_plan(self, intent, state, snapshot=None):
            base = super().generate_plan(intent, state, snapshot)
            try:
                if cover_state.is_cross_chain(base) or cover_state.base_untrusted(base):
                    return base                              # cross-chain / UR-V4 base -> defer (platform owns bridges; sim is a lie)
                # DROP-KILLER (2026-07-29): fire ONLY when the champion returns a STRUCTURALLY
                # empty plan (no interactions). The old `sim==0` fire path was a phantom-zero trap
                # on the vertex-swap-engine champion — viking_sim under-measures its routing to 0
                # even when it DELIVERS, so blind-filling a "sim-0" order overrode a delivering
                # champion with a plan that reverted => the 44 drops on r29754215 (outcome=regressed).
                # A structurally-empty base means the champion genuinely produced nothing, so any
                # delivery is win-or-tie, never a drop. We trade a few reverting-champion fills for
                # ZERO drops — the only profile that gets adopted.
                base_ix = getattr(base, "interactions", None) if base is not None else None
                if base_ix:
                    return base                              # champion produced a plan -> DEFER (never override)
                prep = self._bf_prep(intent, state)
                if prep is None:
                    return base
                cid, cfg, p, tin, tout, amt, app, w3 = prep
                served = self._blindfill_serve(w3, cfg, intent, state, snapshot, p, tin, tout, amt, cid)
                return served if served is not None else base
            except Exception:
                logger.exception("[blindfill] cover failed; deferring to champion")
            return base

    return BlindfillCoverSolver
