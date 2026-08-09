"""Relocated leaf helper -- _fw6, moved out of apex_king_base.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. apex_king_base.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _fw6():
    _DR_UNSET = object()

    def _dr58():
        _DR_UNSET = object()
        import logging
        import os
        import time
        from _apex_champ import SOLVER_CLASS as _Base
        from minotaur_subnet.sdk.intent_solver import SolverMetadata
        from minotaur_subnet.shared.types import ExecutionPlan, Interaction
        logger = logging.getLogger(__name__)
        SOLVER_NAME = os.environ.get('MINOTAUR_SOLVER_NAME', 'putty-clean-solver')
        SOLVER_VERSION = os.environ.get('MINOTAUR_SOLVER_VERSION', '0.127.0')
        import king_base as _kb
        _BOTZ = '0xca179f3978137f5745e6d731591aaef985ee9d6d'
        _USDC_ = '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'
        _NO_HOOK = '0x0000000000000000000000000000000000000000'
        return (ExecutionPlan, Interaction, SOLVER_NAME, SOLVER_VERSION, SolverMetadata, _BOTZ, _Base, _DR_UNSET, _NO_HOOK, _USDC_, _kb, logger, logging, os, time)
    ExecutionPlan, Interaction, SOLVER_NAME, SOLVER_VERSION, SolverMetadata, _BOTZ, _Base, _DR_UNSET, _NO_HOOK, _USDC_, _kb, logger, logging, os, time = _dr58()
    try:

        def _dr28():
            _kb._STATIC_EXOTIC_ROUTES[_USDC_, _BOTZ] = ('uniswap_v4_ur', {'pool': (_USDC_, _BOTZ, 250000, 5000, _NO_HOOK), 'settle': _USDC_, 'zero_for_one': True})
            _WETH_ = '0x4200000000000000000000000000000000000006'
            _ZERO_ADDR_ = '0x0000000000000000000000000000000000000000'
            _T182 = '0x182fa643e5f29d5eca75e7b9cf9336a3fe4620b2'
            _kb._STATIC_EXOTIC_ROUTES[_WETH_, _T182] = ('uniswap_v4_ur', {'unwrap_weth': True, 'pool': (_ZERO_ADDR_, _T182, 10000, 200, _NO_HOOK), 'settle': _ZERO_ADDR_, 'zero_for_one': True, 'sweep_settle': True})
        _dr28()
    except Exception:
        logging.getLogger(__name__).exception('[botz-v4] static-exotic patch failed')
    return dict(locals())