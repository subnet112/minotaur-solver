# SN112 shape library — pair/composite row builders.
from shape_lib2 import _V_V3_ROUTERS

def _xfer_cd(pair, amt):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    return '0x' + (_keccak(text='transfer(address,uint256)')[:4] + _enc(['address', 'uint256'], [_ck(pair), int(amt)])).hex()

def _swap_cd(a0, a1, rcpt):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    return '0x' + (_keccak(text='swap(uint256,uint256,address,bytes)')[:4] + _enc(['uint256', 'uint256', 'address', 'bytes'], [a0, a1, _ck(rcpt), b''])).hex()

def _v_build_v2p(spec, tin, tout, amt, est, chain_id):
    """Single-leg V2/Solidly pair row builder (transfer + pair.swap)."""
    from minotaur_subnet.shared.types import Interaction as _IX
    xfer = _xfer_cd(spec['pair'], amt)
    a0, a1 = (0, int(est)) if spec.get('in_is_t0') else (int(est), 0)

    def _dr348(rcpt):
        return [_IX(target=tin, value='0', call_data=xfer, chain_id=chain_id), _IX(target=spec['pair'], value='0', call_data=_swap_cd(a0, a1, rcpt), chain_id=chain_id)]
    return _dr348

def _sv3_path(spec, tout):
    return bytes.fromhex(spec['mid1'][2:]) + int(spec['f2']).to_bytes(3, 'big') + bytes.fromhex(spec['mid2'][2:]) + int(spec['f3']).to_bytes(3, 'big') + bytes.fromhex(tout[2:])

def _sv3_parts(spec, tin, tout, amt, exec_addr, chain_id):
    from strategies.dex_aggregator import aerodrome as _aero
    slip_router = spec.get('r') or _aero.AERODROME_SLIPSTREAM_ROUTER[chain_id]
    leg1 = _aero.encode_exact_input_single(token_in=tin, token_out=spec['mid1'], tick_spacing=int(spec['slip_ts']), recipient=exec_addr, deadline=9999999999, amount_in=int(amt), amount_out_minimum=0)
    return slip_router, leg1, _sv3_path(spec, tout)

def _sv3_leg2(path, q1, rcpt):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    sel = _keccak(text='exactInput((bytes,address,uint256,uint256))')[:4]
    return '0x' + (sel + _enc(['(bytes,address,uint256,uint256)'], [(path, _ck(rcpt), int(q1), 0)])).hex()

