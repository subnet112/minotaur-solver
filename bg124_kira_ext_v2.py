"""Relocated leaf helper -- _meets_min_out, moved out of chain1.py for the bg124 rebase.

Same code, same call site, different module. Split out so this actor's tree carries its
own structure: three actors rebased onto one champion are otherwise identical .py-for-.py
and the structural fingerprint collapses them into one identity, costing one its seat.
This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it
cannot change resolution of any name it uses.
"""

def _meets_min_out(q, mo):
    """Whether quote `q` clears the order's declared minimum output.

    `mo > 0` is what separates "no minimum declared" from a floor: _amounts coerces a missing
    or null min_output_amount to 0, and 0 has to mean unset. The clause is redundant as pure
    arithmetic -- a quote is never negative, so `q < 0` could not fire anyway -- but writing
    the intent down is the point. Read without it, the test looks like it enforces a
    zero floor, and the next edit to _amounts (a sentinel, a signed value) would silently
    turn every unset order into a rejection with nothing here to contradict it.
    """
    return not (mo > 0 and q < mo)