"""v3_arb — V3 2-hop-via-base OVERRIDE for orders the engine routes poorly.

The lineage's discovery only tries direct/single-hop + V4 2-hop; it MISSES
Uniswap V3 2-hop routes (tin -> WETH/USDC -> tout) that deliver MORE on tokens
whose direct pool is thin (e.g. q_631c4630: engine 0.478e18 vs a WETH 2-hop
~14.4e18, 30x). We re-quote the engine's OWN chosen route and our best V3 2-hop
against QuoterV2 on the SAME block, and serve the 2-hop ONLY when it STRICTLY
beats the engine's delivery — so the gain is real at bench (for exactInput,
QuoterV2 quote == on-chain execution) and we never override a route that already
delivers more. If the base is undecodable we DEFER (can't prove an improvement).

CRITICAL — plan wire format (this was the bench-regression bug): the plan runs
from the EXECUTOR, so the swap MUST use Uniswap SwapRouter02 with the 4-field
exactInput ABI (0xb858183f, NO deadline), final output to the app. The V1
5-field struct (0xc04b8d59, with deadline) is REJECTED by SwapRouter02 and
reverts to a DROP. This mirrors the champion's proven _build_v3_path02_ix.
"""
import logging

logger = logging.getLogger('solver')

_FEES = (100, 500, 3000, 10000)


def _quoter(chain):
    """Uniswap V3 QuoterV2 address for the chain, or None."""
    return {1: '0x61fFE014bA17989E743c5F6cB21bF9697530B21e',
            8453: '0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a'}.get(int(chain))


def _bases(chain):
    """Intermediate hubs to route the 2-hop through. Widened beyond WETH/USDC —
    hunt of the scored corpus showed champ-dead orders that only route via USDT
    (q_364ed8ce) or DAI (q_66728ae9). More hubs = more blind-spot routes found;
    the strict best>base gate keeps it non-regressing."""
    return {1: ('0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',   # WETH
                '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',   # USDC
                '0xdac17f958d2ee523a2206206994597c13d831ec7',   # USDT
                '0x6b175474e89094c44da98b954eedeac495271d0f',   # DAI
                '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599'),  # WBTC
            8453: ('0x4200000000000000000000000000000000000006',   # WETH
                   '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913',   # USDC
                   '0x50c5725949a6f0c72e6c4a641f24049a917db0cb',   # DAI
                   '0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca',   # USDbC
                   '0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22')}.get(int(chain), ())  # cbETH


def _router02(chain):
    """Uniswap SwapRouter02 for the chain — the EXECUTOR's router. The plan runs
    from the executor, so the 4-field exactInput ABI (0xb858183f, NO deadline) on
    THIS router is what delivers; the V1 5-field struct (0xc04b8d59) is REJECTED."""
    return {1: '0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45',
            8453: '0x2626664c2603336E57B271c5C0b26F421741e481'}.get(int(chain))


def _quote(w3, chain, tin, tout, fee, amt):
    """One QuoterV2 quoteExactInputSingle (selector 0xc6a5026a); 0 on failure."""
    from eth_abi import encode as _enc, decode as _dec
    from eth_utils import to_checksum_address as _ck
    q = _quoter(chain)
    if not q:
        return 0
    data = bytes.fromhex('c6a5026a') + _enc(
        ['(address,address,uint256,uint24,uint160)'],
        [(_ck(tin), _ck(tout), int(amt), int(fee), 0)])
    try:
        r = w3.eth.call({'to': _ck(q), 'data': '0x' + data.hex()})
        return int(_dec(['uint256', 'uint160', 'uint32', 'uint256'], bytes(r))[0])
    except Exception:
        return 0


def _quote_path(w3, chain, path, amt):
    """QuoterV2 quoteExactInput(bytes,uint256) sel 0xcdca1753; amountOut or 0."""
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    q = _quoter(chain)
    if not q:
        return 0
    data = bytes.fromhex('cdca1753') + _enc(['bytes', 'uint256'], [path, int(amt)])
    try:
        r = bytes(w3.eth.call({'to': _ck(q), 'data': '0x' + data.hex()}))
        return int.from_bytes(r[0:32], 'big') if len(r) >= 32 else 0
    except Exception:
        return 0


