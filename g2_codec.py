from __future__ import annotations
_DR_UNSET = object()
from g2_codec_base import *

def _mk_routers():
    """The router registry, built in a function so the dict literal sits in a FUNCTION
    region rather than the module's. Same object, same import-time construction.
    """
    return {1: {'v3': _ROUTER_V3, 'v2': _ROUTER_V2}, 8453: {'v3': '0x2626664c2603336E57B271c5C0b26F421741e481', 'v2': '0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24'}}
_ROUTERS = _mk_routers()

def _chain_ready(spec) -> bool:
    """Early per-chain capability gate: a spec row on a chain with neither a
    registry entry nor its own router override cannot build legs — fail
    closed before any leg assembly instead of inside the builders."""
    if spec.get('router'):
        return True
    cid = int(spec.get('chain_id') or 1)
    return cid in _ROUTERS

def _router_for(spec, venue):
    r = spec.get('router')
    if r:
        return str(r)
    cid = int(spec.get('chain_id') or 1)
    return (_ROUTERS.get(cid) or {}).get(venue)

def _v3_swap_cd(spec, rcpt) -> str:
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck

    def _dz72():
        nonlocal args, sel
        from eth_abi import encode as _enc
        from eth_utils import keccak as _keccak, to_checksum_address as _ck
        if int(spec.get('chain_id') or 1) == 8453:
            sel = _keccak(text='exactInput((bytes,address,uint256,uint256))')[:4]
            args = _enc(['(bytes,address,uint256,uint256)'], [(_pack_path(spec['tokens'], spec.get('fees') or []), _ck(rcpt), int(spec['amt_in']), 0)])
            return ('0x' + (sel + args).hex(),)
        return _DR_UNSET
    _r_dz72 = _dz72()
    if _r_dz72 is not _DR_UNSET:
        return _r_dz72[0]
    sel = _keccak(text='exactInput((bytes,address,uint256,uint256,uint256))')[:4]
    args = _enc(['(bytes,address,uint256,uint256,uint256)'], [(_pack_path(spec['tokens'], spec.get('fees') or []), _ck(rcpt), 9999999999, int(spec['amt_in']), 0)])
    return '0x' + (sel + args).hex()

def _curve_swap_cd(hop, rcpt=None) -> str:

    def _c_curve_swap_cd_0(hop, rcpt):

        def _dz65():
            recv = hop.get('recv') if rcpt is not None else None
            recv = '6a' if recv == '6a' else bool(recv)
            sig, types = _curve_abi(hop.get('flavor') or 'stable', recv)
            sel = _keccak(text=sig)[:4]
            args = _curve_args(i, j, dx, recv, rcpt, _ck)
            return ((_enc, args, sel, types),)
            return _DR_UNSET
        from eth_abi import encode as _enc
        from eth_utils import keccak as _keccak, to_checksum_address as _ck
        dx, i, j = (int(hop['dx']), int(hop['i']), int(hop['j']))
        _r_dz65 = _dz65()
        if _r_dz65 is not _DR_UNSET:
            return _r_dz65[0]
    _enc, args, sel, types = _c_curve_swap_cd_0(hop, rcpt)
    return '0x' + (sel + _enc(types, args)).hex()

def _hop_target_cd(spec, hop, is_last, rcpt):
    """(target, calldata) for one hop. v3 hops carry an explicit recipient:
    the FINAL hop pays rcpt, a MID hop pays the executor so the next hop's
    input is actually held by the spender. Curve exchange pays msg.sender
    (the executor), never the scored recipient."""
    if hop['kind'] == 'v3':
        cd = _v3_swap_cd({'tokens': hop['tokens'], 'fees': hop.get('fees') or [], 'amt_in': int(hop['dx'])}, rcpt if is_last else _EXECUTOR)
        return (_router_for(spec, 'v3'), cd)
    return (hop['pool'], _curve_swap_cd(hop, rcpt if is_last else None))

