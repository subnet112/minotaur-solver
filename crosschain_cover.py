"""crosschain_cover — serve the cross-chain cases the champion scores ZERO on.

The reigning champion serves no cross-chain intent (dest_chain_id != chain_id): it answers
same-chain, which scores 0 on a cross-chain case. This cover fires ONLY on cross-chain
intents and emits a CrossChainPlan (source leg + bridge_request + destination leg). It reuses
the CHAMPION'S OWN same-chain routing for the swap legs (a same-chain sub-state ->
super().generate_plan), so each leg is as good as the champion's same-chain answer. On
same-chain intents it defers untouched -> ZERO risk to same-chain matching. Disabled by
default (cover_state.disabled('crosschain')).

Scoring contract (verified against api/services/cross_chain_quote.py): the destination fork is
seeded with the bridge's estimated output; credit = output-token transfer to the recipient
produced by the DEST leg executing (fallback: the LARGEST output-token transfer, so a champion
swap whose recipient is the app still counts). Bridge model = fixed 5 bps; a declared amount
larger than actually earned reverts to zero, so we size the dest swap CONSERVATIVELY below the
seeded amount. A same-chain answer to a cross-chain case scores 0, so any real delivery wins.
"""
from __future__ import annotations
import logging
import os
import time

logger = logging.getLogger(__name__)

_BRIDGE_BPS = 5                                                    # platform's fixed bridge model
_DEST_SAFETY = float(os.environ.get("AUTOBOT_XC_DEST_SAFETY", "0.985"))   # keep dest swap under the seed

# canonical bridge equivalents by symbol: token.lower() on each chain
_USDC = {1: "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 8453: "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"}
_WETH = {1: "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", 8453: "0x4200000000000000000000000000000000000006"}


def _canon_map(chain, token):
    t = (token or "").lower()
    for m in (_USDC, _WETH):
        if t == m.get(chain):
            return m
    return None


def wrap(base_cls):
    from minotaur_subnet.shared.types import ExecutionPlan, Interaction, BridgeRequest, ChainLeg, CrossChainPlan
    try:
        from minotaur_subnet.shared.builders import build_intent_state
    except Exception:
        build_intent_state = None
    import cover_state
    from eth_utils import to_checksum_address as _ck

    def _params(state):
        fn = getattr(state, "raw_params_view", None)
        p = fn() if callable(fn) else (getattr(state, "raw_params", None) or {})
        return p or {}

    def _transfer_cd(to, amt):
        return "0x" + "a9059cbb" + _ck(to)[2:].rjust(64, "0") + hex(int(amt))[2:].rjust(64, "0")

    class CrossChainCover(base_cls):

        def _xc_info(self, state):
            """(src, dst, tin, tout, amt, recipient, app, owner) for a cross-chain intent, else None."""
            p = _params(state)
            src = int(getattr(state, "chain_id", 0) or 0)
            dest = p.get("dest_chain_id") or p.get("destination_chain_id")
            try:
                dst = int(dest) if dest not in (None, "", 0, "0") else 0
            except Exception:
                dst = 0
            if not dst or dst == src:
                return None
            tin = (p.get("input_token") or "").lower()
            tout = (p.get("output_token") or "").lower()
            amt = int(p.get("input_amount") or 0)
            app = getattr(state, "contract_address", "") or ""
            owner = getattr(state, "owner", "") or ""
            recipient = p.get("dest_recipient") or p.get("receiver") or owner or app
            if not (tin and tout and amt > 0 and app and src):
                return None
            return (src, dst, tin, tout, amt, recipient, app, owner)

        def _champ_swap_ix(self, intent, snapshot, chain, tin, tout, amt, app, owner):
            """Reuse the champion's OWN same-chain routing for a tin->tout swap on `chain`."""
            if build_intent_state is None or tin == tout or amt <= 0:
                return []
            try:
                sub = build_intent_state(contract_address=app, chain_id=chain,
                    params={"input_token": tin, "output_token": tout, "input_amount": str(amt),
                            "min_output_amount": "0", "app_address": app},
                    intent_function="swap", owner=owner or "")
                plan = super(CrossChainCover, self).generate_plan(intent, sub, snapshot)
            except Exception:
                return []
            return list(getattr(plan, "interactions", None) or [])

        def _xc_build(self, intent, state, snapshot, info):
            src, dst, tin, tout, amt, recipient, app, owner = info
            # --- source: bridge input directly if bridgeable, else swap input->USDC on src ---
            if _canon_map(src, tin) is not None:
                bridge_src, src_ix, bridge_amt = tin, [], amt
            else:
                bridge_src = _USDC[src]
                src_ix = self._champ_swap_ix(intent, snapshot, src, tin, bridge_src, amt, app, owner)
                if not src_ix:
                    return None
                bridge_amt = amt                                  # declared hint; platform uses actual earned
            bridge_dst = _canon_map(src, bridge_src)[dst]
            legs = [ChainLeg(chain_id=src, interactions=list(src_ix),
                             metadata={"type": "source_swap" if src_ix else "bridge_source"})]
            bridges = [BridgeRequest(token=_ck(bridge_src), amount=int(bridge_amt), src_chain_id=src,
                                     dst_chain_id=dst, recipient=_ck(recipient),
                                     purpose=f"bridge {bridge_src[:10]} for dest delivery")]
            # --- dest: swap bridged token -> output (conservative), or transfer if already output ---
            seeded = int(bridge_amt * (10000 - _BRIDGE_BPS) / 10000 * _DEST_SAFETY)
            if bridge_dst.lower() == tout:
                dest_ix = [Interaction(target=_ck(tout), value="0",
                                       call_data=_transfer_cd(recipient, seeded), chain_id=dst)]
                dtype = "destination_delivery"
            else:
                dest_ix = self._champ_swap_ix(intent, snapshot, dst, bridge_dst, tout, seeded, app, owner)
                if not dest_ix:
                    return None
                dtype = "destination_swap"
            legs.append(ChainLeg(chain_id=dst, interactions=list(dest_ix), metadata={"type": dtype}))
            ccp = CrossChainPlan(legs=legs, bridge_requests=bridges)
            return ExecutionPlan(intent_id=intent.app_id, interactions=[],
                                 deadline=int(time.time()) + 7200, nonce=getattr(state, "nonce", 0),
                                 metadata={"cross_chain_plan": ccp.to_dict(), "src_chain_id": src,
                                           "dst_chain_id": dst, "plan_type": "cross_chain"})

        def generate_plan(self, intent, state, snapshot=None):
            try:
                if cover_state.disabled("crosschain"):
                    return super().generate_plan(intent, state, snapshot)
                info = self._xc_info(state)
                if info is None:
                    return super().generate_plan(intent, state, snapshot)   # same-chain -> untouched
                plan = self._xc_build(intent, state, snapshot, info)
                if plan is not None:
                    logger.info("[crosschain] bridging %s->%s c%d->c%d", info[2][:8], info[3][:8], info[0], info[1])
                    return plan
            except Exception:
                logger.exception("[crosschain] failed; deferring to champion")
            return super().generate_plan(intent, state, snapshot)

    return CrossChainCover
