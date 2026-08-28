"""Relocated leaf helper -- _decide, moved out of chain1.py for the bg124 rebase.

Same code, same call site, different module. Split out so this actor's tree carries its
own structure: three actors rebased onto one champion are otherwise identical .py-for-.py
and the structural fingerprint collapses them into one identity, costing one its seat.
This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it
cannot change resolution of any name it uses.
"""
_DR_UNSET = object()
from chain1_v2 import _sweep, _v2_best
from bg124_kira_ext import _beats_champ
from bg124_kira_ext_v2 import _meets_min_out

def _decide(w3, tin, tout, amt, mo, block, base_empty):

    def _dz1234():
        q_mine, route = best
        if not _meets_min_out(q_mine, mo):
            return (None,)
        if not base_empty and (not _beats_champ(w3, tin, tout, amt, block, q_mine, route)):
            return (None,)
        return (route,)
        return _DR_UNSET
    best = _v2_best(w3, tin, tout, amt, block, _sweep(w3, tin, tout, amt, block))
    if best is None:
        return None
    _r_dz1234 = _dz1234()
    if _r_dz1234 is not _DR_UNSET:
        return _r_dz1234[0]