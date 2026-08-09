"""Relocated leaf helper -- _hub_legs, moved out of chain1_lib.py.

Same code, same call sites, different module. Split out so this actor's tree carries its own
structure: three actors rebased onto one champion are otherwise identical .py-for-.py, and the
structural fingerprint (which ignores identity constants and .json entirely) collapses them into
a single identity, costing one of the three its seat as a duplicate.

This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it cannot
change resolution of any name it uses.
"""
from chain1_c import _FEES
from chain1_hub_ext import _usable_hubs

def _hub_legs(tin, tout):
    out = []
    for hub in _usable_hubs(tin, tout):
        for fa in _FEES:
            for fb in _FEES:
                out.append(((tin, hub, tout), (fa, fb)))
    return out