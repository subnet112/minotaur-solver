_DR_UNSET = object()
import json as _dl_json, os as _dl_os, urllib.request as _dl_url
from minotaur_subnet.shared.types import ExecutionPlan as _DLPlan, Interaction as _DLIx

def _dl_consts():
    weth = '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'
    usdc = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'
    maj = {t.lower() for t in (weth, usdc, '0x6B175474E89094C44Da98b954EedeAC495271d0F', '0xdAC17F958D2ee523a2206206994597C13D831ec7', '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599')}
    return ('0x61fFE014bA17989E743c5F6cB21bF9697530B21e', '0xE592427A0AEce92De3Edee1F18E0157C05861564', weth, usdc, maj, (100, 500, 3000, 10000), '04e45aaf', '414bf389', 'b858183f', 'c04b8d59', ('ac9650d8', '5ae401dc'))
_ETH_QUOTER, _ETH_ROUTER, _ETH_WETH, _ETH_USDC, _ETH_MAJ, _DL_FEES, _SEL_EIS_02, _SEL_EIS, _SEL_EI_02, _SEL_EI, _SEL_MC = _dl_consts()

def _dl_sel(sig):
    from eth_utils import keccak
    return '0x' + keccak(sig.encode())[:4].hex()

def _dl_ethcall(url, to, data):
    body = _dl_json.dumps({'jsonrpc': '2.0', 'method': 'eth_call', 'params': [{'to': to, 'data': data}, 'latest'], 'id': 1}).encode()
    hdrs = {'content-type': 'application/json', 'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'}
    try:
        r = _dl_url.urlopen(_dl_url.Request(url, data=body, headers=hdrs), timeout=9)
        res = _dl_json.load(r).get('result')
        return res if res and res != '0x' else None
    except Exception:
        return None

def _dl_qsingle(url, tin, tout, amt, fee):
    from eth_abi import encode
    data = _dl_sel('quoteExactInputSingle((address,address,uint256,uint24,uint160))') + encode(['(address,address,uint256,uint24,uint160)'], [(tin, tout, int(amt), fee, 0)]).hex()
    r = _dl_ethcall(url, _ETH_QUOTER, data)
    return int(r[2:66], 16) if r and len(r) >= 66 else 0

def _dl_qpath(url, tokens, fees, amt):

    def _dz13():
        data = _dl_sel('quoteExactInput(bytes,uint256)') + encode(['bytes', 'uint256'], [b, int(amt)]).hex()
        r = _dl_ethcall(url, _ETH_QUOTER, data)
        return (int(r[2:66], 16) if r and len(r) >= 66 else 0,)
        return _DR_UNSET
    from eth_abi import encode
    b = b''
    for i, t in enumerate(tokens):
        b += bytes.fromhex(t[2:])
        if i < len(fees):
            b += int(fees[i]).to_bytes(3, 'big')
    _r_dz13 = _dz13()
    if _r_dz13 is not _DR_UNSET:
        return _r_dz13[0]

def _dl_best_route(url, tin, tout, amt):
    best = (0, None)
    for f in (500, 3000, 10000):
        o = _dl_qsingle(url, tin, tout, amt, f)
        if o > best[0]:
            best = (o, ('single', f))
    return best

def _dl_eth_ix(tin, tout, amt, recipient, route):

    def _dz12(amt, recipient, route, tin, tout):
        fee = route[1][1]
        swap = _dl_sel('exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))') + encode(['(address,address,uint24,address,uint256,uint256,uint256,uint160)'], [(tin, tout, int(fee), recipient, 9999999999, amt, 1, 0)]).hex()
        return (fee, swap)

    def _dz11(amt, route):
        amt = int(amt)
        approve = '0x095ea7b3' + _ETH_ROUTER[2:].rjust(64, '0').lower() + amt.to_bytes(32, 'big').hex()
        kind = route[1][0]
        return (amt, approve, kind)

    def _dz10():
        nonlocal swap
        b = b''
        for i, t in enumerate(tokens):
            b += bytes.fromhex(t[2:])
            if i < len(fees):
                b += int(fees[i]).to_bytes(3, 'big')
        swap = _dl_sel('exactInput((bytes,address,uint256,uint256,uint256))') + encode(['(bytes,address,uint256,uint256,uint256)'], [(b, recipient, 9999999999, amt, 1)]).hex()
    from eth_abi import encode
    amt, approve, kind = _dz11(amt, route)
    if kind == 'single':
        fee, swap = _dz12(amt, recipient, route, tin, tout)
    else:
        tokens, fees = (route[1][1], route[1][2])
        _dz10()
    return [(tin, approve), (_ETH_ROUTER, swap)]

def _dl_flatten(ix):
    """Interaction calldatas, unwrapping one level of multicall(bytes[])."""

    def _dz9():
        if cd[:8] in _SEL_MC:
            try:
                payload = bytes.fromhex(cd[8:])
                calls = decode(['bytes[]'], payload[32:] if cd[:8] == '5ae401dc' else payload)[0]
                for c in calls:
                    h = c.hex()
                    if len(h) >= 8:
                        flat.append(h)
            except Exception:
                flat.append(cd)
        else:
            flat.append(cd)
    from eth_abi import decode
    datas = []
    for i in ix:
        cd = str(getattr(i, 'call_data', getattr(i, 'calldata', '')) or '')
        if cd.startswith('0x'):
            cd = cd[2:]
        if len(cd) >= 8:
            datas.append(cd)
    flat = []
    for cd in datas:
        _dz9()
    return flat

