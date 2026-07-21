"""viking_v4 — exact-key Uniswap V4 cover (table-driven quote side).

The engine's V4 discovery probes a fixed hub/fee grid, so pools with exotic fee
tiers, native-ETH currency, or launchpad hooks are invisible to it and their
orders drop to zero. viking_v4.json carries oracle-harvested, on-chain-verified
pool keys per (chain|tin|tout); every serve re-quotes the exact key through the
V4Quoter same-block (plus any chained v2/v3 tail through the standard quoters),
so the lift-only gate compares real executable output. Rows whose pools die
simply quote None — stale data degrades to the old defer, never a regression."""
import viking_quote as _q
_V4Q = {1: '0x52F0E24D1c21C8A0cB1e5a5dD6198556BD9E1203', 8453: '0x0d5e0F971ED27FBfF6c2837bf31316121532048D'}
_TAB = None

def _table():
    global _TAB
    if _TAB is None:
        import json
        import os
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'viking_v4.json')
        try:
            _TAB = json.load(open(path))
        except Exception:
            _TAB = {}
    return _TAB

def _q_v4_data(row, amt):
    from eth_abi import encode as _enc
    from eth_utils import keccak, to_checksum_address as _ck
    c0, c1, fee, ts, hook = row['key']
    sel = keccak(b'quoteExactInputSingle(((address,address,uint24,int24,address),bool,uint128,bytes))')[:4]
    return sel + _enc(['((address,address,uint24,int24,address),bool,uint128,bytes)'], [((_ck(c0), _ck(c1), int(fee), int(ts), _ck(hook)), bool(row['zfo']), int(amt), b'')])

def _q_v4(w3, chain, row, amt):
    """Same-block V4Quoter output for one exact-key row, or None."""
    from eth_abi import decode as _dec
    try:
        r = w3.eth.call({'to': _V4Q[chain], 'data': '0x' + _q_v4_data(row, amt).hex()})
        return _dec(['uint256', 'uint256'], r)[0]
    except Exception:
        return None

def _post_out(w3, chain, post, amt):
    """Output of the chained post-leg (['v3', tokens, fees] | ['v2', tokens])."""
    if post[0] == 'v3':
        toks, fees = (post[1], post[2])
        if len(toks) == 2:
            return _q._q_single(w3, chain, toks[0], toks[1], fees[0], amt)
        return None
    return _q._v2_out(w3, chain, post[1], amt)

def v4_candidates(w3, chain, tin, tout, amt):
    """(out, 'v4', row) per live table row for this order, execution-accurate."""
    rows = _table().get(f'{chain}|{tin}|{tout}') or []
    out = []
    for row in rows:
        o = _q_v4(w3, chain, row, amt)
        if o and row.get('post'):
            o = _post_out(w3, chain, row['post'], o)
        if o:
            out.append((o, 'v4', row))
    return out