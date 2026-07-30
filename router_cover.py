"""Generic live-quoting cover router for SN112 quote blind spots.

Given (chain, tin, tout, amount) it live-quotes a menu of venues the champion's
chain-1 fastpath / Base engine can miss — uniV3 all fee tiers (direct + WETH/USDC
2-hop), uniV2 + Sushi, Curve stable pools — picks the best-delivering route, and
emits an ExecutionPlan whose final leg lands `tout` on the app contract. Used
ONLY on champion-confirmed-zero keys or where the inherited plan is empty, so a
positive delivery is always a blind-spot win and a dead quote just defers to the
champion (never a regression).

No third-party solver code; only stdlib + eth_abi. eth_call goes to the RPC the
harness/sandbox provides (same endpoints the champion quotes against).
"""
from __future__ import annotations
_DR_UNSET = object()
_FR_UNSET = object()
from _fx_shard_0 import *

def _fr_29():
    global BUDGET_S, DEADLINE, S_APPROVE, S_QUOTE_SINGLE, S_V2_SWAP, S_V3_PATH_02, S_V3_PATH_V1, S_V3_SINGLE_02, S_V3_SINGLE_V1, Web3, _SEARCH_DEADLINE, _aero_candidates, _dec, _enc, _fx_20, _legs_curve, _scan_v2, _scan_v3, json, q_curve, time
    import json
    import time
    from eth_abi import encode as _enc, decode as _dec
    from web3 import Web3
    DEADLINE = 9999999999
    BUDGET_S = 6.0
    _SEARCH_DEADLINE = [0.0]
    S_APPROVE = '095ea7b3'
    S_V3_SINGLE_V1 = '414bf389'
    S_V3_SINGLE_02 = '04e45aaf'
    S_V3_PATH_V1 = 'c04b8d59'
    S_V3_PATH_02 = 'b858183f'
    S_V2_SWAP = '38ed1739'
    S_QUOTE_SINGLE = 'c6a5026a'

    def _fx_20():

        def _dz272():
            S_QUOTE_PATH = 'cdca1753'
            S_V2_AMOUNTS = 'd06ca61f'
            S_CURVE_FIND = 'a87df06c'
            S_CURVE_IDX = 'eb85226d'
            S_CURVE_GETDY = '5e0d443f'
            S_CURVE_EXCH = '3df02124'
            S_CURVE_EXCH_RECV = 'ddc1f59d'
            S_TRANSFER = 'a9059cbb'
            S_AERO_GAO = '5509a1ac'
            S_AERO_SWAP = 'cac88ea9'
            FEES = (100, 500, 3000, 10000)
            AERO_ROUTER = '0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43'
            AERO_FACTORY = '0x420DD381b31aEf6683db6B902084cB0FFECe40Da'
            return (AERO_FACTORY, AERO_ROUTER, FEES, S_AERO_GAO, S_AERO_SWAP, S_CURVE_EXCH, S_CURVE_EXCH_RECV, S_CURVE_FIND, S_CURVE_GETDY, S_CURVE_IDX, S_QUOTE_PATH, S_TRANSFER, S_V2_AMOUNTS)
        global AERO_FACTORY, AERO_ROUTER, CHAINS, FEES, S_AERO_SWAP, S_CURVE_EXCH_RECV, S_CURVE_FIND, S_CURVE_GETDY, S_CURVE_IDX, _approve, _v3_path_bytes, eth_call, q_aero, q_v2, q_v3_path, q_v3_single
        AERO_FACTORY, AERO_ROUTER, FEES, S_AERO_GAO, S_AERO_SWAP, S_CURVE_EXCH, S_CURVE_EXCH_RECV, S_CURVE_FIND, S_CURVE_GETDY, S_CURVE_IDX, S_QUOTE_PATH, S_TRANSFER, S_V2_AMOUNTS = _dz272()

        def _cfg_eth():
            return {'quoter': '0x61fFE014bA17989E743c5F6cB21bF9697530B21e', 'v3router': '0xE592427A0AEce92De3Edee1F18E0157C05861564', 'v3sel_single': S_V3_SINGLE_V1, 'v3sel_path': S_V3_PATH_V1, 'v3_deadline': True, 'v2routers': ['0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D', '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F'], 'hubs': ['0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', '0xdAC17F958D2ee523a2206206994597C13D831ec7', '0x6B175474E89094C44Da98b954EedeAC495271d0F', '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599'], 'curve_metareg': '0xF98B45FA17DE75FB1aD0e7aFD971b0ca00e379fC'}

        def _cfg_base():
            return {'quoter': '0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a', 'v3router': '0x2626664c2603336E57B271c5C0b26F421741e481', 'v3sel_single': S_V3_SINGLE_02, 'v3sel_path': S_V3_PATH_02, 'v3_deadline': False, 'v2routers': ['0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24'], 'hubs': ['0x4200000000000000000000000000000000000006', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'], 'curve_metareg': None}
        CHAINS = {1: _cfg_eth(), 8453: _cfg_base()}

        def _ck(a):
            return a
        _W3_CACHE: dict = {}

        def _w3(rpc_url, timeout=3):
            """Cached Web3 client per RPC url. The SDK's web3 (shipped in the solver base
    image) is the SANCTIONED chain-RPC path — raw network modules (urllib/socket/
    requests) are a screening-time banned import (`banned_import`, ARMED v2)."""
            w = _W3_CACHE.get(rpc_url)
            if w is None:
                w = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': timeout}))
                _W3_CACHE[rpc_url] = w
            return w

        def eth_call(rpc_url, to, data_hex, timeout=1.5):
            """eth_call via web3; returns raw bytes or None (revert / empty / hiccup / out of
    time). Refuses to START a call once the search deadline has passed, so the total
    search can never overrun the per-plan timeout no matter how slow the RPC is."""
            dl = _SEARCH_DEADLINE[0]
            if dl and time.monotonic() >= dl:
                return None
            try:
                res = _w3(rpc_url, timeout).eth.call({'to': Web3.to_checksum_address(to), 'data': data_hex})
                return bytes(res) if res else None
            except Exception:
                return None

        def _approve(token, spender, amount):
            return '0x' + S_APPROVE + _enc(['address', 'uint256'], [spender, int(amount)]).hex()

        def _v3_path_bytes(tokens, fees):
            b = bytes.fromhex(tokens[0][2:])
            for i, f in enumerate(fees):
                b += int(f).to_bytes(3, 'big') + bytes.fromhex(tokens[i + 1][2:])
            return b

        def q_v3_single(rpc, cfg, tin, tout, amt, fee):
            data = '0x' + S_QUOTE_SINGLE + _enc(['(address,address,uint256,uint24,uint160)'], [(tin, tout, int(amt), int(fee), 0)]).hex()
            r = eth_call(rpc, cfg['quoter'], data)
            if not r:
                return 0
            try:
                return int(_dec(['uint256'], r[:32])[0])
            except Exception:
                return 0

        def q_v3_path(rpc, cfg, tokens, fees, amt):
            path = _v3_path_bytes(tokens, fees)
            data = '0x' + S_QUOTE_PATH + _enc(['bytes', 'uint256'], [path, int(amt)]).hex()
            r = eth_call(rpc, cfg['quoter'], data)
            if not r:
                return 0
            try:
                return int(_dec(['uint256'], r[:32])[0])
            except Exception:
                return 0

        def q_v2(rpc, router, path, amt):
            data = '0x' + S_V2_AMOUNTS + _enc(['uint256', 'address[]'], [int(amt), path]).hex()
            r = eth_call(rpc, router, data)
            if not r:
                return 0
            try:
                outs = _dec(['uint256[]'], r)[0]
                return int(outs[-1]) if outs else 0
            except Exception:
                return 0

        def q_aero(rpc, routes, amt):
            """Aerodrome getAmountsOut for a Route[] list. Returns final out int (0 if none)."""
            data = '0x' + S_AERO_GAO + _enc(['uint256', '(address,address,bool,address)[]'], [int(amt), routes]).hex()
            r = eth_call(rpc, AERO_ROUTER, data)
            if not r:
                return 0
            try:
                outs = _dec(['uint256[]'], r)[0]
                return int(outs[-1]) if outs else 0
            except Exception:
                return 0
    _fx_20()

    def q_curve(rpc, cfg, tin, tout, amt):
        """Curve stable/meta pools via MetaRegistry. Returns {pool,i,j,dy} or None.

    Only the RECEIVER variant is used downstream (`exchange(i,j,dx,0,receiver)`,
    0xddc1f59d), which pays the app directly — so unlike the old classic-pool cover
    there is no fixed-amount `transfer(app, dy)` leg that could revert when the
    realized dy is 1 wei below the quote. Covers the stETH/wstETH/crvUSD/3pool tail
    that Uniswap-only routing misses."""
        mr = pool = None

        def _fr_30():
            nonlocal mr, pool
            mr = cfg.get('curve_metareg')
            if not mr:
                return None
            d = eth_call(rpc, mr, '0x' + S_CURVE_FIND + _enc(['address', 'address'], [tin, tout]).hex())
            if not d or len(d) < 32:
                return None
            pool = '0x' + d[12:32].hex()
            return _FR_UNSET
        _rv_30 = _fr_30()
        if _rv_30 is not _FR_UNSET:
            return _rv_30
        if int(pool, 16) == 0:
            return None
        di = eth_call(rpc, mr, '0x' + S_CURVE_IDX + _enc(['address', 'address', 'address'], [pool, tin, tout]).hex())
        if not di:
            return None
        return _fx_23(_dec, _enc, amt, di, pool, rpc)

    def _legs_curve(tin, amt, app_addr, route):
        """approve + exchange with receiver=app (0xddc1f59d) — no forward leg, no revert."""
        body = _enc(['int128', 'int128', 'uint256', 'uint256', 'address'], [route['i'], route['j'], int(amt), 0, app_addr])
        return [(tin, _approve(tin, route['pool'], amt)), (route['pool'], '0x' + S_CURVE_EXCH_RECV + body.hex())]

    def _aero_candidates(tin, tout, hubs):
        """Candidate Aerodrome Route[] lists: direct (volatile/stable) + 2-hop via hubs."""
        cands = [[(tin, tout, False, AERO_FACTORY)], [(tin, tout, True, AERO_FACTORY)]]
        for hub in hubs:
            if hub.lower() in (tin, tout):
                continue
            for s1 in (False, True):
                for s2 in (False, True):
                    cands.append([(tin, hub.lower(), s1, AERO_FACTORY), (hub.lower(), tout, s2, AERO_FACTORY)])
        return cands

    def _scan_v3(rpc, cfg, tin, tout, amt, take, expired):
        """Direct uniV3 across fee tiers, then 2-hop via each hub."""

        def _dz271():
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
        _r_dz271 = _dz271()
        if _r_dz271 is not _DR_UNSET:
            return _r_dz271[0]

    def _scan_v2(rpc, cfg, tin, tout, amt, take, expired):
        """uniV2-style routers: direct, then via each hub."""

        def _dz270():
            if expired():
                return (None,)
            take(q_v2(rpc, router, [tin, tout], amt), {'kind': 'v2', 'router': router, 'path': [tin, tout]})
            for hub in cfg['hubs']:
                if hub.lower() in (tin, tout) or expired():
                    continue
                take(q_v2(rpc, router, [tin, hub, tout], amt), {'kind': 'v2', 'router': router, 'path': [tin, hub, tout]})
            return _DR_UNSET
        for router in cfg['v2routers']:
            _r_dz270 = _dz270()
            if _r_dz270 is not _DR_UNSET:
                return _r_dz270[0]
_fr_29()

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
    _scan_v3(rpc, cfg, tin, tout, amt, take, expired)

    def _fr_31():
        _scan_v2(rpc, cfg, tin, tout, amt, take, expired)
        if int(chain_id) == 8453:
            _scan_aero(rpc, cfg, tin, tout, amt, take, expired)
        if cfg.get('curve_metareg') and (not expired()):
            cv = q_curve(rpc, cfg, tin, tout, amt)
            if cv:
                take(cv['dy'], {'kind': 'curve', **cv})
    _fr_31()
    return best

def _legs_v3_single(cfg, tin, tout, amt, app_addr, route):

    def _dz275():
        nonlocal body
        body = _enc(['address', 'address', 'uint24', 'address', 'uint256', 'uint256', 'uint256', 'uint160'], [tin, tout, int(route['fee']), app_addr, DEADLINE, int(amt), 0, 0])
    r = cfg['v3router']
    if cfg['v3_deadline']:
        _dz275()
    else:
        body = _enc(['address', 'address', 'uint24', 'address', 'uint256', 'uint256', 'uint160'], [tin, tout, int(route['fee']), app_addr, int(amt), 0, 0])
    return [(tin, _approve(tin, r, amt)), (r, '0x' + cfg['v3sel_single'] + body.hex())]

def _legs_v3_path(cfg, tin, amt, app_addr, route):

    def _dz274():
        if cfg['v3_deadline']:
            body = _enc(['bytes', 'address', 'uint256', 'uint256', 'uint256'], [path, app_addr, DEADLINE, int(amt), 0])
        else:
            body = _enc(['bytes', 'address', 'uint256', 'uint256'], [path, app_addr, int(amt), 0])
        return ([(tin, _approve(tin, r, amt)), (r, '0x' + cfg['v3sel_path'] + body.hex())],)
        return _DR_UNSET
    r = cfg['v3router']
    path = _v3_path_bytes(route['tokens'], route['fees'])
    _r_dz274 = _dz274()
    if _r_dz274 is not _DR_UNSET:
        return _r_dz274[0]

def _legs_v2(tin, amt, app_addr, route):
    r = route['router']
    body = _enc(['uint256', 'uint256', 'address[]', 'address', 'uint256'], [int(amt), 0, route['path'], app_addr, DEADLINE])
    return [(tin, _approve(tin, r, amt)), (r, '0x' + S_V2_SWAP + body.hex())]

def _legs_aero(tin, amt, app_addr, route):
    body = _enc(['uint256', 'uint256', '(address,address,bool,address)[]', 'address', 'uint256'], [int(amt), 0, route['routes'], app_addr, DEADLINE])
    return [(tin, _approve(tin, AERO_ROUTER, amt)), (AERO_ROUTER, '0x' + S_AERO_SWAP + body.hex())]
_LEG_BUILDERS = {'v3_single', 'v3_path', 'v2', 'aero'}

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

    def _dz273():
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
    _r_dz273 = _dz273()
    if _r_dz273 is not _DR_UNSET:
        return _r_dz273[0]

def cover(app_id, chain_id, tin, tout, amt, app_addr, nonce, rpc_url, ExecutionPlan, Interaction):
    """Full path: live-quote best route, build plan. Returns (plan, expected_out) or (None, 0)."""
    br = best_route(rpc_url, chain_id, tin, tout, amt)
    if not br:
        return (None, 0)
    out, route = br
    plan = build_plan(app_id, chain_id, tin, tout, amt, app_addr, nonce, route, ExecutionPlan, Interaction)
    return (plan, out)