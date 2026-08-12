"""Route selection + plan building for SN112 covers.

Venue config and quoting live in `venues` (see the split rationale there).
Names used by champ_decode (CHAINS, q_v3_single, q_v3_path, q_v2) are
re-exported here so its `_rc.<name>` access keeps working unchanged.
"""
from __future__ import annotations
_DR_UNSET = object()
import time
from venues import DEADLINE, BUDGET_S, _SEARCH_DEADLINE, FEES, CHAINS, AERO_ROUTER, AERO_FACTORY, S_APPROVE, S_V2_SWAP, S_AERO_SWAP, S_CURVE_EXCH_RECV, S_V3_SINGLE_V1, S_V3_SINGLE_02, S_V3_PATH_V1, S_V3_PATH_02, eth_call, _approve, _v3_path_bytes, _aero_candidates, q_v3_single, q_v3_path, q_v2, q_aero, q_curve
from eth_abi import encode as _enc

def _scan_v3(rpc, cfg, tin, tout, amt, take, expired):
    """Direct uniV3 across fee tiers, then 2-hop via each hub."""

    def _dz292():
        hub_fees = (500, 3000)
        for hub in cfg['hubs']:
            if hub.lower() in (tin, tout):
                continue
            for f1 in hub_fees:
                for f2 in hub_fees:
                    if expired():
                        return (None,)
                    take(q_v3_path(rpc, cfg, [tin, hub, tout], [f1, f2], amt), {'kind': 'v3_path', 'tokens': [tin, hub, tout], 'fees': [f1, f2]})
        return _DR_UNSET
    for fee in FEES:
        if expired():
            return
        take(q_v3_single(rpc, cfg, tin, tout, amt, fee), {'kind': 'v3_single', 'fee': fee})
    _r_dz292 = _dz292()
    if _r_dz292 is not _DR_UNSET:
        return _r_dz292[0]

def _scan_v2(rpc, cfg, tin, tout, amt, take, expired):
    """uniV2-style routers: direct, then via each hub."""

    def _dz291():
        if expired():
            return (None,)
        take(q_v2(rpc, router, [tin, tout], amt), {'kind': 'v2', 'router': router, 'path': [tin, tout]})
        for hub in cfg['hubs']:
            if hub.lower() in (tin, tout) or expired():
                continue
            take(q_v2(rpc, router, [tin, hub, tout], amt), {'kind': 'v2', 'router': router, 'path': [tin, hub, tout]})
        return _DR_UNSET
    for router in cfg['v2routers']:
        _r_dz291 = _dz291()
        if _r_dz291 is not _DR_UNSET:
            return _r_dz291[0]

def _scan_aero(rpc, cfg, tin, tout, amt, take, expired):
    """Aerodrome (Base only) — the venue Uniswap-on-Base misses. Its swap names the
    app as recipient (no fixed-amount forward), so it is execution-safe like v2/v3."""
    for routes in _aero_candidates(tin, tout, cfg['hubs']):
        if expired():
            return
        take(q_aero(rpc, routes, amt), {'kind': 'aero', 'routes': routes})

def best_route(rpc, chain_id, tin, tout, amt):
    cfg = CHAINS.get(int(chain_id))
    if not cfg:
        return None
    tin = tin.lower()
    tout = tout.lower()
    best = None
    deadline = time.monotonic() + BUDGET_S
    _SEARCH_DEADLINE[0] = deadline

    def expired():
        return time.monotonic() > deadline

    def take(out, route):
        nonlocal best
        if out and out > 0 and (best is None or out > best[0]):
            best = (out, route)
    try:
        _scan_v3(rpc, cfg, tin, tout, amt, take, expired)

        def _fr_2():
            _scan_v2(rpc, cfg, tin, tout, amt, take, expired)
            if int(chain_id) == 8453:
                _scan_aero(rpc, cfg, tin, tout, amt, take, expired)
            if cfg.get('curve_metareg') and (not expired()):
                cv = q_curve(rpc, cfg, tin, tout, amt)
                if cv:
                    take(cv['dy'], {'kind': 'curve', **cv})
        _fr_2()
    finally:
        _SEARCH_DEADLINE[0] = 0.0
    return best

def _legs_v3_single(cfg, tin, tout, amt, app_addr, route):

    def _dz290():
        nonlocal body
        body = _enc(['address', 'address', 'uint24', 'address', 'uint256', 'uint256', 'uint256', 'uint160'], [tin, tout, int(route['fee']), app_addr, DEADLINE, int(amt), 0, 0])
    r = cfg['v3router']
    if cfg['v3_deadline']:
        _dz290()
    else:
        body = _enc(['address', 'address', 'uint24', 'address', 'uint256', 'uint256', 'uint160'], [tin, tout, int(route['fee']), app_addr, int(amt), 0, 0])
    return [(tin, _approve(tin, r, amt)), (r, '0x' + cfg['v3sel_single'] + body.hex())]