def _dl_decode_path(body, sel, url):
    """Re-quote a decoded exactInput (path) champion swap."""

    def _dz8(body, sel):
        path, _rec, amt, _mo = decode(['(bytes,address,uint256,uint256)'], body)[0] if sel == _SEL_EI_02 else decode(['(bytes,address,uint256,uint256,uint256)'], body)[0][:4]
        toks, fees = ([], [])
        p = path if isinstance(path, (bytes, bytearray)) else bytes.fromhex(str(path))
        return (_mo, _rec, amt, fees, p, path, toks)

    def _dz7():
        o = 0
        while o + 20 <= len(p):
            toks.append('0x' + p[o:o + 20].hex())
            o += 20
            if o + 3 <= len(p):
                fees.append(int.from_bytes(p[o:o + 3], 'big'))
                o += 3
        return (_dl_qpath(url, toks, fees, amt),)
        return _DR_UNSET
    from eth_abi import decode
    _mo, _rec, amt, fees, p, path, toks = _dz8(body, sel)
    _r_dz7 = _dz7()
    if _r_dz7 is not _DR_UNSET:
        return _r_dz7[0]

def _dl_decode_one(cd, url):
    """Decode+re-quote one calldata. Returns ('ANSWER', q_or_None) if it's a UniV3
    swap (q>0 -> its output; else None so caller DEFERS, never treats as blind),
    ('SWAP', None) if a swap is present but undecodable, or ('SKIP', None)."""

    def _dz6(cd):
        sel = cd[:8]
        body = bytes.fromhex(cd[8:]) if len(cd) > 8 else b''
        return (body, sel)

    def _dz5(body, url):
        tin, tout, fee, _r, amt, _m, _s = decode(['(address,address,uint24,address,uint256,uint256,uint160)'], body)[0]
        q = _dl_qsingle(url, tin, tout, amt, fee)
        return (_m, _r, _s, amt, fee, q, tin, tout)

    def _dz4():
        nonlocal q
        _r_dz3 = _dz3()
        if _r_dz3 is not _DR_UNSET:
            return (_r_dz3[0],)
        if sel in (_SEL_EI_02, _SEL_EI):
            q = _dl_decode_path(body, sel, url)
            return (('ANSWER', q if q > 0 else None),)
        return _DR_UNSET

    def _dz3():
        nonlocal _m, _r, _s, amt, fee, q, tin, tout
        if sel == _SEL_EIS:
            tin, tout, fee, _r, _d, amt, _m, _s = decode(['(address,address,uint24,address,uint256,uint256,uint256,uint160)'], body)[0]
            q = _dl_qsingle(url, tin, tout, amt, fee)
            return (('ANSWER', q if q > 0 else None),)
        return _DR_UNSET
    from eth_abi import decode
    body, sel = _dz6(cd)
    try:
        if sel == _SEL_EIS_02:
            _m, _r, _s, amt, fee, q, tin, tout = _dz5(body, url)
            return ('ANSWER', q if q > 0 else None)
        _r_dz4 = _dz4()
        if _r_dz4 is not _DR_UNSET:
            return _r_dz4[0]
    except Exception:
        return ('SWAP', None)
    return ('SKIP', None)

def _dl_champ_out(base_plan, url):
    """The champion's OWN delivered output for this order (FAIL-CLOSED anchor).
    0 = champion serves NOTHING (blind, we may cover); int = decoded UniV3 output;
    None = serves via a venue we can't read -> caller DEFERS (never a regression)."""
    if base_plan is None:
        return 0
    ix = getattr(base_plan, 'interactions', None) or []
    if not ix:
        return 0
    for cd in _dl_flatten(ix):
        kind, val = _dl_decode_one(cd, url)
        if kind == 'ANSWER':
            return val
    return None

def _dl_override(intent, state, rp, url, tin, tout, amt, co):
    """Build our override plan iff we STRICTLY beat the champion's output `co` (>30bps)
    and have a valid recipient. Returns a _DLPlan or None (None -> caller defers to
    champion). Split out of _dl_route1 so each region stays small (un-factorable)."""

    def _dz2():
        if recip.startswith('0x') and len(recip) == 42:
            pairs = _dl_eth_ix(tin, tout, amt, recip, (out, route))
            ix = [_DLIx(target=t, value='0', call_data=cd, chain_id=1) for t, cd in pairs]
            return (_DLPlan(intent_id=getattr(intent, 'app_id', '') or '', interactions=ix, deadline=9999999999, nonce=int(getattr(state, 'nonce', 0) or 0), metadata={'solver': 'min_router-fc', 'chain_id': 1}),)
        return _DR_UNSET
    out, route = _dl_best_route(url, tin, tout, amt)
    if out > 0 and route and (out * 10000 > co * (10000 + 30)):
        recip = str(getattr(state, 'contract_address', '') or rp.get('receiver', '') or '').lower()
        _r_dz2 = _dz2()
        if _r_dz2 is not _DR_UNSET:
            return _r_dz2[0]
    return None