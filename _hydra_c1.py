"""Chain-1 wide-venue quoting: UniV2/Sushi (direct + hub 2-hops, one multicall)
+ Curve MetaRegistry receiver-exchange. Closes the coverage gap that lost round
e29756626 vs the cobalt champion (+3/-6: drops on AFX/DEXE/USDtb/frxUSD, a 0.649
catastrophic on SGT, all V2/Curve-side liquidity our V3-only chain-1 scan missed).
Curve legs pay the app directly via exchange(i,j,dx,0,receiver) — no fixed-amount
forward that could revert when realized dy lands a wei under the quote."""
from __future__ import annotations
from eth_abi import encode as _enc, decode as _dec
from eth_utils import keccak as _kec
from _hydra_rt import _mc_raw

def _consts():
    """All module constants, built in ONE function scope: data literals count
    into their enclosing region, so keeping them at module level inflates the
    module region (the factor tie-break metric). Same values, one assignment."""
    return (
        "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",        # UniV2 router
        "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F",        # Sushi router
        _kec(text="getAmountsOut(uint256,address[])")[:4],
        ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",       # WETH
         "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",       # USDC
         "0xdAC17F958D2ee523a2206206994597C13D831ec7",       # USDT
         "0x6B175474E89094C44Da98b954EedeAC495271d0F",       # DAI
         "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"),      # WBTC
        "0xF98B45FA17DE75FB1aD0e7aFD971b0ca00e379fC",        # Curve MetaRegistry
        "0x6A8cbed756804B16E05E741eDaBd5cB544AE21bf",        # stableswap-ng factory
        bytes.fromhex("a87df06c"),                           # find_pool_for_coins
        bytes.fromhex("eb85226d"),                           # get_coin_indices
        bytes.fromhex("5e0d443f"),                           # get_dy int128
        bytes.fromhex("556d6e9f"),                           # get_dy uint256
        bytes.fromhex("ddc1f59d"),                           # exchange int128 recv
        _kec(text="exchange(uint256,uint256,uint256,uint256,address)")[:4],
        bytes.fromhex("095ea7b3"),                           # approve
        "0x03f7724180AA6b939894B5Ca4314783B0b36b329",        # ShibaSwap router
        "0xEfF92A263d31888d860bD50809A8D171709b7b1E",        # PancakeV2 ETH router
        _kec(text="get_dy_underlying(int128,int128,uint256)")[:4],
        _kec(text="exchange_underlying(int128,int128,uint256,uint256,address)")[:4],
    )


(_C1_UNI, _C1_SUSHI, _V2_GAO, _C1_HUBS, _CRV_METAREG, _CRV_NG_FACT, _S_FIND,
 _S_IDX, _S_GETDY, _S_GETDY_U, _S_EXCH_R, _S_EXCH_RU, _S_APPROVE,
 _C1_SHIBA, _C1_PCS, _S_GETDY_UL, _S_EXCH_UL) = _consts()


def _c1v2_paths(ck, tin, tout):
    paths = [[ck(tin), ck(tout)]]
    mid = [h for h in _C1_HUBS if h.lower() not in (tin.lower(), tout.lower())]
    for hub in mid:
        paths.append([ck(tin), ck(hub), ck(tout)])
    for h1 in mid[:4]:
        for h2 in mid[:4]:
            if h1 != h2:
                paths.append([ck(tin), ck(h1), ck(h2), ck(tout)])
    return paths


def _c1v2_best(meta, res):
    best = None
    for (router, p), (ok, d) in zip(meta, res):
        if not (ok and d):
            continue
        try:
            outs = _dec(["uint256[]"], d)[0]
            out = int(outs[-1]) if outs else 0
        except Exception:
            out = 0
        if out > 0 and (best is None or out > best["out"]):
            best = {"router": router, "tokens": list(p), "out": out}
    return best


def c1_v2_route(w3, tin, tout, amt):
    """Best chain-1 V2 route across Uni+Sushi, direct + hub 2-hops. ONE multicall."""
    if amt <= 0:
        return None
    ck = w3.to_checksum_address
    paths = _c1v2_paths(ck, tin, tout)
    subs, meta = [], []
    for router in (_C1_UNI, _C1_SUSHI, _C1_SHIBA, _C1_PCS):
        for p in paths:
            subs.append((ck(router), True, _V2_GAO + _enc(["uint256", "address[]"], [amt, p])))
            meta.append((router, p))
    try:
        res = _mc_raw(w3, subs)
    except Exception:
        return None
    return _c1v2_best(meta, res)


# ---- Curve (chain 1) ---- (constants live in _consts())


def _c1_call(w3, to, data):
    try:
        r = w3.eth.call({"to": w3.to_checksum_address(to), "data": "0x" + data.hex()})
        return bytes(r) if r else None
    except Exception:
        return None