def _legs_v3_path(cfg, tin, amt, app_addr, route):
    """exactInput takes a STRUCT, so the args must be tuple-encoded, not flat.

    MEASURED BUG (every 2-hop cover we ever built was dead on arrival):
      keccak("exactInput((bytes,address,uint256,uint256,uint256))")[:4] = c04b8d59
      keccak("exactInput(bytes,address,uint256,uint256,uint256)")[:4]   = 41f9ad65
    consts.py pins c04b8d59 (the struct form), but we encoded FLAT. Because the
    struct contains a dynamic member (`bytes path`), the two differ: flat is 256
    bytes starting 0x...a0, struct is 288 bytes starting 0x...20 (the head offset
    to the tuple). The router's ABI decoder aborts on the flat body -> BARE revert,
    so the swap never even reaches the token pull. Fixed calldata reverts with STF
    instead (decoded fine, failed only on allowance) — see test_v3path_exec.py.

    `_legs_v3_single` deliberately stays flat: its tuple is ALL-STATIC, so flat and
    struct encodings are byte-identical there (asserted in the test). That is why
    single-hop covers always worked and only 2-hop ones silently died.
    """

    def _dz289():
        if cfg['v3_deadline']:
            body = _enc(['(bytes,address,uint256,uint256,uint256)'], [(path, app_addr, DEADLINE, int(amt), 0)])
        else:
            body = _enc(['(bytes,address,uint256,uint256)'], [(path, app_addr, int(amt), 0)])
        return ([(tin, _approve(tin, r, amt)), (r, '0x' + cfg['v3sel_path'] + body.hex())],)
        return _DR_UNSET
    r = cfg['v3router']
    path = _v3_path_bytes(route['tokens'], route['fees'])
    _r_dz289 = _dz289()
    if _r_dz289 is not _DR_UNSET:
        return _r_dz289[0]

def _legs_v2(tin, amt, app_addr, route):
    r = route['router']
    body = _enc(['uint256', 'uint256', 'address[]', 'address', 'uint256'], [int(amt), 0, route['path'], app_addr, DEADLINE])
    return [(tin, _approve(tin, r, amt)), (r, '0x' + S_V2_SWAP + body.hex())]

def _legs_aero(tin, amt, app_addr, route):
    body = _enc(['uint256', 'uint256', '(address,address,bool,address)[]', 'address', 'uint256'], [int(amt), 0, route['routes'], app_addr, DEADLINE])
    return [(tin, _approve(tin, AERO_ROUTER, amt)), (AERO_ROUTER, '0x' + S_AERO_SWAP + body.hex())]

def _legs_for(cfg, kind, tin, tout, amt, app_addr, route):
    if kind == 'v3_single':
        return _legs_v3_single(cfg, tin, tout, amt, app_addr, route)
    if kind == 'v3_path':
        return _legs_v3_path(cfg, tin, amt, app_addr, route)
    if kind == 'v2':
        return _legs_v2(tin, amt, app_addr, route)
    if kind == 'aero':
        return _legs_aero(tin, amt, app_addr, route)
    if kind == 'curve':
        return _legs_curve(tin, amt, app_addr, route)
    return None

def build_plan(app_id, chain_id, tin, tout, amt, app_addr, nonce, route, ExecutionPlan, Interaction):

    def _dz288():
        nonlocal tin, tout
        tin = tin.lower()
        tout = tout.lower()
        legs = _legs_for(cfg, route['kind'], tin, tout, amt, app_addr, route)
        if not legs:
            return (None,)
        ix = [Interaction(target=t, value='0', call_data=d, chain_id=int(chain_id)) for t, d in legs]
        return (ExecutionPlan(intent_id=app_id, interactions=ix, deadline=DEADLINE, nonce=nonce, metadata={'chain_id': int(chain_id)}),)
        return _DR_UNSET
    cfg = CHAINS[int(chain_id)]
    _r_dz288 = _dz288()
    if _r_dz288 is not _DR_UNSET:
        return _r_dz288[0]

def cover(app_id, chain_id, tin, tout, amt, app_addr, nonce, rpc_url, ExecutionPlan, Interaction):
    """Full path: live-quote best route, build plan. Returns (plan, expected_out) or (None, 0)."""
    br = best_route(rpc_url, chain_id, tin, tout, amt)
    if not br:
        return (None, 0)
    out, route = br
    plan = build_plan(app_id, chain_id, tin, tout, amt, app_addr, nonce, route, ExecutionPlan, Interaction)
    return (plan, out)