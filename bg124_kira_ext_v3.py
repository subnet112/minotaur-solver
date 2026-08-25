"""Relocated leaf helper -- _mk_plan, moved out of chain1.py for the bg124 rebase.

Same code, same call site, different module. Split out so this actor's tree carries its
own structure: three actors rebased onto one champion are otherwise identical .py-for-.py
and the structural fingerprint collapses them into one identity, costing one its seat.
This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it
cannot change resolution of any name it uses.
"""
from chain1_lib import _build
from chain1_v2 import _v2_build

def _mk_plan(route, tin, amt, rcpt, intent, state):
    from minotaur_subnet.shared.types import ExecutionPlan as _EP
    if isinstance(route, tuple) and route and (route[0] == 'v2'):
        ixs = _v2_build(route[1], route[2], tin, amt, route[3], rcpt, 1)
    else:
        ixs = _build(route, tin, amt, rcpt, 1)
    return _EP(intent_id=intent.app_id, interactions=ixs, deadline=9999999999, nonce=state.nonce, metadata={'solver': 'viking-eth-dyn', 'chain_id': 1})