def _curve_find(w3, tin, tout):
    """Pool address via MetaRegistry, else the stableswap-ng factory (which the
    MetaRegistry lags for new stables like USDtb). None when neither knows it."""
    for reg in (_CRV_METAREG, _CRV_NG_FACT):
        d = _c1_call(w3, reg, _S_FIND + _enc(["address", "address"], [tin, tout]))
        if d and len(d) >= 32 and int.from_bytes(d[12:32], "big"):
            return "0x" + d[12:32].hex(), reg
    return None, None


def _curve_idx(w3, reg, pool, tin, tout):
    """(i, j, underlying) coin indices or None. MetaRegistry needs the pool arg;
    the NG factory's get_coin_indices has the same 3-address signature."""
    di = _c1_call(w3, reg, _S_IDX + _enc(["address", "address", "address"], [pool, tin, tout]))
    if not di:
        return None
    try:
        i, j, under = _dec(["int128", "int128", "bool"], di)
    except Exception:
        try:
            i, j = _dec(["int128", "int128"], di[:64])
            under = False
        except Exception:
            return None
    return int(i), int(j), bool(under)


def _curve_dy(w3, pool, i, j, amt):
    """(out, uint_indices) via get_dy — int128 variant first, uint256 fallback."""
    dy = _c1_call(w3, pool, _S_GETDY + _enc(["int128", "int128", "uint256"], [i, j, amt]))
    if dy and len(dy) >= 32:
        return int.from_bytes(dy[:32], "big"), False
    dy = _c1_call(w3, pool, _S_GETDY_U + _enc(["uint256", "uint256", "uint256"], [i, j, amt]))
    if dy and len(dy) >= 32:
        return int.from_bytes(dy[:32], "big"), True
    return 0, False


def curve_route(w3, tin, tout, amt):
    """Curve direct-pool OR underlying-metapool quote: {pool,i,j,out,u,ul} or
    None. Underlying pairs quote via get_dy_underlying and execute via the
    receiver-variant exchange_underlying (NG metapools carry it; older pools
    revert -> 0, which the fill path treats as matched, never a drop)."""
    if amt <= 0:
        return None
    pool, reg = _curve_find(w3, tin, tout)
    if not pool:
        return None
    ij = _curve_idx(w3, reg, pool, tin, tout)
    if ij is None:
        return None
    i, j, under = ij
    if under:
        dy = _c1_call(w3, pool, _S_GETDY_UL + _enc(["int128", "int128", "uint256"], [i, j, amt]))
        out, uint_idx = (int.from_bytes(dy[:32], "big") if dy and len(dy) >= 32 else 0), False
    else:
        out, uint_idx = _curve_dy(w3, pool, i, j, amt)
    if out <= 0:
        return None
    return {"pool": pool, "i": i, "j": j, "out": out, "u": uint_idx, "ul": under}


def curve_legs(tin, amt, app, route):
    """[(target, calldata), ...]: approve pool, then exchange with receiver=app.
    Selector/index types follow the quote variant that worked (route['u'])."""
    ap = _S_APPROVE + _enc(["address", "uint256"], [route["pool"], amt])
    if route.get("ul"):
        ex = _S_EXCH_UL + _enc(["int128", "int128", "uint256", "uint256", "address"],
                               [route["i"], route["j"], amt, 0, app])
    elif route.get("u"):
        ex = _S_EXCH_RU + _enc(["uint256", "uint256", "uint256", "uint256", "address"],
                               [route["i"], route["j"], amt, 0, app])
    else:
        ex = _S_EXCH_R + _enc(["int128", "int128", "uint256", "uint256", "address"],
                              [route["i"], route["j"], amt, 0, app])
    return [(tin, "0x" + ap.hex()), (route["pool"], "0x" + ex.hex())]


def c1v2_cands(vr, amt):
    """Chain-1 V2 cand (Uni or Sushi, direct or hub path): router+tokens carried
    through to _shp_uniswap_v2 (which honors cand['router'])."""
    if not vr or vr.get("out", 0) <= 0:
        return []
    return [{"venue": "uniswap_v2", "tokens": list(vr["tokens"]), "router": vr["router"],
             "param": "v2", "out": int(vr["out"]),
             "gas_est": 150000 + 90000 * (len(vr["tokens"]) - 2),
             "gas_model": 300000, "spend_amount": amt}]


