"""Relocated leaf helper -- _curve_args, moved out of g2_codec_base.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. g2_codec_base.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _curve_args(i, j, dx, recv, rcpt, _ck):
    """Curve exchange args, lifted verbatim from _curve_swap_cd.

    The "6a" form is the NG-crypto receiver overload and takes a use_eth flag the plain receiver
    overload does not -- the two arg lists are not interchangeable, so both branches move together.
    """
    if recv == '6a':
        return [i, j, dx, 0, False, _ck(rcpt)]
    return [i, j, dx, 0] + ([_ck(rcpt)] if recv else [])