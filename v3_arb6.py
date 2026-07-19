"""v3_arb6 — PancakeSwap V3 leg for the cover.

Pancake V3 is a Uniswap-V3 fork with its OWN pools + fee tiers (100/500/2500/
10000). The champion (hydra) sweeps Uniswap V3/V2, Aerodrome, Sushi + Pancake
*V2* and Uniswap V4 — but NOT Pancake *V3*, leaving live orders it can't route
(apxUSD->apyUSD, LINK->RED, JitoSOL->TOSHI, TAIKO, BLEND, Cake, cbLTC,
cbBTC->cbADA...) that Pancake V3 serves with a real, higher output.

Quoting: Pancake QuoterV2 (0xB048Bbc1..., both chains), same quoteExactInputSingle
ABI (sel 0xc6a5026a) as Uniswap — for exactInput the quote == on-chain delivery.
Swap: exactInput(path) on the chain's Pancake router, selector matched to the
router version DETECTED on-chain (bytecode selector probe):
  ETH  router 0x1b81D678 (v1-style, WITH deadline)  -> exactInput 0xc04b8d59
  Base router 0x678Aa4bF (SR02-style, NO deadline)  -> exactInput 0xb858183f
Path bytes = token(20)+fee(3)+token(20)[+fee+token...]. Leaf: depends on nothing
in the v3_arb tree. Every region kept <=110 AST nodes."""

_FEES = (100, 500, 2500, 10000)


def _pcs_quoter():
    """Pancake QuoterV2 (same CREATE2 address on ETH + Base)."""
    return '0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997'


def _pcs_router(chain):
    """Pancake V3 exactInput router for the chain, or None off ETH/Base."""
    return {1: '0x1b81D678ffb9C0263b24A97847620C99d213eB14',
            8453: '0x678Aa4bF4E210cf2166753e054d5b7c31cc7fa86'}.get(int(chain))


def _pcs_hubs(chain):
    """Intermediate hubs for the 2-hop (WETH/USDC/USDT)."""
    return {1: ('0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',
                '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',
                '0xdac17f958d2ee523a2206206994597c13d831ec7'),
            8453: ('0x4200000000000000000000000000000000000006',
                   '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913')}.get(int(chain), ())


def _pcs_quote(w3, tin, tout, fee, amt):
    """One Pancake QuoterV2 quoteExactInputSingle (sel 0xc6a5026a); 0 on fail."""
    from eth_abi import encode as _enc, decode as _dec
    from eth_utils import to_checksum_address as _ck
    cd = bytes.fromhex('c6a5026a') + _enc(
        ['(address,address,uint256,uint24,uint160)'],
        [(_ck(tin), _ck(tout), int(amt), int(fee), 0)])
    try:
        r = w3.eth.call({'to': _ck(_pcs_quoter()), 'data': '0x' + cd.hex()})
        return int(_dec(['uint256', 'uint160', 'uint32', 'uint256'], bytes(r))[0])
    except Exception:
        return 0


def _pcs_direct(w3, a, b, amt):
    """Best direct a->b over Pancake fee tiers: (out, fee) or None."""
    best = None
    for f in _FEES:
        o = _pcs_quote(w3, a, b, f, amt)
        if o > 0 and (best is None or o > best[0]):
            best = (o, f)
    return best


def _pcs_via(w3, tin, hub, tout, amt):
    """Best 2-hop tin->hub->tout: (out, [tin,hub,tout], [f1,f2]) or None."""
    d1 = _pcs_direct(w3, tin, hub, amt)
    if d1 is None:
        return None
    d2 = _pcs_direct(w3, hub, tout, d1[0])
    if d2 is None:
        return None
    return (d2[0], [tin, hub, tout], [d1[1], d2[1]])


def _pcs_hub_best(w3, chain, tin, tout, amt, best):
    """Fold each hub's 2-hop candidate into `best` (highest output wins)."""
    for hub in _pcs_hubs(chain):
        if hub == tin or hub == tout:
            continue
        r = _pcs_via(w3, tin, hub, tout, amt)
        if r is not None and (best is None or r[0] > best[0]):
            best = r
    return best


def _pcs_best(w3, chain, tin, tout, amt):
    """Best Pancake V3 route (direct or via a hub): (out, path, fees) or None."""
    d = _pcs_direct(w3, tin, tout, amt)
    best = (d[0], [tin, tout], [d[1]]) if d is not None else None
    return _pcs_hub_best(w3, chain, tin, tout, amt, best)


def _pcs_path(path, fees):
    """Packed Uniswap-V3-style path bytes: token+fee+token[+fee+token...]."""
    from eth_utils import to_checksum_address as _ck
    b = bytes.fromhex(_ck(path[0])[2:])
    for i, f in enumerate(fees):
        b += int(f).to_bytes(3, 'big') + bytes.fromhex(_ck(path[i + 1])[2:])
    return b


def _pcs_encode(chain, path, fees, amt, recipient):
    """exactInput calldata for the chain's Pancake router version (struct ABI)."""
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    p = _pcs_path(path, fees)
    if int(chain) == 1:
        sel = bytes.fromhex('c04b8d59')
        args = _enc(['(bytes,address,uint256,uint256,uint256)'],
                    [(p, _ck(recipient), 9999999999, int(amt), 0)])
    else:
        sel = bytes.fromhex('b858183f')
        args = _enc(['(bytes,address,uint256,uint256)'],
                    [(p, _ck(recipient), int(amt), 0)])
    return '0x' + (sel + args).hex()


def _pcs_swap_ix(chain, path, fees, amt, recipient):
    """approve(Pancake router, amt) on tin + exactInput; None if no router."""
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction
    router = _pcs_router(chain)
    if not router:
        return None
    cd = _pcs_encode(chain, path, fees, amt, recipient)
    return [Interaction(target=_ck(path[0]), value='0',
                        call_data=encode_approve(_ck(router), int(amt)), chain_id=chain),
            Interaction(target=_ck(router), value='0', call_data=cd, chain_id=chain)]
