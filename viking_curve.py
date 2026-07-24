"""viking_curve — live Curve pool cover (Base only, absorbed from a rival's
proven blind-spot fill 07-20: the champion lineage carries only a static
per-pool `curve_full` table, so census-discovered pools it never learned about
quote 0/absent through the base engine). viking_curve.json is an offline
factory-enumerated table of (pool -> coins/kind); quoting is get_dy on the
solver's OWN round-pinned w3 so it is execution-accurate. Folded into the
standard candidate union (viking_v3hop._best_lift) rather than a separate
champion-empty-only gate, so it lifts whenever it beats the floor — a strict
superset of only firing when the base plan is null."""
_IDX = {'stable': 'int128', 'crypto': 'uint256'}
_TAB = None

def _table():
    global _TAB
    if _TAB is None:
        import json
        import os
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'viking_curve.json')
        try:
            d = json.load(open(path))
            _TAB = (d.get('pools') or {}, d.get('bytoken') or {})
        except Exception:
            _TAB = ({}, {})
    return _TAB

def _pool_candidates(tin, tout):
    _, bytoken = _table()
    return list(set(bytoken.get(tin, ())) & set(bytoken.get(tout, ())))

def _pool_ij(pool, tin, tout):
    pools, _ = _table()
    info = pools.get(pool) or {}
    coins = info.get('coins') or []
    if tin not in coins or tout not in coins:
        return None
    return (coins.index(tin), coins.index(tout), info.get('kind', 'stable'))

def _quote(w3, pool, kind, i, j, amt):
    from eth_abi import encode as _enc, decode as _dec
    from eth_utils import keccak, to_checksum_address as _ck
    x = _IDX[kind]
    sel = keccak(text=f'get_dy({x},{x},uint256)')[:4]
    data = sel + _enc([x, x, 'uint256'], [i, j, amt])
    try:
        r = w3.eth.call({'to': _ck(pool), 'data': '0x' + data.hex()})
        return _dec(['uint256'], r)[0]
    except Exception:
        return 0

def _pool_quote(w3, pool, tin, tout, amt):
    """(out, 'curve', det) for one pool, or None (no matching coins / quotes 0)."""
    ij = _pool_ij(pool, tin, tout)
    if ij is None:
        return None
    i, j, kind = ij
    q = _quote(w3, pool, kind, i, j, amt)
    return (q, 'curve', (pool, kind, i, j)) if q > 0 else None

def curve_candidates(w3, chain, tin, tout, amt):
    """(out, 'curve', (pool, kind, i, j)) for the best live-quoted Curve pool,
    or [] (Base only; unsupported chain / no candidate pools / all quote 0)."""
    if int(chain) != 8453:
        return []
    rows = (_pool_quote(w3, p, tin, tout, amt) for p in _pool_candidates(tin, tout)[:6])
    return [r for r in rows if r is not None]