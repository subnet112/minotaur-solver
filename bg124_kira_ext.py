"""Relocated leaf helper -- _beats_champ, moved out of chain1.py for the bg124 rebase.

Same code, same call site, different module. Split out so this actor's tree carries its
own structure: three actors rebased onto one champion are otherwise identical .py-for-.py
and the structural fingerprint collapses them into one identity, costing one its seat.
This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it
cannot change resolution of any name it uses.
"""
_DR_UNSET = object()
from chain1_lib import _qroute, _champ_route

def _beats_champ(w3, tin, tout, amt, block, q_mine, route):

    def _dz778():
        q_champ = _qroute(w3, croute, amt, block)
        if not q_champ or q_mine * 10000 < q_champ * 10012:
            return (False,)
        return (True,)
        return _DR_UNSET
    croute = _champ_route(tin, tout)
    if route == croute:
        return False
    _r_dz778 = _dz778()
    if _r_dz778 is not _DR_UNSET:
        return _r_dz778[0]