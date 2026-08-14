"""Relocated leaf helper -- _p2, moved out of viking_data.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. viking_data.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _p2():
    return {('0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', '0x940181a94a35a4569e4529a3cdfb74e38fd98631'): [('aerodrome_slipstream', 200), ('aerodrome_slipstream', 100), ('uniswap_v3', 3000), ('pancake_v3', 2500)], ('0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', '0x4200000000000000000000000000000000000006'): [('uniswap_v3', 500), ('aerodrome_slipstream', 100), ('uniswap_v3', 100)], ('0x4200000000000000000000000000000000000006', '0x940181a94a35a4569e4529a3cdfb74e38fd98631'): [('aerodrome_slipstream', 200), ('aerodrome_slipstream', 100), ('uniswap_v3', 3000)], ('0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca', '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'): [('uniswap_v3', 100), ('aerodrome_slipstream', 1), ('uniswap_v3', 500)]}