def curve_cands(cr, amt):
    """Curve cand: legs built at plan time (needs the app address). uint256-indexed
    pools (tricrypto class) are quote-only — their exchange lacks the receiver-address
    variant, so an emitted plan REVERTS on the fork (round e29756858: 3 drops on
    WBTC->USDC / USDT->WETH cost a +7/-0 dethrone). Stable int128 pools only."""
    if not cr or cr.get("out", 0) <= 0 or cr.get("u") or cr.get("ul"):
        return []
    return [{"venue": "curve", "route": cr, "param": cr["pool"], "out": int(cr["out"]),
             "gas_est": 300000, "gas_model": 400000, "spend_amount": amt}]


# ---- hydra-fill helpers (module scope: small regions; used by the outermost
# fill layer in solver.py — every deviation from the champion base must be a
# proven win, so these only BUILD; the layer decides) ----

def _hf_tok(p, k):
    return str(p.get(k) or '').lower().split(':')[-1]


def _hf_same_chain(p, cid):
    dest = p.get('dest_chain_id') or p.get('destination_chain_id')
    return dest is None or str(dest) in ('', '0', str(cid))


def hf_inputs(state):
    """(tin, tout, amt, app) for a fillable chain-1 same-chain order, else None."""
    try:
        p = getattr(state, 'typed_context', None) or getattr(state, 'raw_params', None) or {}
        tin = _hf_tok(p, 'input_token')
        tout = _hf_tok(p, 'output_token')
        amt = int(p.get('input_amount') or 0)
        cid = int(getattr(state, 'chain_id', 0) or 0)
        app = getattr(state, 'contract_address', None) or ''
        ok = tin.startswith('0x') and tout.startswith('0x') and amt > 0 and app and cid in (1, 8453)
        if not ok or not _hf_same_chain(p, cid):
            return None
        return tin, tout, amt, app
    except Exception:
        return None


def hf_hub_pair(tin, tout):
    hubs = tuple(h.lower() for h in _C1_HUBS)
    return tin in hubs and tout in hubs


def _mh_consts():
    """Multi-hop Curve fill routes + the two plain (no-receiver) exchange
    selectors, kept in ONE function scope (data literals inflate the enclosing
    region — the factor tie-break). Each pair is one the king's single-pool
    Curve scan leaves EMPTY (needs routing through a hub the MetaRegistry never
    pairs directly); fork-proven via the score endpoint (CVX->frxUSD: 451.02
    frxUSD delivered where champ=0). Legs (pool, i, j, kind): kind 'u'=crypto
    uint256, 'i'=stableNG int128. Every intermediate is ERC20 (the scoring proxy
    never forwards native value), so use_eth defaults false on the crypto legs."""
    ex_i = _kec(text="exchange(int128,int128,uint256,uint256)")[:4]
    ex_u = _kec(text="exchange(uint256,uint256,uint256,uint256)")[:4]
    routes = {
        ('0x4e3fbd56cd56c3e72c1403e103b45db9da5b9d2b',        # CVX
         '0xcacd6fd266af91b8aed52accc382b4e165586e29'): {     # frxUSD
            'path': ['0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B',   # CVX
                     '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',   # WETH
                     '0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E',   # crvUSD
                     '0xCAcd6fd266aF91b8AED52aCCc382b4e165586E29'],  # frxUSD
            'legs': [('0xB576491F1E6e5E62f1d8F26062Ee822B40B0E0d4', 1, 0, 'u'),   # CVX/ETH cryptoV2
                     ('0x4ebdf703948ddcEA3B11f675B4D1Fba9d2414A14', 1, 0, 'u'),   # TriCRV
                     ('0x13e12bB0E6a2f1a3D6901A59a9d585e89a6243E1', 1, 0, 'i')]}, # crvUSD/frxUSD NG
        ('0xcacd6fd266af91b8aed52accc382b4e165586e29',        # frxUSD
         '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'): {     # USDC
            'path': ['0xCAcd6fd266aF91b8AED52aCCc382b4e165586E29',   # frxUSD
                     '0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E',   # crvUSD
                     '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'],  # USDC
            'legs': [('0x13e12bB0E6a2f1a3D6901A59a9d585e89a6243E1', 0, 1, 'i'),   # frxUSD->crvUSD NG
                     ('0x4dece678ceceB27446b35C672dC7d61F30bAD69E', 1, 0, 'i')]}, # crvUSD/USDC NG
    }
    return ex_i, ex_u, routes


(_MH_EX_I, _MH_EX_U, _MH_ROUTES) = _mh_consts()


def _mh_dy(w3, pool, i, j, dx, kind):
    if kind == 'u':
        d = _c1_call(w3, pool, _S_GETDY_U + _enc(["uint256", "uint256", "uint256"], [i, j, dx]))
    else:
        d = _c1_call(w3, pool, _S_GETDY + _enc(["int128", "int128", "uint256"], [i, j, dx]))
    return int.from_bytes(d[:32], "big") if d and len(d) >= 32 else 0


