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
import time as _time

logger = logging.getLogger(__name__)
_MIN_BUDGET_S = 8.0
_CALL_TIMEOUT_S = 4.0          # hard cap per RPC (sim or multicall); on timeout -> defer
_RUN_RPC_BUDGET_S = 45.0       # total RPC seconds this cover may spend across the run
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
           "0xdAC17F958D2ee523a2206206994597C13D831ec7"), True),
    8453:("0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a", "0x2626664c2603336E57B271c5C0b26F421741e481",
          ("0x4200000000000000000000000000000000000006", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"), False),
}
_MC3 = "0xcA11bde05977b3631167028862bE2a173976CA11"
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

    def _best_route(w3, quoter, tin, tout, amt, hubs):
        paths = [_pd(tin, f, tout) for f in _FEES]
        for hub in hubs:
            if hub.lower() in (tin.lower(), tout.lower()):
                continue
            paths += [_p2(tin, fa, hub, tout, fb) for fa in _FEES for fb in _FEES]
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

    class BlindfillCoverSolver(base_cls):
        """Champion + general Uni blind-fill where the champion delivers nothing (drop-safe)."""

        def _blindfill_serve(self, w3, cfg, intent, state, snapshot, p, tin, tout, amt, cid):
            """Build a best-Uni-route plan for (tin,tout,amt); None if no live route."""
            quoter, router, hubs, needs_dl = cfg
            out, path = _timed(_best_route, w3, quoter, _ck(tin), _ck(tout), amt, [_ck(h) for h in hubs])
            if not out or out <= 0 or path is None:
                return None
            recipient = self._apex_recipient(state, p)
            deadline = int(self._apex_deadline(snapshot))
            if needs_dl:   # original SwapRouter (ETH): exactInput struct includes deadline
                cd = encode_exact_input(path=path, recipient=_ck(recipient), deadline=deadline,
                                        amount_in=amt, amount_out_minimum=0)
            else:          # SwapRouter02 (Base): 4-field exactInput, no deadline
                cd = "0x" + (_EISEL + _e(["(bytes,address,uint256,uint256)"],
                                         [(path, _ck(recipient), int(amt), 0)])).hex()
            ix = [Interaction(target=_ck(tin), value="0", call_data=encode_approve(_ck(router), amt), chain_id=cid),
                  Interaction(target=_ck(router), value="0", call_data=cd, chain_id=cid)]
            logger.info("[blindfill] champion=0, serving Uni route out=%d %s->%s", out, tin[:10], tout[:10])
            return ExecutionPlan(intent_id=intent.app_id, interactions=ix, deadline=deadline,
                                 nonce=state.nonce, metadata={"solver": "blindfill", "chain_id": cid})

        def generate_plan(self, intent, state, snapshot=None):
            base = super().generate_plan(intent, state, snapshot)
            try:
                if cover_state.disabled("blindfill") or _EXEC is None:
                    return base
                if _RPC_SPENT[0] >= _RUN_RPC_BUDGET_S:
                    return base                                  # run RPC budget spent -> passthrough
                cid = int(getattr(state, "chain_id", 0) or 0)
                cfg = _CFG.get(cid)
                if cfg is None or float(getattr(self, "_dyn_order_budget", None) or 99.0) < _MIN_BUDGET_S:
                    return base
                p = self._normalized_swap_params(intent, state)
                tin = str(p.get("input_token", "") or "").lower()
                tout = str(p.get("output_token", "") or "").lower()
                amt = int(p.get("input_amount", 0) or 0)
                app = getattr(state, "contract_address", "") or ""
                if amt <= 0 or not tin or not tout or tin == tout or not app:
                    return base
                w3 = self._get_web3(cid)
                if w3 is None:
                    return base
                base_ix = getattr(base, "interactions", None) if base is not None else None
                if not base_ix:
                    # (1) champion returned an EMPTY plan -> no sim needed, serve live Uni floor.
                    served = self._blindfill_serve(w3, cfg, intent, state, snapshot, p, tin, tout, amt, cid)
                    return served if served is not None else base
                # (2) champion returned a NON-EMPTY plan -> sim it; only fire if it delivers 0.
                f = _timed(viking_sim.sim_floor, w3, base, tin, tout, amt, app)
                if f is None or f > 0:
                    return base                                  # delivers / unverifiable / timed-out -> defer
                served = self._blindfill_serve(w3, cfg, intent, state, snapshot, p, tin, tout, amt, cid)
                return served if served is not None else base
            except Exception:
                logger.exception("[blindfill] cover failed; deferring to champion")
            return base

    return BlindfillCoverSolver
