"""viking_curve_build — approve+exchange calldata for a viking_curve candidate.
Curve's exchange() pulls from msg.sender like the base engine's own V2/V3
swaps, so it executes through the same scoreIntent path (no proxy funding
concerns)."""
_IDX = {'stable': 'int128', 'crypto': 'uint256'}


def _exchange_cd(kind, i, j, amt, min_dy, recipient):
    from eth_abi import encode as _enc
    from eth_utils import keccak, to_checksum_address as _ck
    x = _IDX[kind]
    sel = keccak(text=f'exchange({x},{x},uint256,uint256,address)')[:4]
    body = _enc([x, x, 'uint256', 'uint256', 'address'],
               [i, j, amt, min_dy, _ck(recipient)])
    return '0x' + (sel + body).hex()


def _curve_ix(chain, tin, det, amt, out, recipient):
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction
    pool, kind, i, j = det
    cd = _exchange_cd(kind, i, j, amt, max(1, out), recipient)
    return [Interaction(target=_ck(tin), value='0',
                        call_data=encode_approve(_ck(pool), amt), chain_id=chain),
            Interaction(target=_ck(pool), value='0', call_data=cd, chain_id=chain)]


def serve_curve(intent, state, chain, tin, tout, det, amt, recipient, out):
    """Serve a viking_curve candidate: approve(pool) + exchange(i,j,...)."""
    import viking_build as _b
    ix = _curve_ix(chain, tin, det, amt, out, recipient)
    return _b._mk_plan(intent, state, chain, ix, 'curve', tin, tout, out)
