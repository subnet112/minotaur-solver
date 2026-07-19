"""v3_arb_build — plan-construction helpers for the v3_arb cover, split out so
v3_arb's module region stays small (factor discipline). Leaf: imports only leg
primitives; v3_arb (top) -> v3_arb_build -> v3_arb2/4/5/6."""
from v3_arb2 import _router02, _encode_2hop, _approve_ix, _swap_ix
from v3_arb4 import _v2_swap_ix
from v3_arb5 import _aero_swap_ix
from v3_arb6 import _pcs_swap_ix


def _mk_plan(intent, state, chain, ix, tag='v3-arb-2hop'):
    """Wrap the interaction list in an ExecutionPlan."""
    from minotaur_subnet.shared.types import ExecutionPlan
    return ExecutionPlan(intent_id=intent.app_id, interactions=ix,
                         deadline=9999999999, nonce=state.nonce,
                         metadata={'solver': tag, 'chain_id': chain})


def _build_plan(intent, state, ctx, best, recipient):
    """Build the approve + exactInput 2-hop ExecutionPlan for the best route."""
    chain, tin, tout, amt = ctx[:4]
    out, base, f1, f2 = best
    router = _router02(chain)
    if not router:
        return None
    cd = _encode_2hop(tin, base, tout, f1, f2, amt, recipient)
    ix = [_approve_ix(tin, router, amt, chain), _swap_ix(router, cd, chain)]
    return _mk_plan(intent, state, chain, ix)


def _build_v2(intent, state, ctx, path, recipient):
    """Build the approve + swapExactTokensForTokens ExecutionPlan (V2 route)."""
    chain, amt = ctx[0], ctx[3]
    ix = _v2_swap_ix(chain, path, amt, recipient)
    return _mk_plan(intent, state, chain, ix, 'v3-arb-v2') if ix else None


def _build_aero(intent, state, ctx, hops, recipient):
    """Build the approve + Aerodrome swapExactTokensForTokens ExecutionPlan."""
    chain, amt = ctx[0], ctx[3]
    ix = _aero_swap_ix(chain, hops, amt, recipient)
    return _mk_plan(intent, state, chain, ix, 'v3-arb-aero') if ix else None


def _build_pcs(intent, state, ctx, data, recipient):
    """Build the approve + Pancake V3 exactInput ExecutionPlan (data=(out,path,fees))."""
    chain, amt = ctx[0], ctx[3]
    ix = _pcs_swap_ix(chain, data[1], data[2], amt, recipient)
    return _mk_plan(intent, state, chain, ix, 'v3-arb-pcs') if ix else None


def _recipient(state, p):
    """Delivery recipient: contract_address, then receiver, then owner."""
    return (getattr(state, 'contract_address', None)
            or p.get('receiver') or getattr(state, 'owner', None))


def _build(intent, state, ctx, r, rcpt):
    """Dispatch a _pick result (out, venue, data) to the venue's plan builder."""
    if r[1] == 'aero':
        return _build_aero(intent, state, ctx, r[2], rcpt)
    if r[1] == 'pcs':
        return _build_pcs(intent, state, ctx, r[2], rcpt)
    if r[1] == 'v2':
        return _build_v2(intent, state, ctx, r[2], rcpt)
    return _build_plan(intent, state, ctx, r[2], rcpt)
