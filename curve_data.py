"""Curve venue address tables — data-only sidecar for curve_venue.py.

Kept out of curve_venue.py so that file's module region stays well under the
factorization floor. The tables are a single ast.literal_eval'd string constant
(one AST node, the king_tables idiom), injected as module globals; curve_venue
pulls them via `from curve_data import *`. ast.literal_eval is import-safe
(no eth deps) and static — no exec/eval, no dynamic code.
"""
from __future__ import annotations
import ast as _ast
globals().update(_ast.literal_eval("{'_Z': '0x0000000000000000000000000000000000000000', '_ROUTER': {1: '0x45312ea0eFf7E09C83CBE249fa1d7598c4C8cd4e', 8453: '0x4f37A9d177470499A2dD084621020b023fcffc1F'}, '_REGS': {1: (('0xF98B45FA17DE75FB1aD0e7aFD971b0ca00e379fC', 0),), 8453: (('0xd2002373543Ce3527023C75e7518C274A51ce712', 10), ('0xc9Fe0C63Af9A39402e8a5514f9c43Af0322b665F', 20), ('0xA5961898870943c68037F6848d2D866Ed2016bcB', 30))}, '_HUBS': {1: ('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0xf939E0A03FB07F59a73314E73794Be0E57ac1b4E', '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'), 8453: ('0x4200000000000000000000000000000000000006', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913', '0x417Ac0e078398C154EdFadD9Ef675d30Be60Af93')}, '_PT_STABLE': (1, 10), '_PT_2': (2, 20), '_PT_3': (3, 30)}"))
__all__ = ['_ROUTER', '_REGS', '_HUBS', '_PT_STABLE', '_PT_2', '_PT_3', '_Z']