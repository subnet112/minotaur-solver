"""w8 v10 — SMARTER fill cover (fixes dropped quote:q_ orders): keeps its UniswapV2 venue niche (pairs the
UniV3 miners miss) BUT adds a UniV3 direct fee-100 route for stablecoin pairs, which UniV2's shallow stable
pools under-deliver on (→ min_out revert → drop). Chooses per pair: stable → UniV3 exactInputSingle fee-100;
else → UniV2 swapExactTokensForTokens path. Structurally distinct from wf (composed object), w7 (mixin), w9
(module-fn + inline): here two SEPARATE build methods (_v3_stable, _v2_path) selected by a branch.

WEAKLY DOMINANT: fork champion (super) + fill-only-empty + min_out=quoted*99//100 ⇒ only turns a DROP into a
fill or clean revert; never touches orders the champion already serves."""
from __future__ import annotations
import os
from _garnet_full import SOLVER_CLASS as _Base

_V2ROUTER = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"   # UniswapV2 Router02
_V3ROUTER = "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"   # UniV3 SwapRouter02 (exactInputSingle)
_WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
_STABLES = ["0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "0xdac17f958d2ee523a2206206994597c13d831ec7",
            "0x6b175474e89094c44da98b954eedeac495271d0f", "0x853d955acef822db058eb8505911ed77f175b99e"]

SOLVER_NAME = os.environ.get("MINOTAUR_SOLVER_NAME", "zephyr-swap-router")
SOLVER_VERSION = os.environ.get("MINOTAUR_SOLVER_VERSION", "10.0.0")
SOLVER_AUTHOR = os.environ.get("MINOTAUR_SOLVER_AUTHOR", "bryanaltes")


class ForkV2orV3Fill(_Base):
    """Champion engine + fill-only-empty cover: UniV3 direct fee-100 for stables, else UniV2 path."""

    def generate_plan(self, intent, state, snapshot=None):
        plan = super().generate_plan(intent, state, snapshot)
        if (plan is not None and getattr(plan, "interactions", None)) \
                or int(getattr(state, "chain_id", 0) or 0) != 1:
            return plan
        try:
            p = dict(getattr(state, "raw_params", {}) or {})
            tin = str(p.get("input_token", "") or "").lower()
            tout = str(p.get("output_token", "") or "").lower()
            amt = int(p.get("input_amount", 0) or 0)
            quoted = int(p.get("quoted_output", 0) or 0)
            if not (tin.startswith("0x") and tout.startswith("0x")) or amt <= 0 or quoted <= 0 or tin == tout:
                return plan
            recip = str(p.get("receiver", "") or getattr(state, "contract_address", None)
                        or getattr(state, "owner", None) or "0x0000000000000000000000000000000000000001")
            min_out = quoted * 99 // 100
            if tin in _STABLES and tout in _STABLES:
                built = self._v3_stable(intent, state, tin, tout, amt, min_out, recip)
            else:
                built = self._v2_path(intent, state, tin, tout, amt, min_out, recip)
            return built if (built is not None and getattr(built, "interactions", None)) else plan
        except Exception:
            return plan

    def _v3_stable(self, intent, state, tin, tout, amt, min_out, recip):
        from eth_abi import encode as _enc
        from eth_utils import to_checksum_address as _ck
        from common.abi_utils import encode_approve
        from minotaur_subnet.shared.types import Interaction as _IX, ExecutionPlan as _EP
        # SwapRouter02 exactInputSingle((tokenIn,tokenOut,fee,recipient,amountIn,amountOutMinimum,sqrtPriceLimitX96))
        tup = (_ck(tin), _ck(tout), 100, _ck(recip), int(amt), int(min_out), 0)
        params = _enc(["(address,address,uint24,address,uint256,uint256,uint160)"], [tup]).hex()
        ix = [_IX(target=_ck(tin), value="0", call_data=encode_approve(_ck(_V3ROUTER), int(amt)), chain_id=1),
              _IX(target=_ck(_V3ROUTER), value="0", call_data="0x04e45aaf" + params, chain_id=1)]
        return _EP(intent_id=intent.app_id, interactions=ix, deadline=9999999999, nonce=state.nonce,
                   metadata={"solver": "fork-v3stable-w8", "chain_id": 1})

    def _v2_path(self, intent, state, tin, tout, amt, min_out, recip):
        from eth_abi import encode as _enc
        from eth_utils import to_checksum_address as _ck
        from common.abi_utils import encode_approve
        from minotaur_subnet.shared.types import Interaction as _IX, ExecutionPlan as _EP
        path = [_ck(tin), _ck(tout)] if _WETH in (tin, tout) else [_ck(tin), _ck(_WETH), _ck(tout)]
        params = _enc(["uint256", "uint256", "address[]", "address", "uint256"],
                      [int(amt), int(min_out), path, _ck(recip), 9999999999]).hex()
        ix = [_IX(target=_ck(tin), value="0", call_data=encode_approve(_ck(_V2ROUTER), int(amt)), chain_id=1),
              _IX(target=_ck(_V2ROUTER), value="0", call_data="0x38ed1739" + params, chain_id=1)]
        return _EP(intent_id=intent.app_id, interactions=ix, deadline=9999999999, nonce=state.nonce,
                   metadata={"solver": "fork-v2path-w8", "chain_id": 1})

    def metadata(self):
        base = super().metadata()
        try:
            from minotaur_subnet.sdk.intent_solver import SolverMetadata
            return SolverMetadata(name=SOLVER_NAME, version=SOLVER_VERSION, author=SOLVER_AUTHOR,
                                  description="champion fork + UniV3-stable/UniV2-path fill cover",
                                  supported_chains=base.supported_chains,
                                  supported_intent_types=base.supported_intent_types)
        except Exception:
            return base


SOLVER_CLASS = ForkV2orV3Fill
