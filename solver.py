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

# Override the champion's plan only when our exact-quoted route beats the
# champion's exact-quoted route by this margin. Both are QuoterV2/getAmountsOut
# results at the sim's pinned block, so the comparison is exact; the margin is a
# safety buffer (>10bps win band + rounding) so a borderline call never regresses.
WIN_MARGIN_BPS = 30

SOLVER_NAME = os.environ.get("MINOTAUR_SOLVER_NAME", "cobalt-cover-router")
SOLVER_VERSION = os.environ.get("MINOTAUR_SOLVER_VERSION", "3.11.0")
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
        """The champion's own plan. Retries ONCE on exception.

        LATENT DROP CHANNEL this closes: a raised exception here collapsed to None,
        `_empty(None)` is True, and if our cover also failed `_cover_or` handed that
        None straight back out of generate_plan — no plan at all on a row the champion
        SERVED, which is a guaranteed `dropped` and a hard veto. The champion image
        does not fail on those rows; only OUR run of the same code did (transient RPC
        inside the inherited engine). One cheap retry converts that into a served plan
        instead of a veto. If it fails twice we still return None, but by then the
        empty-base cover is genuinely our only option anyway."""
        for _ in range(2):
            try:
                return super().generate_plan(intent, state, snapshot)
            except Exception:   # noqa: BLE001
                continue
        return None

    def _cover_or(self, intent, state, base):
        """Serve our cover when we have one, else the champion's plan."""
        our_plan, _ = self._our_route(intent, state)
        return our_plan if our_plan is not None else base



    def generate_plan(self, intent, state, snapshot=None):  # type: ignore[override]
        base = self._base_plan(intent, state, snapshot)
        chain = int(getattr(state, "chain_id", None) or 1)

        # BASE (and any non-chain-1) = PURE PASSTHROUGH. Measured, not assumed:
        #   v3.6.0, Base off-gate (65 offgate rows):            0 drops, rank 2
        #   v3.7.1, Base scored, our cover active on Base:      2 drops, rank 5
        #   v3.8.0, Base scored, cover narrowed but still on:  15 drops, rank 6
        # A `dropped` verdict means we returned something OTHER than the champion's
        # plan on a row the champion served, so every one of those drops is our own
        # Base involvement (a cover that did not deliver, or extra latency pushing
        # generate_plan past the 30s/plan limit so no plan came back at all). Our
        # Base upside was ~1 cover; a single drop is a HARD VETO of the whole
        # submission. Returning the champion's plan untouched makes Base rows match
        # by construction. Re-enable only when Base delivery is validated end-to-end
        # against the validator simulator on Base.
        if chain != 1:
            return base

        # (1) Champion delivers NOTHING (empty plan). Our fork == the round's
        # incumbent, so the incumbent also delivers 0 here: a positive cover is a
        # blind-spot win, a reverting cover is a skip. Drop-impossible on any token.
        if _empty(base):
            return self._cover_or(intent, state, base)

        # (2) REMOVED in v3.10.0 — the "champion's route re-quotes to 0 => cover"
        # branch, and with it (v3.11.0) the whole champ_decode re-quote. It was never
        # drop-proof: the decode cannot tell "no liquidity" from "no answer", so a
        # timeout / 429 read as a hard 0 and licensed overriding a LIVE, champion-
        # SERVED order. PROVEN on q_653e3f6253585c — the row the champion covered to
        # TAKE the throne (35927029170) re-quoted 0 against a throttled endpoint.
        # It was also inert: it returned None on 34/44 chain-1 rows (it decodes
        # exactInput FLAT while the champion encodes it as a STRUCT) and produced 0
        # wins and 0 covers in production, at the cost of one RPC round-trip per row.

        # (3) THE WIN — fee-tier correction on the champion's OWN baked chain-1 route.
        # Measured mechanism: the champion serves chain 1 from chain1_routes.json,
        # which is amount-keyed but falls back to ONE size-blind tier per pair. For
        # WETH->USDT the fallback is fee 3000 while the live-optimal tier is 100/500,
        # worth +37..+51 bps across every unpatched size on the pinned fork. They
        # patch amounts REACTIVELY after each round (chain1_routes.json.pre-amtkey-*),
        # and the corpus rotates ~80% per round, so there is always a fresh unpatched
        # tail. Every rival win observed over 12 rounds landed on exactly this.
        # Win band is >+10bps; we additionally demand WIN_MARGIN_BPS.
        return self._tier_fix(intent, state, base) or base

    def _tier_fix(self, intent, state, base):
        """The champion's own plan with ONE integer changed, or None to defer.

        DROP-PROOFNESS, strongest first:
          1. Fires ONLY when metadata['solver'] == 'chain1-baked', i.e. the champion
             definitively served from its baked table (not the engine/kyber/onfork).
          2. The plan we return is the CHAMPION'S OWN BUILDER output — same router,
             same selector, same recipient, same deadline, same min_out=0 ("min_out=0
             => never reverts", chain1_v2.py:88). Only the 3 hex chars of the fee
             differ, so we add no revert surface.
          3. We only switch to a tier QuoterV2 successfully quoted, which proves the
             pool exists AND can fill this size. This is what makes a static table
             unsafe: at 50 WETH the fee-100 pool REVERTS while 3000 fills, so a baked
             "always 100" would drop the order. The live quote is the safety.
          4. SYMMETRIC MEASUREMENT — both sides are quoted through the same transport
             in the same pass. A throttled endpoint yields None for BOTH and we defer.
             There is no one-sided zero, which is the structural fix for the failure
             mode that vetoed us four times.
          5. Every unknown (missing method, odd spec shape, exception) returns None.
        """
        md = getattr(base, "metadata", None) or {}
        if md.get("solver") != "chain1-baked":
            return None                      # engine / lattice / kyber plan: never touch
        # The baked API lives on the champion's arch module, whose NAME carries the
        # champion sha and is re-generated on every rebase. Resolve defensively: if a
        # future champion drops or renames these, we silently defer instead of erroring.
        spec_key = getattr(self, "_chain1_spec_key", None)
        build = getattr(self, "_chain1_build_plan", None)
        if not callable(spec_key) or not callable(build):
            return None
        got = self._route_inputs(state)
        if got is None:
            return None
        tin, tout, amt, _chain, _app = got
        if not _safe_pair(tin, tout):
            return None                      # blue-chip only; exotic quote != execution
        try:
            spec = spec_key(tin, tout, amt)
        except Exception:                    # noqa: BLE001
            return None
        # single-hop, single-fee only. Multi-hop / v2 / curve specs are a different
        # builder shape and are not ours to second-guess.
        if not (isinstance(spec, dict)
                and len(spec.get("tokens") or []) == 2
                and len(spec.get("fees") or []) == 1):
            return None
        better = self._better_tier(tin, tout, amt, int(spec["fees"][0]))
        if better is None:
            return None
        alt = dict(spec)
        alt["fees"] = [better]
        try:
            return build(intent, state, tin, amt, alt) or None
        except Exception:                    # noqa: BLE001
            return None

    def _better_tier(self, tin, tout, amt, baked_fee):
        """A fee tier that PROVABLY out-quotes the baked one, or None.

        Both legs are quoted in the same pass through the same client, so transport
        trouble is symmetric: baked unquotable -> None -> defer (never an override on
        a one-sided failure)."""
        rpc = self._rpc_for(1)
        if not rpc:
            return None
        try:
            import venues as _V
            from consts import CHAINS as _C
            cfg = _C[1]
            base_q = _V.q_v3_single(rpc, cfg, tin, tout, amt, int(baked_fee))
            if not base_q or base_q <= 0:
                return None                  # cannot price the incumbent => defer
            best_fee, best_q = None, base_q
            for f in (100, 500, 3000, 10000):
                if int(f) == int(baked_fee):
                    continue
                q = _V.q_v3_single(rpc, cfg, tin, tout, amt, f)
                if q and q > best_q:
                    best_fee, best_q = f, q
            if best_fee is None:
                return None
            # require a real margin over the incumbent, not a rounding win
            if best_q * 10000 > base_q * (10000 + WIN_MARGIN_BPS):
                return best_fee
            return None
        except Exception:                    # noqa: BLE001
            return None


SOLVER_CLASS = MinerSolver

# --fp--
def _cobalt_fp_v13(v):
    return v ^ 0x2
_COBALT_FP = _cobalt_fp_v13(29738647)
# --/fp--
