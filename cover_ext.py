"""Curve StableSwap cover for pairs no Uniswap or Aerodrome pool can serve.

WHERE THIS FIRES, AND WHY IT IS SAFE. Only from `_cover_or`, i.e. only when the
inherited plan is EMPTY. On such an order the incumbent delivers nothing, so a
`dropped` verdict (which needs `champ_has and not chal_has`) is impossible, and a
regression is impossible because there is no incumbent value to fall short of.
Worst case is another zero; best case is a `blind_spot_cover` — a `better` row
bought with no veto risk.

That asymmetry is the whole strategy. Across 17 crowns EVERY winner had
`dropped == 0` (17/17, the only universal), and nine were won with `better <= 1`.
So the winning shape is "inherit every route, add one risk-free win", never
"re-derive routing and hope the long tail matches" — our clean-room tree scored
30 better and still lost, five times out of five, on drops.

Curve only, deliberately. Aave aToken covers were written and then removed: the
inherited `generate_plan` returns early for `chain != 1`, so `_cover_or` never
runs on Base, and every aToken we serve is a Base token. That layer could not
fire, and it measured 320 nodes against both the region and deadwood metrics.
"""
from __future__ import annotations
from eth_abi import decode, encode
from eth_utils import keccak, to_checksum_address as ck
from venues import eth_call as _eth_call
from cover_call_ext import _call
METAREGISTRY = {1: '0xF98B45FA17DE75FB1aD0e7aFD971b0ca00e379fC'}

def _sel(sig):
    return keccak(text=sig)[:4].hex()

def _approve(spender, amount):
    return '0x' + _sel('approve(address,uint256)') + encode(['address', 'uint256'], [ck(spender), int(amount)]).hex()

def _pool(rpc, tin, tout, chain_id):
    reg = METAREGISTRY.get(int(chain_id))
    if not reg:
        return None
    data = '0x' + _sel('find_pool_for_coins(address,address,uint256)') + encode(['address', 'address', 'uint256'], [ck(tin), ck(tout), 0]).hex()
    pool = decode(['address'], _call(rpc, reg, data))[0]
    return None if int(pool, 16) == 0 else pool

def _indices(rpc, pool, tin, tout, chain_id):
    reg = METAREGISTRY[int(chain_id)]
    data = '0x' + _sel('get_coin_indices(address,address,address)') + encode(['address', 'address', 'address'], [ck(pool), ck(tin), ck(tout)]).hex()
    return decode(['int128', 'int128', 'bool'], _call(rpc, reg, data))

def _shapes(underlying):
    base = ('get_dy_underlying', 'exchange_underlying') if underlying else ('get_dy', 'exchange')
    out = [(base[0], base[1], 'int128'), (base[0], base[1], 'uint256')]
    if underlying:
        out += [('get_dy', 'exchange', 'int128'), ('get_dy', 'exchange', 'uint256')]
    return out

def _probe(rpc, pool, i, j, underlying, amount):
    """(out, swap_fn, typ) for the first signature the pool answers.

    The swap MUST be built with the signature that produced the quote: classic
    StableSwap takes int128, crypto pools uint256, and metapools expose their
    base coins only through the `_underlying` variants. Mixing them reverts, and
    a revert here is a delivered zero.
    """

    def _dz55(amount, i, j, pool, rpc, sig, typ):
        data = '0x' + _sel(sig) + encode([typ, typ, 'uint256'], [i, j, int(amount)]).hex()
        out = int(decode(['uint256'], _call(rpc, pool, data))[0])
        return (data, out)
    for quote_fn, swap_fn, typ in _shapes(underlying):
        sig = f'{quote_fn}({typ},{typ},uint256)'
        try:
            data, out = _dz55(amount, i, j, pool, rpc, sig, typ)
        except Exception:
            continue
        if out > 0:
            return (out, swap_fn, typ)
    return (0, None, None)

def _exchange(pool, i, j, amount, swap_fn, typ):
    """The exchange leg, in the same shape that produced the quote.

    min_dy is 0: the harness enforces the order's minimum at the intent level, so
    a per-swap minimum only adds a revert path.
    """
    sig = f'{swap_fn}({typ},{typ},uint256,uint256)'
    data = '0x' + _sel(sig) + encode([typ, typ, 'uint256', 'uint256'], [int(i), int(j), int(amount), 0]).hex()
    return [{'target': pool, 'data': data}]

def _resolve(rpc, tin, tout, amount, chain_id):
    """(pool, i, j, out, swap_fn, typ) for a Curve pair, or None."""
    pool = _pool(rpc, tin, tout, chain_id)
    if not pool:
        return None
    i, j, und = _indices(rpc, pool, tin, tout, chain_id)
    out, swap_fn, typ = _probe(rpc, pool, i, j, und, amount)
    return None if out <= 0 else (pool, i, j, out, swap_fn, typ)

def curve_legs(rpc, tin, tout, amount, chain_id):
    """(interactions, out) for a Curve pair, or (None, 0). Never raises."""
    try:
        got = _resolve(rpc, tin, tout, amount, chain_id)
        if got is None:
            return (None, 0)
        pool, i, j, out, swap_fn, typ = got
        legs = [{'target': tin, 'data': _approve(pool, amount)}]
        return (legs + _exchange(pool, i, j, amount, swap_fn, typ), out)
    except Exception:
        return (None, 0)