def _hop_legs(spec, hop, is_last, rcpt, Interaction, cid):
    """Approve + swap legs for one hop; [] when the hop has no routable
    target (fails the whole route closed)."""
    target, cd = _hop_target_cd(spec, hop, is_last, rcpt)
    if not target:
        return []
    legs = _approve_legs(str(hop['tokens'][0]).lower(), int(hop['dx']), target, Interaction, cid)
    legs.append(Interaction(target=target, value='0', call_data=cd, chain_id=cid))
    return legs

def _final_transfer(spec, rcpt, Interaction, cid):
    """Curve-FINAL routes need an explicit transfer moving the output from
    the executor to rcpt, or the scorer measures zero (measured: 3 curve
    routes executed clean, on-chain score 5000, raw_output 0).

    The leg is skipped when the amount rounds to nothing. ERC20s revert a
    zero-value transfer (`Transfer amount must be greater than zero`), and
    that reverts the WHOLE intent, so a dust leg does not cost dust — it
    costs the entire order. `not spec.get('out')` does not catch it: `out`
    reaches here as the string `'0'` (truthy) on a zero-quote row, and a
    small nonzero `out` still floors to 0 through `* bps // 10000`.
    Measured 2026-08-25 on the exec fork, both trees reverting at ~398k
    gas: veto:q_2ed4bdf29aea and veto:q_44f422b84029, USDC ->
    0x72e4f9F8, quoted_output '0'. Returning None keeps the hop legs, so
    the route can still deliver instead of reverting to zero."""

    def _dz68():
        if last['kind'] == 'v3' or not spec.get('out'):
            return (None,)
        if last.get('recv'):
            return (None,)
        bps = int(spec.get('transfer_bps') or 9500)
        amt = int(spec['out']) * bps // 10000
        if amt <= 0:
            return (None,)
        return (_transfer_leg(str(last['tokens'][-1]), amt, rcpt, Interaction, cid),)
        return _DR_UNSET
    last = spec['hops'][-1]
    _r_dz68 = _dz68()
    if _r_dz68 is not _DR_UNSET:
        return _r_dz68[0]

def _route_legs(spec, rcpt, Interaction):

    def _dz71():
        nonlocal legs
        n = len(spec['hops'])
        for idx, hop in enumerate(spec['hops']):
            built = _hop_legs(spec, hop, idx == n - 1, rcpt, Interaction, cid)
            if not built:
                return ([],)
            legs += built
        extra = _final_transfer(spec, rcpt, Interaction, cid)
        if extra is not None:
            legs.append(extra)
        return (legs,)
        return _DR_UNSET
    legs = []
    cid = int(spec.get('chain_id') or 1)
    _r_dz71 = _dz71()
    if _r_dz71 is not _DR_UNSET:
        return _r_dz71[0]

def _approve_legs(tin, amt, router, Interaction, cid=1):
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    legs = []
    if cid == 1 and tin == _USDT:
        legs.append(Interaction(target=tin, value='0', call_data=encode_approve(_ck(router), 0), chain_id=cid))
    legs.append(Interaction(target=tin, value='0', call_data=encode_approve(_ck(router), amt), chain_id=cid))
    return legs

def _legs_router_cd(spec, rcpt):
    """(router, swap calldata) for a single-venue spec, lifted verbatim from _legs.

    v2 is selected only on an explicit venue=="v2"; every other value falls to v3, which is the
    original's else-branch and not a default worth "tidying" -- an unknown venue must keep taking
    the v3 path, not fail closed.
    """
    if spec.get('venue') == 'v2':
        return (_router_for(spec, 'v2'), _v2_swap_cd(spec, rcpt))
    return (_router_for(spec, 'v3'), _v3_swap_cd(spec, rcpt))

