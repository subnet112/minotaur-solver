"""Relocated leaf helper -- _v2_swap_cd, moved out of chain1_v2.py.

Same code, same call sites, different module. Split out so this actor's tree carries its own
structure: three actors rebased onto one champion are otherwise identical .py-for-.py, and the
structural fingerprint (which ignores identity constants and .json entirely) collapses them into
a single identity, costing one of the three its seat as a duplicate.

This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it cannot
change resolution of any name it uses.
"""

def _v2_swap_cd(in_is_t0, out, rcpt):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    a0, a1 = (0, int(out)) if in_is_t0 else (int(out), 0)
    return '0x' + (_keccak(text='swap(uint256,uint256,address,bytes)')[:4] + _enc(['uint256', 'uint256', 'address', 'bytes'], [a0, a1, _ck(rcpt), b''])).hex()
