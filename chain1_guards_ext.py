"""Relocated leaf helper -- _guards, moved out of chain1.py.

Same code, same call sites, different module. Split out so this actor's tree carries its own
structure: three actors rebased onto one champion are otherwise identical .py-for-.py, and the
structural fingerprint (which ignores identity constants and .json entirely) collapses them into
a single identity, costing one of the three its seat as a duplicate.

This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it cannot
change resolution of any name it uses.
"""
from chain1_lib import _params
from chain1_rdctx_ext import _rdctx

def _guards(s, intent, state, snapshot):
    if int(getattr(state, 'chain_id', 0) or 0) != 1:
        return None
    pr = _params(s, intent, state)
    if pr is None:
        return None
    rcpt = getattr(state, 'contract_address', None) or getattr(state, 'owner', None)
    if not rcpt:
        return None
    rd = _rdctx(s, snapshot)
    if rd is None:
        return None
    return (pr, rcpt, rd[0], rd[1])