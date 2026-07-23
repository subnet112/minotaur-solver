"""viking_batch — Multicall-batched candidate search for the strict-better cover.

The whole per-order route search (v3-direct all tiers + v3-2hop via hubs + v2
direct/2-hop) collapses to 2 aggregate3 eth_calls: round 1 = v3-direct + v3-leg1
+ v2, round 2 = v3-leg2 for each positive leg1. This replaces ~50-90 individual
eth_calls that, under bench-load, storm the sandbox archive into rate-limit flakes
(so viking's rescue-cover of a base-dropped order sometimes fails and stays a
drop). Route selection is IDENTICAL to the per-call form (same tiers/hubs/paths,
same first-max tie-break, same v3d/v3h/v2 order) — verified route-for-route at a
pinned block; only the round-trip count drops ~30x. Primitives live in viking_quote."""
import logging
from viking_quote import _FEES, _QUOTERS, _V2ROUTER, _HUBS, _v2_paths, _agg3, _enc_single, _enc_v2, _dec_single, _dec_v2out
logger = logging.getLogger('solver')

def _add_direct(calls, tags, q, tin, tout, amt):
    for fee in _FEES:
        calls.append((q, _enc_single(tin, tout, amt, fee)))
        tags.append(('v3d', fee, None))

def _add_leg1(calls, tags, chain, q, tin, tout, amt):
    for hub in _HUBS.get(int(chain), ()):
        if hub == tin or hub == tout:
            continue
        for f1 in _FEES:
            calls.append((q, _enc_single(tin, hub, amt, f1)))
            tags.append(('leg1', hub, f1))

def _add_v2(calls, tags, chain, v2r, tin, tout, amt):
    if not v2r:
        return
    for path in _v2_paths(chain, tin, tout):
        calls.append((v2r, _enc_v2(amt, path)))
        tags.append(('v2', tuple(path), None))

def _round1(chain, tin, tout, amt):
    """Round-1 (calls, tags): v3-direct + v3-leg1(tin->hub) + v2."""
    q = _QUOTERS.get(int(chain))
    v2r = _V2ROUTER.get(int(chain))
    calls, tags = ([], [])
    _add_direct(calls, tags, q, tin, tout, amt)
    _add_leg1(calls, tags, chain, q, tin, tout, amt)
    _add_v2(calls, tags, chain, v2r, tin, tout, amt)
    return (calls, tags)

def _best_direct(pairs):
    """Best v3 direct: (out, (fee,)) or None. First-max tie-break in _FEES order."""
    best = None
    for (kind, a, b), (ok, rb) in pairs:
        if kind == 'v3d':
            o = _dec_single(ok, rb)
            if o > 0 and (best is None or o > best[0]):
                best = (o, (a,))
    return best

def _best_v2(pairs):
    """Best v2: (out, path_list) or None. Direct scanned first => wins ties."""
    best = None
    for (kind, a, b), (ok, rb) in pairs:
        if kind == 'v2':
            o = _dec_v2out(ok, rb)
            if o > 0 and (best is None or o > best[0]):
                best = (o, list(a))
    return best

def _leg1_map(pairs):
    """Positive leg1 outputs: {(hub, f1): out}."""
    m = {}
    for (kind, a, b), (ok, rb) in pairs:
        if kind == 'leg1':
            o = _dec_single(ok, rb)
            if o > 0:
                m[a, b] = o
    return m

def _leg2_calls(q, tout, l1):
    calls, tags = ([], [])
    for (hub, f1), amt1 in l1.items():
        for f2 in _FEES:
            calls.append((q, _enc_single(hub, tout, amt1, f2)))
            tags.append((hub, f1, f2))
    return (calls, tags)

def _pick_2hop(tags, res):
    best = None
    for (hub, f1, f2), (ok, rb) in zip(tags, res):
        o = _dec_single(ok, rb)
        if o > 0 and (best is None or o > best[0]):
            best = (o, (hub, f1, f2))
    return best

def _best_2hop(w3, chain, tout, l1):
    """Round-2 aggregate3: v3-leg2(hub->tout) for each positive leg1 -> best 2hop."""
    if not l1:
        return None
    q = _QUOTERS.get(int(chain))
    calls, tags = _leg2_calls(q, tout, l1)
    res = _agg3(w3, calls)
    if res is None:
        return None
    return _pick_2hop(tags, res)

def _assemble(best_d, best_h, best_v2):
    out = []
    if best_d is not None:
        out.append((best_d[0], 'v3d', best_d[1]))
    if best_h is not None:
        out.append((best_h[0], 'v3h', best_h[1]))
    if best_v2 is not None:
        out.append((best_v2[0], 'v2', best_v2[1]))
    return out

def candidates(w3, chain, tin, tout, amt):
    """All strict-better route candidates [(out, kind, det), ...], v3d/v3h/v2 order.
    Two aggregate3 calls instead of ~50-90 singletons; selection is identical."""
    if not _QUOTERS.get(int(chain)):
        return []
    r1c, r1t = _round1(chain, tin, tout, amt)
    r1 = _agg3(w3, r1c)
    if r1 is None:
        return []
    pairs = list(zip(r1t, r1))
    best_h = _best_2hop(w3, chain, tout, _leg1_map(pairs))
    return _assemble(_best_direct(pairs), best_h, _best_v2(pairs))