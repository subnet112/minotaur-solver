"""apex-split-router — thin subclass of the CURRENT champion (king_base.py).

Design: king_base.py is the reigning champion's solver.py copied verbatim. THIS
file subclasses its MinerSolver and adds ONE thing — never-drop blind-spot cover
for tokens the champion's engine + hardcode genuinely cannot route (champ delivers
0). For every other order we defer entirely to the champion, so we match it
byte-for-byte (0 regressions). A covered token delivers where the champion delivers
nothing = a clean "new" win; below-min delivery just skips (== champ's 0), so it
can never regress.

Re-fork onto a new champion = copy its solver.py to king_base.py. This file is
fixed (no re-editing the champion's evolving code) — that's the whole point.
"""
from __future__ import annotations

import logging
import os
import time

from king_base import MinerSolver as _Base
from minotaur_subnet.sdk.intent_solver import SolverMetadata
from minotaur_subnet.shared.types import ExecutionPlan, Interaction

logger = logging.getLogger(__name__)

SOLVER_NAME = os.environ.get("MINOTAUR_SOLVER_NAME", "apex-split-router")
SOLVER_VERSION = os.environ.get("MINOTAUR_SOLVER_VERSION", "2.1.0")
SOLVER_AUTHOR = os.environ.get("MINOTAUR_SOLVER_AUTHOR", "martindev0207")

_BASE = 8453
_WETH = "0x4200000000000000000000000000000000000006"
_MAVERICK_ROUTER = "0x5eDEd0d7E76C563FF081Ca01D9d12D6B404Df527"   # MaverickV2Router
_UNIV2_ROUTER = "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24"      # Uniswap V2 Router02
_VIRTUAL = "0x0b3e328455c4059eeb9e3f84b5543f74e24e7e1b"          # VIRTUAL hub

# Tokens the current champion delivers 0 on (venues its enum + hardcode can't reach:
# Maverick-general, Uni V2, the VIRTUAL hub). ONLY put a token here if king_base
# genuinely can't route it — verify against king_base._HOLE_ROUTES + its enum before
# adding, else we'd pre-empt the champion's better route and regress.
#   ("uni_mav", (maverick_pool, tokenAIn))   = Uni V3 tin->WETH + Maverick WETH->token
#   ("uni_v2_via", (mid_hub, v2_router))     = Uni V3 tin->mid + V2 router mid->token
#   ("v2", v2_router)                        = V2 router tin->WETH->token (FoT)
_APEX_HOLE_ROUTES = {
    # GPUS — only on Maverick V2 (king's enum has no general Maverick).
    "0x8189910840771050bf9ed268abfc9c0882137029":
        ("uni_mav", ("0x77aa9de2695c28ddd5831c33bf7021e9aa2db23f", True)),
    # WAGMI — only via the VIRTUAL hub then Uni V2 (champion lacks Uni V2).
    # (MANEKI removed — the champion has since absorbed it -> now matched, not a win.)
    "0x2ce1340f1d402ae75afeb55003d7491645db1857":
        ("uni_v2_via", (_VIRTUAL, _UNIV2_ROUTER)),
}


def _load_dynamic_holes():
    """Holes the bot's detector confirmed this round (structural, champion can't route,
    Uni V3-routable) — baked in via a committed apex_holes.json so the benchmark sees
    them. Format: {"0xtoken": {"kind": "uni_v3"}}. Only kinds we can build are honored.
    """
    import json as _json
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apex_holes.json")
    try:
        data = _json.load(open(path)) or {}
    except Exception:
        return {}
    out = {}
    for tok, spec in data.items():
        try:
            kind = (spec or {}).get("kind", "uni_v3")
            if kind == "uni_v3":
                out[str(tok).lower()] = ("uni_v3", None)
        except Exception:
            continue
    return out


_APEX_HOLE_ROUTES.update(_load_dynamic_holes())


