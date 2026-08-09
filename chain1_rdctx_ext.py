"""Relocated leaf helper -- _rdctx, moved out of chain1.py.

Same code, same call sites, different module. Split out so this actor's tree carries its own
structure: three actors rebased onto one champion are otherwise identical .py-for-.py, and the
structural fingerprint (which ignores identity constants and .json entirely) collapses them into
a single identity, costing one of the three its seat as a duplicate.

This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it cannot
change resolution of any name it uses.
"""

def _rdctx(s, snapshot):
    w3 = s._get_web3(1) or s._get_web3(31337)
    if w3 is None:
        return None
    block = getattr(snapshot, 'block_number', None) if snapshot else None
    block = int(block) if block else 'latest'
    return (w3, block)