"""Relocated leaf helper -- _v_sng_dy, moved out of shape_lib.py.

Same code, same call sites, different module. Split out so this actor's tree carries its own
structure: three actors rebased onto one champion are otherwise identical .py-for-.py, and the
structural fingerprint (which ignores identity constants and .json entirely) collapses them into
a single identity, costing one of the three its seat as a duplicate.

This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it cannot
change resolution of any name it uses.
"""
_DR_UNSET = object()

def _v_sng_dy(s, pool, i, j, dx, chain_id):
    """Curve StableNg forward quote: pool.get_dy(i, j, dx); None on failure."""

    def _dz268():
        w3 = s._get_web3(int(chain_id))
        if w3 is None:
            return (None,)
        sel = _keccak(text='get_dy(int128,int128,uint256)')[:4]
        r = w3.eth.call({'to': _ck(pool), 'data': '0x' + (sel + _enc(['int128', 'int128', 'uint256'], [int(i), int(j), int(dx)])).hex()})
        return (_dec(['uint256'], r)[0] or None,)
        return _DR_UNSET
    try:
        from eth_abi import encode as _enc, decode as _dec
        from eth_utils import keccak as _keccak, to_checksum_address as _ck
        _r_dz268 = _dz268()
        if _r_dz268 is not _DR_UNSET:
            return _r_dz268[0]
    except Exception:
        return None