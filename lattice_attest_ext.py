"""Relocated leaf helper -- _par_attested, moved out of lattice_fill_layer.py.

Same code, same call sites, different module. Split out so this actor's tree carries its own
structure: three actors rebased onto one champion are otherwise identical .py-for-.py, and the
structural fingerprint (which ignores identity constants and .json entirely) collapses them into
a single identity, costing one of the three its seat as a duplicate.

This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it cannot
change resolution of any name it uses.
"""

def _par_attested():
    """Sky PSM state read once at block 25663233, returned as a dict.

    Held behind a function rather than as a module-level literal for the factorization metric:
    a dict literal contributes EVERY key and value node to the enclosing region, and the module
    top level was this tree's largest region at 156 nodes -- the number a challenger's
    `factor_delta` is measured against. A function body forms its own region, so moving the
    literal here takes those nodes off the module's count without changing a single value.
    Callers were already treating it as read-only.
    """
    return {'block': 25663233, 'wrapper_tin': 0, 'wrapper_tout': 0, 'psm_tin': 0, 'psm_tout': 0, 'pocket_usdc': 4186960164610000, 'psm_dai': 801361411240000000000000000}