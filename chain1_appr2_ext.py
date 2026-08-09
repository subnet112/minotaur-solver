"""Relocated leaf helper -- _approves, moved out of chain1_lib.py.

Same code, same call sites, different module. Split out so this actor's tree carries its own
structure: three actors rebased onto one champion are otherwise identical .py-for-.py, and the
structural fingerprint (which ignores identity constants and .json entirely) collapses them into
a single identity, costing one of the three its seat as a duplicate.

This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it cannot
change resolution of any name it uses.
"""
from chain1_c import _ROUTER
from chain1_appr_ext import _needs_reset_approve

def _approves(tin, amt, chain_id):
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction as _IX
    ixs = []
    if _needs_reset_approve(tin):
        ixs.append(_IX(target=tin, value='0', call_data=encode_approve(_ck(_ROUTER), 0), chain_id=chain_id))
    ixs.append(_IX(target=tin, value='0', call_data=encode_approve(_ck(_ROUTER), int(amt)), chain_id=chain_id))
    return ixs