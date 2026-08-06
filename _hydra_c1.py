"""Cross-chain (xchain) leg builders — the only part of the old wide-venue
mining module the shipped tree still uses. The mining/quoting machinery moved
offline (.mine_mods) 2026-08-04 when the deadwood-v1 intake gate landed (cap
4600 dead AST nodes; the dead dyn/hf functions here alone carried ~1459)."""
from __future__ import annotations
from eth_abi import encode as _enc
from eth_utils import keccak as _kec

_S_APPROVE = _kec(text="approve(address,uint256)")[:4]


def _hx_consts():
    return (
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",         # WETH.eth
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",         # USDC.eth
        "0x4200000000000000000000000000000000000006",         # WETH.base
        "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",         # USDC.base
        "0xE592427A0AEce92De3Edee1F18E0157C05861564",         # V3 SwapRouter (eth, deadline)
        "0x2626664c2603336E57B271c5C0b26F421741e481",         # V3 SwapRouter02 (base)
        "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",         # anvil default receiver
    )


(_HXW1, _HXU1, _HXWB, _HXUB, _HXR1, _HXRB, _HX_RCPT) = _hx_consts()


def hx_bridged(tin, dst):
    m = {(_HXW1, 8453): _HXWB, (_HXWB, 1): _HXW1,
         (_HXU1, 8453): _HXUB, (_HXUB, 1): _HXU1}
    return m.get((tin, dst))


def _hx_ix(t, d, dst):
    return {'target': t, 'value': '0', 'call_data': '0x' + d.hex(), 'chain_id': dst}


def hx_dest_ixs(bridged, tout, dst, est, rcpt):
    from eth_utils import to_checksum_address as ck
    if bridged == tout:
        cd = _kec(text='transfer(address,uint256)')[:4] + _enc(['address', 'uint256'], [ck(rcpt), est])
        return [_hx_ix(ck(bridged), cd, dst)]
    router = _HXRB if dst == 8453 else _HXR1
    ap = _S_APPROVE + _enc(['address', 'uint256'], [ck(router), est])
    path = bytes.fromhex(bridged[2:]) + (500).to_bytes(3, 'big') + bytes.fromhex(tout[2:])
    if dst == 8453:
        sw = _kec(text='exactInput((bytes,address,uint256,uint256))')[:4] + \
            _enc(['(bytes,address,uint256,uint256)'], [(path, ck(rcpt), est, 0)])
    else:
        sw = _kec(text='exactInput((bytes,address,uint256,uint256,uint256))')[:4] + \
            _enc(['(bytes,address,uint256,uint256,uint256)'], [(path, ck(rcpt), 4102444800, est, 0)])
    return [_hx_ix(ck(bridged), ap, dst), _hx_ix(ck(router), sw, dst)]


def hx_ccp(cid, dst, tin, amt, rcpt, ixs):
    from eth_utils import to_checksum_address as ck
    leg = {'intent_selector': '', 'intent_params_hex': '', 'metadata': {}}
    return {'legs': [{'chain_id': cid, 'interactions': [], **leg},
                     {'chain_id': dst, 'interactions': ixs, **leg}],
            'bridge_requests': [{'token': ck(tin), 'amount': amt, 'src_chain_id': cid,
                                 'dst_chain_id': dst, 'recipient': ck(rcpt), 'min_output': 0,
                                 'purpose': 'canonical bridge for cross-chain intent'}]}
