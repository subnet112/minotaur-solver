"""v3_arb2 — leaf primitives for the v3_arb 2-hop override cover (quoting,
path/calldata encoding, router-call decoding). Split out of v3_arb so every
region stays <=110 AST nodes (hydra base is factor 110). No dependency on
v3_arb: the call graph is strictly v3_arb (top) -> v3_arb2 (leaf)."""

_FEES = (100, 500, 3000, 10000)


def _quoter(chain):
    """Uniswap V3 QuoterV2 address for the chain, or None."""
    return {1: '0x61fFE014bA17989E743c5F6cB21bF9697530B21e',
            8453: '0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a'}.get(int(chain))


def _bases(chain):
    """Intermediate hubs for the 2-hop (WETH/USDC/USDT/DAI/WBTC etc.)."""
    return {1: ('0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',
                '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',
                '0xdac17f958d2ee523a2206206994597c13d831ec7',
                '0x6b175474e89094c44da98b954eedeac495271d0f',
                '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599'),
            8453: ('0x4200000000000000000000000000000000000006',
                   '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913',
                   '0x50c5725949a6f0c72e6c4a641f24049a917db0cb',
                   '0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca',
                   '0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22')}.get(int(chain), ())


def _router02(chain):
    """Uniswap SwapRouter02 (the executor's router). 4-field exactInput ABI
    (0xb858183f) delivers here; the V1 5-field (0xc04b8d59) is rejected."""
    return {1: '0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45',
            8453: '0x2626664c2603336E57B271c5C0b26F421741e481'}.get(int(chain))


def _q_cd(tin, tout, amt, fee):
    """quoteExactInputSingle calldata bytes (selector 0xc6a5026a)."""
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    return bytes.fromhex('c6a5026a') + _enc(
        ['(address,address,uint256,uint24,uint160)'],
        [(_ck(tin), _ck(tout), int(amt), int(fee), 0)])


def _quote(w3, chain, tin, tout, fee, amt):
    """One QuoterV2 quoteExactInputSingle; 0 on failure."""
    from eth_abi import decode as _dec
    from eth_utils import to_checksum_address as _ck
    q = _quoter(chain)
    if not q:
        return 0
    try:
        r = w3.eth.call({'to': _ck(q), 'data': '0x' + _q_cd(tin, tout, amt, fee).hex()})
        return int(_dec(['uint256', 'uint160', 'uint32', 'uint256'], bytes(r))[0])
    except Exception:
        return 0


def _quote_path(w3, chain, path, amt):
    """QuoterV2 quoteExactInput(bytes,uint256) sel 0xcdca1753; amountOut or 0."""
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    q = _quoter(chain)
    if not q:
        return 0
    data = bytes.fromhex('cdca1753') + _enc(['bytes', 'uint256'], [path, int(amt)])
    try:
        r = bytes(w3.eth.call({'to': _ck(q), 'data': '0x' + data.hex()}))
        return int.from_bytes(r[0:32], 'big') if len(r) >= 32 else 0
    except Exception:
        return 0


def _v3_path(tin, base, tout, f1, f2):
    """Packed Uniswap V3 path. base None => direct single-hop (tin,f1,tout);
    else 2-hop (tin,f1,base,f2,tout). Served as exactInput either way."""
    from eth_utils import to_checksum_address as _ck
    head = bytes.fromhex(_ck(tin)[2:]) + int(f1).to_bytes(3, 'big')
    if base is None:
        return head + bytes.fromhex(_ck(tout)[2:])
    return (head + bytes.fromhex(_ck(base)[2:]) + int(f2).to_bytes(3, 'big')
            + bytes.fromhex(_ck(tout)[2:]))


def _encode_2hop(tin, base, tout, f1, f2, amt, recipient):
    """exactInput calldata via SwapRouter02 (4-field 0xb858183f, NO deadline);
    router does both hops internally, final output to recipient (the app)."""
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    sel = _keccak(text='exactInput((bytes,address,uint256,uint256))')[:4]
    return '0x' + (sel + _enc(['(bytes,address,uint256,uint256)'],
                              [(_v3_path(tin, base, tout, f1, f2), _ck(recipient), int(amt), 0)])).hex()


def _approve_ix(tin, router, amt, chain):
    """ERC20 approve(router, amt) Interaction for the input token."""
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction
    return Interaction(target=_ck(tin), value='0',
                       call_data=encode_approve(_ck(router), int(amt)), chain_id=chain)


def _swap_ix(router, cd, chain):
    """Router exactInput Interaction carrying the 2-hop calldata."""
    from eth_utils import to_checksum_address as _ck
    from minotaur_subnet.shared.types import Interaction
    return Interaction(target=_ck(router), value='0', call_data=cd, chain_id=chain)


def _ds0(body):
    """Decode exactInputSingle 0x04e45aaf (7-field) -> (tin,tout,fee,amtIn)."""
    from eth_abi import decode as _d
    t = _d(['(address,address,uint24,address,uint256,uint256,uint160)'], body)[0]
    return (t[0], t[1], t[2], t[4])


def _ds1(body):
    """Decode exactInputSingle 0x414bf389 (8-field) -> (tin,tout,fee,amtIn)."""
    from eth_abi import decode as _d
    t = _d(['(address,address,uint24,address,uint256,uint256,uint256,uint160)'], body)[0]
    return (t[0], t[1], t[2], t[5])


def _decode_single(cd):
    """exactInputSingle -> (tin, tout, fee, amtIn) or None (both variants)."""
    sel = cd[:10]
    body = bytes.fromhex(cd[10:])
    try:
        if sel == '0x04e45aaf':
            return _ds0(body)
        if sel == '0x414bf389':
            return _ds1(body)
    except Exception:
        return None
    return None


def _decode_path(cd):
    """exactInput -> (path_bytes, amtIn) or None (deadline / no-deadline)."""
    from eth_abi import decode as _d
    sel = cd[:10]
    body = bytes.fromhex(cd[10:])
    try:
        if sel == '0xc04b8d59':
            t = _d(['(bytes,address,uint256,uint256,uint256)'], body)[0]
            return (t[0], t[3])
        if sel == '0xb858183f':
            t = _d(['(bytes,address,uint256,uint256)'], body)[0]
            return (t[0], t[2])
    except Exception:
        return None
    return None


def _requote(w3, chain, cd):
    """Re-quote a decodable router call to its delivered amount; None if the
    selector is unknown (=> caller can't prove the base is dead)."""
    sng = _decode_single(cd)
    if sng is not None:
        return _quote(w3, chain, sng[0], sng[1], sng[2], sng[3])
    pth = _decode_path(cd)
    if pth is not None:
        return _quote_path(w3, chain, pth[0], pth[1])
    return None
