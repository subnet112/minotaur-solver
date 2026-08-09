"""Relocated leaf helper -- _usable_hubs, moved out of chain1_lib.py.

Same code, same call sites, different module. Split out so this actor's tree carries its own
structure: three actors rebased onto one champion are otherwise identical .py-for-.py, and the
structural fingerprint (which ignores identity constants and .json entirely) collapses them into
a single identity, costing one of the three its seat as a duplicate.

It reads _HUBS, which chain1_lib.py imports from chain1_c -- so the move has to carry that
import with it. Leaving it behind made every call raise NameError, which _hub_legs swallowed as
"no hub candidates", silently narrowing the route sweep instead of failing loudly.
"""
from chain1_c import _HUBS

def _usable_hubs(tin, tout):
    return [hub for hub in _HUBS if hub not in (tin, tout)]