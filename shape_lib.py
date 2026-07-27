# SN112 shape library — quote helpers (builders live in shape_lib2/shape_lib3).

def _res_call(s, pair, chain_id):
    from eth_abi import decode as _dec
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    w3 = s._get_web3(int(chain_id))
    if w3 is None:
        return None
    res = _dec(['uint112', 'uint112', 'uint32'], w3.eth.call({'to': _ck(pair), 'data': '0x' + _keccak(text='getReserves()')[:4].hex()}))
    return (int(res[0]), int(res[1]))

def _v_v2_out(s, pair, amt_in, in_is_t0, chain_id):
    """UniswapV2-style pair forward quote from getReserves (997/1000 fee)."""
    try:
        res = _res_call(s, pair, chain_id)
        if res is None:
            return None
        rin, rout = (res[0], res[1]) if in_is_t0 else (res[1], res[0])
        ai = int(amt_in) * 997
        return ((ai * rout) // (rin * 1000 + ai)) or None
    except Exception:
        return None

def _v_bs_quote(s, venue, param, tin, tout, amt, chain_id):
    """Same-block forward quote of one single-hop candidate via the engine's
    own quoters; None on any failure (absent pool / no liquidity)."""
    try:
        if venue == 'aerodrome_slipstream':
            return slip_quote(s, int(param), tin, tout, amt, chain_id)
        router = 'pancake' if venue == 'pancake_v3' else 'uni'
        return s._hydra_quote_leg1({'leg1_router': router, 'leg1_fee': int(param), 'mid': tout}, tin, amt, chain_id)
    except Exception:
        return None

def _v_sng_dy(s, pool, i, j, dx, chain_id):
    """Curve StableNg forward quote: pool.get_dy(i, j, dx); None on failure."""
    try:
        from eth_abi import encode as _enc, decode as _dec
        from eth_utils import keccak as _keccak, to_checksum_address as _ck
        w3 = s._get_web3(int(chain_id))
        if w3 is None:
            return None
        sel = _keccak(text='get_dy(int128,int128,uint256)')[:4]
        r = w3.eth.call({'to': _ck(pool), 'data': '0x' + (sel + _enc(['int128', 'int128', 'uint256'], [int(i), int(j), int(dx)])).hex()})
        return _dec(['uint256'], r)[0] or None
    except Exception:
        return None

def _v_pair_gao(s, pair, amt, tin, chain_id):
    """Solidly/Aero V2 pair forward quote via the pair's own getAmountOut."""
    try:
        from eth_abi import encode as _enc, decode as _dec
        from eth_utils import keccak as _keccak, to_checksum_address as _ck
        w3 = s._get_web3(int(chain_id))
        if w3 is None:
            return None
        sel = _keccak(text='getAmountOut(uint256,address)')[:4]
        r = w3.eth.call({'to': _ck(pair), 'data': '0x' + (sel + _enc(['uint256', 'address'], [int(amt), _ck(tin)])).hex()})
        return _dec(['uint256'], r)[0] or None
    except Exception:
        return None

def pair_out(s, pair, amt, tok_in, chain_id):
    """Aerodrome/V2 pair getAmountOut(uint256,address) — the pair's own
    fee-exact forward quote."""
    try:
        out = _v_pair_gao(s, pair, amt, tok_in, chain_id)
        return out if out and out > 0 else None
    except Exception:
        return None

def _e1_qdata(path_hex, amt):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak
    sel = _keccak(text='quoteExactInput(bytes,uint256)')[:4]
    return '0x' + (sel + _enc(['bytes', 'uint256'], [bytes.fromhex(path_hex), int(amt)])).hex()

def _v_e1_qpath(s, path_hex, amt, chain_id):
    """Forward quote of a packed v3 path on chain 1; None off-chain-1 or on failure."""
    try:
        if int(chain_id) != 1:
            return None
        from eth_abi import decode as _dec
        from eth_utils import to_checksum_address as _ck
        from shape_lib2 import _V_E1_QUOTER
        w3 = s._get_web3(1) or s._get_web3(31337)
        if w3 is None:
            return None
        r = w3.eth.call({'to': _ck(_V_E1_QUOTER), 'data': _e1_qdata(path_hex, amt)})
        return _dec(['uint256', 'uint160[]', 'uint32[]', 'uint256'], r)[0] or None
    except Exception:
        return None

def _slip_call(s, ts, tin, tout, amt, chain_id, quoter):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    from king_consts import _AERO_QUOTER
    w3 = s._get_web3(int(chain_id))
    if w3 is None:
        return None
    sel = _keccak(text='quoteExactInputSingle((address,address,uint256,int24,uint160))')[:4]
    params = _enc(['(address,address,uint256,uint24,uint160)'], [(_ck(tin), _ck(tout), int(amt), int(ts), 0)])
    return w3.eth.call({'to': _ck(quoter or _AERO_QUOTER), 'data': '0x' + (sel + params).hex()})

def slip_quote(s, ts, tin, tout, amt, chain_id, quoter=None):
    """Slipstream-family quoter exact-in single — int24 tickSpacing selector
    (the lineage's uint24 variant reverts on every pool). `quoter` overrides the
    canonical deployment for CLFactory variants (factory3 etc)."""
    try:
        from eth_abi import decode as _dec
        r = _slip_call(s, ts, tin, tout, amt, chain_id, quoter)
        if r is None:
            return None
        out = int(_dec(['uint256', 'uint160', 'uint32', 'uint256'], r)[0])
        return out if out > 0 else None
    except Exception:
        return None
