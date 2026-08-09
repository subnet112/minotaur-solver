"""Relocated leaf helper -- _direct_legs, moved out of chain1_lib.py.

Same code, same call sites, different module. Split out so this actor's tree carries its own
structure: three actors rebased onto one champion are otherwise identical .py-for-.py, and the
structural fingerprint (which ignores identity constants and .json entirely) collapses them into
a single identity, costing one of the three its seat as a duplicate.

This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it cannot
change resolution of any name it uses.
"""
from chain1_c import _FEES


def _direct_legs(tin, tout):
    """Every (route, fees) pair for the single-hop tin -> tout, one per fee tier.

    Sibling of `_hub_legs`, named for the same reason: the two differ in ARITY -- a direct
    route carries ONE fee, a two-hop an ordered pair -- and `_pack` walks fees alongside
    tokens, so a one-element tuple written `(f)` instead of `(f,)` is not a tuple at all and
    packs a truncated path that quotes some other pool rather than raising.

    ORDER IS LOAD-BEARING and belongs to the caller: these are emitted BEFORE any hub leg so
    the sweep's strict `>` leaves a direct route in place when a two-hop merely ties it.
    """
    return [((tin, tout), (f,)) for f in _FEES]
