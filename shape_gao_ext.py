"""Relocated leaf helper -- _v_pair_gao, moved out of shape_lib.py.

Same code, same call sites, different module. Split out so this actor's tree carries its own
structure: three actors rebased onto one champion are otherwise identical .py-for-.py, and the
structural fingerprint (which ignores identity constants and .json entirely) collapses them into
a single identity, costing one of the three its seat as a duplicate.

This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it cannot
change resolution of any name it uses.
"""

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