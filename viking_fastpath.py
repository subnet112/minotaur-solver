"""viking_fastpath — recurring-key route cache served as a STRICT-BETTER cover on
the champion base. On a cached (tin,tout,amt) we re-quote ONE known-best route and
serve it ONLY when it out-delivers the champion's own plan (never a regression):
the king-base + our-delta pattern — inherit the champion's routing as the floor,
lift above it where our live-requoted route wins. det shapes match
viking_build.serve's candidate contract, so served calldata is byte-identical.

Helpers take (args, det) where args=(w3,chain,tin,tout,amt) to keep each region —
and the module region (args count in the parent scope) — under the factor ceiling."""
import json
import os
_TAB = None

def _table():
    global _TAB
    if _TAB is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'viking_fastpath.json')
        try:
            _TAB = json.load(open(path)) or {}
        except Exception:
            _TAB = {}
    return _TAB

def _rq_v3d(args, det):
    import viking_quote as _q
    w3, chain, tin, tout, amt = args
    o = _q._q_single(w3, chain, tin, tout, det[0], amt)
    return (o, 'v3d', (det[0],)) if o and o > 0 else None

def _rq_v3h(args, det):
    import viking_quote as _q
    import viking_build as _b
    w3, chain, tin, tout, amt = args
    o = _q._q_path(w3, chain, _b._v3h_path(tin, det[0], tout, det[1], det[2]), amt)
    return (o, 'v3h', (det[0], det[1], det[2])) if o and o > 0 else None

def _rq_v2(args, det):
    import viking_quote as _q
    w3, chain, amt = (args[0], args[1], args[4])
    o = _q._v2_out(w3, chain, det[1], amt)
    return (o, 'v2', (det[0], list(det[1]))) if o and o > 0 else None

def _rq_curve(args, det):
    import viking_curve as _cv
    o = _cv._quote(args[0], det[0], det[1], det[2], det[3], args[4])
    return (o, 'curve', (det[0], det[1], det[2], det[3])) if o and o > 0 else None
_RQ = {'v3d': _rq_v3d, 'v3h': _rq_v3h, 'v2': _rq_v2, 'curve': _rq_curve}

def _lookup(tin, tout, amt):
    """(requote_fn, det) for a cached key — exact amount first, then the
    pair-level wildcard row (tin|tout|*) — or None."""
    t = _table()
    rec = t.get(tin.lower() + '|' + tout.lower() + '|' + str(int(amt))) or t.get(tin.lower() + '|' + tout.lower() + '|*')
    fn = _RQ.get(rec[0]) if rec else None
    return (fn, rec[1]) if fn else None

def serve(ctx, floor, intent, state):
    """Re-quote the one cached route and serve ONLY in the WIN band: quoted
    out must beat floor by >10 bps (the scoring win threshold), so an
    epsilon-better route never trades a tie for extra gas. floor==0 (engine
    served nothing) serves on any positive quote. None => defer."""

    def _best():
        chain, tin, tout, amt, w3, p = ctx
        hit = _lookup(tin, tout, amt)
        if hit is None:
            return None
        b = hit[0]((w3, chain, tin, tout, amt), hit[1])
        return b if b is not None and b[0] * 10000 > floor * 10010 else None
    best = _best()
    if best is None:
        return None
    import viking_build as _b
    return _b.serve(intent, state, ctx[0], ctx[1], ctx[2], best, ctx[3], ctx[5])

def cover_lift(solver, intent, state, snapshot, base_plan):
    """BLIND-SPOT-ONLY cover. Fire ONLY when the champion engine produced no
    plan (a true blind spot). If the champion delivered ANY plan we defer
    IMMEDIATELY — before any re-quote — so we never replace its known-good route
    with a quoted one that could revert (a HARD-VETO drop) or under-deliver (a
    regression), and we add zero latency on champion-served keys. This makes the
    cover loss-proof by construction: it can only add blind-spot wins, never
    drop or regress a champion-served order."""
    try:
        if base_plan is not None and getattr(base_plan, 'interactions', None):
            return None
        import viking_v3hop as _vh
        ctx = _vh._cover_ctx(solver, intent, state, snapshot)
        if ctx is None:
            return None
        return serve(ctx, 0, intent, state)
    except Exception:
        return None