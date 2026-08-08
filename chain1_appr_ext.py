"""Relocated leaf helper -- _needs_reset_approve, moved out of chain1_lib.py.

Same code, same call sites, different module. Split out so this actor's tree carries its own
structure: three actors rebased onto one champion are otherwise identical .py-for-.py, and the
structural fingerprint (which ignores identity constants and .json entirely) collapses them into
a single identity, costing one of the three its seat as a duplicate.

This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it cannot
change resolution of any name it uses.
"""
from chain1_c import _USDT

def _needs_reset_approve(tin):
    """Whether `tin` must be approved to 0 before being approved to the real amount.

    USDT's approve() reverts outright when it would move a NON-ZERO allowance to another
    non-zero value -- it is not ERC-20 compliant on that path. Every other token in the
    corpus overwrites its allowance happily, so the extra interaction is spent only where it
    is load-bearing.

    The failure mode this guards is quiet and expensive: the approve reverts, the whole plan
    reverts with it, and the row scores as a delivery failure rather than as anything that
    points at an allowance. Naming the condition keeps the reason attached to the test, which
    a bare `tin == _USDT` beside a zero-amount approve does not.
    """
    return tin == _USDT