"""Relocated leaf helper -- _c1_build_ix_v2, moved out of chain1_v2.py for the bg124 rebase.

Same code, same call site, different module. Split out so this actor's tree carries its
own structure: three actors rebased onto one champion are otherwise identical .py-for-.py
and the structural fingerprint collapses them into one identity, costing one its seat.
This is a LEAF -- it reads only its arguments and what it imports itself -- so moving it
cannot change resolution of any name it uses.
"""

def _c1_build_ix_v2(tin, recip, tokens, amt):
    """ZERO-RPC Uniswap-V2 router serve (baked-spec sibling of solver._c1_build_ix).
    Returns [approve_ix, v2swap_ix] for the V2 SwapRouter02:
    swapExactTokensForTokensSupportingFeeOnTransferTokens (sel 0x5c11d795), min_out=0,
    deadline 9999999999. The SupportingFeeOnTransfer variant + min_out=0 make it safe for
    fee-on-transfer exotics (never reverts on tax skim). `tokens` is the full V2 path
    (direct [tin,tout] or 2-hop [tin,WETH,tout]) baked pre-verified via getAmountsOut>0."""
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction as _IX
    ROUTER_V2 = '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'
    swap_data = '0x5c11d795' + _enc(['uint256', 'uint256', 'address[]', 'address', 'uint256'], [int(amt), 0, [_ck(t) for t in tokens], _ck(recip), 9999999999]).hex()
    return [_IX(target=_ck(tin), value='0', call_data=encode_approve(_ck(ROUTER_V2), int(amt)), chain_id=1), _IX(target=_ck(ROUTER_V2), value='0', call_data=swap_data, chain_id=1)]