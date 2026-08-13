"""Relocated leaf helper -- _word, moved out of axm_word_ext.py.

Dependency-closed by construction: the body reads no module-level name, so nothing
imports back and no cycle is possible. axm_word_ext.py re-imports the name, which keeps it in
that module's namespace and therefore in its `from ... import *` surface.
"""
from __future__ import annotations

def _word(x) -> str:
    """One 32-byte ABI word as 64 hex chars, no prefix.

    Both operands of `_abi_addr_uint` are the same shape -- a left-padded 256-bit word -- so
    they are encoded by the same function rather than by two hand-rolled expressions that
    happened to agree. The previous pair did agree on every valid input, but each was wrong
    off the happy path in a way that would have produced a MALFORMED word rather than an
    error: `.replace("0x", "")` strips the substring everywhere, not just the prefix, and
    `hex(int(v))[2:]` yields a leading "-" for a negative value, which rjust then pads into a
    plausible-looking 64-char string. Calldata that is wrong but well-formed is the expensive
    kind -- it reverts at bench, which scores `dropped`, which is a hard veto.

    format(..., '064x') raises on a negative int instead of encoding one, so the failure is
    loud. Values above 2**256 still truncate silently; nothing in this layer can produce one
    (amounts come from the table, addresses from the row key).
    """
    return format(int(x), '064x')
