"""Relocated leaf helper -- _pack_path, moved out of g2_codec_base.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. g2_codec_base.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _pack_path(tokens, fees) -> bytes:
    b = b''
    for i, t in enumerate(tokens):
        b += bytes.fromhex(str(t)[2:])
        if i < len(fees):
            b += int(fees[i]).to_bytes(3, 'big')
    return b