"""viking_v3hop — strict-better route cover (V3 direct + V3 2-hop + V2).

Re-quotes the engine's OWN final route (the floor) and the best of:
  * Uniswap V3 direct single-hop across all fee tiers,
  * Uniswap V3 2-hop via a hub (WETH/USDC/USDT/DAI/WBTC etc.),
  * Uniswap V2 direct or 2-hop-via-hub (memecoin / thin pools the V3 quoter
    returns 0 for — ~29 of the live ETH corpus route ONLY on V2),
and serves the best ONLY when it STRICTLY beats the floor. Quotes are
execution-accurate same-block (QuoterV2 for V3, getAmountsOut for V2 constant
product), so the served amount == on-chain delivery at bench. A non-empty base
we cannot decode DEFERS (no blind override). Empty base => floor 0, so any
positive route fills the blind spot => lift-only, never a regression.
"""
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
    """Best V3 direct single-hop: (out, fee) or None."""
    best = None
    for fee in _FEES:
        o = _q_single(w3, chain, tin, tout, fee, amt)
        if o > 0 and (best is None or o > best[0]):
            best = (o, fee)
    return best


def _v3_2hop(w3, chain, tin, tout, amt):
    """Best V3 2-hop via a hub: (out, hub, f1, f2) or None."""
    def _via(hub):
        b = None
        for f1 in _FEES:
            l1 = _q_single(w3, chain, tin, hub, f1, amt)
            if l1 <= 0:
                continue
            for f2 in _FEES:
                l2 = _q_single(w3, chain, hub, tout, f2, l1)
                if l2 > 0 and (b is None or l2 > b[0]):
                    b = (l2, hub, f1, f2)
        return b
    best = None
    for hub in _HUBS.get(int(chain), ()):
        if hub == tin or hub == tout:
            continue
        r = _via(hub)
        if r is not None and (best is None or r[0] > best[0]):
            best = r
    return best


def _v2_best(w3, chain, tin, tout, amt):
    """Best V2 route (direct or via WETH/USDC hub): (out, path_list) or None."""
    best = None
    o = _v2_out(w3, chain, [tin, tout], amt)
    if o > 0:
        best = (o, [tin, tout])
    for hub in _V2HUBS.get(int(chain), ()):
        if hub == tin or hub == tout:
            continue
        o = _v2_out(w3, chain, [tin, hub, tout], amt)
        if o > 0 and (best is None or o > best[0]):
            best = (o, [tin, hub, tout])
    return best


def _dec_v3(cd):
    sel = cd[:10]
    def _sng():
        from eth_abi import decode as _d
        body = bytes.fromhex(cd[10:])
        if sel == '0x04e45aaf':
            t = _d(['(address,address,uint24,address,uint256,uint256,uint160)'], body)[0]
            return ('single', t[0], t[1], t[2], t[4])
        t = _d(['(address,address,uint24,address,uint256,uint256,uint256,uint160)'], body)[0]
        return ('single', t[0], t[1], t[2], t[5])
    def _pth():
        from eth_abi import decode as _d
        body = bytes.fromhex(cd[10:])
        if sel == '0xb858183f':
            t = _d(['(bytes,address,uint256,uint256)'], body)[0]
            return ('path', t[0], t[2])
        t = _d(['(bytes,address,uint256,uint256,uint256)'], body)[0]
        return ('path', t[0], t[3])
    try:
        if sel in ('0x04e45aaf', '0x414bf389'):
            return _sng()
        if sel in ('0xb858183f', '0xc04b8d59'):
            return _pth()
    except Exception:
        return None
    return None


def _dec_v2(cd):
    from eth_abi import decode as _d
    if cd[:10] not in ('0x38ed1739', '0x5c11d795', '0xd06ca61f'):
        return None
    try:
        t = _d(['uint256', 'uint256', 'address[]', 'address', 'uint256'],
               bytes.fromhex(cd[10:]))
        return (list(t[2]), int(t[0]))
    except Exception:
        return None


def _base_out(w3, chain, plan):
    """Re-quoted delivery of the engine's plan: 0 if empty, int if decodable,
    None if non-empty but undecodable (defer)."""
    ix = getattr(plan, 'interactions', None) if plan else None
    if not ix:
        return 0
    def _val():
        cd = ix[-1].call_data or ''
        c = cd if cd.startswith('0x') else '0x' + cd
        v3 = _dec_v3(c)
        if v3 is not None:
            if v3[0] == 'single':
                return _q_single(w3, chain, v3[1], v3[2], v3[3], v3[4])
            return _q_path(w3, chain, v3[1], v3[2])
        v2 = _dec_v2(c)
        if v2 is not None:
            return _v2_out(w3, chain, v2[0], v2[1])
        return None
    return _val()


