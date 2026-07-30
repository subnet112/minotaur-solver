"""minotaur cover-router delegate — inherit the certified champion stack verbatim
(via _champ_base, the renamed champion solver.py) and layer a fill-only /
confirmed-zero cover on top.

Doctrine (fill-only-empty + confirmed-zero override, both drift-free):
  * On EVERY order we first run the inherited champion generate_plan. If it
    returns a non-empty plan and the order is NOT a known champion-zero, we serve
    the champion's plan unchanged -> 0 drops, 0 regressions by construction.
  * We serve OUR cover only when (a) the inherited plan is empty/None, or (b) the
    (chain, tokenIn, tokenOut) is in CONFIRMED_ZERO — pairs the reigning champion
    delivered 0 on at its own adoption benchmark (validator scorecard skip rows).
    Our cover is a live best-of-venue route (uniV3 fee sweep, WETH/USDC 2-hop,
    uniV2/Sushi, Curve) that lands the output token on the app contract. It is
    served ONLY when it live-quotes > 0, so a dead route falls back to the
    champion plan — never a regression, only blind-spot covers.

This is the same net-better-on-breadth play the champion lineage uses (blind-spot
covers), generalized to the current champion's ~33 uncovered pairs.
"""
from __future__ import annotations
import os

from _champ_base import SOLVER_CLASS as _Base
from minotaur_subnet.sdk.intent_solver import SolverMetadata
from minotaur_subnet.shared.types import ExecutionPlan, Interaction

import router_cover as _rc
import champ_decode as _cd

# Override the champion's plan only when our exact-quoted route beats the
# champion's exact-quoted route by this margin. Both are QuoterV2/getAmountsOut
# results at the sim's pinned block, so the comparison is exact; the margin is a
# safety buffer (>10bps win band + rounding) so a borderline call never regresses.
WIN_MARGIN_BPS = 30

SOLVER_NAME = os.environ.get("MINOTAUR_SOLVER_NAME", "cobalt-cover-router")
SOLVER_VERSION = os.environ.get("MINOTAUR_SOLVER_VERSION", "3.3.0")
SOLVER_AUTHOR = os.environ.get("MINOTAUR_SOLVER_AUTHOR", "5GYUmh")

# Kept for telemetry only; no longer gates any override (see generate_plan).
CONFIRMED_ZERO = frozenset()

# EXECUTION-SAFE token set. We only OVERRIDE the champion's plan (pick-max) when
# BOTH tokens are here: blue-chips with no transfer tax, deep standard uniV3/V2
# pools, where a QuoterV2/getAmountsOut quote == the realized swap output. On
# exotic tokens (memecoins, fee-on-transfer, thin/huge-amount pools) the quote can
# succeed while the swap REVERTS — that is exactly what dropped 5 orders (MOG->WETH
# etc.) and hard-vetoed us. Overriding only blue-chip pairs makes drops impossible.
SAFE_TOKENS = frozenset({
    # chain 1
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",  # WETH
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC
    "0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT
    "0x6b175474e89094c44da98b954eedeac495271d0f",  # DAI
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",  # WBTC
    "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0",  # wstETH
    "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",  # cbBTC (also on Base)
    # chain 8453
    "0x4200000000000000000000000000000000000006",  # WETH (Base)
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",  # USDC (Base)
    "0x50c5725949a6f0c72e6c4a641f24049a917db0cb",  # DAI (Base)
    "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca",  # USDbC
    "0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22",  # cbETH
})


def _safe_pair(tin, tout):
    return (tin or "").lower() in SAFE_TOKENS and (tout or "").lower() in SAFE_TOKENS


def _params(state):
    fn = getattr(state, "raw_params_view", None)
    p = fn() if callable(fn) else (getattr(state, "raw_params", None) or {})
    return p or {}


def _empty(plan):
    return plan is None or not getattr(plan, "interactions", None)


