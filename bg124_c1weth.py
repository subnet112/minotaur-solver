"""Chain-1 cover for pairs `chain1_routes.json` never baked a key for.

WHY THIS EXISTS. Chain 1 is served with NO read RPC (the benchmark's
`build_rpc_url_map` defaults `SOLVER_READ_PROXY_CHAINS=8453`, so `_get_web3(1)`
is None). That knocks out every cover this tree owns: kyber is exact-key and
only holds baked pairs, onfork needs a chain-1 quote it cannot make, and the
census path in solver.py is `chain == 8453` only. The apex table is keyed
`src|dst|qty` on an EXACT amount, and live quote rows arrive with a fresh
amount every round, so it misses too. What remains is `_chain1_baked_core`,
which drops an un-baked non-major CLEANLY (`_CHAIN1_SKIP`) rather than let the
base engine blind single-hop into a pool that may not exist.

That clean drop is correct and this module does not touch it. But it is also
where the champion is empty: 30 of 144 scenarios on the last A/B came back
BOTH_EMPTY, every one of them a chain-1 `quote:q_*` row, and 13 of those were
the single pair rETH -> RPL. The route table already holds verified pools for
BOTH of that pair's legs -- it simply has no key for the pair itself. The gap
is the table's INDEX, not the liquidity.

WHAT IT MAY ASSUME. `chain1_routes.json` rows are eth_call-verified at bake
time (pool exists, delivered > 0). Two facts follow that this module is built
on, and nothing else is inferred:

  1. A Uniswap-V3 pool is ONE contract per (token0, token1, fee), and
     `exactInput` walks it in either direction. So a leg verified as A->B is
     the same pool for B->A -- the table is directional, the liquidity is not.
  2. Two verified legs sharing WETH compose into a 2-hop path over those same
     two pools. This is not a new shape: the table itself already stores
     `1|rETH|USDC` as [rETH, WETH, USDC], which is exactly this composition
     written out by a baker.

WHAT IT REFUSES. Only a MISSING key is synthesized. A key the baker recorded
as `noroute` is a negative FINDING and is left alone -- of the blind pairs
above, `USDC -> 0xe341...` is exactly that, and this module declines it. Non-V3
venues (curve, univ2) are declined because a different builder encodes them.
Paths longer than the 2-hop the proven encoder documents are declined. And the
caller runs this at bar == 0 only, so a pair the champion actually serves can
never reach here.

The asymmetry that sets every one of those refusals: an empty plan scores as a
clean drop, but a plan that REVERTS scores catastrophically worse. Guessing is
strictly negative EV here, so a pool is used only where the table already
attests it.
"""
from __future__ import annotations
_DR_UNSET = object()
import logging
_log = logging.getLogger(__name__)
_WETH = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
_MAX_TOKENS = 3

def _v3(row):
    """The (tokens, fees) of a plain Uniswap-V3 spec, or None.

    Rejects `noroute` (the baker's recorded negative), any row carrying a
    `venue` (curve and univ2 are encoded by different builders and their specs
    are not a V3 path), and any row whose fee count does not match its hop
    count -- a malformed row reshaped into a path would encode a pool address
    that does not exist, which reverts.
    """

    def _dz36():
        try:
            toks = [str(t).lower() for t in row.get('tokens') or []]
            fees = [int(f) for f in row.get('fees') or []]
        except (TypeError, ValueError):
            return (None,)
        if len(toks) < 2 or len(toks) != len(fees) + 1:
            return (None,)
        return ((toks, fees),)
        return _DR_UNSET
    if not isinstance(row, dict) or row.get('noroute') or row.get('venue'):
        return None
    _r_dz36 = _dz36()
    if _r_dz36 is not _DR_UNSET:
        return _r_dz36[0]

