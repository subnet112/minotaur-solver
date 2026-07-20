"""viking_v4_build — Universal Router execute() calldata for exact-key V4 rows.

Encoding mirrors the engine's delivery-verified V4 UR builder byte-for-byte:
fund the router by plain ERC-20 transfer, then execute() with V4 actions
[SETTLE(11) CONTRACT_BALANCE, SWAP_EXACT_IN_SINGLE(6), TAKE(14) open-delta].
A native-currency pool output is TAKEn to the router and WRAP_ETH'd (0x0b);
a chained tail re-swaps the router balance via V3 (0x00) or V2 (0x08) with
payerIsUser=False. The take/wrap/tail recipient is the final recipient exactly
once — intermediate hops stay in the router."""
_UR = {1: '0x66a9893cC07D91D95644AEDD05D03f95e1dBA8Af',
       8453: '0x6ff5693b99212da76ad316178a184ab56d299b43'}
_THIS = '0x0000000000000000000000000000000000000002'
_CBAL = 1 << 255


def _swap_param(row):
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    c0, c1, fee, ts, hook = row['key']
    return _enc(['((address,address,uint24,int24,address),bool,uint128,uint128,bytes)'],
                [((_ck(c0), _ck(c1), int(fee), int(ts), _ck(hook)),
                  bool(row['zfo']), 0, 0, b'')])


def _settle_take(row, tin, recipient):
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    cur_out = row['key'][1] if row['zfo'] else row['key'][0]
    return (_enc(['address', 'uint256', 'bool'], [_ck(tin), _CBAL, False]),
            _enc(['address', 'address', 'uint256'], [_ck(cur_out), _ck(recipient), 0]))


def _v4_input(row, tin, recipient):
    """abi(actions, params) for the single-hop V4 leg of `row`."""
    from eth_abi import encode as _enc
    settle, take = _settle_take(row, tin, recipient)
    return _enc(['bytes', 'bytes[]'], [bytes([11, 6, 14]), [settle, _swap_param(row), take]])


def _wrap_input(post, recipient):
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    return _enc(['address', 'uint256'], [_ck(_THIS if post else recipient), _CBAL])


def _v3_tail_input(post, recipient):
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    toks, fees = post[1], post[2]
    path = bytes.fromhex(_ck(toks[0])[2:]) + int(fees[0]).to_bytes(3, 'big') + bytes.fromhex(_ck(toks[1])[2:])
    return _enc(['address', 'uint256', 'uint256', 'bytes', 'bool'],
                [_ck(recipient), _CBAL, 0, path, False])


def _v2_tail_input(post, recipient):
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    return _enc(['address', 'uint256', 'uint256', 'address[]', 'bool'],
                [_ck(recipient), _CBAL, 0, [_ck(t) for t in post[1]], False])


def _post_tail(post, recipient):
    if post[0] == 'v3':
        return bytes([0]), _v3_tail_input(post, recipient)
    return bytes([8]), _v2_tail_input(post, recipient)


def _tail(row, recipient):
    """(commands, inputs) for wrap + chained v2/v3 tail after the V4 leg."""
    post = row.get('post')
    cmds, ins = b'', []
    if row.get('wrap'):
        cmds += bytes([11])
        ins.append(_wrap_input(post, recipient))
    if post:
        c, i = _post_tail(post, recipient)
        cmds += c
        ins.append(i)
    return cmds, ins


def _exec_cd(commands, inputs):
    from eth_abi import encode as _enc
    from eth_utils import keccak
    return '0x' + (keccak(text='execute(bytes,bytes[],uint256)')[:4]
                   + _enc(['bytes', 'bytes[]', 'uint256'], [commands, inputs, 9999999999])).hex()


def _xfer_cd(ur, amt):
    from eth_abi import encode as _enc
    from eth_utils import keccak
    return '0x' + (keccak(text='transfer(address,uint256)')[:4]
                   + _enc(['address', 'uint256'], [ur, int(amt)])).hex()


def _fund_exec_ix(chain, tin, ur, commands, inputs, amt):
    """[transfer tin->UR, UR.execute()] interaction pair."""
    from eth_utils import to_checksum_address as _ck
    from minotaur_subnet.shared.types import Interaction
    return [Interaction(target=_ck(tin), value='0', call_data=_xfer_cd(ur, amt), chain_id=chain),
            Interaction(target=ur, value='0', call_data=_exec_cd(commands, inputs), chain_id=chain)]


def _commands(row, tin, recipient):
    """(commands, inputs) for the full execute(): V4 leg + wrap/post tail."""
    mid = recipient if not (row.get('wrap') or row.get('post')) else _THIS
    tail_cmds, tail_ins = _tail(row, recipient)
    return bytes([16]) + tail_cmds, [_v4_input(row, tin, mid)] + tail_ins


def serve_v4(intent, state, chain, tin, tout, row, amt, recipient, out):
    """transfer -> UR execute() plan for one verified V4 table row."""
    import viking_build as _b
    from eth_utils import to_checksum_address as _ck
    cmds, ins = _commands(row, tin, recipient)
    ix = _fund_exec_ix(chain, tin, _ck(_UR[chain]), cmds, ins, amt)
    return _b._mk_plan(intent, state, chain, ix, 'v4', tin, tout, out)
