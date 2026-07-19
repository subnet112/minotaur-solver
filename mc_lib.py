"""_McSolver body extractions (hoisted verbatim from solver.py): base-route
re-quote decode, the skip-fill setup gate, and the dead-fill key table."""
import os
from mc_data import _MC_QUOTER, _MC_PANCAKE_Q
_MC_DEAD_FILL_CACHE = None


def dead_fill():
    """Lazy dead_fill.json — 'tin|tout|amt' keys where BOTH the champion tree
    and our base are executor-sim PROVEN to deliver 0 end-to-end. Treated as
    FORCE keys: the live fill can only lift a proven 0, never regress."""
    global _MC_DEAD_FILL_CACHE
    if _MC_DEAD_FILL_CACHE is None:
        import json as _json
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dead_fill.json')
        try:
            data = _json.load(open(path))
            _MC_DEAD_FILL_CACHE = {str(k).lower() for k in data} if isinstance(data, list) else set()
        except Exception:
            _MC_DEAD_FILL_CACHE = set()
    return _MC_DEAD_FILL_CACHE

def _bc_v3s(s, sel, body, tin, tout, amt):
    fee = int.from_bytes(body[64:96], 'big')
    q = _MC_QUOTER if sel == '0x04e45aaf' else _MC_PANCAKE_Q
    return (q, s._mc_qdata(tin, tout, amt, fee))

def base_call(s, base_plan, tin, tout, amt):
    """(target,callbytes) that re-quotes the champion's OWN route, or None (undecodable)."""
    try:
        ix = base_plan.interactions[-1]
        cd = ix.call_data if ix.call_data.startswith('0x') else '0x' + ix.call_data
        def _fw1():
            sel = cd[:10]
            body = bytes.fromhex(cd[10:])
            if sel in ('0x04e45aaf', '0x414bf389'):
                return (_bc_v3s(s, sel, body, tin, tout, amt),)
            if sel == '0xb858183f':
                return ((_MC_QUOTER, s._mc_path_qdata(body, amt)),)
        _fwr1 = _fw1()
        if _fwr1 is not None:
            return _fwr1[0]
    except Exception:
        return None
    return None

def _setup_gate(s, intent, state):
    if int(getattr(state, 'chain_id', 0) or 0) != 8453:
        return None
    pr = s._mc_params(intent, state)
    if pr is None:
        return None
    tin, tout, amt, mino = pr
    cls = s._mc_class(tin, tout, amt)
    if cls is None:
        return None
    return (tin, tout, amt, mino, cls)

def setup(s, intent, state, base_plan):
    """One gate: chain + params + target-class + w3 + Multicall list. None to defer."""
    g = _setup_gate(s, intent, state)
    if g is None:
        return None
    tin, tout, amt, mino, cls = g
    w3 = s._get_web3(8453)
    if w3 is None:
        return None
    calls, base_call = s._mc_calls(base_plan, tin, tout, amt, cls)
    if calls is None:
        return None
    return (w3, tin, tout, amt, mino, cls, calls, base_call)