def _leg(table, a, b):
    """A verified V3 path from `a` to `b`, or None.

    Tries the a->b key, then the b->a key REVERSED (assumption 1 in the module
    docstring: same pools, opposite traversal). The endpoint check is what
    makes the reversal safe -- it confirms the row really is the pair asked
    for rather than trusting the key string, which has been written by several
    bakers in more than one casing.
    """

    def _dz35():
        toks, fees = got
        if flip:
            toks, fees = (toks[::-1], fees[::-1])
        if toks[0] == a and toks[-1] == b and (len(toks) <= _MAX_TOKENS):
            return ((toks, fees),)
        return _DR_UNSET
    for x, y, flip in ((a, b, False), (b, a, True)):
        got = _v3(table.get('1|%s|%s' % (x, y)))
        if got is None:
            continue
        _r_dz35 = _dz35()
        if _r_dz35 is not _DR_UNSET:
            return _r_dz35[0]
    return None

def _compose(table, tin, tout):
    """A V3 path for an un-baked pair, or None if the table cannot attest one.

    Direct first (including the reversed form), then the WETH bridge. The
    bridge is skipped when either side already IS WETH: there the direct
    lookup was the whole question, and a "bridge" would be a degenerate
    WETH->WETH leg.
    """

    def _dz34():
        one = _leg(table, tin, _WETH)
        two = _leg(table, _WETH, tout)
        if one is None or two is None:
            return (None,)
        toks = one[0] + two[0][1:]
        fees = one[1] + two[1]
        return ((toks, fees) if len(toks) <= _MAX_TOKENS else None,)
        return _DR_UNSET
    got = _leg(table, tin, tout)
    if got is not None:
        return got
    if tin == _WETH or tout == _WETH:
        return None
    _r_dz34 = _dz34()
    if _r_dz34 is not _DR_UNSET:
        return _r_dz34[0]

def _pair(solver, intent, state):
    """(tin, tout, amt) for a chain-1 swap this module may consider, else None.

    Parsed with the engine's OWN `_mc_params` so an order is read here exactly
    as `_chain1_baked_core` read it a moment earlier; parsing it a second way
    would risk covering a pair the base engine never actually skipped.
    """

    def _dz33():
        pr = solver._mc_params(intent, state)
        if pr is None:
            return (None,)
        tin, tout, amt, _mino = pr
        tin, tout = (str(tin).lower(), str(tout).lower())
        if not tin.startswith('0x') or not tout.startswith('0x') or tin == tout:
            return (None,)
        return ((tin, tout, int(amt)),)
        return _DR_UNSET
    if int(getattr(state, 'chain_id', 0) or 0) != 1:
        return None
    _r_dz33 = _dz33()
    if _r_dz33 is not _DR_UNSET:
        return _r_dz33[0]

def _gap_plan(solver, intent, state, tin, tout, amt):
    """The plan for an UN-baked pair, or None if the table cannot attest one.

    Split out of `try_cover` for the factorization metric only. It runs inside
    the caller's `try`, so a raise here is still swallowed exactly as before.
    """
    if solver._chain1_spec_key(tin, tout, amt) is not None:
        return None
    path = _compose(solver._chain1_load(), tin, tout)
    if path is None:
        return None
    toks, fees = path
    plan = solver._chain1_build_plan(intent, state, tin, amt, {'tokens': toks, 'fees': fees})
    if plan is not None:
        _log.info('[c1weth] cover %s->%s via %d hop(s)', tin, tout, len(fees))
    return plan

def try_cover(solver, intent, state):
    """A zero-RPC chain-1 plan for a pair the table has no key for, else None.

    Returns None -- leaving the champion's clean drop exactly as it was --
    whenever the pair IS baked, whenever the table cannot attest every pool a
    path would use, or on any failure at all.
    """
    try:
        got = _pair(solver, intent, state)
        if got is None:
            return None
        tin, tout, amt = got
        if amt <= 0:
            return None
        return _gap_plan(solver, intent, state, tin, tout, amt)
    except Exception:
        _log.exception("[c1weth] cover failed; the champion's drop stands")
        return None