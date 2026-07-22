"""viking_build — ExecutionPlan builders for the strict-better route cover.

Given the winning candidate (kind + det), build the approve+swap interactions
and the plan. Calldata encoders are split from the plan wiring so each named
region stays small (factorization discipline); the emitted calldata is
byte-identical to the pre-split inline builders — all encoders are my own
(no foreign calldata)."""
import logging

from viking_quote import _ROUTER02, _V2ROUTER

logger = logging.getLogger('solver')


def _recipient(state, p):
    return (getattr(state, 'contract_address', None)
            or p.get('receiver') or getattr(state, 'owner', None))


def _mk_plan(intent, state, chain, ix, tag, tin, tout, out):
    from minotaur_subnet.shared.types import ExecutionPlan
    logger.info('[v3hop] override %s->%s out=%s via=%s', tin[:8], tout[:8], out, tag)
    return ExecutionPlan(intent_id=intent.app_id, interactions=ix,
                         deadline=9999999999, nonce=state.nonce,
                         metadata={'solver': 'viking-' + tag, 'chain_id': chain})


def _v3_approve_ix(chain, tin, amt, router, cd):
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction
    return [Interaction(target=_ck(tin), value='0',
                        call_data=encode_approve(_ck(router), int(amt)), chain_id=chain),
            Interaction(target=_ck(router), value='0', call_data=cd, chain_id=chain)]


def _cd_v3d(tin, tout, fee, recipient, amt):
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    return '0x' + (bytes.fromhex('04e45aaf') + _enc(
        ['(address,address,uint24,address,uint256,uint256,uint160)'],
        [(_ck(tin), _ck(tout), int(fee), _ck(recipient), int(amt), 0, 0)])).hex()


def _v3h_path(tin, hub, tout, f1, f2):
    from eth_utils import to_checksum_address as _ck
    return (bytes.fromhex(_ck(tin)[2:]) + int(f1).to_bytes(3, 'big')
            + bytes.fromhex(_ck(hub)[2:]) + int(f2).to_bytes(3, 'big')
            + bytes.fromhex(_ck(tout)[2:]))


def _cd_v3h(tin, hub, tout, f1, f2, recipient, amt):
    from eth_abi import encode as _enc
    from eth_utils import keccak as _kk, to_checksum_address as _ck
    path = _v3h_path(tin, hub, tout, f1, f2)
    sel = _kk(text='exactInput((bytes,address,uint256,uint256))')[:4]
    return '0x' + (sel + _enc(['(bytes,address,uint256,uint256)'],
                              [(path, _ck(recipient), int(amt), 0)])).hex()


def _cd_v2(path, recipient, amt):
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    return '0x' + (bytes.fromhex('38ed1739') + _enc(
        ['uint256', 'uint256', 'address[]', 'address', 'uint256'],
        [int(amt), 0, [_ck(a) for a in path], _ck(recipient), 9999999999])).hex()


def _serve_v3d(intent, state, chain, tin, tout, det, amt, recipient, out):
    router = _ROUTER02.get(int(chain))
    cd = _cd_v3d(tin, tout, det[0], recipient, amt)
    ix = _v3_approve_ix(chain, tin, amt, router, cd)
    return _mk_plan(intent, state, chain, ix, 'v3d', tin, tout, out)


def _serve_v3h(intent, state, chain, tin, tout, det, amt, recipient, out):
    router = _ROUTER02.get(int(chain))
    hub, f1, f2 = det
    cd = _cd_v3h(tin, hub, tout, f1, f2, recipient, amt)
    ix = _v3_approve_ix(chain, tin, amt, router, cd)
    return _mk_plan(intent, state, chain, ix, 'v3h', tin, tout, out)


def _serve_v2(intent, state, chain, tin, tout, det, amt, recipient, out):
    router = _V2ROUTER.get(int(chain))
    if not router:
        return None
    cd = _cd_v2(det, recipient, amt)
    ix = _v3_approve_ix(chain, tin, amt, router, cd)
    return _mk_plan(intent, state, chain, ix, 'v2', tin, tout, out)


def _builders():
    """kind -> plan builder (uniform signature). Pancake lives in viking_pcs_build."""
    import viking_pcs_build as _pcsb
    import viking_v4_build as _v4b
    import viking_curve_build as _cvb
    return {'v3d': _serve_v3d, 'v3h': _serve_v3h, 'pcs': _pcsb.serve_pcs,
            'v4': _v4b.serve_v4, 'curve': _cvb.serve_curve}


def serve(intent, state, chain, tin, tout, best, amt, p):
    """Dispatch the winning candidate to its builder. None if no recipient."""
    recipient = _recipient(state, p)
    if not recipient:
        return None
    out, kind, det = best
    fn = _builders().get(kind, _serve_v2)
    return fn(intent, state, chain, tin, tout, det, amt, recipient, out)
