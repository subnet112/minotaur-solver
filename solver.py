"""uid220 champion + Balancer V2 venue — genuine differentiator.

The incumbent champion covers Uni V2/V3/V4, Aerodrome, Pancake, Sushi, Curve,
Maverick — but NOT Balancer. This solver keeps the champion verbatim
(FlowEnhanceMixin + _ChampionBase) and adds Balancer as an extra venue:

  * exact output via Vault.queryBatchSwap (real pool math, RPC view call)
  * revert-safe execution via approve + Vault.swap (validated on a mainnet fork)

It emits a Balancer plan ONLY when Balancer's exact quote beats the champion's
own quote by a safe margin; otherwise the champion runs untouched. The whole
Balancer path is wrapped so ANY failure (no RPC in screening, no pool for the
pair, quote error) falls straight back to the champion — it can never regress
or crash. This is the "net-better on breadth, zero-regression" adoption path.
"""
from __future__ import annotations

import logging
import time

from _champion_entry import SOLVER_CLASS as _ChampionBase
from minopot_flow import FlowEnhanceMixin
from minotaur_subnet.shared.types import ExecutionPlan, Interaction

import balancer

logger = logging.getLogger(__name__)

# Balancer must beat the champion's quote by at least this margin to be chosen.
# Clears the 10bps match band with headroom and absorbs quote-vs-sim drift so a
# chosen Balancer route is a real win, not a regression risk.
_MARGIN_BPS = 50


class MinerSolver(FlowEnhanceMixin, _ChampionBase):
    """Champion + Balancer V2 venue (regression-safe, quote-gated)."""

    def initialize(self, config: dict) -> None:
        super().initialize(config)
        self._bal_rpc = dict((config or {}).get("rpc_urls", {}) or {})
        self._bal_w3: dict = {}

    # --- helpers ---
    def _eth_call(self, chain_id: int):
        rpc = getattr(self, "_bal_rpc", {}) or {}
        url = rpc.get(chain_id) or rpc.get(str(chain_id))
        if not url:
            return None
        from web3 import Web3
        w3 = getattr(self, "_bal_w3", {}).get(chain_id)
        if w3 is None:
            w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 4}))
            self._bal_w3[chain_id] = w3

        def call(to, data):
            try:
                return w3.eth.call({"to": Web3.to_checksum_address(to), "data": data}).hex()
            except Exception:
                return None

        return call

    def _swap_params(self, state):
        ctx = getattr(state, "typed_context", None)
        if ctx is not None and getattr(ctx, "input_token", None):
            try:
                return ctx.input_token, ctx.output_token, int(ctx.input_amount)
            except Exception:
                pass
        rp = getattr(state, "raw_params", None) or {}
        try:
            return rp.get("input_token", ""), rp.get("output_token", ""), int(rp.get("input_amount", "0") or 0)
        except Exception:
            return "", "", 0

    def _min_out(self, state):
        rp = getattr(state, "raw_params", None) or {}
        try:
            return int(rp.get("min_output_amount", 0) or 0)
        except Exception:
            return 0

    def _maybe_balancer(self, intent, state, snapshot):
        chain_id = getattr(state, "chain_id", None) or 1
        tin, tout, amount = self._swap_params(state)
        if not tin or not tout or amount <= 0:
            return None
        if balancer.pool_for(chain_id, tin, tout) is None:
            return None  # no Balancer pool for this pair -> champion (zero overhead)
        call = self._eth_call(chain_id)
        if call is None:
            return None  # no RPC (e.g. screening sandbox) -> champion
        bal_out = balancer.quote(call, chain_id, tin, tout, amount)
        if bal_out <= 0:
            return None
        try:
            champ_out = int(super().quote(intent, state, snapshot).estimated_output)
        except Exception:
            return None  # can't compare -> champion
        if champ_out <= 0 or bal_out <= champ_out * (10000 + _MARGIN_BPS) // 10000:
            return None  # not clearly better -> champion
        # Balancer wins by margin -> build the plan.
        min_out = self._min_out(state)
        recipient = getattr(state, "contract_address", None) or getattr(state, "owner", None) or tin
        ts = snapshot.timestamp if snapshot is not None else int(time.time())
        deadline = ts + 600
        cd = balancer.build_calldata(tin, tout, amount, min_out, recipient, chain_id, deadline)
        if not cd:
            return None
        approve_cd, swap_cd = cd
        logger.info("uid220-balancer WIN: %s->%s bal=%d champ=%d", tin[:8], tout[:8], bal_out, champ_out)
        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=[
                Interaction(target=tin, value="0", call_data=approve_cd, chain_id=chain_id),
                Interaction(target=balancer.VAULT, value="0", call_data=swap_cd, chain_id=chain_id),
            ],
            deadline=deadline,
            nonce=state.nonce,
            metadata={"route": "balancer_v2", "pool": balancer.pool_for(chain_id, tin, tout),
                      "chain_id": chain_id, "solver": "uid220-balancer"},
        )

    def generate_plan(self, intent, state, snapshot=None):
        try:
            plan = self._maybe_balancer(intent, state, snapshot)
            if plan is not None:
                return plan
        except Exception:
            logger.exception("balancer path errored; falling back to champion")
        return super().generate_plan(intent, state, snapshot)


SOLVER_CLASS = MinerSolver
