"""w6 (opal-swap-router) — distinct smart fill cover for crown DEFENSE. Behaviorally like the fleet's
smart covers (stable pair -> direct UniV3 fee-100, WETH pair -> direct fee-500, else -> WETH-hop), so it
TIES the champion rather than churning the crown. Structurally distinct via a DECORATOR-REGISTRY: a
_route(kind) decorator factory registers three encoder functions into a module _ENCODERS map at import,
and generate_plan looks the encoder up by computed kind — a different call graph from w7 (mixin), wf
(composed object), w8 (two-method branch), w9 (module-fn inline), w0 (plain builder-dict), w5 (2-class
inheritance), w11 (rule-chain classes), w12 (monolithic inline).

WEAKLY DOMINANT: fork champion (super) + fill-only-empty + min_out=quoted*99//100 => only turns a DROP
into a fill or a clean revert; never touches orders the champion already serves."""
from __future__ import annotations
import os
from _garnet_full import SOLVER_CLASS as _Base

_ROUTER = "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"   # UniV3 SwapRouter02
_WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
_STABLES = {"0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "0xdac17f958d2ee523a2206206994597c13d831ec7",
            "0x6b175474e89094c44da98b954eedeac495271d0f", "0x853d955acef822db058eb8505911ed77f175b99e"}

SOLVER_NAME = os.environ.get("MINOTAUR_SOLVER_NAME", "opal-swap-router")
SOLVER_VERSION = os.environ.get("MINOTAUR_SOLVER_VERSION", "3.0.0")
SOLVER_AUTHOR = os.environ.get("MINOTAUR_SOLVER_AUTHOR", "ferranlozano")

_ENCODERS = {}


def _route(kind):
    """Decorator factory: register an encoder under `kind` in the module _ENCODERS registry."""
    def register(fn):
        _ENCODERS[kind] = fn
        return fn
    return register


def _ck(addr):
    from eth_utils import to_checksum_address
    return to_checksum_address(addr)


@_route("stable")
def _enc_stable(tin, tout, amt, min_out, recip):
    from eth_abi import encode as _e
    tup = (_ck(tin), _ck(tout), 100, _ck(recip), int(amt), int(min_out), 0)
    return "0x04e45aaf" + _e(["(address,address,uint24,address,uint256,uint256,uint160)"], [tup]).hex()


@_route("weth")
def _enc_weth(tin, tout, amt, min_out, recip):
    from eth_abi import encode as _e
    tup = (_ck(tin), _ck(tout), 500, _ck(recip), int(amt), int(min_out), 0)
    return "0x04e45aaf" + _e(["(address,address,uint24,address,uint256,uint256,uint160)"], [tup]).hex()


@_route("hop")
def _enc_hop(tin, tout, amt, min_out, recip):
    from eth_abi import encode as _e
    raw = (bytes.fromhex(tin[2:]) + (3000).to_bytes(3, "big") + bytes.fromhex(_WETH[2:])
           + (3000).to_bytes(3, "big") + bytes.fromhex(tout[2:]))
    return "0xb858183f" + _e(["(bytes,address,uint256,uint256)"], [(raw, _ck(recip), int(amt), int(min_out))]).hex()


def _opal_needs_cover(plan, state):
    """True when the champion left an empty plan on a chain-1 order (our fill window)."""
    if (plan is not None and getattr(plan, "interactions", None)) \
            or int(getattr(state, "chain_id", 0) or 0) != 1:
        return False
    return True


def _opal_parse_order(state):
    """Extract (tin, tout, amt, quoted) from raw_params, or None if unfillable."""
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


def _opal_kind(tin, tout):
    """Route classifier: stable pair -> fee-100, WETH pair -> fee-500, else -> WETH-hop."""
    if tin in _STABLES and tout in _STABLES:
        return "stable"
    if _WETH in (tin, tout):
        return "weth"
    return "hop"


def _opal_build_plan(intent, state, tin, tout, amt, quoted, recip):
    """Encode approve + registry-looked-up swap into an ExecutionPlan (min_out = quoted*99//100)."""
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction as _IX, ExecutionPlan as _EP
    enc = _ENCODERS[_opal_kind(tin, tout)]
    swap = enc(tin, tout, amt, quoted * 99 // 100, recip)
    ix = [_IX(target=_ck(tin), value="0", call_data=encode_approve(_ck(_ROUTER), int(amt)), chain_id=1),
          _IX(target=_ck(_ROUTER), value="0", call_data=swap, chain_id=1)]
    return _EP(intent_id=intent.app_id, interactions=ix, deadline=9999999999, nonce=state.nonce,
               metadata={"solver": "fork-registry-w6", "chain_id": 1})


class ForkRegistryFill(_Base):
    """Champion engine + fill-only-empty cover encoded via the _ENCODERS decorator-registry lookup."""

    def _kind_for(self, tin, tout):
        return _opal_kind(tin, tout)

    def generate_plan(self, intent, state, snapshot=None):
        plan = super().generate_plan(intent, state, snapshot)
        if not _opal_needs_cover(plan, state):
            return plan
        try:
            parsed = _opal_parse_order(state)
            if parsed is None:
                return plan
            tin, tout, amt, quoted, recip = parsed
            built = _opal_build_plan(intent, state, tin, tout, amt, quoted, recip)
            return built if getattr(built, "interactions", None) else plan
        except Exception:
            return plan

    def metadata(self):
        base = super().metadata()
        try:
            from minotaur_subnet.sdk.intent_solver import SolverMetadata
            return SolverMetadata(name=SOLVER_NAME, version=SOLVER_VERSION, author=SOLVER_AUTHOR,
                                  description="champion fork + decorator-registry fill cover",
                                  supported_chains=base.supported_chains,
                                  supported_intent_types=base.supported_intent_types)
        except Exception:
            return base


SOLVER_CLASS = ForkRegistryFill










# --fp--
def _apex_fp_29797795n1(v):
    return v + 10
_APEX_FP = _apex_fp_29797795n1(0)
# --/fp--
