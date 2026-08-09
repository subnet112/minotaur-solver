"""Relocated leaf helper -- _par_venue_need, moved out of lattice_fill_layer.py.

Same code, same call sites, different module. Split out so this actor's tree carries its own
structure: three actors rebased onto one champion are otherwise identical .py-for-.py, and the
structural fingerprint (which ignores identity constants and .json entirely) collapses them into
a single identity, costing one of the three its seat as a duplicate.

This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it cannot
change resolution of any name it uses.
"""

def _par_venue_need(d, gem):
    """(token, holder, amount) the venue must hold to fund THIS direction.

    The two directions are funded from different reserves, and checking the wrong one would
    pass a leg that cannot settle. buyGem pays USDC out of the LitePSM pocket. sellGem takes
    USDC in and pays USDS out, which the wrapper sources as DAI from the LitePSM itself before
    converting -- so the reserve that has to cover it is the PSM's DAI, at 18 decimals.
    """
    _tin, tout, _wrap, _sel, up = d
    if up:
        return ('0x6b175474e89094c44da98b954eedeac495271d0f', '0xf6e72db5454dd049d0788e411b06cfaf16853042', int(gem) * 10 ** 12)
    return (tout, '0x37305b1cd40574e4c5ce33f8e8306be057fd7341', int(gem))