def _fw2():
    def _v_build_sv3(spec, tin, tout, amt, q1, exec_addr, chain_id):
        """3-leg sv3 row builder (slipstream leg1 to executor, uni 2-hop leg2)."""
        from eth_utils import to_checksum_address as _ck
        from common.abi_utils import encode_approve
        from minotaur_subnet.shared.types import Interaction as _IX
        slip_router, leg1, path = _sv3_parts(spec, tin, tout, amt, exec_addr, chain_id)
        uni_r = _V_V3_ROUTERS['uni']

        def _dr347(rcpt):
            leg2 = _sv3_leg2(path, q1, rcpt)
            return [_IX(target=tin, value='0', call_data=encode_approve(_ck(slip_router), int(amt)), chain_id=chain_id), _IX(target=slip_router, value='0', call_data=leg1, chain_id=chain_id), _IX(target=spec['mid1'], value='0', call_data=encode_approve(_ck(uni_r), int(q1)), chain_id=chain_id), _IX(target=uni_r, value='0', call_data=leg2, chain_id=chain_id)]
        return _dr347

    def _vs2_leg1(spec, tin, amt):
        from eth_abi import encode as _enc
        from eth_utils import keccak as _keccak, to_checksum_address as _ck
        sel = _keccak(text='exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))')[:4]
        return '0x' + (sel + _enc(['(address,address,uint24,address,uint256,uint256,uint160)'], [(_ck(tin), _ck(spec['mid']), int(spec['l1_fee']), '0x0000000000000000000000000000000000000001', int(amt), 0, 0)])).hex()

    def _v_build_vs2(spec, tin, tout, amt, q1, chain_id):
        """2-leg vs2 row builder (v3 sentinel leg1, slipstream leg2)."""
        from eth_utils import to_checksum_address as _ck
        from strategies.dex_aggregator import aerodrome as _aero
        from common.abi_utils import encode_approve
        from minotaur_subnet.shared.types import Interaction as _IX
        uni_r = '0x2626664c2603336E57B271c5C0b26F421741e481'
        slip_router = spec.get('r') or _aero.AERODROME_SLIPSTREAM_ROUTER[chain_id]
        leg1 = _vs2_leg1(spec, tin, amt)

        def _dr343(rcpt):
            leg2 = _aero.encode_exact_input_single(token_in=spec['mid'], token_out=tout, tick_spacing=int(spec['slip_ts']), recipient=rcpt, deadline=9999999999, amount_in=int(q1), amount_out_minimum=0)
            def _fw1():
                return ([_IX(target=tin, value='0', call_data=encode_approve(_ck(uni_r), int(amt)), chain_id=chain_id), _IX(target=uni_r, value='0', call_data=leg1, chain_id=chain_id), _IX(target=spec['mid'], value='0', call_data=encode_approve(_ck(slip_router), int(q1)), chain_id=chain_id), _IX(target=slip_router, value='0', call_data=leg2, chain_id=chain_id)],)
            _fwr1 = _fw1()
            if _fwr1 is not None:
                return _fwr1[0]
        return _dr343

    def _p2_leg1(spec, tin, amt):
        from eth_abi import encode as _enc
        from eth_utils import keccak as _keccak, to_checksum_address as _ck
        sel = _keccak(text='exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))')[:4]
        return '0x' + (sel + _enc(['(address,address,uint24,address,uint256,uint256,uint256,uint160)'], [(_ck(tin), _ck(spec['mid']), int(spec['l1_fee']), _ck(spec['pair']), 9999999999, int(amt), 0, 0)])).hex()

    def _v_build_p2(spec, tin, tout, amt, est, chain_id):
        """2-leg p2 row builder (pancake v3 leg paid to the V2 pair, pair.swap)."""
        from eth_utils import to_checksum_address as _ck
        from common.abi_utils import encode_approve
        from minotaur_subnet.shared.types import Interaction as _IX
        pan_router = '0x1b81D678ffb9C0263b24A97847620C99d213eB14'
        leg1 = _p2_leg1(spec, tin, amt)
        a0, a1 = (int(est), 0) if int(spec['out_index']) == 0 else (0, int(est))

        def _dr340(rcpt):
            return [_IX(target=tin, value='0', call_data=encode_approve(_ck(pan_router), int(amt)), chain_id=chain_id), _IX(target=pan_router, value='0', call_data=leg1, chain_id=chain_id), _IX(target=spec['pair'], value='0', call_data=_swap_cd(a0, a1, rcpt), chain_id=chain_id)]
        return _dr340

    def _a3_leg2(spec, q1, chain_id):
        from strategies.dex_aggregator import aerodrome as _aero
        return _aero.encode_exact_input_single(token_in=spec['mid1'], token_out=spec['mid2'], tick_spacing=int(spec['slip_ts']), recipient=spec['pair'], deadline=9999999999, amount_in=int(q1), amount_out_minimum=0)

    def _a3_parts(spec, tin, amt, q1, est, chain_id):
        from strategies.dex_aggregator import aerodrome as _aero
        leg1 = _vs2_leg1(dict(spec, mid=spec['mid1']), tin, amt)
        slip_router = _aero.AERODROME_SLIPSTREAM_ROUTER[chain_id]
        a0, a1 = (int(est), 0) if int(spec['out_index']) == 0 else (0, int(est))
        return (leg1, slip_router, _a3_leg2(spec, q1, chain_id), a0, a1)

    def _a3_head(tin, amt, leg1, chain_id):
        from eth_utils import to_checksum_address as _ck
        from common.abi_utils import encode_approve
        from minotaur_subnet.shared.types import Interaction as _IX
        uni = '0x2626664c2603336E57B271c5C0b26F421741e481'
        return [_IX(target=tin, value='0', call_data=encode_approve(_ck(uni), int(amt)), chain_id=chain_id), _IX(target=uni, value='0', call_data=leg1, chain_id=chain_id)]

    def _a3_ixs(spec, tin, amt, q1, parts, rcpt, chain_id):
        from eth_utils import to_checksum_address as _ck
        from common.abi_utils import encode_approve
        from minotaur_subnet.shared.types import Interaction as _IX
        leg1, slip_router, leg2, a0, a1 = parts
        def _fw4():
            tail = [_IX(target=spec['mid1'], value='0', call_data=encode_approve(_ck(slip_router), int(q1)), chain_id=chain_id), _IX(target=slip_router, value='0', call_data=leg2, chain_id=chain_id), _IX(target=spec['pair'], value='0', call_data=_swap_cd(a0, a1, rcpt), chain_id=chain_id)]
            return (tail,)
        tail, = _fw4()
        return _a3_head(tin, amt, leg1, chain_id) + tail

    def build_a3(spec, tin, tout, amt, q1, q2, est, chain_id):
        """3-leg a3 row builder (uni sentinel leg1, slip leg2 to pair, pair.swap)."""
        parts = _a3_parts(spec, tin, amt, q1, est, chain_id)

        def _dr311(rcpt):
            return _a3_ixs(spec, tin, amt, q1, parts, rcpt, chain_id)
        return _dr311

    def build_s2(spec, tin, tout, amt, q1, est, chain_id):
        """2-leg s2 row builder (slip leg paid to the pair, pair.swap)."""
        from eth_utils import to_checksum_address as _ck
        from strategies.dex_aggregator import aerodrome as _aero
        from common.abi_utils import encode_approve
        from minotaur_subnet.shared.types import Interaction as _IX
        slip_router = spec.get('r') or _aero.AERODROME_SLIPSTREAM_ROUTER[chain_id]
        def _fw3():
            leg1 = _aero.encode_exact_input_single(token_in=tin, token_out=spec['mid'], tick_spacing=int(spec['slip_ts']), recipient=spec['pair'], deadline=9999999999, amount_in=int(amt), amount_out_minimum=0)
            a0, a1 = (int(est), 0) if int(spec['out_index']) == 0 else (0, int(est))

            def _dr320(rcpt):
                return [_IX(target=tin, value='0', call_data=encode_approve(_ck(slip_router), int(amt)), chain_id=chain_id), _IX(target=slip_router, value='0', call_data=leg1, chain_id=chain_id), _IX(target=spec['pair'], value='0', call_data=_swap_cd(a0, a1, rcpt), chain_id=chain_id)]
            return (_dr320,)
        _dr320, = _fw3()
        return _dr320
    globals().update(locals())
_fw2()
