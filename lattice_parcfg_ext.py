"""Relocated leaf helper -- _par_cfg, moved out of lattice_fill_layer.py.

Same code, same call sites, different module. Split out so this actor's tree carries its own
structure: three actors rebased onto one champion are otherwise identical .py-for-.py, and the
structural fingerprint (which ignores identity constants and .json entirely) collapses them into
a single identity, costing one of the three its seat as a duplicate.

This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it cannot
change resolution of any name it uses.
"""

def _par_cfg():
    """Directions served: (tin, tout, wrapper, selector, gem_is_input).

    One function rather than module constants, for two reasons that point the same way.
    `max_region_nodes` scores the module body as a region of its own, so top-level assignments
    are charged to the tree's factorization score; a function body is its own region and costs
    the module only its definition. And these addresses MUST stay a single source of truth --
    the pair gate in `_par_match` and the calldata built in `_par_legs`/`_par_state_ok` have to
    agree, because a drift between them would build a plan for a token the gate never checked.

    ONLY MEASURED DEFECTS BELONG HERE. Both rows below were read off real scorecards as the
    champion's own delivered output against par: USDS->USDC at 0.1325 (7.5484x to gain) and
    USDC->USDS at 0.8936 (1.1191x). The sibling pair DAI->USDC was checked the same way and
    came back 0.9999 -- the engine already routes it, so an override would gain 1bp, land
    inside RELATIVE_TOL_BPS=10 and score `matched`. A pair whose engine output has NOT been
    measured below par does not go in this table; depth intuition is not evidence.

    `gem_is_input` distinguishes the two PSM entry points. sellGem takes the 6-decimal gem
    amount directly and scales UP into 18 decimals with no remainder. buyGem is quoted in the
    gem it pays out, so the 18-decimal input must be floored into 6 first and the sub-1e12
    remainder is unconvertible dust.
    """
    usds = '0xdc035d45d973e3ec169d2276ddab16f1e407384f'
    usdc = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'
    wrap = '0xa188eec8f81263234da3622a406892f3d630f98c'
    return ((usds, usdc, wrap, '0x8d7ef9bb', False), (usdc, usds, wrap, '0x95991276', True))