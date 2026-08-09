_V_V3_ROUTERS = {'uni': '0x2626664c2603336E57B271c5C0b26F421741e481', 'pancake': '0x678Aa4bF4E210cf2166753e054d5b7c31cc7fa86'}
_V_E1_QUOTER = '0x61fFE014bA17989E743c5F6cB21bF9697530B21e'
_V_E1_ROUTER = '0xE592427A0AEce92De3Edee1F18E0157C05861564'

def _v_build_ss(spec, tin, tout, amt, chain_id):
    """Slipstream-family single-hop row builder."""
    from eth_utils import to_checksum_address as _ck
    from strategies.dex_aggregator import aerodrome as _aero
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction as _IX
    slip_router = spec.get('r') or _aero.AERODROME_SLIPSTREAM_ROUTER[chain_id]

    def _dr339(rcpt):
        leg = _aero.encode_exact_input_single(token_in=tin, token_out=tout, tick_spacing=int(spec['slip_ts']), recipient=rcpt, deadline=9999999999, amount_in=int(amt), amount_out_minimum=0)
        return [_IX(target=tin, value='0', call_data=encode_approve(_ck(slip_router), int(amt)), chain_id=chain_id), _IX(target=slip_router, value='0', call_data=leg, chain_id=chain_id)]
    return _dr339

def _sg2_legs(spec, tin, amt):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    v3_r = _V_V3_ROUTERS[spec.get('l1r') or 'uni']
    sel1 = _keccak(text='exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))')[:4]
    leg1 = '0x' + (sel1 + _enc(['(address,address,uint24,address,uint256,uint256,uint160)'], [(_ck(tin), _ck(spec['mid']), int(spec['l1_fee']), '0x0000000000000000000000000000000000000001', int(amt), 0, 0)])).hex()
    return (v3_r, leg1)

def _sg2_leg2(spec, q1, rcpt):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    sel2 = _keccak(text='exchange(int128,int128,uint256,uint256,address)')[:4]
    return '0x' + (sel2 + _enc(['int128', 'int128', 'uint256', 'uint256', 'address'], [int(spec['i']), int(spec['j']), int(q1), 0, _ck(rcpt)])).hex()

def _v_build_sg2(spec, tin, tout, amt, q1, chain_id):
    """2-leg sg2 row builder (v3 sentinel leg1, StableNg leg2)."""
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction as _IX
    v3_r, leg1 = _sg2_legs(spec, tin, amt)

    def _dr344(rcpt):
        leg2 = _sg2_leg2(spec, q1, rcpt)
        return [_IX(target=tin, value='0', call_data=encode_approve(_ck(v3_r), int(amt)), chain_id=chain_id), _IX(target=v3_r, value='0', call_data=leg1, chain_id=chain_id), _IX(target=spec['mid'], value='0', call_data=encode_approve(_ck(spec['pool']), int(q1)), chain_id=chain_id), _IX(target=spec['pool'], value='0', call_data=leg2, chain_id=chain_id)]
    return _dr344

def _v_build_sgs(spec, tin, tout, amt, chain_id):
    """Single-leg Curve StableNg: approve + exchange(i, j, amt, 0, rcpt)."""
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction as _IX

    def _dr345(rcpt):
        leg = _sg2_leg2(spec, amt, rcpt)
        return [_IX(target=tin, value='0', call_data=encode_approve(_ck(spec['pool']), int(amt)), chain_id=chain_id), _IX(target=spec['pool'], value='0', call_data=leg, chain_id=chain_id)]
    return _dr345

def _gs2_legs(spec, amt):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    v3_r = _V_V3_ROUTERS[spec.get('l2r') or 'uni']
    sel1 = _keccak(text='exchange(int128,int128,uint256,uint256,address)')[:4]
    leg1 = '0x' + (sel1 + _enc(['int128', 'int128', 'uint256', 'uint256', 'address'], [int(spec['i']), int(spec['j']), int(amt), 0, _ck(v3_r)])).hex()
    return (v3_r, leg1)

def _gs2_leg2(spec, tout, rcpt):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    sel2 = _keccak(text='exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))')[:4]
    return '0x' + (sel2 + _enc(['(address,address,uint24,address,uint256,uint256,uint160)'], [(_ck(spec['mid']), _ck(tout), int(spec['l2_fee']), _ck(rcpt), 0, 0, 0)])).hex()

def _v_build_gs2(spec, tin, tout, amt, q1, exec_addr, chain_id):
    """2-leg gs2 route builder."""
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction as _IX
    v3_r, leg1 = _gs2_legs(spec, amt)

    def _dr346(rcpt):
        leg2 = _gs2_leg2(spec, tout, rcpt)
        return [_IX(target=tin, value='0', call_data=encode_approve(_ck(spec['pool']), int(amt)), chain_id=chain_id), _IX(target=spec['pool'], value='0', call_data=leg1, chain_id=chain_id), _IX(target=v3_r, value='0', call_data=leg2, chain_id=chain_id)]
    return _dr346

def _e1_leg(spec, amt, rcpt):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    sel = _keccak(text='exactInput((bytes,address,uint256,uint256,uint256))')[:4]
    return '0x' + (sel + _enc(['(bytes,address,uint256,uint256,uint256)'], [(bytes.fromhex(spec['p']), _ck(rcpt), 9999999999, int(amt), 0)])).hex()

def _v_build_e1(spec, tin, amt, chain_id):
    """approve + SwapRouter exactInput over the row's packed path."""
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction as _IX

    def _dr349(rcpt):
        leg = _e1_leg(spec, amt, rcpt)
        return [_IX(target=tin, value='0', call_data=encode_approve(_ck(_V_E1_ROUTER), int(amt)), chain_id=chain_id), _IX(target=_V_E1_ROUTER, value='0', call_data=leg, chain_id=chain_id)]
    return _dr349