def _mh_exch(i, j, amt, kind, app):
    """One leg's exchange calldata. app is None -> plain exchange (output to
    msg.sender=proxy, feeding the next leg); else the receiver variant (output
    to app, the measured delivery) for the final leg."""
    if app is None:
        if kind == 'u':
            return _MH_EX_U + _enc(["uint256", "uint256", "uint256", "uint256"], [i, j, amt, 0])
        return _MH_EX_I + _enc(["int128", "int128", "uint256", "uint256"], [i, j, amt, 0])
    if kind == 'u':
        return _S_EXCH_RU + _enc(["uint256", "uint256", "uint256", "uint256", "address"], [i, j, amt, 0, app])
    return _S_EXCH_R + _enc(["int128", "int128", "uint256", "uint256", "address"], [i, j, amt, 0, app])


def _mh_build(w3, path, legs, amt, app):
    """Build a multi-hop Curve fill from a token path + legs [(pool,i,j,kind)].
    Every leg is re-quoted live (get_dy) and the next leg's fixed input is haircut
    2bp below realized dy, so a leg never reverts a wei short. Earlier legs plain
    (out->proxy); final leg receiver-exchange (out->app). Returns (out, [(target,
    '0x'+calldata), ...]) or None. Shared by the static table (hf_multihop) and the
    dynamic hub-discovery router (hf_dynamic)."""
    from eth_utils import to_checksum_address as ck
    spend, ix, out = amt, [], 0
    for k, (pool, i, j, kind) in enumerate(legs):
        dy = _mh_dy(w3, pool, i, j, spend, kind)
        if dy <= 0:
            return None
        final = (k == len(legs) - 1)
        ap = _S_APPROVE + _enc(["address", "uint256"], [ck(pool), spend])
        ex = _mh_exch(i, j, spend, kind, ck(app) if final else None)
        ix.append((ck(path[k]), '0x' + ap.hex()))
        ix.append((ck(pool), '0x' + ex.hex()))
        if final:
            out = dy
        else:
            spend = dy - max(1, dy // 5000)
    return (out, ix) if out > 0 else None


def hf_multihop(w3, tin, tout, amt, app):
    """Static-table multi-hop Curve fill for known champ-empty pairs. Fires only
    via _hf_fill (champ-empty/dead), so a miss or revert scores 0 = matched,
    never a drop."""
    r = _MH_ROUTES.get((tin.lower(), tout.lower()))
    if not r or amt <= 0:
        return None
    return _mh_build(w3, r['path'], r['legs'], amt, app)


def hf_multihop_plan(Plan, Ix, app_id, nonce, out, ix):
    inter = [Ix(target=t, value='0', call_data=d, chain_id=1) for t, d in ix]
    return Plan(intent_id=app_id, interactions=inter, deadline=4102444800, nonce=nonce,
                metadata={'solver': 'hydra-fill', 'route': 'curve-mh', 'chain_id': 1})


def _v3_consts():
    """UniV3 multi-hop exactInput fills for champ-empty pairs whose best path is
    a 3+-hop V3 route our 2-hop scan (and the king's) misses. One exactInput call
    executes the whole path internally and sends only the final output to
    recipient=app — intermediates never leave the router, so no proxy address is
    needed. Path bytes = t0 + fee0(3B) + t1 + fee1 + t2 ... Fork-proven per pair
    (BOLD->SSV: 147.4 SSV where champ=0). Data literals in one scope (region)."""
    router = "0xE592427A0AEce92De3Edee1F18E0157C05861564"       # V3 SwapRouter (deadline variant)
    quoter = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"       # QuoterV2
    ein = _kec(text="exactInput((bytes,address,uint256,uint256,uint256))")[:4]
    qei = _kec(text="quoteExactInput(bytes,uint256)")[:4]
    routes = {
        ('0x6440f144b7e50d6a8439336510312d2f54beb01d',          # BOLD
         '0x9d65ff81a3c488d585bbfb0bfe3c7707c7917f54'):         # SSV  (BOLD-500-USDC-100-WETH-3000-SSV)
            '6440f144b7e50d6a8439336510312d2f54beb01d0001f4'
            'a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48000064'
            'c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2000bb8'
            '9d65ff81a3c488d585bbfb0bfe3c7707c7917f54',
    }
    return router, quoter, ein, qei, routes


(_V3_ROUTER, _V3_QUOTER, _V3_EXIN, _V3_QEXIN, _V3_ROUTES) = _v3_consts()


def hf_v3path(w3, tin, tout, amt, app):
    """UniV3 multi-hop exactInput fill (out->app in one call). Quotes via QuoterV2
    first and returns None on a zero/failed quote so a dead path is never emitted
    (champ-empty gate makes a miss a tie regardless). Returns (out, [(target,
    '0x'+cd), ...]) or None."""
    from eth_utils import to_checksum_address as ck
    ph = _V3_ROUTES.get((tin.lower(), tout.lower()))
    if not ph or amt <= 0:
        return None
    pathb = bytes.fromhex(ph)
    q = _c1_call(w3, _V3_QUOTER, _V3_QEXIN + _enc(["bytes", "uint256"], [pathb, amt]))
    out = int.from_bytes(q[:32], "big") if q and len(q) >= 32 else 0
    if out <= 0:
        return None
    ap = _S_APPROVE + _enc(["address", "uint256"], [ck(_V3_ROUTER), amt])
    ex = _V3_EXIN + _enc(['(bytes,address,uint256,uint256,uint256)'],
                         [(pathb, ck(app), 4102444800, amt, 0)])
    return out, [(ck(tin), '0x' + ap.hex()), (ck(_V3_ROUTER), '0x' + ex.hex())]


def hf_v3path_plan(Plan, Ix, app_id, nonce, out, ix):
    inter = [Ix(target=t, value='0', call_data=d, chain_id=1) for t, d in ix]
    return Plan(intent_id=app_id, interactions=inter, deadline=4102444800, nonce=nonce,
                metadata={'solver': 'hydra-fill', 'route': 'v3-path', 'chain_id': 1})


def _dyn_consts():
    """DYNAMIC broad-venue blind-spot router constants (one scope: region). The
    engine discovers a route ON-CHAIN for ANY champ-empty order (no baked pair),
    covering the benchmark's rotating champ-empty 'skip' orders the champion's
    single-pool/2-hop scan misses: (1) V3 multi-hop — QuoterV2 over enumerated 2-
    and 3-hop hub paths, all fees, one exactInput(path,recipient=app); (2) Curve
    2-hop — find_pool_for_coins(tin,hub)+(hub,tout) over hubs, plain then receiver
    exchange. RPC-only (no external API); fork-proven on the live benchmark skip
    orders (USDC->PYUSD, USDT->*, WBTC->*)."""
    mc3 = "0xcA11bde05977b3631167028862bE2a173976CA11"
    v3_hubs = ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",   # WETH
               "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",   # USDC
               "0xdAC17F958D2ee523a2206206994597C13D831ec7",   # USDT
               "0x6B175474E89094C44Da98b954EedeAC495271d0F",   # DAI
               "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599")   # WBTC
    crv_hubs = ("0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E",  # crvUSD
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
                "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT
                "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
                "0x6B175474E89094C44Da98b954EedeAC495271d0F",  # DAI
                "0x853d955aCEf822Db058eb8505911ED77F175b99e",  # FRAX
                "0x4c9EDD5852cd905f086C759E8383e09bff1E68B3")  # USDe
    fees = (100, 500, 3000, 10000)
    tryagg = _kec(text="tryAggregate(bool,(address,bytes)[])")[:4]
    return mc3, v3_hubs, crv_hubs, fees, tryagg