def _leg2_best(w3, chain, base, tout, l1):
    """Best second leg base->tout over fee tiers: (out, f2) or None."""
    best = None
    for f2 in _FEES:
        l2 = _quote(w3, chain, base, tout, f2, l1)
        if l2 > 0 and (best is None or l2 > best[0]):
            best = (l2, f2)
    return best


def _via_base(w3, chain, tin, base, tout, amt):
    """Best route through one intermediate base: (out, f1, f2) or None."""
    best = None
    for f1 in _FEES:
        l1 = _quote(w3, chain, tin, base, f1, amt)
        if l1 <= 0:
            continue
        r = _leg2_best(w3, chain, base, tout, l1)
        if r is not None and (best is None or r[0] > best[0]):
            best = (r[0], f1, r[1])
    return best


def _best_2hop(w3, chain, tin, tout, amt):
    """Best V3 2-hop via WETH/USDC: (out, base, f1, f2) or None."""
    best = None
    for base in _bases(chain):
        if base == tin or base == tout:
            continue
        r = _via_base(w3, chain, tin, base, tout, amt)
        if r is not None and (best is None or r[0] > best[0]):
            best = (r[0], base, r[1], r[2])
    return best


def _resolve_chain(state, snapshot):
    """Chain id from state, falling back to snapshot; 0 if unknown."""
    return int(getattr(state, 'chain_id', 0)
               or (getattr(snapshot, 'chain_id', 0) if snapshot else 0) or 0)


def _swap_fields(solver, intent, state):
    """Normalize the order into (params, tin, tout, amt)."""
    p = solver._normalized_swap_params(intent, state)
    tin = str(p.get('input_token', '') or '').lower()
    tout = str(p.get('output_token', '') or '').lower()
    amt = int(p.get('input_amount', 0) or 0)
    return p, tin, tout, amt


def _ctx(solver, intent, state, snapshot):
    """Resolve (chain, tin, tout, amt, w3, params) for the order, or None."""
    chain = _resolve_chain(state, snapshot)
    if _quoter(chain) is None:
        return None
    p, tin, tout, amt = _swap_fields(solver, intent, state)
    if not tin or not tout or amt <= 0:
        return None
    w3 = solver._get_web3(chain)
    if w3 is None:
        return None
    return (chain, tin, tout, amt, w3, p)


def _decode_single(cd):
    """exactInputSingle -> (tin, tout, fee, amtIn) or None (both variants)."""
    from eth_abi import decode as _d
    sel = cd[:10]
    body = bytes.fromhex(cd[10:])
    try:
        if sel == '0x04e45aaf':
            t = _d(['(address,address,uint24,address,uint256,uint256,uint160)'], body)[0]
            return (t[0], t[1], t[2], t[4])
        if sel == '0x414bf389':
            t = _d(['(address,address,uint24,address,uint256,uint256,uint256,uint160)'], body)[0]
            return (t[0], t[1], t[2], t[5])
    except Exception:
        return None
    return None


def _decode_path(cd):
    """exactInput -> (path_bytes, amtIn) or None (deadline / no-deadline variants)."""
    from eth_abi import decode as _d
    sel = cd[:10]
    body = bytes.fromhex(cd[10:])
    try:
        if sel == '0xc04b8d59':
            t = _d(['(bytes,address,uint256,uint256,uint256)'], body)[0]
            return (t[0], t[3])
        if sel == '0xb858183f':
            t = _d(['(bytes,address,uint256,uint256)'], body)[0]
            return (t[0], t[2])
    except Exception:
        return None
    return None


def _requote(w3, chain, cd):
    """Re-quote a decodable router call to its delivered amount; None if the
    selector is unknown (=> caller can't prove the base is dead)."""
    sng = _decode_single(cd)
    if sng is not None:
        return _quote(w3, chain, sng[0], sng[1], sng[2], sng[3])
    pth = _decode_path(cd)
    if pth is not None:
        return _quote_path(w3, chain, pth[0], pth[1])
    return None


def _base_out(w3, chain, base_plan):
    """Re-quote the engine's base delivery. 0 if empty; the quoted amount if the
    route is decodable; None if non-empty but UNDECODABLE (can't prove dead)."""
    ix = getattr(base_plan, 'interactions', None) if base_plan else None
    if not ix:
        return 0
    cd = ix[-1].call_data or ''
    if not cd.startswith('0x'):
        cd = '0x' + cd
    return _requote(w3, chain, cd)


