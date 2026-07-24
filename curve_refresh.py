"""curve_refresh — veto-safe LIVE ETH Curve AMOUNT-WIN cover.

Aimed squarely at the current champion (dl_router): it live-requotes ONLY Uniswap V3
on ETH. This cover targets the venue it structurally can't fresh-quote — Curve — and
serves a fresh Curve exchange ONLY when it strictly out-delivers the champion's own
plan by >30bps (matching the champion's own dl_router gate). Wins where the champion
routes a pegged/stable/LST pair via Uni V3 (or a decayed frozen cover) but a fresh
Curve get_dy delivers more.

Improvement over curve_cover (blind-fill only, 10bps): amount-wins at 30bps, with a
FAIL-CLOSED measurement so a mis-measured champion output can't cause a regression:
  * champion plan uses UniversalRouter/V4 (viking under-measures bare)  -> DEFER
  * champion non-empty but sims to 0 (phantom-zero)                     -> DEFER
  * Curve receiver-variant exchange doesn't execute (sims to 0)         -> DEFER
  * Curve not strictly >30bps better than the champion                  -> DEFER
Reuses the champion's own audited mv_venue Curve router + curve_ix plan builder.
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)
_MARGIN_BPS = 30        # match the champion's dl_router >30bps gate
_MIN_BUDGET_S = 8.0     # our find_pools + get_dy + double-sim cost; below this, DEFER
# UniversalRouter/V4 base plans revert/under-pull when viking runs them bare (no proxy/
# Permit2) -> a phantom-low champion output -> false win. If the base uses these, DEFER.
_UNIVERSAL_ROUTERS = {"0x6ff5693b99212da76ad316178a184ab56d299b43"}
_UR_SELECTORS = ("0x3593564c", "0xcac88ea9")


def _base_untrusted(base):
    for ix in (getattr(base, "interactions", None) or []):
        try:
            if str(getattr(ix, "target", "") or "").lower() in _UNIVERSAL_ROUTERS:
                return True
        except Exception:
            pass
        cd = (getattr(ix, "call_data", "") or "").lower()
        if any(cd.startswith(s) for s in _UR_SELECTORS):
            return True
    return False


def wrap(base_cls):
    from mv_venue import _curve_best_live, _curve_ix
    from minotaur_subnet.shared.types import ExecutionPlan
    import viking_sim
    import cover_state

    class CurveRefreshSolver(base_cls):
        """Champion + live ETH-Curve amount-win cover, fail-closed (never regresses)."""

        def generate_plan(self, intent, state, snapshot=None):
            base = super().generate_plan(intent, state, snapshot)
            try:
                if cover_state.disabled("curve_refresh"):
                    return base
                if int(getattr(state, "chain_id", 0) or 0) != 1:          # Curve gap is on ETH
                    return base
                if float(getattr(self, "_dyn_order_budget", None) or 99.0) < _MIN_BUDGET_S:
                    return base
                p = self._normalized_swap_params(intent, state)
                tin = str(p.get("input_token", "") or "").lower()
                tout = str(p.get("output_token", "") or "").lower()
                amt = int(p.get("input_amount", 0) or 0)
                app = getattr(state, "contract_address", "") or ""
                if amt <= 0 or not tin or not tout or tin == tout or not app:
                    return base
                base_ix = getattr(base, "interactions", None) or []
                if base_ix and _base_untrusted(base):
                    return base                                            # unmeasurable champion -> defer
                w3 = self._get_web3(1)
                if w3 is None:
                    return base
                block = getattr(snapshot, "block_number", None) if snapshot else None
                try:
                    block = int(block) if block else "latest"
                except Exception:
                    block = "latest"
                dy, pool, i, j, sig = _curve_best_live(w3, tin, tout, amt, block)
                if pool is None or dy <= 0:
                    return base                                            # no Curve route -> defer
                recipient = self._apex_recipient(state, p)
                w = {"pool": pool, "i": i, "j": j, "ex": ("u256_recv" if sig == "u256" else "i128_recv")}
                cplan = ExecutionPlan(intent_id=intent.app_id, interactions=_curve_ix(w, amt, tin, recipient),
                                      deadline=int(self._apex_deadline(snapshot)), nonce=state.nonce,
                                      metadata={"solver": "curve-refresh", "chain_id": 1})
                curve_out = viking_sim.sim_floor(w3, cplan, tin, tout, amt, app)
                if curve_out is None or curve_out <= 0:
                    return base                                            # Curve didn't execute -> defer
                if not base_ix:
                    co = 0                                                 # champion empty -> blind-fill
                else:
                    co = viking_sim.sim_floor(w3, base, tin, tout, amt, app)
                    if co is None or co <= 0:
                        return base                                        # phantom-zero -> defer
                if curve_out > co * (1 + cover_state.margin_bps(_MARGIN_BPS) / 10000):
                    logger.info("[curve_refresh] WIN champ=%d curve=%d %s->%s amt=%d",
                                co, curve_out, tin[:10], tout[:10], amt)
                    return cplan                                           # strict >30bps win (veto-safe)
            except Exception:
                logger.exception("[curve_refresh] failed; deferring to champion")
            return base

    return CurveRefreshSolver