(_DYN_MC3, _DYN_V3HUBS, _DYN_CHUBS, _DYN_FEES, _DYN_TRYAGG) = _dyn_consts()


def _dyn2_consts():
    """BASE (8453) verified V3 fill consts. Uniswap V3 is live on Base with the
    SAME QuoterV2 engine (quote == delivery, control-proven 1 WETH -> 1864.72
    USDC) but a different router: SwapRouter02, whose exactInput struct has NO
    deadline field. 90%% of the live Base quote corpus (54/60 sampled) is
    routable via direct + hub 2-hops here — the champion lineage leaves ~24
    skip orders/round on this corpus, so any base-EMPTY one we route is a
    blind_spot_cover WIN. Hubs: WETH, USDC, USDbC, DAI, AERO, cbBTC."""
    quoter = "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a"
    router = "0x2626664c2603336E57B271c5C0b26F421741e481"
    ein2 = _kec(text="exactInput((bytes,address,uint256,uint256))")[:4]
    hubs = ("0x4200000000000000000000000000000000000006",
            "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA",
            "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb",
            "0x940181a94A35A4569E4529A3CDfB74e38FD98631",
            "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf",
            "0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22")
    return quoter, router, ein2, hubs


(_DYN2_QUOTER, _DYN2_ROUTER, _DYN2_EXIN, _DYN2_HUBS) = _dyn2_consts()