def _recipient(state, p):
    return (getattr(state, 'contract_address', None)
            or p.get('receiver') or getattr(state, 'owner', None))


def v3hop_cover(solver, intent, state, snapshot, base_plan):
    """Serve the best V3/V2 route ONLY when it strictly beats the re-quoted base."""
    def _ctx():
        chain = int(getattr(state, 'chain_id', 0)
                    or (getattr(snapshot, 'chain_id', 0) if snapshot else 0) or 0)
        if _QUOTERS.get(chain) is None:
            return None
        p = solver._normalized_swap_params(intent, state)
        tin = str(p.get('input_token', '') or '').lower()
        tout = str(p.get('output_token', '') or '').lower()
        amt = int(p.get('input_amount', 0) or 0)
        if not tin or not tout or amt <= 0:
            return None
        w3 = solver._get_web3(chain)
        if w3 is None:
            return None
        return (chain, tin, tout, amt, w3, p)
    try:
        ctx = _ctx()
        if ctx is None:
            return None
        chain, tin, tout, amt, w3, p = ctx
        floor = _base_out(w3, chain, base_plan)
        if floor is None:
            return None
        cands = []
        d = _v3_direct(w3, chain, tin, tout, amt)
        if d is not None:
            cands.append((d[0], 'v3d', (d[1],)))
        h = _v3_2hop(w3, chain, tin, tout, amt)
        if h is not None:
            cands.append((h[0], 'v3h', (h[1], h[2], h[3])))
        v2 = _v2_best(w3, chain, tin, tout, amt)
        if v2 is not None:
            cands.append((v2[0], 'v2', (v2[1],)))
        if not cands:
            return None
        best = max(cands, key=lambda c: c[0])
        if best[0] <= floor:
            return None
        return _serve(intent, state, chain, tin, tout, best, amt, p)
    except Exception:
        logger.exception('[v3hop] cover failed; serving base plan')
        return None


def _serve(intent, state, chain, tin, tout, best, amt, p):
    recipient = _recipient(state, p)
    if not recipient:
        return None
    out, kind, det = best
    def _v3_ixs(cd, router):
        from eth_utils import to_checksum_address as _ck
        from common.abi_utils import encode_approve
        from minotaur_subnet.shared.types import Interaction
        return [Interaction(target=_ck(tin), value='0',
                            call_data=encode_approve(_ck(router), int(amt)), chain_id=chain),
                Interaction(target=_ck(router), value='0', call_data=cd, chain_id=chain)]
    def _mk(ix, tag):
        from minotaur_subnet.shared.types import ExecutionPlan
        logger.info('[v3hop] override %s->%s out=%s via=%s', tin[:8], tout[:8], out, tag)
        return ExecutionPlan(intent_id=intent.app_id, interactions=ix,
                             deadline=9999999999, nonce=state.nonce,
                             metadata={'solver': 'viking-' + tag, 'chain_id': chain})
    if kind == 'v3d':
        from eth_abi import encode as _enc
        from eth_utils import to_checksum_address as _ck
        router = _ROUTER02.get(int(chain))
        cd = '0x' + (bytes.fromhex('04e45aaf') + _enc(
            ['(address,address,uint24,address,uint256,uint256,uint160)'],
            [(_ck(tin), _ck(tout), int(det[0]), _ck(recipient), int(amt), 0, 0)])).hex()
        return _mk(_v3_ixs(cd, router), 'v3d')
    if kind == 'v3h':
        from eth_abi import encode as _enc
        from eth_utils import keccak as _kk, to_checksum_address as _ck
        router = _ROUTER02.get(int(chain))
        hub, f1, f2 = det
        path = (bytes.fromhex(_ck(tin)[2:]) + int(f1).to_bytes(3, 'big')
                + bytes.fromhex(_ck(hub)[2:]) + int(f2).to_bytes(3, 'big')
                + bytes.fromhex(_ck(tout)[2:]))
        sel = _kk(text='exactInput((bytes,address,uint256,uint256))')[:4]
        cd = '0x' + (sel + _enc(['(bytes,address,uint256,uint256)'],
                                [(path, _ck(recipient), int(amt), 0)])).hex()
        return _mk(_v3_ixs(cd, router), 'v3h')
    # V2
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction
    router = _V2ROUTER.get(int(chain))
    if not router:
        return None
    path = det[0]
    cd = '0x' + (bytes.fromhex('38ed1739') + _enc(
        ['uint256', 'uint256', 'address[]', 'address', 'uint256'],
        [int(amt), 0, [_ck(a) for a in path], _ck(recipient), 9999999999])).hex()
    ix = [Interaction(target=_ck(tin), value='0',
                      call_data=encode_approve(_ck(router), int(amt)), chain_id=chain),
          Interaction(target=_ck(router), value='0', call_data=cd, chain_id=chain)]
    return _mk(ix, 'v2')
