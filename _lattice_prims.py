from __future__ import annotations
import concurrent.futures as _cf
_EXEC_BY_CHAIN = {1: '0xcd42cf6fd6e0c539cae038fe6a73c67f8c1c7a52', 8453: '0xe0d97941103c30799fa0aa9d54a34246846c73bf'}
_CONFIRM_POOL = _cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix='fill-confirm')

def _addr(v) -> str:
    """An address-ish field, normalised the single way this layer compares them.

    Open-coded as `str(x or "").lower()` at six sites. A missed `.lower()` does not raise --
    it silently fails to match a row key, and the order is dropped rather than served.
    """
    return str(v or '').lower()

def _num(v) -> int:
    """An integer field, normalised: never None, never a string. Seven sites."""
    return int(v or 0)

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

def _abi_addr_uint(sel, addr, val):
    """`sel(address,uint256)` with both words hand-encoded.

    Hand-encoding rather than importing eth_abi keeps this module stdlib-only, which is the
    property that let it survive the champion rebase that deleted every other lattice file.
    """
    return sel + _word(int(str(addr).strip(), 16)) + _word(val)