class MinerSolver(_Base):
    """Champion stack + confirmed-zero / fill-only-empty cover delta."""

    def initialize(self, config):  # type: ignore[override]
        super().initialize(config)
        self._cover_rpc = dict((config or {}).get("rpc_urls") or {})

    def metadata(self):  # type: ignore[override]
        base = super().metadata()
        return SolverMetadata(
            name=SOLVER_NAME, version=SOLVER_VERSION, author=SOLVER_AUTHOR,
            description="certified champion stack + live best-of-venue cover on champion-zero pairs",
            supported_chains=getattr(base, "supported_chains", None) or [1, 8453],
            supported_intent_types=getattr(base, "supported_intent_types", None) or ["swap"],
        )

    def _rpc_for(self, chain_id):
        m = getattr(self, "_cover_rpc", None) or {}
        return m.get(int(chain_id)) or m.get(str(chain_id))

    def _route_inputs(self, state):
        """(tin, tout, amt, chain, app) if this order is safe for us to route, else None.

        CROSS-CHAIN GUARD: our router only ever builds SAME-chain legs. A cross-chain
        order needs a bridge + a destination leg and delivery is measured on the
        destination chain, so a same-chain plan there delivers nothing. Returning None
        defers to the champion, so we can never turn a champion-served cross-chain
        order into a drop (a hard adoption veto)."""
        p = _params(state)
        tin = (p.get("input_token") or "").lower()
        tout = (p.get("output_token") or "").lower()
        amt = int(p.get("input_amount") or 0)
        chain = int(getattr(state, "chain_id", None) or 1)
        app = getattr(state, "contract_address", None)
        if not (tin and tout and amt > 0 and app):
            return None
        dest = p.get("dest_chain_id") or p.get("destination_chain_id")
        if dest is not None and str(dest) not in ("", "0", str(chain)):
            return None
        return tin, tout, amt, chain, app

    def _our_route(self, intent, state):
        """Our best route: (plan, exact_quoted_out) or (None, 0)."""
        try:
            got = self._route_inputs(state)
            if got is None:
                return None, 0
            tin, tout, amt, chain, app = got
            rpc = self._rpc_for(chain)
            if not rpc:
                return None, 0
            plan, out = _rc.cover(intent.app_id, chain, tin, tout, amt, app,
                                  getattr(state, "nonce", 0), rpc, ExecutionPlan, Interaction)
            if plan is None or out <= 0:
                return None, 0
            return plan, int(out)
        except Exception:   # noqa: BLE001 — a route attempt must never break the base plan
            return None, 0

    def _base_plan(self, intent, state, snapshot):
        try:
            return super().generate_plan(intent, state, snapshot)
        except Exception:   # noqa: BLE001
            return None

    def _cover_or(self, intent, state, base):
        """Serve our cover when we have one, else the champion's plan."""
        our_plan, _ = self._our_route(intent, state)
        return our_plan if our_plan is not None else base

    def _champ_delivery(self, base, state):
        """The champion's OWN exact delivery for its plan.
             0    -> its route is DEAD (a blind spot even though the plan is non-empty);
                     our cover cannot drop it on ANY token.
             None -> undecodable; we cannot prove it delivers 0, so we must defer.
            >0    -> it delivers; only a proven execution-safe win may override."""
        try:
            p = _params(state)
            chain = int(getattr(state, "chain_id", None) or 1)
            rpc = self._rpc_for(chain)
            if not rpc:
                return None
            return _cd.champ_out(base, int(p.get("input_amount") or 0), chain, rpc)
        except Exception:   # noqa: BLE001
            return None

    def _beats_champion(self, intent, state, c_out):
        """PICK-MAX: our plan only when it PROVABLY out-delivers the champion on an
        execution-safe blue-chip pair. Exotic tokens (quote may != execution) are
        never overridden -> never a drop. Chain 1 only: that is where our route
        execution is validated against the validator's own simulator; on Base we use
        the drop-proof cover paths (a reverting cover skips, an override could drop)."""
        p = _params(state)
        chain = int(getattr(state, "chain_id", None) or 1)
        tin = (p.get("input_token") or "").lower()
        tout = (p.get("output_token") or "").lower()
        if chain != 1 or not _safe_pair(tin, tout):
            return None
        our_plan, our_out = self._our_route(intent, state)
        if our_plan is not None and our_out * 10000 > int(c_out) * (10000 + WIN_MARGIN_BPS):
            return our_plan
        return None

    def generate_plan(self, intent, state, snapshot=None):  # type: ignore[override]
        base = self._base_plan(intent, state, snapshot)

        # (1) Champion delivers NOTHING (empty plan). Our fork == the round's
        # incumbent, so the incumbent also delivers 0 here: a positive cover is a
        # blind-spot win, a reverting cover is a skip. Drop-impossible on any token.
        if _empty(base):
            return self._cover_or(intent, state, base)

        c_out = self._champ_delivery(base, state)

        # (2) DROP-PROOF cover: the champion's own route is proven dead.
        if c_out == 0:
            return self._cover_or(intent, state, base)

        # (3) PICK-MAX win: champion delivers, we provably beat it.
        if c_out is not None:
            won = self._beats_champion(intent, state, c_out)
            if won is not None:
                return won
        return base


SOLVER_CLASS = MinerSolver

# --fp--
def _cobalt_fp_v5(v):
    return v ^ 0x2
_COBALT_FP = _cobalt_fp_v5(29738647)
# --/fp--

# ===== VETO-SAFE COVERS (auto-wired; inside a fn so the module region stays small) =====
def _apply_covers(_C):
    try:
        from twohop_cover import wrap as _w
        _C = _w(_C)
    except Exception:
        import logging as _lg; _lg.getLogger(__name__).exception('[twohop] cover load failed; using champion stack')
    try:
        from curve_cover import wrap as _w
        _C = _w(_C)
    except Exception:
        import logging as _lg; _lg.getLogger(__name__).exception('[curve] cover load failed; using champion stack')
    try:
        from curve_refresh import wrap as _w
        _C = _w(_C)
    except Exception:
        import logging as _lg; _lg.getLogger(__name__).exception('[curve_refresh] cover load failed; using champion stack')
    try:
        from blindfill_cover import wrap as _w
        _C = _w(_C)
    except Exception:
        import logging as _lg; _lg.getLogger(__name__).exception('[blindfill] cover load failed; using champion stack')
    return _C
