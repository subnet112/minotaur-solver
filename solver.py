"""uid220 champion + Balancer V2 venue (direct + 2-hop) — genuine differentiator.

The current champion's solver.py is preserved verbatim as `_champ_base.py`; this
file subclasses whatever class it exports and adds Balancer as an extra venue:

  * exact output via Vault.queryBatchSwap (real pool math)
  * DIRECT (Vault.swap) or 2-HOP via WETH/USDC hubs (Vault.batchSwap)
  * revert-safe execution (both shapes validated on a mainnet fork)

Emits a Balancer plan ONLY when its exact quote beats the champion's own quote
by a safe margin; otherwise the champion runs untouched. Any failure (no RPC in
screening, no route, quote error) falls back to the champion — never a regression.
"""
from __future__ import annotations

import logging
import time

from _champ_base import SOLVER_CLASS as _ChampionBase
from minotaur_subnet.shared.types import ExecutionPlan, Interaction

import balancer

logger = logging.getLogger(__name__)

_MARGIN_BPS = 50


class MinerSolver(_ChampionBase):
    """Current champion + Balancer V2 (direct + 2-hop), regression-safe, quote-gated."""

    def initialize(self, config: dict) -> None:
        super().initialize(config)
        self._bal_rpc = dict((config or {}).get("rpc_urls", {}) or {})
        self._bal_w3 = {}

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
        call = self._eth_call(chain_id)
        if call is None:
            return None
        br = balancer.best_route(call, chain_id, tin, tout, amount)
        if not br or br[0] <= 0:
            return None
        bal_out, route = br
        try:
            champ_out = int(super().quote(intent, state, snapshot).estimated_output)
        except Exception:
            return None
        if champ_out <= 0 or bal_out <= champ_out * (10000 + _MARGIN_BPS) // 10000:
            return None
        min_out = self._min_out(state)
        recipient = getattr(state, "contract_address", None) or getattr(state, "owner", None) or tin
        ts = snapshot.timestamp if snapshot is not None else int(time.time())
        deadline = ts + 600
        approve_cd, swap_cd = balancer.build_route(route, tin, tout, amount, min_out, recipient, deadline)
        logger.info("uid220-balancer WIN(%s): %s->%s bal=%d champ=%d", route[0], tin[:8], tout[:8], bal_out, champ_out)
        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=[
                Interaction(target=tin, value="0", call_data=approve_cd, chain_id=chain_id),
                Interaction(target=balancer.VAULT, value="0", call_data=swap_cd, chain_id=chain_id),
            ],
            deadline=deadline,
            nonce=state.nonce,
            metadata={"route": f"balancer_{route[0]}", "chain_id": chain_id, "solver": "uid220-balancer"},
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