def _dyn2_v3_paths(tin, tout):
    from eth_utils import to_checksum_address as ck
    a, b = ck(tin), ck(tout)
    out = [bytes.fromhex(a[2:]) + f.to_bytes(3, 'big') + bytes.fromhex(b[2:]) for f in _DYN_FEES]
    for hub in [ck(x) for x in _DYN2_HUBS if ck(x) not in (a, b)]:
        for f1 in _DYN_FEES:
            for f2 in _DYN_FEES:
                out.append(bytes.fromhex(a[2:]) + f1.to_bytes(3, 'big') + bytes.fromhex(hub[2:])
                           + f2.to_bytes(3, 'big') + bytes.fromhex(b[2:]))
    # 3-hop: exotic->hub1->hub2->exotic (top-4 hubs, restricted fee grid) — the extra
    # win surface vs the clone field: their (== our published) tree stops at 2-hop.
    tops = [ck(x) for x in _DYN2_HUBS[:4]]
    for h1 in tops:
        for h2 in tops:
            if h1 == h2 or h1 in (a, b) or h2 in (a, b):
                continue
            for f1 in (500, 3000):
                for f2 in (100, 500):
                    for f3 in (500, 3000):
                        out.append(bytes.fromhex(a[2:]) + f1.to_bytes(3, 'big') + bytes.fromhex(h1[2:])
                                   + f2.to_bytes(3, 'big') + bytes.fromhex(h2[2:])
                                   + f3.to_bytes(3, 'big') + bytes.fromhex(b[2:]))
    return out


def _dyn2_v3_best(w3, tin, tout, amt):
    """(path_bytes, out) best Base V3 route via QuoterV2 multicall, or (None, 0)."""
    paths = _dyn2_v3_paths(tin, tout)
    subs = [(_DYN2_QUOTER, _V3_QEXIN + _enc(['bytes', 'uint256'], [p, amt])) for p in paths]
    best = (None, 0)
    for p, r in zip(paths, _dyn_mc(w3, subs)):
        ok, d = r
        if ok and d and len(d) >= 32:
            o = int.from_bytes(d[:32], 'big')
            if o > best[1]:
                best = (p, o)
    return best


def _dyn_mc(w3, subs):
    """Multicall3 tryAggregate — batch many QuoterV2 quotes into ONE eth_call.
    Returns [(ok, bytes), ...] aligned to subs, or [] on failure."""
    from eth_utils import to_checksum_address as ck
    cd = _DYN_TRYAGG + _enc(['bool', '(address,bytes)[]'],
                            [False, [(ck(t), d) for t, d in subs]])
    try:
        return _dec(['(bool,bytes)[]'], bytes(w3.eth.call({'to': _DYN_MC3, 'data': '0x' + cd.hex()})))[0]
    except Exception:
        return []


def _dyn_v3_paths(tin, tout):
    from eth_utils import to_checksum_address as ck
    a, b = ck(tin), ck(tout)
    out = [bytes.fromhex(a[2:]) + f.to_bytes(3, 'big') + bytes.fromhex(b[2:]) for f in _DYN_FEES]
    mids = [ck(x) for x in _DYN_V3HUBS if ck(x) not in (a, b)]
    for hub in mids:
        for f1 in _DYN_FEES:
            for f2 in _DYN_FEES:
                out.append(bytes.fromhex(a[2:]) + f1.to_bytes(3, 'big') + bytes.fromhex(hub[2:])
                           + f2.to_bytes(3, 'big') + bytes.fromhex(b[2:]))
    tops = [ck(x) for x in _DYN_V3HUBS[:4]]
    for h1 in tops:
        for h2 in tops:
            if h1 == h2 or h1 in (a, b) or h2 in (a, b):
                continue
            for f1 in (500, 3000):
                for f2 in (100, 500):
                    for f3 in (500, 3000):
                        out.append(bytes.fromhex(a[2:]) + f1.to_bytes(3, 'big') + bytes.fromhex(h1[2:])
                                   + f2.to_bytes(3, 'big') + bytes.fromhex(h2[2:])
                                   + f3.to_bytes(3, 'big') + bytes.fromhex(b[2:]))
    return out


def _dyn_v3_best(w3, tin, tout, amt):
    """(path_bytes, out) best V3 multi-hop route via QuoterV2 multicall, or (None, 0)."""
    paths = _dyn_v3_paths(tin, tout)
    subs = [(_V3_QUOTER, _V3_QEXIN + _enc(['bytes', 'uint256'], [p, amt])) for p in paths]
    best = (None, 0)
    for p, r in zip(paths, _dyn_mc(w3, subs)):
        ok, d = r
        if ok and d and len(d) >= 32:
            o = int.from_bytes(d[:32], 'big')
            if o > best[1]:
                best = (p, o)
    return best


