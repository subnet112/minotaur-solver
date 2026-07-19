"""viking_quote — address tables + same-block quote primitives.

Tables (quoters/routers/hubs), the single-shot quoters used by viking_v3hop to
re-quote the engine's OWN base route (1-2 calls), and the low-level aggregate3
primitives (encode/decode/exec) the batched search in viking_batch composes. The
heavy candidate SEARCH lives in viking_batch (2 aggregate3 calls instead of ~50-90
singletons) so viking's rescue-cover stays flake-robust under bench load. Split so
each named region stays small (factorization discipline). My own encoders."""
import logging

logger = logging.getLogger('solver')

_FEES = (100, 500, 3000, 10000)
_MC_ADDR = '0xcA11bde05977b3631167028862bE2a173976CA11'   # Multicall3 (all chains)
_MC_AGG3 = '0x82ad56cb'                                    # aggregate3((address,bool,bytes)[])


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


def _v2_paths(chain, tin, tout):
    """[direct] + [via-hub] V2 paths, direct FIRST (so it wins output ties)."""
    paths = [[tin, tout]]
    for hub in _V2HUBS.get(int(chain), ()):
        if hub != tin and hub != tout:
            paths.append([tin, hub, tout])
    return paths


# ── aggregate3 primitives (composed by viking_batch) ─────────────────────────

def _agg3(w3, calls):
    """One aggregate3 eth_call. calls=[(target,callbytes)...] -> [(ok,bytes)...] or None."""
    from eth_abi import encode as _enc, decode as _dec
    from eth_utils import to_checksum_address as _ck
    if not calls:
        return []
    try:
        arr = [(_ck(t), True, cb) for t, cb in calls]
        data = _MC_AGG3 + _enc(['(address,bool,bytes)[]'], [arr]).hex()
        r = bytes(w3.eth.call({'to': _ck(_MC_ADDR), 'data': data}))
        return _dec(['(bool,bytes)[]'], r)[0]
    except Exception:
        return None


def _enc_single(tin, tout, amt, fee):
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    return bytes.fromhex('c6a5026a') + _enc(
        ['(address,address,uint256,uint24,uint160)'],
        [(_ck(tin), _ck(tout), int(amt), int(fee), 0)])


def _enc_v2(amt, path):
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    return bytes.fromhex('d06ca61f') + _enc(
        ['uint256', 'address[]'], [int(amt), [_ck(a) for a in path]])


def _dec_single(ok, rb):
    if not ok:
        return 0
    from eth_abi import decode as _dec
    b = bytes(rb)
    if len(b) < 32:
        return 0
    try:
        return int(_dec(['uint256', 'uint160', 'uint32', 'uint256'], b)[0])
    except Exception:
        return 0


def _dec_v2out(ok, rb):
    if not ok:
        return 0
    from eth_abi import decode as _dec
    try:
        outs = _dec(['uint256[]'], bytes(rb))[0]
        return int(outs[-1]) if outs else 0
    except Exception:
        return 0