def _legs(spec, rcpt, Interaction):

    def _dz70():
        tin = str(spec['tokens'][0]).lower()
        amt = int(spec['amt_in'])
        router, swap_cd = _legs_router_cd(spec, rcpt)
        if not router:
            return ([],)
        legs = _approve_legs(tin, amt, router, Interaction, cid)
        legs.append(Interaction(target=router, value='0', call_data=swap_cd, chain_id=cid))
        return (legs,)
        return _DR_UNSET
    if spec.get('venue') == 'route':
        return _route_legs(spec, rcpt, Interaction)
    cid = int(spec.get('chain_id') or 1)
    _r_dz70 = _dz70()
    if _r_dz70 is not _DR_UNSET:
        return _r_dz70[0]

def _set_rpc(urls):
    try:
        _RPC_URLS.update({int(k): str(v) for k, v in (urls or {}).items()})
    except Exception:
        pass

def _bal_w3(cid):
    url = _RPC_URLS.get(int(cid))
    if not url:
        return None
    from web3 import Web3
    return Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 8}))

def _bal_bench_order_id(state):

    def _dz69():
        control = getattr(state, 'control', None) or {}
        seed = '|'.join((str(getattr(state, 'contract_address', '')).lower(), str(getattr(state, 'chain_id', '')), str(control.get('_scenario_name', '')), str(control.get('_intent_function', 'swap')), str(fork_block)))
        return ('bench_' + hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16],)
        return _DR_UNSET
    import hashlib
    w3 = _bal_w3(getattr(state, 'chain_id', 1))
    if w3 is None:
        return None
    try:
        fork_block = int(w3.eth.block_number)
    except Exception:
        return None
    _r_dz69 = _dz69()
    if _r_dz69 is not _DR_UNSET:
        return _r_dz69[0]

def _bal_proxy(state):

    def _dz68():
        data = _keccak(text='predictProxy(bytes32)')[:4] + _bal_order_id32(oid)
        try:
            r = w3.eth.call({'to': _ck(str(state.contract_address)), 'data': '0x' + data.hex()})
            rb = bytes(r)
            if len(rb) < 20:
                return (None,)
            return (_ck('0x' + rb[-20:].hex()),)
        except Exception:
            return (None,)
        return _DR_UNSET
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    w3 = _bal_w3(getattr(state, 'chain_id', 1))
    if w3 is None:
        return None
    oid = _bal_bench_order_id(state)
    if oid is None:
        return None
    _r_dz68 = _dz68()
    if _r_dz68 is not _DR_UNSET:
        return _r_dz68[0]

def _bal_swap_cd(spec, proxy, rcpt, deadline) -> bytes | None:

    def _dz67():
        amount = int(spec['amt_in'])
        funds = (_ck(proxy), False, _ck(rcpt), False)
        if route[0] == 'direct':
            return (_lift_bal_swap_cd_0(_ck, _enc, _keccak, amount, deadline, funds, route, tin, tout),)
        if route[0] == 'hop':
            return (_lift_bal_swap_cd_1(_ck, _enc, _keccak, amount, deadline, funds, route, tin, tout),)
        return (None,)
        return _DR_UNSET
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    route = spec['route']
    tin, tout = (spec['tokens'][0], spec['tokens'][-1])
    _r_dz67 = _dz67()
    if _r_dz67 is not _DR_UNSET:
        return _r_dz67[0]

def _bal_serve_legs(spec, rcpt, state, Interaction):

    def _dz66():
        cid = int(spec.get('chain_id') or 1)
        cd = _bal_swap_cd(spec, proxy, rcpt, 9999999999)
        if cd is None:
            return ([],)
        legs = _approve_legs(str(spec['tokens'][0]).lower(), int(spec['amt_in']), _BAL_VAULT, Interaction, cid)
        legs.append(Interaction(target=_BAL_VAULT, value='0', call_data='0x' + cd.hex(), chain_id=cid))
        return (legs,)
        return _DR_UNSET
    try:
        proxy = _bal_proxy(state)
        if proxy is None:
            return []
        _r_dz66 = _dz66()
        if _r_dz66 is not _DR_UNSET:
            return _r_dz66[0]
    except Exception:
        return []

