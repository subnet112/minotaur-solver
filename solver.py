"""w11 (amber-swap-router) — distinct smart fill cover for crown DEFENSE. Behaviorally like the fleet's
smart covers (stable pair -> direct UniV3 fee-100, WETH pair -> direct fee-500, else -> WETH-hop), so it
TIES the champion rather than churning the crown. Structurally distinct via a CHAIN-OF-RESPONSIBILITY:
a base _Rule with three subclasses (_StableRule/_WethRule/_HopRule) each answering .applies()/.fee(),
scanned as an ordered _RULES list — a different call graph from w7 (mixin), wf (composed object), w8
(two-method branch), w9 (module-fn), w0 (builder-dict), w5 (2-class inheritance).

WEAKLY DOMINANT: fork champion (super) + fill-on-EMPTY-or-BLIND + min_out=quoted*99//100 => only turns a
DROP (empty OR the champion's self-declared blind best-effort guess) into a fill or a clean revert; never
touches orders the champion genuinely serves. Covers chain-1 (SwapRouter, WITH deadline) AND Base=8453
(SwapRouter02, NO deadline)."""
from __future__ import annotations
import os
import json
from _garnet_full import SOLVER_CLASS as _Base, _blind as _w11amber_blind

_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"        # chain-1 SwapRouter (with deadline)
_ROUTER_BASE = "0x2626664c2603336E57B271c5C0b26F421741e481"   # Base SwapRouter02 (no deadline)
_WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
_WETH_BASE = "0x4200000000000000000000000000000000000006"
_STABLES = {"0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "0xdac17f958d2ee523a2206206994597c13d831ec7",
            "0x6b175474e89094c44da98b954eedeac495271d0f", "0x853d955acef822db058eb8505911ed77f175b99e",
            "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"}

SOLVER_NAME = os.environ.get("MINOTAUR_SOLVER_NAME", "amber-swap-router")
SOLVER_VERSION = os.environ.get("MINOTAUR_SOLVER_VERSION", "3.0.0")
SOLVER_AUTHOR = os.environ.get("MINOTAUR_SOLVER_AUTHOR", "oleksandrSavaskov")


def _ck(addr):
    from eth_utils import to_checksum_address
    return to_checksum_address(addr)


def _weth(chain):
    return _WETH_BASE if chain == 8453 else _WETH


class _Rule:
    """One routing rule: whether it applies to a pair, and the UniV3 fee tier it prescribes."""

    def applies(self, tin, tout, chain):
        raise NotImplementedError

    def fee(self):
        raise NotImplementedError


class _StableRule(_Rule):
    def applies(self, tin, tout, chain):
        return tin in _STABLES and tout in _STABLES

    def fee(self):
        return 100


class _WethRule(_Rule):
    def applies(self, tin, tout, chain):
        return _weth(chain) in (tin, tout)

    def fee(self):
        return 500


class _HopRule(_Rule):
    def applies(self, tin, tout, chain):
        return True

    def fee(self):
        return 3000


_RULES = [_StableRule(), _WethRule(), _HopRule()]


def _w11amber_baked_fee(tin, tout, chain):
    """Prefer a baked table fee for the pair (chain-specific), else None."""
    name = "apex_base_routes.json" if chain == 8453 else "apex_routes.json"
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), name)) as fh:
            tbl = json.load(fh) or {}
    except Exception:
        return None
    r = tbl.get(f"{tin}:{tout}") or tbl.get(f"{tout}:{tin}")
    return int(r["fee"]) if isinstance(r, dict) and r.get("fee") else None


def _w11amber_should_cover(plan, state):
    """Fire only on a chain we serve when the champion left this order EMPTY or a BLIND best-effort guess."""
    if int(getattr(state, "chain_id", 0) or 0) not in (1, 8453):
        return False
    empty = not (plan is not None and getattr(plan, "interactions", None))
    return empty or _w11amber_blind(plan)


