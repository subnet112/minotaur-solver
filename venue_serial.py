"""Serial venue scan -- the fallback path, one `eth_call` per candidate.

`venue_batch` is the primary scan; this is what runs when its aggregate3 batch
does not come back (no Multicall3 on the chain, a node that rejects the batch,
a reverting outer call). Behaviour is the pre-batch behaviour verbatim, TRUNCATION
INCLUDED: every call is refused once the shared `_SEARCH_DEADLINE` closes, so a
slow run quotes fewer venues than a fast one. That race is exactly what
`venue_batch` exists to remove, and it is deliberately still here -- a truncated
scan still returns the best of what it did reach, which beats returning nothing
and dropping the order.

Split out of `router_cover` so the scanners' def headers stop counting against
that module's top-level region; the `_DR_UNSET` sentinel dance they used to carry
was scaffolding for that same node budget and is gone with it, since a fresh
module has the room to say `return` directly.
"""
from __future__ import annotations
_DR_UNSET = object()
from venues import FEES, q_v3_single, q_v3_path, q_v2, q_aero, q_curve, _aero_candidates
HUB_FEES = (500, 3000)

def _scan_v3(rpc, cfg, tin, tout, amt, take, expired):
    """Direct uniV3 across fee tiers, then 2-hop via each hub."""

    def _dz149():
        for hub in cfg['hubs']:
            if hub.lower() in (tin, tout):
                continue
            for f1 in HUB_FEES:
                for f2 in HUB_FEES:
                    if expired():
                        return (None,)
                    take(q_v3_path(rpc, cfg, [tin, hub, tout], [f1, f2], amt), {'kind': 'v3_path', 'tokens': [tin, hub, tout], 'fees': [f1, f2]})
        return _DR_UNSET
    for fee in FEES:
        if expired():
            return
        take(q_v3_single(rpc, cfg, tin, tout, amt, fee), {'kind': 'v3_single', 'fee': fee})
    _r_dz149 = _dz149()
    if _r_dz149 is not _DR_UNSET:
        return _r_dz149[0]

def _scan_v2(rpc, cfg, tin, tout, amt, take, expired):
    """uniV2-style routers: direct, then via each hub."""

    def _dz148():
        if expired():
            return (None,)
        take(q_v2(rpc, router, [tin, tout], amt), {'kind': 'v2', 'router': router, 'path': [tin, tout]})
        for hub in cfg['hubs']:
            if hub.lower() in (tin, tout) or expired():
                continue
            take(q_v2(rpc, router, [tin, hub, tout], amt), {'kind': 'v2', 'router': router, 'path': [tin, hub, tout]})
        return _DR_UNSET
    for router in cfg['v2routers']:
        _r_dz148 = _dz148()
        if _r_dz148 is not _DR_UNSET:
            return _r_dz148[0]

def _scan_aero(rpc, cfg, tin, tout, amt, take, expired):
    """Aerodrome (Base only) -- the venue Uniswap-on-Base misses. Its swap names the
    app as recipient (no fixed-amount forward), so it is execution-safe like v2/v3."""
    for routes in _aero_candidates(tin, tout, cfg['hubs']):
        if expired():
            return
        take(q_aero(rpc, routes, amt), {'kind': 'aero', 'routes': routes})

def scan_serial(rpc, cfg, chain_id, tin, tout, amt, take, expired):
    """Every non-curve venue, quoted one call at a time."""
    _scan_v3(rpc, cfg, tin, tout, amt, take, expired)
    _scan_v2(rpc, cfg, tin, tout, amt, take, expired)
    if int(chain_id) == 8453:
        _scan_aero(rpc, cfg, tin, tout, amt, take, expired)

def scan_curve(rpc, cfg, tin, tout, amt, take, expired):
    """Curve tail, serial on BOTH paths: pool lookup -> coin indices -> get_dy are
    three DEPENDENT calls, so there is no candidate list to batch. Runs after the
    venue scan either way, and stays deadline-gated because it is last."""
    if not cfg.get('curve_metareg') or expired():
        return
    cv = q_curve(rpc, cfg, tin, tout, amt)
    if cv:
        take(cv['dy'], {'kind': 'curve', **cv})