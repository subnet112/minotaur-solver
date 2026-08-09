"""Lower layer of g2_codec.py, split out to reduce max_region_nodes.

Dependency-closed: every module-level name these statements read is defined here
too, so this module never imports back from g2_codec and no cycle is possible.
Semantics unchanged -- same objects, same names, same order.
"""
from __future__ import annotations
_DR_UNSET = object()
__all__ = ['_BAL_VAULT', '_EXECUTOR', '_ROUTER_V2', '_ROUTER_V3', '_RPC_URLS', '_USDT', '_V4_ADDRESS_THIS', '_V4_CONTRACT_BALANCE', '_V4_UR', '_bal_order_id32', '_curve_abi', '_curve_args', '_lift_bal_swap_cd_0', '_lift_bal_swap_cd_1', '_pack_path', '_transfer_leg', '_v2_swap_cd', 'annotations']
'g2 codec + leg builders — split from g2_fill (region hygiene: each\nmodule top is its own region; the serve/table/guard logic stays in g2_fill).\nRouting constants live here with the builders that consume them.'
_ROUTER_V3 = '0xE592427A0AEce92De3Edee1F18E0157C05861564'
_ROUTER_V2 = '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'
_USDT = '0xdac17f958d2ee523a2206206994597c13d831ec7'

def _pack_path(tokens, fees) -> bytes:
    b = b''
    for i, t in enumerate(tokens):
        b += bytes.fromhex(str(t)[2:])
        if i < len(fees):
            b += int(fees[i]).to_bytes(3, 'big')
    return b

def _v2_swap_cd(spec, rcpt) -> str:
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    args = _enc(['uint256', 'uint256', 'address[]', 'address', 'uint256'], [int(spec['amt_in']), 0, [_ck(t) for t in spec['tokens']], _ck(rcpt), 9999999999])
    return '0x5c11d795' + args.hex()

def _curve_abi(flavor, recv=False):
    """(signature, arg types) for a curve pool's exchange entrypoint. The
    int128 index width is the stable/underlying convention; crypto pools take
    uint256 indices — a mismatch encodes a valid-looking call that reverts.

    recv=True selects the RECEIVER overload, which pays an explicit address
    instead of msg.sender. That matters beyond convenience: without it a
    curve-final route must append a transfer of a BAKED amount, and a route
    that thins past that amount reverts and delivers nothing — a dropped row,
    which is an un-nettable veto. Paying the recipient inside the swap removes
    that failure mode entirely. Only pools whose bytecode carries the overload
    may set it (checked at bake time); assuming it would encode a call the
    pool cannot answer."""
    idx = 'uint256' if flavor == 'crypto' else 'int128'
    name = 'exchange_underlying' if flavor == 'underlying' else 'exchange'
    if recv == '6a':
        args = [idx, idx, 'uint256', 'uint256', 'bool', 'address']
    else:
        args = [idx, idx, 'uint256', 'uint256'] + (['address'] if recv else [])
    return (f'{name}({','.join(args)})', args)

def _curve_args(i, j, dx, recv, rcpt, _ck):
    """Curve exchange args, lifted verbatim from _curve_swap_cd.

    The "6a" form is the NG-crypto receiver overload and takes a use_eth flag the plain receiver
    overload does not -- the two arg lists are not interchangeable, so both branches move together.
    """
    if recv == '6a':
        return [i, j, dx, 0, False, _ck(rcpt)]
    return [i, j, dx, 0] + ([_ck(rcpt)] if recv else [])
_EXECUTOR = '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266'

def _transfer_leg(token, amt, rcpt, Interaction, cid=1):
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    cd = '0xa9059cbb' + _enc(['address', 'uint256'], [_ck(rcpt), amt]).hex()
    return Interaction(target=token, value='0', call_data=cd, chain_id=cid)
_BAL_VAULT = '0xBA12222222228d8Ba445958a75a0704d566BF2C8'
_RPC_URLS = {}
from g2_orderid_ext import _bal_order_id32
from g2_bal0_ext import _lift_bal_swap_cd_0

def _lift_bal_swap_cd_1(_ck, _enc, _keccak, amount, deadline, funds, route, tin, tout):

    def _c_lift_bal_swap_cd_1_0(_ck, _keccak, amount, route, tin, tout):
        """Lifted from _bal_swap_cd: a return-terminated branch, verbatim."""

        def _dz98():
            sel = _keccak(text='batchSwap(uint8,(bytes32,uint256,uint256,uint256,bytes)[],address[],(address,bool,address,bool),int256[],uint256)')[:4]
            swaps = [(bytes.fromhex(str(p1).replace('0x', '')), 0, 1, amount, b''), (bytes.fromhex(str(p2).replace('0x', '')), 1, 2, 0, b'')]
            assets = [_ck(tin), _ck(hub), _ck(tout)]
            limits = [amount, 0, 0]
            return ((assets, limits, sel, swaps),)
            return _DR_UNSET
        p1, p2, hub = (route[1], route[2], route[3])
        _r_dz98 = _dz98()
        if _r_dz98 is not _DR_UNSET:
            return _r_dz98[0]
    assets, limits, sel, swaps = _c_lift_bal_swap_cd_1_0(_ck, _keccak, amount, route, tin, tout)
    return sel + _enc(['uint8', '(bytes32,uint256,uint256,uint256,bytes)[]', 'address[]', '(address,bool,address,bool)', 'int256[]', 'uint256'], [0, swaps, assets, funds, limits, int(deadline)])
_V4_UR = '0x66a9893cC07D91D95644AEDD05D03f95e1dBA8Af'
_V4_ADDRESS_THIS = '0x0000000000000000000000000000000000000002'
_V4_CONTRACT_BALANCE = 1 << 255