"""viking_pcs — PancakeSwap V3 leg for the strict-better route cover.

Pancake V3 is a Uniswap-V3 fork with its OWN pools + fee tiers (100/500/2500/
10000). The base engine + viking sweep Uniswap V3/V2 but NOT Pancake V3, so live
orders whose deepest pool is on Pancake get under-served or dropped (measured:
corpus orders where Pancake delivers 5.8x-179x our best, and some we miss at 0).
Pancake QuoterV2 (0xB048..., same CREATE2 address on ETH + Base) uses the
identical quoteExactInputSingle ABI (sel 0xc6a5026a) as Uniswap, so for exactInput
the quote == on-chain delivery at bench. Serve is LIFT-ONLY (viking overrides only
when strictly better than the base floor), so adding this venue never regresses an
order — it only fills gaps / raises output. Quotes are batched (2 aggregate3
rounds: direct+leg1, then leg2) to keep the RPC footprint low. My own encoders;
swap calldata matches the proven champion Pancake router wiring byte-for-byte."""
import logging

from viking_quote import _agg3, _enc_single, _dec_single

logger = logging.getLogger('solver')

_PCS_Q = '0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997'   # Pancake QuoterV2 (ETH + Base)
_PCS_FEES = (100, 500, 2500, 10000)


def _pcs_router(chain):
    """Pancake V3 exactInput router for the chain, or None off ETH/Base."""
    return {1: '0x1b81D678ffb9C0263b24A97847620C99d213eB14',
            8453: '0x678Aa4bF4E210cf2166753e054d5b7c31cc7fa86'}.get(int(chain))


def _pcs_hubs(chain):
    """Intermediate hubs for the 2-hop (WETH/USDC/USDT on ETH; WETH/USDC on Base)."""
    return {1: ('0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',
                '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',
                '0xdac17f958d2ee523a2206206994597c13d831ec7'),
            8453: ('0x4200000000000000000000000000000000000006',
                   '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913')}.get(int(chain), ())


def _direct_r1(tin, tout, amt):
    calls, tags = [], []
    for f in _PCS_FEES:
        calls.append((_PCS_Q, _enc_single(tin, tout, amt, f)))
        tags.append(('d', tout, f))
    return calls, tags


def _leg1_r1(chain, tin, tout, amt):
    calls, tags = [], []
    for hub in _pcs_hubs(chain):
        if hub == tin or hub == tout:
            continue
        for f in _PCS_FEES:
            calls.append((_PCS_Q, _enc_single(tin, hub, amt, f)))
            tags.append(('l1', hub, f))
    return calls, tags


def _r1_calls(chain, tin, tout, amt):
    """(calls, tags) round1: direct tin->tout + leg1 tin->hub over Pancake tiers."""
    dc, dt = _direct_r1(tin, tout, amt)
    lc, lt = _leg1_r1(chain, tin, tout, amt)
    return dc + lc, dt + lt


def _best_direct(tin, tout, tags, res):
    """Best direct: (out, [tin,tout], [fee]) or None. First-max tie-break in tier order."""
    best = None
    for (k, tgt, f), r in zip(tags, res):
        if k != 'd':
            continue
        o = _dec_single(r[0], r[1])
        if o > 0 and (best is None or o > best[0]):
            best = (o, [tin, tout], [f])
    return best


def _leg1_map(tags, res):
    """{(hub, f1): out} for the positive leg1 (tin->hub) quotes."""
    m = {}
    for (k, hub, f), r in zip(tags, res):
        if k == 'l1':
            o = _dec_single(r[0], r[1])
            if o > 0:
                m[(hub, f)] = o
    return m


def _r2_calls(tout, l1):
    calls, tags = [], []
    for (hub, f1), amt1 in l1.items():
        for f2 in _PCS_FEES:
            calls.append((_PCS_Q, _enc_single(hub, tout, amt1, f2)))
            tags.append((hub, f1, f2))
    return calls, tags


def _pick2(tin, tout, tags, res):
    best = None
    for (hub, f1, f2), r in zip(tags, res):
        o = _dec_single(r[0], r[1])
        if o > 0 and (best is None or o > best[0]):
            best = (o, [tin, hub, tout], [f1, f2])
    return best


def _best_2hop(w3, tin, tout, l1):
    """Best 2-hop (out, [tin,hub,tout], [f1,f2]) or None (one round-2 aggregate3)."""
    if not l1:
        return None
    calls, tags = _r2_calls(tout, l1)
    res = _agg3(w3, calls)
    if res is None:
        return None
    return _pick2(tin, tout, tags, res)


def _assemble(w3, tin, tout, r1t, r1):
    """[(out, 'pcs', (path, fees)), ...] from the round-1 results (direct + 2-hop)."""
    out = []
    bd = _best_direct(tin, tout, r1t, r1)
    if bd is not None:
        out.append((bd[0], 'pcs', (bd[1], bd[2])))
    bh = _best_2hop(w3, tin, tout, _leg1_map(r1t, r1))
    if bh is not None:
        out.append((bh[0], 'pcs', (bh[1], bh[2])))
    return out


def pcs_candidates(w3, chain, tin, tout, amt):
    """Pancake V3 candidates [(out, 'pcs', (path, fees)), ...]: best direct + best
    2-hop. Two aggregate3 rounds. Empty off ETH/Base or when the batch flakes."""
    if _pcs_router(chain) is None:
        return []
    r1c, r1t = _r1_calls(chain, tin, tout, amt)
    r1 = _agg3(w3, r1c)
    if r1 is None:
        return []
    return _assemble(w3, tin, tout, r1t, r1)