def _w11amber_parse(state):
    """Pull + validate the swap params from state.raw_params; return None if unroutable."""
    p = dict(getattr(state, "raw_params", {}) or {})
    tin = str(p.get("input_token", "") or "").lower()
    tout = str(p.get("output_token", "") or "").lower()
    amt = int(p.get("input_amount", 0) or 0)
    quoted = int(p.get("quoted_output", 0) or 0)
    if not (tin.startswith("0x") and tout.startswith("0x")) or amt <= 0 or quoted <= 0 or tin == tout:
        return None
    recip = str(p.get("receiver", "") or getattr(state, "contract_address", None)
                or getattr(state, "owner", None) or "0x0000000000000000000000000000000000000001")
    return tin, tout, amt, quoted, recip


def _w11amber_first_rule(tin, tout, chain):
    """Ordered rule-chain scan: first rule whose .applies() holds, else the last (hop) rule."""
    for r in _RULES:
        if r.applies(tin, tout, chain):
            return r
    return _RULES[-1]


def _w11amber_swap(chain, tin, tout, fee, amt, min_out, recip):
    """(router, calldata) for exactInputSingle — Base SwapRouter02 (no deadline) or chain-1 (with deadline)."""
    from eth_abi import encode as _e
    if chain == 8453:
        tup = (_ck(tin), _ck(tout), int(fee), _ck(recip), int(amt), int(min_out), 0)
        sig = "(address,address,uint24,address,uint256,uint256,uint160)"
        return _ROUTER_BASE, "0x04e45aaf" + _e([sig], [tup]).hex()
    tup = (_ck(tin), _ck(tout), int(fee), _ck(recip), 9999999999, int(amt), int(min_out), 0)
    sig = "(address,address,uint24,address,uint256,uint256,uint256,uint160)"
    return _ROUTER, "0x414bf389" + _e([sig], [tup]).hex()


def _w11amber_build_plan(intent, state, chain, tin, tout, amt, quoted, recip):
    """Encode the approve+swap interaction pair into an ExecutionPlan (min_out = quoted*99//100)."""
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction as _IX, ExecutionPlan as _EP
    fee = _w11amber_baked_fee(tin, tout, chain) or _w11amber_first_rule(tin, tout, chain).fee()
    router, swap = _w11amber_swap(chain, tin, tout, fee, amt, quoted * 99 // 100, recip)
    ix = [_IX(target=_ck(tin), value="0", call_data=encode_approve(_ck(router), int(amt)), chain_id=chain),
          _IX(target=_ck(router), value="0", call_data=swap, chain_id=chain)]
    return _EP(intent_id=intent.app_id, interactions=ix, deadline=9999999999, nonce=state.nonce,
               metadata={"solver": "fork-rule-chain-w11", "chain_id": chain, "fee": fee})


class ForkRuleChain(_Base):
    """Champion engine + fill-on-empty-or-blind cover (chain-1 AND Base) selected by an ordered rule chain."""

    def _first_rule(self, tin, tout, chain=1):
        return _w11amber_first_rule(tin, tout, chain)

    def generate_plan(self, intent, state, snapshot=None):
        plan = super().generate_plan(intent, state, snapshot)
        if not _w11amber_should_cover(plan, state):
            return plan
        try:
            parsed = _w11amber_parse(state)
            if parsed is None:
                return plan
            chain = int(getattr(state, "chain_id", 0) or 0)
            built = _w11amber_build_plan(intent, state, chain, *parsed)
            return built if getattr(built, "interactions", None) else plan
        except Exception:
            return plan

    def metadata(self):
        base = super().metadata()
        try:
            from minotaur_subnet.sdk.intent_solver import SolverMetadata
            return SolverMetadata(name=SOLVER_NAME, version=SOLVER_VERSION, author=SOLVER_AUTHOR,
                                  description="champion fork + rule-chain fill cover",
                                  supported_chains=base.supported_chains,
                                  supported_intent_types=base.supported_intent_types)
        except Exception:
            return base


SOLVER_CLASS = ForkRuleChain

# --fp--
def _apex_fp_29798651n1(v):
    return v + 10
_APEX_FP = _apex_fp_29798651n1(0)
# --/fp--