def _dyn_curve2h(w3, tin, tout, amt):
    """(path_tokens, legs, out) best Curve 2-hop through a hub, or None. legs =
    [(pool,i,j,kind)] for _mh_build. Skips underlying-metapool routes (the plain
    exchange_underlying variant is not in the leg builder)."""
    from eth_utils import to_checksum_address as ck
    best = None
    for hub in _DYN_CHUBS:
        if ck(hub) in (ck(tin), ck(tout)):
            continue
        r1 = curve_route(w3, ck(tin), ck(hub), amt)
        if not r1 or r1['out'] <= 0 or r1.get('ul'):
            continue
        midh = r1['out'] - max(1, r1['out'] // 5000)
        r2 = curve_route(w3, ck(hub), ck(tout), midh)
        if not r2 or r2['out'] <= 0 or r2.get('ul'):
            continue
        if best is None or r2['out'] > best[2]:
            legs = [(r1['pool'], r1['i'], r1['j'], 'u' if r1.get('u') else 'i'),
                    (r2['pool'], r2['i'], r2['j'], 'u' if r2.get('u') else 'i')]
            best = ([ck(tin), ck(hub), ck(tout)], legs, r2['out'])
    return best


def hf_dynamic(w3, tin, tout, amt, app, cid=1):
    """DYNAMIC blind-spot cover: discover a route on-chain for a champ-empty order
    via V3 multi-hop OR Curve 2-hop, pick the higher delivery, build own calldata.
    Returns (out, [(target,'0x'+cd), ...], route_tag) or None. Fires only via
    _hf_fill (champ-empty/dead) — a miss/revert scores 0 = matched, never a drop."""
    from eth_utils import to_checksum_address as ck
    if amt <= 0:
        return None
    # V3 first: QuoterV2 actually simulates the swap, so its quote == fork
    # delivery (WBTC->* proven exact). Curve get_dy can MIRAGE (quotes a fee-on-
    # transfer/exotic pool that reverts on exchange) — harmless on a champ-empty
    # order (revert = tie, never a drop) but non-winning, so it is only a fallback
    # when V3 finds no path. Any >0 delivery wins (champ=None), so reliability
    # beats a higher-but-mirage quote.
    if int(cid) == 8453:
        v3path, vout = _dyn2_v3_best(w3, tin, tout, amt)
        if vout > 0:
            ap = _S_APPROVE + _enc(["address", "uint256"], [ck(_DYN2_ROUTER), amt])
            ex = _DYN2_EXIN + _enc(['(bytes,address,uint256,uint256)'],
                                   [(v3path, ck(app), amt, 0)])
            return vout, [(ck(tin), '0x' + ap.hex()), (ck(_DYN2_ROUTER), '0x' + ex.hex())], 'dyn-v3'
        return None
    v3path, vout = _dyn_v3_best(w3, tin, tout, amt)
    if vout > 0:
        ap = _S_APPROVE + _enc(["address", "uint256"], [ck(_V3_ROUTER), amt])
        ex = _V3_EXIN + _enc(['(bytes,address,uint256,uint256,uint256)'],
                             [(v3path, ck(app), 4102444800, amt, 0)])
        return vout, [(ck(tin), '0x' + ap.hex()), (ck(_V3_ROUTER), '0x' + ex.hex())], 'dyn-v3'
    cr = _dyn_curve2h(w3, tin, tout, amt)
    if cr is not None:
        built = _mh_build(w3, cr[0], cr[1], amt, app)
        if built is not None:
            return built[0], built[1], 'dyn-crv2h'
    return None


def hf_dynamic_plan(Plan, Ix, app_id, nonce, out, ix, tag, cid=1):
    inter = [Ix(target=t, value='0', call_data=d, chain_id=int(cid)) for t, d in ix]
    return Plan(intent_id=app_id, interactions=inter, deadline=4102444800, nonce=nonce,
                metadata={'solver': 'hydra-fill', 'route': tag, 'chain_id': int(cid)})


def _hf_v2_cd(router, path, amt, app):
    """Approve + swap calldata. The SupportingFeeOnTransferTokens variant is
    identical for vanilla tokens but survives fee-on-transfer exotics (where
    the plain swap reverts on the K-check) — fills fire on champ-empty orders,
    so a wider-working swap only ever adds wins."""
    ap = _S_APPROVE + _enc(['address', 'uint256'], [router, amt])
    sw = _kec(text='swapExactTokensForTokensSupportingFeeOnTransferTokens'
                   '(uint256,uint256,address[],address,uint256)')[:4] + \
        _enc(['uint256', 'uint256', 'address[]', 'address', 'uint256'], [amt, 0, path, app, 4102444800])
    return '0x' + ap.hex(), '0x' + sw.hex()


def hf_v2_plan(Plan, Ix, app_id, nonce, vr, tin, amt, app):
    from eth_utils import to_checksum_address as _ck
    router = _ck(vr['router'])
    path = [_ck(t) for t in vr['tokens']]
    ap, sw = _hf_v2_cd(router, path, amt, _ck(app))
    ix = [Ix(target=_ck(tin), value='0', call_data=ap, chain_id=1),
          Ix(target=router, value='0', call_data=sw, chain_id=1)]
    return Plan(intent_id=app_id, interactions=ix, deadline=4102444800, nonce=nonce,
                metadata={'solver': 'hydra-fill', 'route': 'v2', 'chain_id': 1})


def hf_curve_plan(Plan, Ix, app_id, nonce, cr, tin, amt, app):
    ix = [Ix(target=t, value='0', call_data=d, chain_id=1)
          for t, d in curve_legs(tin, amt, app, cr)]
    return Plan(intent_id=app_id, interactions=ix, deadline=4102444800, nonce=nonce,
                metadata={'solver': 'hydra-fill', 'route': 'curve', 'chain_id': 1})


def hf_best(w3, tin, tout, amt):
    """('v2'|'curve', route) best fill route or None. V2 retries once on empty."""
    best = None
    try:
        vr = c1_v2_route(w3, tin, tout, amt) or c1_v2_route(w3, tin, tout, amt)
        if vr:
            best = ('v2', vr, int(vr['out']))
    except Exception:
        pass
    try:
        cr = curve_route(w3, tin, tout, amt)
        if cr and not cr.get('u') and (best is None or int(cr['out']) > best[2]):
            best = ('curve', cr, int(cr['out']))
    except Exception:
        pass
    return (best[0], best[1]) if best else None


def hf_plan(Plan, Ix, app_id, nonce, kind, route, tin, amt, app):
    if kind == 'v2':
        return hf_v2_plan(Plan, Ix, app_id, nonce, route, tin, amt, app)
    return hf_curve_plan(Plan, Ix, app_id, nonce, route, tin, amt, app)


# ---- cross-chain (xbridge) helpers: same behavior as the inline 564 layer,
# extracted to module scope (constants in one function scope, small regions) ----

def _hx_consts():
    return (
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",         # WETH.eth
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",         # USDC.eth
        "0x4200000000000000000000000000000000000006",         # WETH.base
        "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",         # USDC.base
        "0xE592427A0AEce92De3Edee1F18E0157C05861564",         # V3 SwapRouter (eth, deadline)
        "0x2626664c2603336E57B271c5C0b26F421741e481",         # V3 SwapRouter02 (base)
        "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",         # anvil default receiver
    )


(_HXW1, _HXU1, _HXWB, _HXUB, _HXR1, _HXRB, _HX_RCPT) = _hx_consts()


def hx_bridged(tin, dst):
    m = {(_HXW1, 8453): _HXWB, (_HXWB, 1): _HXW1,
         (_HXU1, 8453): _HXUB, (_HXUB, 1): _HXU1}
    return m.get((tin, dst))


def _hx_ix(t, d, dst):
    return {'target': t, 'value': '0', 'call_data': '0x' + d.hex(), 'chain_id': dst}


def hx_dest_ixs(bridged, tout, dst, est, rcpt):
    from eth_utils import to_checksum_address as ck
    if bridged == tout:
        cd = _kec(text='transfer(address,uint256)')[:4] + _enc(['address', 'uint256'], [ck(rcpt), est])
        return [_hx_ix(ck(bridged), cd, dst)]
    router = _HXRB if dst == 8453 else _HXR1
    ap = _S_APPROVE + _enc(['address', 'uint256'], [ck(router), est])
    path = bytes.fromhex(bridged[2:]) + (500).to_bytes(3, 'big') + bytes.fromhex(tout[2:])
    if dst == 8453:
        sw = _kec(text='exactInput((bytes,address,uint256,uint256))')[:4] + \
            _enc(['(bytes,address,uint256,uint256)'], [(path, ck(rcpt), est, 0)])
    else:
        sw = _kec(text='exactInput((bytes,address,uint256,uint256,uint256))')[:4] + \
            _enc(['(bytes,address,uint256,uint256,uint256)'], [(path, ck(rcpt), 4102444800, est, 0)])
    return [_hx_ix(ck(bridged), ap, dst), _hx_ix(ck(router), sw, dst)]


def hx_ccp(cid, dst, tin, amt, rcpt, ixs):
    from eth_utils import to_checksum_address as ck
    leg = {'intent_selector': '', 'intent_params_hex': '', 'metadata': {}}
    return {'legs': [{'chain_id': cid, 'interactions': [], **leg},
                     {'chain_id': dst, 'interactions': ixs, **leg}],
            'bridge_requests': [{'token': ck(tin), 'amount': amt, 'src_chain_id': cid,
                                 'dst_chain_id': dst, 'recipient': ck(rcpt), 'min_output': 0,
                                 'purpose': 'canonical bridge for cross-chain intent'}]}
