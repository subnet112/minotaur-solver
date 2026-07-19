"""viking_quote — execution-accurate route quoting for the strict-better cover.

Address tables + same-block quoters (QuoterV2 for V3 single/2-hop, getAmountsOut
for V2 constant-product), and the candidate builder v3hop_cover picks from. Each
venue quoter returns ``(out, det)`` where ``det`` is exactly the tuple the
matching viking_build builder consumes. Split out of viking_v3hop so each named
region stays small (factorization discipline); pure lift-only quoting."""
import logging

logger = logging.getLogger('solver')

_FEES = (100, 500, 3000, 10000)


def _tabs():
    quoters = {1: '0x61fFE014bA17989E743c5F6cB21bF9697530B21e',
               8453: '0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a'}
    routers = {1: '0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45',
               8453: '0x2626664c2603336E57B271c5C0b26F421741e481'}
    v2routers = {1: '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
                 8453: '0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24'}
    hubs = {1: ('0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',
                '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',
                '0xdac17f958d2ee523a2206206994597c13d831ec7',
                '0x6b175474e89094c44da98b954eedeac495271d0f',
                '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599'),
            8453: ('0x4200000000000000000000000000000000000006',
                   '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913',
                   '0x50c5725949a6f0c72e6c4a641f24049a917db0cb',
                   '0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca',
                   '0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22')}
    v2hubs = {1: ('0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',
                  '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'),
              8453: ('0x4200000000000000000000000000000000000006',
                     '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913')}
    return quoters, routers, v2routers, hubs, v2hubs


_QUOTERS, _ROUTER02, _V2ROUTER, _HUBS, _V2HUBS = _tabs()


def _q_single(w3, chain, tin, tout, fee, amt):
    q = _QUOTERS.get(int(chain))
    if not q:
        return 0
    def _run():
        from eth_abi import encode as _enc, decode as _dec
        from eth_utils import to_checksum_address as _ck
        data = bytes.fromhex('c6a5026a') + _enc(
            ['(address,address,uint256,uint24,uint160)'],
            [(_ck(tin), _ck(tout), int(amt), int(fee), 0)])
        try:
            r = w3.eth.call({'to': _ck(q), 'data': '0x' + data.hex()})
            return int(_dec(['uint256', 'uint160', 'uint32', 'uint256'], bytes(r))[0])
        except Exception:
            return 0
    return _run()


def _q_path(w3, chain, path, amt):
    q = _QUOTERS.get(int(chain))
    if not q:
        return 0
    def _run():
        from eth_abi import encode as _enc
        from eth_utils import to_checksum_address as _ck
        data = bytes.fromhex('cdca1753') + _enc(['bytes', 'uint256'], [path, int(amt)])
        try:
            r = bytes(w3.eth.call({'to': _ck(q), 'data': '0x' + data.hex()}))
            return int.from_bytes(r[0:32], 'big') if len(r) >= 32 else 0
        except Exception:
            return 0
    return _run()


def _v2_out(w3, chain, path, amt):
    r = _V2ROUTER.get(int(chain))
    if not r:
        return 0
    def _run():
        from eth_abi import encode as _enc, decode as _dec
        from eth_utils import to_checksum_address as _ck
        data = bytes.fromhex('d06ca61f') + _enc(
            ['uint256', 'address[]'], [int(amt), [_ck(a) for a in path]])
        try:
            raw = w3.eth.call({'to': _ck(r), 'data': '0x' + data.hex()})
            outs = _dec(['uint256[]'], bytes(raw))[0]
            return int(outs[-1]) if outs else 0
        except Exception:
            return 0
    return _run()


def _v3_direct(w3, chain, tin, tout, amt):
    """Best V3 direct single-hop: (out, (fee,)) or None. det=(fee,)."""
    best = None
    for fee in _FEES:
        o = _q_single(w3, chain, tin, tout, fee, amt)
        if o > 0 and (best is None or o > best[0]):
            best = (o, (fee,))
    return best


def _v3_2hop(w3, chain, tin, tout, amt):
    """Best V3 2-hop via a hub: (out, (hub, f1, f2)) or None. det=(hub,f1,f2)."""
    def _via(hub):
        b = None
        for f1 in _FEES:
            l1 = _q_single(w3, chain, tin, hub, f1, amt)
            if l1 <= 0:
                continue
            for f2 in _FEES:
                l2 = _q_single(w3, chain, hub, tout, f2, l1)
                if l2 > 0 and (b is None or l2 > b[0]):
                    b = (l2, (hub, f1, f2))
        return b
    best = None
    for hub in _HUBS.get(int(chain), ()):
        if hub == tin or hub == tout:
            continue
        r = _via(hub)
        if r is not None and (best is None or r[0] > best[0]):
            best = r
    return best


def _v2_paths(chain, tin, tout):
    """[direct] + [via-hub] V2 paths, direct FIRST (so it wins output ties)."""
    paths = [[tin, tout]]
    for hub in _V2HUBS.get(int(chain), ()):
        if hub != tin and hub != tout:
            paths.append([tin, hub, tout])
    return paths


def _v2_scan(w3, chain, tin, tout, amt):
    """Best V2 route over direct + via-hub paths: (out, path_list) or None."""
    best = None
    for path in _v2_paths(chain, tin, tout):
        o = _v2_out(w3, chain, path, amt)
        if o > 0 and (best is None or o > best[0]):
            best = (o, path)
    return best


def _v2_best(w3, chain, tin, tout, amt):
    """Best V2 route (direct or via hub): (out, path_list) or None. det=path_list."""
    return _v2_scan(w3, chain, tin, tout, amt)


def candidates(w3, chain, tin, tout, amt):
    """All strict-better route candidates for this order: [(out, kind, det), ...],
    in v3d, v3h, v2 order (the tie-break order v3hop_cover's max() relies on)."""
    out = []
    for kind, fn in (('v3d', _v3_direct), ('v3h', _v3_2hop), ('v2', _v2_best)):
        r = fn(w3, chain, tin, tout, amt)
        if r is not None:
            out.append((r[0], kind, r[1]))
    return out
