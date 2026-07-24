"""twohop_cover — veto-safe cover for the champion's MISSING Uni V3 2-hop fee combos.

The champion's _UNI_TWOHOP_FEES quotes 12 of the 16 fee-pairs; it never tries
(500,3000), (3000,500), (3000,3000), (10000,10000). This cover quotes ONLY those
4 missing combos (across the standard hubs, in parallel so it's cheap), builds
the exactInput plan with the champion's own v3_codec, and serves it ONLY when it
strictly out-delivers the champion's plan (viking_sim.sim_floor on both). So it
can only win where the order's optimal 2-hop uses a fee-pair the champion can't
produce — never a regression. NARROW edge (audit-rated low), zero risk.
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)
_MARGIN_BPS = 10
_MIN_BUDGET_S = 8.0
_MISSING = ((500, 3000), (3000, 500), (3000, 3000), (10000, 10000))   # combos the champion skips

# (quoter QuoterV2, SwapRouter02, hub tokens) per chain
_CFG = {
    1: ("0x61fFE014bA17989E743c5F6cB21bF9697530B21e",
        "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
        ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
         "0xdAC17F958D2ee523a2206206994597C13D831ec7", "0x6B175474E89094C44Da98b954EedeAC495271d0F",
         "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599")),
    8453: ("0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",
           "0x2626664c2603336E57B271c5C0b26F421741e481",
           ("0x4200000000000000000000000000000000000006", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA", "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb",
            "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf", "0x940181a94A35A4569E4529A3CDfB74e38FD98631")),
}


def wrap(base_cls):
    from mv_venue import _v3_path, _v3_quote_at
    from strategies.dex_aggregator.v3_codec import encode_exact_input
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import ExecutionPlan, Interaction
    import viking_sim
    import cover_state

    class TwoHopCoverSolver(base_cls):
        """Champion + the 4 missing Uni V3 2-hop fee combos, sim-gated (fail-closed)."""

        def _best_missing_2hop(self, w3, quoter, tin, tout, amt, block, hubs):
            jobs = [(hub, fa, fb) for hub in hubs if hub.lower() not in (tin, tout)
                    for (fa, fb) in _MISSING]
            best = (0, None)
            try:
                from concurrent.futures import ThreadPoolExecutor
                paths = [_v3_path(tin, fa, hub, tout, fb) for (hub, fa, fb) in jobs]
                with ThreadPoolExecutor(max_workers=8) as ex:
                    for path, out in zip(paths, ex.map(lambda pp: _v3_quote_at(w3, quoter, pp, amt, block), paths)):
                        if out > best[0]:
                            best = (out, path)
            except Exception:
                logger.exception("[2hop] quote sweep failed")
            return best

        def generate_plan(self, intent, state, snapshot=None):
            base = super().generate_plan(intent, state, snapshot)
            try:
                if cover_state.disabled("twohop"):
                    return base
                cid = int(getattr(state, "chain_id", 0) or 0)
                cfg = _CFG.get(cid)
                if cfg is None:
                    return base
                if float(getattr(self, "_dyn_order_budget", None) or 99.0) < _MIN_BUDGET_S:
                    return base
                quoter, router, hubs = cfg
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
                block = getattr(snapshot, "block_number", None) if snapshot else None
                try:
                    block = int(block) if block else "latest"
                except Exception:
                    block = "latest"
                from eth_utils import to_checksum_address as _ck
                out, path = self._best_missing_2hop(w3, quoter, _ck(tin), _ck(tout), amt, block, [_ck(h) for h in hubs])
                if path is None or out <= 0:
                    return base
                recipient = self._apex_recipient(state, p)
                deadline = int(self._apex_deadline(snapshot))
                cd = encode_exact_input(path=path, recipient=_ck(recipient), deadline=deadline,
                                        amount_in=amt, amount_out_minimum=0)
                ix = [Interaction(target=_ck(tin), value="0", call_data=encode_approve(_ck(router), amt), chain_id=cid),
                      Interaction(target=_ck(router), value="0", call_data=cd, chain_id=cid)]
                cand = ExecutionPlan(intent_id=intent.app_id, interactions=ix, deadline=deadline,
                                     nonce=state.nonce, metadata={"solver": "2hop-cover", "chain_id": cid})
                champ_out = viking_sim.sim_floor(w3, base, tin, tout, amt, app)
                cand_out = viking_sim.sim_floor(w3, cand, tin, tout, amt, app)
                if champ_out is None or cand_out is None:
                    return base
                if cand_out > champ_out * (1 + cover_state.margin_bps(_MARGIN_BPS) / 10000):
                    logger.info("[2hop] cover WIN champ=%d cand=%d %s->%s", champ_out, cand_out, tin[:10], tout[:10])
                    return cand
            except Exception:
                logger.exception("[2hop] cover failed; deferring to champion")
            return base

    return TwoHopCoverSolver
