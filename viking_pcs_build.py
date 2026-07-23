"""viking_pcs_build — PancakeSwap V3 swap calldata + ExecutionPlan builder.

Split from viking_pcs (quote/discovery) so each named region stays <=110 AST
nodes (factorization discipline). Path packing is Uniswap-V3-style; the swap is
approve(router, amt) on tin + exactInput on the chain's Pancake router, with the
router version + exactInput selector matched to what is deployed on-chain:
  ETH  router 0x1b81D678 (v1-style, WITH deadline)  -> exactInput 0xc04b8d59
  Base router 0x678Aa4bF (SR02-style, NO deadline)  -> exactInput 0xb858183f
This wiring is byte-identical to the proven champion Pancake leg. My own encoders."""
_DR_UNSET = object()
import logging
from viking_pcs import _pcs_router
logger = logging.getLogger('solver')

def _pcs_path(path, fees):
    """Packed Uniswap-V3-style path bytes: token(20)+fee(3)+token(20)[+fee+token...]."""
    from eth_utils import to_checksum_address as _ck
    b = bytes.fromhex(_ck(path[0])[2:])
    for i, f in enumerate(fees):
        b += int(f).to_bytes(3, 'big') + bytes.fromhex(_ck(path[i + 1])[2:])
    return b

def _pcs_encode(chain, path, fees, amt, recipient):
    """exactInput calldata for the chain's Pancake router version (ETH with deadline,
    Base SR02-style without)."""

    def _dz22():
        p = _pcs_path(path, fees)
        if int(chain) == 1:
            sel = bytes.fromhex('c04b8d59')
            args = _enc(['(bytes,address,uint256,uint256,uint256)'], [(p, _ck(recipient), 9999999999, int(amt), 0)])
        else:
            sel = bytes.fromhex('b858183f')
            args = _enc(['(bytes,address,uint256,uint256)'], [(p, _ck(recipient), int(amt), 0)])
        return ('0x' + (sel + args).hex(),)
        return _DR_UNSET
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    _r_dz22 = _dz22()
    if _r_dz22 is not _DR_UNSET:
        return _r_dz22[0]

def pcs_ix(chain, path, fees, amt, recipient):
    """approve(Pancake router, amt) on path[0] + exactInput; None if no router."""
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction
    router = _pcs_router(chain)
    if not router:
        return None
    cd = _pcs_encode(chain, path, fees, amt, recipient)
    return [Interaction(target=_ck(path[0]), value='0', call_data=encode_approve(_ck(router), int(amt)), chain_id=chain), Interaction(target=_ck(router), value='0', call_data=cd, chain_id=chain)]

def serve_pcs(intent, state, chain, tin, tout, det, amt, recipient, out):
    """Build the Pancake exactInput plan (approve + swap); None if no router."""
    from minotaur_subnet.shared.types import ExecutionPlan
    ix = pcs_ix(chain, det[0], det[1], amt, recipient)
    if ix is None:
        return None
    logger.info('[v3hop] override %s->%s out=%s via=pcs', tin[:8], tout[:8], out)
    return ExecutionPlan(intent_id=intent.app_id, interactions=ix, deadline=9999999999, nonce=state.nonce, metadata={'solver': 'viking-pcs', 'chain_id': chain})