def _v4_leg_param(pool_key, zfo, _enc, _ck):
    """One V4 SWAP_EXACT_IN_SINGLE param word, lifted verbatim from _v4_execute_cd's leg loop."""
    c0, c1, fee, ts, hooks = pool_key
    return _enc(['((address,address,uint24,int24,address),bool,uint128,uint128,bytes)'], [((_ck(c0), _ck(c1), int(fee), int(ts), _ck(hooks)), bool(zfo), 0, 0, b'')])

def _v4_actions_params(spec, rcpt, _enc, _ck):

    def _c_v4_actions_params_0(_ck, _enc, rcpt, spec):
        """The V4Router actions blob and its params, lifted verbatim from _v4_execute_cd.

        _V4_ADDRESS_THIS / _V4_CONTRACT_BALANCE are module globals and this helper stays in the same
        module, so they resolve exactly as they did inside the parent.
        """

        def _dz64():
            actions = bytes([11] + [6] * len(legs) + [14])
            params = [_enc(['address', 'uint256', 'bool'], [_ck(str(spec['settle'])), _V4_CONTRACT_BALANCE, False])]
            params += [_v4_leg_param(pk, zfo, _enc, _ck) for pk, zfo in legs]
            take_to = _V4_ADDRESS_THIS if spec.get('wrap_out') else rcpt
            return ((actions, params, take_to),)
            return _DR_UNSET
        legs = [(tuple(pk), bool(zfo)) for pk, zfo in spec['pools']]
        _r_dz64 = _dz64()
        if _r_dz64 is not _DR_UNSET:
            return _r_dz64[0]
    actions, params, take_to = _c_v4_actions_params_0(_ck, _enc, rcpt, spec)

    def _c_v4_actions_params_1(_ck, _enc, params, spec, take_to):
        params.append(_enc(['address', 'address', 'uint256'], [_ck(str(spec['take'])), _ck(take_to), 0]))
    _c_v4_actions_params_1(_ck, _enc, params, spec, take_to)
    return (actions, params)

def _v4_execute_cd(spec, rcpt) -> str:

    def _c_v4_execute_cd_0(rcpt, spec):

        def _dz63():
            nonlocal commands
            if spec.get('unwrap_weth'):
                inputs.append(_enc(['address', 'uint256'], [_ck(_V4_ADDRESS_THIS), 0]))
                commands += bytes([12])
            actions, params = _v4_actions_params(spec, rcpt, _enc, _ck)
            inputs.append(_enc(['bytes', 'bytes[]'], [actions, params]))
            commands += bytes([16])
            return ((_ck, _enc, _keccak, commands, inputs),)
            return _DR_UNSET
        from eth_abi import encode as _enc
        from eth_utils import keccak as _keccak, to_checksum_address as _ck
        commands = b''
        inputs = []
        _r_dz63 = _dz63()
        if _r_dz63 is not _DR_UNSET:
            return _r_dz63[0]
    _ck, _enc, _keccak, commands, inputs = _c_v4_execute_cd_0(rcpt, spec)

    def _c_v4_execute_cd_1(_ck, _enc, commands, inputs, rcpt, spec):
        if spec.get('wrap_out'):
            inputs.append(_enc(['address', 'uint256'], [_ck(rcpt), _V4_CONTRACT_BALANCE]))
            commands += bytes([11])
        return commands
    commands = _c_v4_execute_cd_1(_ck, _enc, commands, inputs, rcpt, spec)
    return '0x' + (_keccak(text='execute(bytes,bytes[],uint256)')[:4] + _enc(['bytes', 'bytes[]', 'uint256'], [commands, inputs, 9999999999])).hex()

def _v4_serve_legs(spec, rcpt, Interaction):
    try:
        cid = int(spec.get('chain_id') or 1)
        tin = str(spec['tokens'][0]).lower()
        amt = int(spec['amt_in'])
        cd = _v4_execute_cd(spec, rcpt)
        return [_transfer_leg(tin, amt, _V4_UR, Interaction, cid), Interaction(target=_V4_UR, value='0', call_data=cd, chain_id=cid)]
    except Exception:
        return []