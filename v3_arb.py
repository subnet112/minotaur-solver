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
from v3_arb2 import _quoter, _requote
from v3_arb3 import _best_2hop
from v3_arb4 import _v2_best
from v3_arb5 import _aero_best
from v3_arb6 import _pcs_best
from v3_arb_build import _build, _recipient

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


def _add(out, r, tag, idx):
    """Append a (out, tag, data) candidate; data = whole result if idx is None,
    else result[idx]. No-op when the finder returned None/empty."""
    if r:
        out.append((r[0], tag, r if idx is None else r[idx]))


def _cands(w3, chain, tin, tout, amt):
    """Collect (out, venue, data) route candidates across V3/V2/Aerodrome/PcsV3.
    'v3'->data (out,base,f1,f2); 'v2'->path list; 'aero'->hops list;
    'pcs'->data (out,path,fees)."""
    out = []
    _add(out, _best_2hop(w3, chain, tin, tout, amt), 'v3', None)
    _add(out, _v2_best(w3, chain, tin, tout, amt), 'v2', 1)
    _add(out, _aero_best(w3, chain, tin, tout, amt), 'aero', 1)
    _add(out, _pcs_best(w3, chain, tin, tout, amt), 'pcs', None)
    return out


def _pick(w3, chain, tin, tout, amt):
    """Highest-output route across V3/V2/Aerodrome: (out, venue, data) or None."""
    cands = _cands(w3, chain, tin, tout, amt)
    return max(cands, key=lambda c: c[0]) if cands else None


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
