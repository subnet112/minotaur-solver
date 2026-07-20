"""Polar-Bear-Router — a fill-only-empty cover on the certified champion base.

Layering: the full certified champion stack runs first (imported from
``_champion_base``). This delta serves its OWN plan ONLY when the champion stack
returns EMPTY on an order, then attempts a lean, CHAIN-CORRECT best-of-fee-tiers
Uniswap V3 fill. Because it fires only on a champion-empty result, it can only lift
a champion-0 to a delivery — it never regresses or drops a champion-served order.

Thesis: the champion's own skip-fill helpers (``_McSolver``/``_py_improve``) are
pinned to BASE addresses (``_MC_QUOTER``/``_MC_ROUTER`` = Base), so on **Ethereum**
its multicall cover mis-targets and some ETH orders fall through EMPTY. This delta
uses the correct QuoterV2 + SwapRouter per chain, so it can cover those.
"""
from __future__ import annotations

import logging

from _champion_base import SOLVER_CLASS as _Base
from minotaur_subnet.shared.types import ExecutionPlan, Interaction

logger = logging.getLogger(__name__)

_BRAND = "Polar-Bear-Router"
_AUTHOR = "wisedev0103"

# Chain-correct Uniswap V3 infrastructure (QuoterV2 + SwapRouter). encode_exact_
# input_single auto-selects V1 (Ethereum, with deadline) vs V2 (Base) by chain_id.
_QUOTER = {
    1: "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",     # Ethereum QuoterV2
    8453: "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",  # Base QuoterV2
}
_ROUTER = {
    1: "0xE592427A0AEce92De3Edee1F18E0157C05861564",     # Ethereum SwapRouter (V1)
    8453: "0x2626664c2603336E57B271c5C0b26F421741e481",  # Base SwapRouter02 (V2)
}
_FEES = (100, 500, 3000, 10000)


class PolarBearRouter(_Base):
    """Champion stack + a chain-correct fill-only-empty cover delta."""

    def metadata(self):
        m = super().metadata()
        try:
            import dataclasses
            if dataclasses.is_dataclass(m):
                return dataclasses.replace(m, name=_BRAND, author=_AUTHOR)
        except Exception:
            pass
        rep = getattr(m, "_replace", None)
        if callable(rep):
            try:
                return rep(name=_BRAND, author=_AUTHOR)
            except Exception:
                pass
        try:
            m.name = _BRAND
        except Exception:
            pass
        return m

    # ── cover helpers ────────────────────────────────────────────────────────
    def _pbr_params(self, intent, state):
        try:
            norm = getattr(self, "_normalized_swap_params", None)
            p = norm(intent, state) if callable(norm) else {}
            if not p:
                p = dict(getattr(state, "raw_params", None) or {})
            tin = str(p.get("input_token", "") or "")
            tout = str(p.get("output_token", "") or "")
            amt = int(p.get("input_amount", 0) or 0)
            mino = int(p.get("min_output_amount", 0) or 0)
            if amt <= 0 or not tin or not tout or tin.lower() == tout.lower():
                return None
            return p, tin, tout, amt, mino
        except Exception:
            return None

    def _pbr_w3(self, cid):
        try:
            gw = getattr(self, "_get_web3", None)
            return gw(cid) if callable(gw) else None
        except Exception:
            return None

    def _pbr_best_quote(self, w3, cid, tin, tout, amt):
        """Best QuoterV2 exactInputSingle output across fee tiers, or (0, None)."""
        from eth_utils import to_checksum_address as _ck
        quoter = _ck(_QUOTER[cid])
        best, best_fee = 0, None
        for fee in _FEES:
            try:
                data = ("0xc6a5026a"
                        + tin[2:].rjust(64, "0").lower()
                        + tout[2:].rjust(64, "0").lower()
                        + format(int(amt), "064x")
                        + format(int(fee), "064x")
                        + format(0, "064x"))
                res = w3.eth.call({"to": quoter, "data": data})
                b = bytes(res)
                if len(b) >= 32:
                    out = int.from_bytes(b[:32], "big")
                    if out > best:
                        best, best_fee = out, fee
            except Exception:
                continue
        return best, best_fee

    def _pbr_recipient(self, state, p):
        try:
            ar = getattr(self, "_apex_recipient", None)
            r = ar(state, p) if callable(ar) else ""
        except Exception:
            r = ""
        if not r:
            r = (str(p.get("receiver", "") or "")
                 or getattr(state, "contract_address", "")
                 or getattr(state, "owner", ""))
        return r

    def _pbr_deadline(self, snapshot):
        try:
            ad = getattr(self, "_apex_deadline", None)
            if callable(ad):
                return int(ad(snapshot))
        except Exception:
            pass
        return 9999999999

    def _pbr_cover(self, intent, state, snapshot):
        pp = self._pbr_params(intent, state)
        if pp is None:
            return None
        p, tin, tout, amt, mino = pp
        cid = int(getattr(state, "chain_id", 0) or 0)
        if cid not in _QUOTER:
            return None
        w3 = self._pbr_w3(cid)
        if w3 is None:
            return None
        best, best_fee = self._pbr_best_quote(w3, cid, tin, tout, amt)
        if best_fee is None or best <= 0 or best < mino:
            return None
        recip = self._pbr_recipient(state, p)
        if not recip:
            return None
        deadline = self._pbr_deadline(snapshot)
        from eth_utils import to_checksum_address as _ck
        from common.abi_utils import encode_approve
        from strategies.dex_aggregator.v3_codec import encode_exact_input_single
        router = _ck(_ROUTER[cid])
        approve = encode_approve(router, int(amt))
        swap = encode_exact_input_single(
            _ck(tin), _ck(tout), int(best_fee), _ck(recip), deadline,
            int(amt), int(mino), 0, cid,
        )
        ix = [
            Interaction(target=_ck(tin), value="0", call_data=approve, chain_id=cid),
            Interaction(target=router, value="0", call_data=swap, chain_id=cid),
        ]
        return ExecutionPlan(
            intent_id=intent.app_id, interactions=ix, deadline=deadline,
            nonce=state.nonce, metadata={"solver": "polar-bear-cover", "chain_id": cid},
        )

    def generate_plan(self, intent, state, snapshot=None):
        base = super().generate_plan(intent, state, snapshot)
        if base is not None and getattr(base, "interactions", None):
            return base  # champion served it — never touch (no regression)
        try:
            cover = self._pbr_cover(intent, state, snapshot)
            if cover is not None and getattr(cover, "interactions", None):
                logger.warning("[polar-bear] covered a champion-empty order")
                return cover
        except Exception:
            logger.exception("[polar-bear] cover failed")
        return base


SOLVER_CLASS = PolarBearRouter
