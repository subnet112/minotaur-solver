"""Relocated leaf helper -- _amounts, moved out of chain1_lib.py for the bg124 rebase.

Same code, same call site, different module. Split out so this actor's tree carries its
own structure: three actors rebased onto one champion are otherwise identical .py-for-.py
and the structural fingerprint collapses them into one identity, costing one its seat.
This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it
cannot change resolution of any name it uses.
"""
from lat_wei_ext import _wei

def _amounts(p):
    return (_wei(p, 'input_amount'), _wei(p, 'min_output_amount'))