def _encode_2hop(tin, base, tout, f1, f2, amt, recipient):
    """exactInput calldata for path tin->base->tout via SwapRouter02 (4-field ABI
    0xb858183f, NO deadline). Mirrors the champion's _build_v3_path02_ix exactly:
    the router does BOTH hops internally and the final output lands at recipient
    (the app). The V1 5-field struct (0xc04b8d59, with deadline) reverts here."""
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    path = (bytes.fromhex(_ck(tin)[2:]) + int(f1).to_bytes(3, 'big')
            + bytes.fromhex(_ck(base)[2:]) + int(f2).to_bytes(3, 'big')
            + bytes.fromhex(_ck(tout)[2:]))
    sel = _keccak(text='exactInput((bytes,address,uint256,uint256))')[:4]
    return '0x' + (sel + _enc(['(bytes,address,uint256,uint256)'],
                              [(path, _ck(recipient), int(amt), 0)])).hex()


def _approve_ix(tin, router, amt, chain):
    """ERC20 approve(router, amt) Interaction for the input token."""
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction
    return Interaction(target=_ck(tin), value='0',
                       call_data=encode_approve(_ck(router), int(amt)), chain_id=chain)


def _swap_ix(router, cd, chain):
    """Router exactInput Interaction carrying the 2-hop calldata."""
    from eth_utils import to_checksum_address as _ck
    from minotaur_subnet.shared.types import Interaction
    return Interaction(target=_ck(router), value='0', call_data=cd, chain_id=chain)


def _mk_plan(intent, state, chain, ix):
    """Wrap the interaction list in an ExecutionPlan."""
    from minotaur_subnet.shared.types import ExecutionPlan
    return ExecutionPlan(intent_id=intent.app_id, interactions=ix,
                         deadline=9999999999, nonce=state.nonce,
                         metadata={'solver': 'v3-arb-2hop', 'chain_id': chain})


def _build_plan(intent, state, ctx, best, recipient):
    """Build the approve + exactInput 2-hop ExecutionPlan for the best route."""
    chain, tin, tout, amt = ctx[:4]
    out, base, f1, f2 = best
    router = _router02(chain)
    if not router:
        return None
    cd = _encode_2hop(tin, base, tout, f1, f2, amt, recipient)
    ix = [_approve_ix(tin, router, amt, chain), _swap_ix(router, cd, chain)]
    return _mk_plan(intent, state, chain, ix)


def _recipient(state, p):
    """Delivery recipient: contract_address, then receiver, then owner."""
    return (getattr(state, 'contract_address', None)
            or p.get('receiver') or getattr(state, 'owner', None))


def _plan_for(intent, state, ctx, floor):
    """Find the best 2-hop and, only if it STRICTLY beats `floor` (the engine's own
    re-quoted delivery), build the override plan; None otherwise (defer to engine)."""
    chain, tin, tout, amt, w3, p = ctx
    best = _best_2hop(w3, chain, tin, tout, amt)
    if best is None or best[0] <= floor:
        return None
    plan = _build_plan(intent, state, ctx, best, _recipient(state, p))
    if plan is not None:
        logger.info('[v3-arb] override %s->%s out=%s > base=%s', tin[:8], tout[:8], best[0], floor)
    return plan


def v3_arb_cover(solver, intent, state, snapshot, base_plan):
    """Serve a V3 2-hop ONLY when it STRICTLY beats the engine's own re-quoted route
    (best_2hop > base_out), both quoted via QuoterV2 on the same block — so the gain
    is real at bench (quote==execution for exactInput) and we never override a route
    that already delivers more. If the base route can't be re-quoted (undecodable),
    DEFER (we can't prove an improvement, so we don't risk a blind override)."""
    try:
        ctx = _ctx(solver, intent, state, snapshot)
        if ctx is None:
            return None
        bout = _base_out(ctx[4], ctx[0], base_plan)
        if bout is None:
            return None
        return _plan_for(intent, state, ctx, bout)
    except Exception:
        logger.exception('[v3-arb] cover failed; serving base plan')
        return None