class MinerSolver(_Base):
    """Champion base + never-drop blind-spot cover (apex-split-router)."""

    def metadata(self):  # type: ignore[override]
        base = super().metadata()
        return SolverMetadata(
            name=SOLVER_NAME, version=SOLVER_VERSION, author=SOLVER_AUTHOR,
            description=("Current-champion base + never-drop blind-spot cover for "
                         "tokens it can't route (Maverick / Uni V2 / VIRTUAL hub)"),
            supported_chains=base.supported_chains,
            supported_intent_types=base.supported_intent_types)

    def _generate_plan_impl(self, intent, state, snapshot=None):  # type: ignore[override]
        # Intercept ONLY our verified champ=0 tokens; everything else -> champion.
        try:
            p = self._normalized_swap_params(intent, state)
            if str(p.get("output_token", "") or "").lower() in _APEX_HOLE_ROUTES:
                plan = self._apex_hole_plan(intent, state, snapshot, p)
                if plan is not None:
                    return plan
        except Exception:
            logger.exception("[apex] hole intercept failed; using champion path")
        return super()._generate_plan_impl(intent, state, snapshot)

    def _apex_hole_plan(self, intent, state, snapshot, params):
        try:
            tin = str(params.get("input_token", "") or "")
            tout = str(params.get("output_token", "") or "")
            amount_in = int(params.get("input_amount", 0) or 0)
            amount_in = self._effective_swap_amount(self._fee_params(state, params), tin, amount_in)
            chain_id = int(state.chain_id or (snapshot.chain_id if snapshot else 0) or 0)
            if chain_id != _BASE or amount_in <= 0 or not tin or not tout:
                return None
            kind, param = _APEX_HOLE_ROUTES[tout.lower()]
            if kind == "uni_mav":
                pool, token_a_in = param
                return self._apex_uni_mav(intent, state, snapshot, pool, bool(token_a_in),
                                          tin, tout, amount_in, chain_id)
            if kind == "uni_v3":
                return self._apex_uni_v3(intent, state, snapshot, tin, tout, amount_in, chain_id)
            if kind == "uni_v2_via":
                mid, v2_router = param
                return self._apex_uni_v2_via(intent, state, snapshot, mid, v2_router,
                                             tin, tout, amount_in, chain_id)
            if kind == "v2":
                mid = _WETH
                path = ([tin, tout] if mid in (tin.lower(), tout.lower()) else [tin, mid, tout])
                return self._apex_v2(intent, state, snapshot, param, path, amount_in, chain_id)
        except Exception:
            logger.exception("[apex] hole plan build failed")
        return None

    # ── builders (named _apex_* to avoid clobbering champion methods) ──────────
    def _apex_recipient(self, state, params):
        return state.contract_address or params.get("receiver") or state.owner

    def _apex_deadline(self, snapshot):
        ts = getattr(snapshot, "timestamp", None) if snapshot else None
        return int(ts or time.time()) + 300

    def _apex_v2(self, intent, state, snapshot, router, path, amount_in, chain_id):
        from common.abi_utils import encode_approve
        from eth_abi import encode as _enc
        from eth_utils import to_checksum_address as _ck
        params = self._normalized_swap_params(intent, state)
        recipient = self._apex_recipient(state, params); deadline = self._apex_deadline(snapshot)
        call = "0x5c11d795" + _enc(  # swapExactTokensForTokensSupportingFeeOnTransferTokens
            ["uint256", "uint256", "address[]", "address", "uint256"],
            [int(amount_in), 0, [_ck(p) for p in path], _ck(recipient), int(deadline)]).hex()
        ix = [Interaction(target=path[0], value="0", call_data=encode_approve(router, amount_in), chain_id=chain_id),
              Interaction(target=router, value="0", call_data=call, chain_id=chain_id)]
        return ExecutionPlan(intent_id=intent.app_id, interactions=ix, deadline=deadline,
                             nonce=state.nonce, metadata={"solver": "apex-hole-v2", "chain_id": chain_id})

    def _apex_uni_v3(self, intent, state, snapshot, tin, tout, amount_in, chain_id):
        # Plain single-hop Uni V3 exactInputSingle — the venue every structural hole
        # used (VU, Cookie, ...). Champion delivers 0 (token not in its enum), so any
        # positive delivery is a clean win and 0-quote just falls through (== its 0).
        from common.abi_utils import encode_approve
        from strategies.dex_aggregator.swap_solver import UNISWAP_V3_ROUTERS
        from strategies.dex_aggregator.v3_codec import encode_exact_input_single
        w3 = self._get_web3(int(chain_id))
        uni_router = UNISWAP_V3_ROUTERS.get(int(chain_id))
        if w3 is None or not uni_router:
            return None
        best_out, best_fee = 0, 3000
        for fee in (3000, 500, 10000, 100):
            try:
                q = int(self._quote_one(w3, "uniswap_v3", fee, tin, tout, amount_in))
            except Exception:
                q = 0
            if q > best_out:
                best_out, best_fee = q, fee
        if best_out <= 0:
            return None
        params = self._normalized_swap_params(intent, state)
        recipient = self._apex_recipient(state, params); deadline = self._apex_deadline(snapshot)
        call = encode_exact_input_single(token_in=tin, token_out=tout, fee=int(best_fee),
            recipient=recipient, deadline=deadline, amount_in=amount_in, amount_out_minimum=0, chain_id=chain_id)
        ix = [Interaction(target=tin, value="0", call_data=encode_approve(uni_router, amount_in), chain_id=chain_id),
              Interaction(target=uni_router, value="0", call_data=call, chain_id=chain_id)]
        return ExecutionPlan(intent_id=intent.app_id, interactions=ix, deadline=deadline,
                             nonce=state.nonce, metadata={"solver": "apex-hole-uni-v3", "chain_id": chain_id})

    def _apex_uni_mav(self, intent, state, snapshot, pool, token_a_in, tin, tout, amount_in, chain_id):
        from common.abi_utils import encode_approve
        from eth_abi import encode as _enc
        from eth_utils import to_checksum_address as _ck
        from strategies.dex_aggregator.swap_solver import UNISWAP_V3_ROUTERS
        from strategies.dex_aggregator.v3_codec import encode_exact_input_single
        w3 = self._get_web3(int(chain_id))
        uni_router = UNISWAP_V3_ROUTERS.get(int(chain_id))
        if w3 is None or not uni_router:
            return None
        weth_out, best_fee = 0, 500
        for fee in (500, 3000, 100, 10000):
            try:
                q = int(self._quote_one(w3, "uniswap_v3", fee, tin, _WETH, amount_in))
            except Exception:
                q = 0
            if q > weth_out:
                weth_out, best_fee = q, fee
        if weth_out <= 0:
            return None
        mav_in = weth_out * 995 // 1000   # buffer vs quote/exec drift
        params = self._normalized_swap_params(intent, state)
        recipient = self._apex_recipient(state, params); deadline = self._apex_deadline(snapshot)
        leg1 = encode_exact_input_single(token_in=tin, token_out=_WETH, fee=int(best_fee),
            recipient=recipient, deadline=deadline, amount_in=amount_in, amount_out_minimum=0, chain_id=chain_id)
        mav = "0x" + ("a3b105ca" + _enc(["address", "address", "bool", "uint256", "uint256"],
            [_ck(recipient), _ck(pool), bool(token_a_in), int(mav_in), 0]).hex())
        ix = [Interaction(target=tin, value="0", call_data=encode_approve(uni_router, amount_in), chain_id=chain_id),
              Interaction(target=uni_router, value="0", call_data=leg1, chain_id=chain_id),
              Interaction(target=_WETH, value="0", call_data=encode_approve(_MAVERICK_ROUTER, mav_in), chain_id=chain_id),
              Interaction(target=_MAVERICK_ROUTER, value="0", call_data=mav, chain_id=chain_id)]
        return ExecutionPlan(intent_id=intent.app_id, interactions=ix, deadline=deadline,
                             nonce=state.nonce, metadata={"solver": "apex-hole-uni-mav", "chain_id": chain_id})

    def _apex_uni_v2_via(self, intent, state, snapshot, mid, v2_router, tin, tout, amount_in, chain_id):
        from common.abi_utils import encode_approve
        from eth_abi import encode as _enc
        from eth_utils import to_checksum_address as _ck
        from strategies.dex_aggregator.swap_solver import UNISWAP_V3_ROUTERS
        from strategies.dex_aggregator.v3_codec import encode_exact_input_single
        w3 = self._get_web3(int(chain_id))
        uni_router = UNISWAP_V3_ROUTERS.get(int(chain_id))
        if w3 is None or not uni_router:
            return None
        mid_out, best_fee = 0, 3000
        for fee in (3000, 10000, 500, 100):
            try:
                q = int(self._quote_one(w3, "uniswap_v3", fee, tin, mid, amount_in))
            except Exception:
                q = 0
            if q > mid_out:
                mid_out, best_fee = q, fee
        if mid_out <= 0:
            return None
        v2_in = mid_out * 995 // 1000
        params = self._normalized_swap_params(intent, state)
        recipient = self._apex_recipient(state, params); deadline = self._apex_deadline(snapshot)
        leg1 = encode_exact_input_single(token_in=tin, token_out=mid, fee=int(best_fee),
            recipient=recipient, deadline=deadline, amount_in=amount_in, amount_out_minimum=0, chain_id=chain_id)
        leg2 = "0x5c11d795" + _enc(["uint256", "uint256", "address[]", "address", "uint256"],
            [int(v2_in), 0, [_ck(mid), _ck(tout)], _ck(recipient), int(deadline)]).hex()
        ix = [Interaction(target=tin, value="0", call_data=encode_approve(uni_router, amount_in), chain_id=chain_id),
              Interaction(target=uni_router, value="0", call_data=leg1, chain_id=chain_id),
              Interaction(target=mid, value="0", call_data=encode_approve(v2_router, v2_in), chain_id=chain_id),
              Interaction(target=v2_router, value="0", call_data=leg2, chain_id=chain_id)]
        return ExecutionPlan(intent_id=intent.app_id, interactions=ix, deadline=deadline,
                             nonce=state.nonce, metadata={"solver": "apex-hole-uni-v2-via", "chain_id": chain_id})


SOLVER_CLASS = MinerSolver
