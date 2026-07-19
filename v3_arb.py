"""v3_arb — V3 2-hop-via-base OVERRIDE for orders the engine routes poorly.

The lineage's discovery misses Uniswap V3 2-hop routes (tin -> hub -> tout) that
deliver MORE on thin-pool tokens (e.g. q_631c4630: engine 0.478e18 vs a WETH
2-hop ~14.4e18). We re-quote the engine's OWN chosen route and our best V3 2-hop
against QuoterV2 on the SAME block, and serve the 2-hop ONLY when it STRICTLY
beats the engine's delivery — so the gain is real at bench (for exactInput,
QuoterV2 quote == on-chain execution) and we never override a route that already
delivers more. If the base is undecodable we DEFER.

Plan wire format (leaf v3_arb2): SwapRouter02 + 4-field exactInput 0xb858183f,
mirroring the champion's _build_v3_path02_ix. Every region here is kept <=110
AST nodes so grafting onto the hydra factor-110 base never raises max_region."""
import logging
from v3_arb2 import (_quoter, _requote, _router02,
                     _encode_2hop, _approve_ix, _swap_ix)
from v3_arb3 import _best_2hop
from v3_arb4 import _v2_best, _v2_swap_ix

logger = logging.getLogger('solver')


def _resolve_chain(state, snapshot):
    """Chain id from state, falling back to snapshot; 0 if unknown."""
    return int(getattr(state, 'chain_id', 0)
               or (getattr(snapshot, 'chain_id', 0) if snapshot else 0) or 0)


def _swap_fields(solver, intent, state):
    """Normalize the order into (params, tin, tout, amt)."""
    p = solver._normalized_swap_params(intent, state)
    tin = str(p.get('input_token', '') or '').lower()
    tout = str(p.get('output_token', '') or '').lower()
    amt = int(p.get('input_amount', 0) or 0)
    return p, tin, tout, amt


def _ctx(solver, intent, state, snapshot):
    """Resolve (chain, tin, tout, amt, w3, params) for the order, or None."""
    chain = _resolve_chain(state, snapshot)
    if _quoter(chain) is None:
        return None
    p, tin, tout, amt = _swap_fields(solver, intent, state)
    if not tin or not tout or amt <= 0:
        return None
    w3 = solver._get_web3(chain)
    if w3 is None:
        return None
    return (chain, tin, tout, amt, w3, p)


def _base_out(w3, chain, base_plan):
    """Re-quote the engine's base delivery. 0 if empty; quoted amount if
    decodable; None if non-empty but UNDECODABLE (can't prove dead)."""
    ix = getattr(base_plan, 'interactions', None) if base_plan else None
    if not ix:
        return 0
    cd = ix[-1].call_data or ''
    if not cd.startswith('0x'):
        cd = '0x' + cd
    return _requote(w3, chain, cd)


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


def _recipient(state, p):
    """Delivery recipient: contract_address, then receiver, then owner."""
    return (getattr(state, 'contract_address', None)
            or p.get('receiver') or getattr(state, 'owner', None))


def _pick(w3, chain, tin, tout, amt):
    """Best of {V3 2-hop, V2}: (out, venue, data) or None. venue 'v3' -> data is
    the (out,base,f1,f2) tuple; 'v2' -> data is the path token list."""
    v3 = _best_2hop(w3, chain, tin, tout, amt)
    v2 = _v2_best(w3, chain, tin, tout, amt)
    a = v3[0] if v3 else 0
    b = v2[0] if v2 else 0
    if b > a and b > 0:
        return (b, 'v2', v2[1])
    if a > 0:
        return (a, 'v3', v3)
    return None


def _build(intent, state, ctx, r, rcpt):
    """Dispatch a _pick result (out, venue, data) to the V2 or V3 builder."""
    if r[1] == 'v2':
        return _build_v2(intent, state, ctx, r[2], rcpt)
    return _build_plan(intent, state, ctx, r[2], rcpt)


def _plan_for(intent, state, ctx, floor):
    """Serve the best of {V3 2-hop, V2} ONLY when it STRICTLY beats `floor`
    (engine's re-quoted delivery); build the winning venue's plan, else None."""
    chain, tin, tout, amt, w3, p = ctx
    r = _pick(w3, chain, tin, tout, amt)
    if r is None or r[0] <= floor:
        return None
    plan = _build(intent, state, ctx, r, _recipient(state, p))
    if plan is not None:
        logger.info('[v3-arb] %s out=%s > base=%s', r[1], r[0], floor)
    return plan


def v3_arb_cover(solver, intent, state, snapshot, base_plan):
    """Serve a V3 2-hop ONLY when it STRICTLY beats the engine's own re-quoted
    route (best_2hop > base_out), both via QuoterV2 same-block. If the base is
    undecodable, DEFER (can't prove an improvement)."""
    try:
        ctx = _ctx(solver, intent, state, snapshot)
        if ctx is None:
            return None
        bout = _base_out(ctx[4], ctx[0], base_plan)
        if bout is None:
            return None
        return _plan_for(intent, state, ctx, bout)
    except Exception:
        logger.exception('[v3-arb] cover failed; serving base plan')
        return None
