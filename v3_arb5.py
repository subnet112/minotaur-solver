"""v3_arb5 — Aerodrome (Base) leg for the cover.

Aerodrome is Base's dominant DEX (stable + volatile pools). Captures Base orders
(FX-stables / memecoins) that route on Aero but not Uniswap V3/V2 — ~8 of the
live corpus (USDC->ROBA/CTX/CADC/MEZO, EUR/HANDL/cbLTC->USDC, OFC->WETH).

Base-only (chain 8453) — returns None on every other chain. getAmountsOut is
execution-accurate same-block (constant-product / stable-invariant), the Aero
analogue of QuoterV2, so the served amount == on-chain delivery at bench.
Route struct = (from, to, stable, factory); we try BOTH stable flags per hop.
Leaf: depends on NOTHING in the v3_arb tree. Regions kept <=120 AST nodes."""


def _aero_addrs(chain):
    """(router, factory, WETH, USDC) for Aerodrome on Base; None off-Base."""
    if int(chain) != 8453:
        return None
    return ('0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43',
            '0x420DD381b31aEf6683db6B902084cB0FFECe40Da',
            '0x4200000000000000000000000000000000000006',
            '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913')


def _aero_route(hops, fac):
    """Route[] tuple list from (from,to,stable) hops + the shared factory."""
    from eth_utils import to_checksum_address as _ck
    return [(_ck(a), _ck(b), bool(s), _ck(fac)) for (a, b, s) in hops]


def _aero_out(w3, router, routes, amt):
    """Aerodrome getAmountsOut(uint256,Route[]) sel 0x5509a1ac; last hop or 0."""
    from eth_abi import encode as _enc, decode as _dec
    from eth_utils import to_checksum_address as _ck
    cd = bytes.fromhex('5509a1ac') + _enc(
        ['uint256', '(address,address,bool,address)[]'], [int(amt), routes])
    try:
        r = w3.eth.call({'to': _ck(router), 'data': '0x' + cd.hex()})
        outs = _dec(['uint256[]'], bytes(r))[0]
        return int(outs[-1]) if outs else 0
    except Exception:
        return 0


def _aero_try(w3, router, fac, hops, amt, best):
    """Quote one Aero route (hops); return (out, hops) if it beats `best`."""
    o = _aero_out(w3, router, _aero_route(hops, fac), amt)
    if o > 0 and (best is None or o > best[0]):
        return (o, hops)
    return best


def _aero_direct(w3, router, fac, tin, tout, amt, best):
    """Best direct tin->tout over {stable, volatile}."""
    for st in (True, False):
        best = _aero_try(w3, router, fac, [(tin, tout, st)], amt, best)
    return best


def _aero_via(w3, router, fac, tin, hub, tout, amt, best):
    """Best 2-hop tin->hub->tout over {stable,volatile} x {stable,volatile}."""
    for s1 in (True, False):
        for s2 in (True, False):
            best = _aero_try(w3, router, fac, [(tin, hub, s1), (hub, tout, s2)], amt, best)
    return best


def _aero_hub_best(w3, router, fac, tin, hubs, tout, amt, best):
    """Fold each hub's 2-hop Aero candidate into `best`."""
    for hub in hubs:
        if hub != tin and hub != tout:
            best = _aero_via(w3, router, fac, tin, hub, tout, amt, best)
    return best


def _aero_best(w3, chain, tin, tout, amt):
    """Best Aerodrome route (direct or via WETH/USDC hub): (out, hops) or None.
    Base-only; None on other chains."""
    a = _aero_addrs(chain)
    if a is None:
        return None
    router, fac = a[0], a[1]
    best = _aero_direct(w3, router, fac, tin, tout, amt, None)
    return _aero_hub_best(w3, router, fac, tin, (a[2], a[3]), tout, amt, best)


def _aero_encode_swap(hops, amt, recipient, fac):
    """swapExactTokensForTokens(uint,uint,Route[],address,uint); minOut=0."""
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck, keccak as _keccak
    sel = _keccak(text=('swapExactTokensForTokens(uint256,uint256,'
                        '(address,address,bool,address)[],address,uint256)'))[:4]
    args = _enc(['uint256', 'uint256', '(address,address,bool,address)[]', 'address', 'uint256'],
                [int(amt), 0, _aero_route(hops, fac), _ck(recipient), 9999999999])
    return '0x' + (sel + args).hex()


def _aero_ix_pair(tin_addr, router, cd, amt, chain):
    """approve(router, amt) on tin + the router swap Interaction, as a 2-item list."""
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction
    return [Interaction(target=_ck(tin_addr), value='0',
                        call_data=encode_approve(_ck(router), int(amt)), chain_id=chain),
            Interaction(target=_ck(router), value='0', call_data=cd, chain_id=chain)]


def _aero_swap_ix(chain, hops, amt, recipient):
    """approve(Aero router, amt) on tin + swapExactTokensForTokens; None off-Base."""
    a = _aero_addrs(chain)
    if a is None:
        return None
    router, fac = a[0], a[1]
    cd = _aero_encode_swap(hops, amt, recipient, fac)
    return _aero_ix_pair(hops[0][0], router, cd, amt, chain)
