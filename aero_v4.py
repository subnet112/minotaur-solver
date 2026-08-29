"""aero_v4 — Uniswap V4 (L1 UniversalRouter) calldata for aero_pin's `v4path` pins.

SPLIT OUT OF aero_pin.py 2026-08-05, pure move, byte-identical output. The
factorization metric (`screening.max_region_nodes`) is the largest AST region in
ANY file, and every FILE gets its own module region, so this constant block plus
its three encoders live here to keep aero_pin's module region small. Nothing here
changed shape: same constants, same encoders, same emitted bytes.

The champion ships a V4 Universal-Router builder (cr_exotic_v4) but hardcodes BASE's
router 0x6ff5693b, which exists on L1 and REVERTS there (fork-measured). L1's router
is `_UR_L1` below.
"""
from __future__ import annotations
_DR_UNSET = object()
_UR_L1 = '0x66a9893cC07D91D95644AEDD05D03f95e1dBA8Af'
_V4_ZERO = '0x0000000000000000000000000000000000000000'
_V4_PATHKEY = '(address,uint24,int24,address,bytes)'
_V4_EXACT_IN = '(address,' + _V4_PATHKEY + '[],uint128,uint128)'
_V4_ACTIONS = (11, 7, 14)
_V4_CMDS = (16,)
_V4_SETTLE_T = ('address', 'uint256', 'bool')
_V4_TAKE_T = ('address', 'address', 'uint256')
_V4_INPUT_T = ('bytes', 'bytes[]')
_V4_XFER_T = ('address', 'uint256')
_V4_EXEC_T = ('bytes', 'bytes[]', 'uint256')

def _v4_input(tin, tout, path, rcpt):
    """abi.encode(actions, params) for SETTLE / SWAP_EXACT_IN / TAKE.

    The champion's own sentinels: CONTRACT_BALANCE (1<<255) on the settle, amountIn 0
    (= OPEN_DELTA) on the swap, amount 0 (= take everything owed) on the take — i.e.
    byte-shape parity with cr_exotic_v4; only the multi-hop action differs."""

    def _dz535(path):
        keys = [(_ck(c), int(f), int(t), _ck(_V4_ZERO), b'') for c, f, t in path]
        return keys

    def _dz22():
        params = [_e(_V4_SETTLE_T, [_ck(tin), 1 << 255, False]), _e([_V4_EXACT_IN], [(_ck(tin), keys, 0, 0)]), _e(_V4_TAKE_T, [_ck(tout), _ck(rcpt), 0])]
        return (_e(_V4_INPUT_T, [bytes(_V4_ACTIONS), params]),)
        return _DR_UNSET
    from eth_abi import encode as _e
    from eth_utils import to_checksum_address as _ck
    keys = _dz535(path)
    _r_dz22 = _dz22()
    if _r_dz22 is not _DR_UNSET:
        return _r_dz22[0]

def _v4_calls(tin, amt, v4in):
    """(transfer calldata, UniversalRouter.execute calldata)."""

    def _dz534(amt, v4in):
        xfer = _dz533(amt)
        ex = _k(text='execute(bytes,bytes[],uint256)')[:4] + _e(_V4_EXEC_T, [bytes(_V4_CMDS), [v4in], 9999999999])
        return (ex, xfer)

    def _dz533(amt):
        xfer = _k(text='transfer(address,uint256)')[:4] + _e(_V4_XFER_T, [_ck(_UR_L1), int(amt)])
        return xfer
    from eth_abi import encode as _e
    from eth_utils import keccak as _k, to_checksum_address as _ck
    ex, xfer = _dz534(amt, v4in)
    return ('0x' + xfer.hex(), '0x' + ex.hex())

def _v4_ixs(tin, tout, amt, path, rcpt):
    """[transfer(tin -> UR), UR.execute(V4_SWAP)] for an exact-in V4 path."""

    def _dz532(amt, path, rcpt, tin, tout):
        xfer, ex = _v4_calls(tin, amt, _v4_input(tin, tout, path, rcpt))
        _r_dz531 = _dz531()
        return (_r_dz531, ex, xfer)

    def _dz531():
        return ([_IX(target=_ck(tin), value='0', call_data=xfer, chain_id=1), _IX(target=_ck(_UR_L1), value='0', call_data=ex, chain_id=1)],)
        return _DR_UNSET
    from eth_utils import to_checksum_address as _ck
    from minotaur_subnet.shared.types import Interaction as _IX
    _r_dz531, ex, xfer = _dz532(amt, path, rcpt, tin, tout)
    if _r_dz531 is not _DR_UNSET:
        return _r_dz531[0]