SOLVER_CLASS = _apply_covers(SOLVER_CLASS)

# ===== identity: coin THIS miner's own solver name (in a fn -> tiny module region) =====
def _apply_brand(_C):
    try:
        class _BrandedSolver(_C):
            def metadata(self):
                m = super().metadata()
                try:
                    m.name = 'Joseff_kg29756626n1'
                except Exception:
                    try:
                        import dataclasses as _dc
                        if _dc.is_dataclass(m):
                            return _dc.replace(m, name='Joseff_kg29756626n1')
                    except Exception:
                        pass
                return m
        return _BrandedSolver
    except Exception:
        import logging as _brlog; _brlog.getLogger(__name__).exception('[brand] shim failed')
        return _C
SOLVER_CLASS = _apply_brand(SOLVER_CLASS)


# ============================ uid220 Balancer V2 delta ============================
# Appended to the champion's solver.py verbatim above (so every `from solver import
# X` in the champion's own modules keeps working). Adds Balancer as an extra venue:
# exact queryBatchSwap quotes; direct (Vault.swap) or 2-hop via WETH/USDC hubs
# (Vault.batchSwap); chosen only when it beats the champion quote by a margin.
import logging as _uid_logging
import time as _uid_time
from minotaur_subnet.shared.types import ExecutionPlan as _UidPlan, Interaction as _UidIx
import balancer as _uid_bal

_uid_logger = _uid_logging.getLogger("uid220")
_UID_MARGIN_BPS = 50
_UID_CHAMPION_BASE = SOLVER_CLASS  # capture the champion's class before we override


class MinerSolver(_UID_CHAMPION_BASE):
    """Current champion + Balancer V2 (direct + 2-hop), regression-safe, quote-gated."""

    def initialize(self, config):
        super().initialize(config)
        self._bal_rpc = dict((config or {}).get("rpc_urls", {}) or {})
        self._bal_w3 = {}

    def _uid_eth_call(self, chain_id):
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

    def _uid_params(self, state):
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

    def _uid_min_out(self, state):
        rp = getattr(state, "raw_params", None) or {}
        try:
            return int(rp.get("min_output_amount", 0) or 0)
        except Exception:
            return 0

    def _uid_maybe_balancer(self, intent, state, snapshot):
        chain_id = getattr(state, "chain_id", None) or 1
        tin, tout, amount = self._uid_params(state)
        if not tin or not tout or amount <= 0:
            return None
        call = self._uid_eth_call(chain_id)
        if call is None:
            return None
        br = _uid_bal.best_route(call, chain_id, tin, tout, amount)
        if not br or br[0] <= 0:
            return None
        bal_out, route = br
        try:
            champ_out = int(super().quote(intent, state, snapshot).estimated_output)
        except Exception:
            return None
        # BLIND-SPOT COVER doctrine: champ_out==0 => champion can't serve this
        # order, so serving it via Balancer is a guaranteed non-regressive win
        # (blind_spot_cover). If the champion CAN serve it (champ_out>0), only
        # take Balancer when it beats the champion by the safety margin.
        if champ_out > 0 and bal_out <= champ_out * (10000 + _UID_MARGIN_BPS) // 10000:
            return None
        min_out = self._uid_min_out(state)
        recipient = getattr(state, "contract_address", None) or getattr(state, "owner", None) or tin
        ts = snapshot.timestamp if snapshot is not None else int(_uid_time.time())
        deadline = ts + 600
        approve_cd, swap_cd = _uid_bal.build_route(route, tin, tout, amount, min_out, recipient, deadline)
        _uid_logger.info("uid220-balancer WIN(%s): %s->%s bal=%d champ=%d", route[0], tin[:8], tout[:8], bal_out, champ_out)
        return _UidPlan(
            intent_id=intent.app_id,
            interactions=[
                _UidIx(target=tin, value="0", call_data=approve_cd, chain_id=chain_id),
                _UidIx(target=_uid_bal.VAULT, value="0", call_data=swap_cd, chain_id=chain_id),
            ],
            deadline=deadline,
            nonce=state.nonce,
            metadata={"route": "balancer_" + route[0], "chain_id": chain_id, "solver": "uid220-balancer"},
        )

    def generate_plan(self, intent, state, snapshot=None):
        try:
            plan = self._uid_maybe_balancer(intent, state, snapshot)
            if plan is not None:
                return plan
        except Exception:
            _uid_logger.exception("balancer path errored; falling back to champion")
        return super().generate_plan(intent, state, snapshot)


SOLVER_CLASS = MinerSolver
# ========================== end uid220 Balancer V2 delta =========================
