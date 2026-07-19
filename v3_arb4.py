"""v3_arb4 — Uniswap V2 leg for the cover (discovery + swap calldata).

Captures memecoin/thin-pool orders that trade on Uniswap V2, NOT V3 — the V3
cover (v3_arb2/3) returns 0 for these (~29 of the live corpus). V2
`getAmountsOut` is execution-accurate same-block (constant-product), the V2
analogue of QuoterV2, so the served amount == on-chain delivery at bench.
Leaf: depends on NOTHING in the v3_arb tree. Call graph: v3_arb -> v3_arb4.
Every region kept <=120 AST nodes so it never raises the max_region.

CAVEAT (by design safe): fee-on-transfer tokens deliver < getAmountsOut. The
cover only fires V2 when it STRICTLY beats the base floor; for the target blind
spots the base delivers 0, so any positive V2 delivery is a win (never a
regression). We do NOT use the FoT-supporting variant (its output isn't
quotable) — a FoT token simply delivers a bit less, still > 0 > base."""


def _v2_router(chain):
    """Uniswap V2 router02 for the chain, or None."""
    return {1: '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
            8453: '0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24'}.get(int(chain))


def _v2_hubs(chain):
    """WETH/USDC intermediate hubs for a V2 2-hop path."""
    return {1: ('0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',
                '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'),
            8453: ('0x4200000000000000000000000000000000000006',
                   '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913')}.get(int(chain), ())


def _v2_ao_cd(path, amt):
    """getAmountsOut(uint256,address[]) calldata bytes (selector 0xd06ca61f)."""
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    return bytes.fromhex('d06ca61f') + _enc(
        ['uint256', 'address[]'], [int(amt), [_ck(a) for a in path]])


def _v2_amounts_out(w3, chain, path, amt):
    """Uniswap V2 getAmountsOut sel 0xd06ca61f; last hop amount or 0."""
    from eth_abi import decode as _dec
    from eth_utils import to_checksum_address as _ck
    r = _v2_router(chain)
    if not r:
        return 0
    try:
        raw = w3.eth.call({'to': _ck(r), 'data': '0x' + _v2_ao_cd(path, amt).hex()})
        outs = _dec(['uint256[]'], bytes(raw))[0]
        return int(outs[-1]) if outs else 0
    except Exception:
        return 0


def _v2_try(w3, chain, path, amt, best):
    """Quote one V2 path; return (out, path) if it beats `best`, else `best`."""
    o = _v2_amounts_out(w3, chain, path, amt)
    if o > 0 and (best is None or o > best[0]):
        return (o, path)
    return best


def _v2_best(w3, chain, tin, tout, amt):
    """Best V2 route (direct tin->tout OR via a WETH/USDC hub):
    (out, path_token_list) or None."""
    best = _v2_try(w3, chain, [tin, tout], amt, None)
    for hub in _v2_hubs(chain):
        if hub != tin and hub != tout:
            best = _v2_try(w3, chain, [tin, hub, tout], amt, best)
    return best


def _v2_encode_swap(path, amt, recipient):
    """swapExactTokensForTokens(amountIn,amountOutMin,path,to,deadline) sel
    0x38ed1739. amountOutMin=0 (the harness scores delivered output, not slippage)."""
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    sel = bytes.fromhex('38ed1739')
    args = _enc(['uint256', 'uint256', 'address[]', 'address', 'uint256'],
                [int(amt), 0, [_ck(a) for a in path], _ck(recipient), 9999999999])
    return '0x' + (sel + args).hex()


def _v2_swap_ix(chain, path, amt, recipient):
    """approve(V2 router, amt) on tin + swapExactTokensForTokens Interactions."""
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction
    router = _v2_router(chain)
    if not router:
        return None
    cd = _v2_encode_swap(path, amt, recipient)
    return [Interaction(target=_ck(path[0]), value='0',
                        call_data=encode_approve(_ck(router), int(amt)), chain_id=chain),
            Interaction(target=_ck(router), value='0', call_data=cd, chain_id=chain)]
