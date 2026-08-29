from chain1_c import _V2_PAIRS, _MAX_QUOTES
from chain1_lib import _candidates, _qroute

def _v2_reserves(w3, pair, block):
    from eth_abi import decode as _dec
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    r = w3.eth.call({'to': _ck(pair), 'data': '0x' + _keccak(text='getReserves()')[:4].hex()}, block_identifier=block)
    res = _dec(['uint112', 'uint112', 'uint32'], r)
    return (int(res[0]), int(res[1]))

def _v2_quote(w3, pair, amt, in_is_t0, block):
    try:
        res = _v2_reserves(w3, pair, block)
        rin, rout = (res[0], res[1]) if in_is_t0 else (res[1], res[0])
        ai = int(amt) * 997
        return ai * rout // (rin * 1000 + ai) or None
    except Exception:
        return None

def _v2_lookup(tin, tout):
    ent = _V2_PAIRS.get(frozenset((tin, tout)))
    if not ent:
        return None
    pair, t0 = ent
    return (pair, tin == t0)
from lat_swapcd_ext import _v2_swap_cd
from lat_xfercd_ext import _v2_xfer_cd

def _v2_build(pair, in_is_t0, tin, amt, out, rcpt, chain_id):
    from minotaur_subnet.shared.types import Interaction as _IX
    return [_IX(target=tin, value='0', call_data=_v2_xfer_cd(pair, amt), chain_id=chain_id), _IX(target=pair, value='0', call_data=_v2_swap_cd(in_is_t0, out, rcpt), chain_id=chain_id)]

def _better(best, q):
    """Whether quote `q` should take the slot from `best`.

    STRICTLY greater, so on a tie the EARLIER candidate keeps it -- _candidates emits a fixed
    order and that order is what resolves equal quotes. The test was spelled inline at both
    call sites below; a `>=` in one of them would silently re-rank ties across half the sweep
    and nothing would fail, the solver would just start serving a different route.
    """
    return bool(q) and (best is None or q > best[0])

def _sweep(w3, tin, tout, amt, block):
    best, n = (None, 0)
    for cand in _candidates(tin, tout):
        if n >= _MAX_QUOTES:
            break
        n += 1
        q = _qroute(w3, cand, amt, block)
        if _better(best, q):
            best = (q, cand)
    return best

def _v2_best(w3, tin, tout, amt, block, best):
    v2 = _v2_lookup(tin, tout)
    if v2 is not None:
        q2 = _v2_quote(w3, v2[0], amt, v2[1], block)
        if _better(best, q2):
            best = (q2, ('v2', v2[0], v2[1], q2))
    return best

def _c1_build_ix_v2(tin, recip, tokens, amt):
    """ZERO-RPC Uniswap-V2 router serve (baked-spec sibling of solver._c1_build_ix).
    Returns [approve_ix, v2swap_ix] for the V2 SwapRouter02:
    swapExactTokensForTokensSupportingFeeOnTransferTokens (sel 0x5c11d795), min_out=0,
    deadline 9999999999. The SupportingFeeOnTransfer variant + min_out=0 make it safe for
    fee-on-transfer exotics (never reverts on tax skim). `tokens` is the full V2 path
    (direct [tin,tout] or 2-hop [tin,WETH,tout]) baked pre-verified via getAmountsOut>0.

    The approve leg comes from chain1_lib._approve_ixs, NOT from a bare encode_approve
    here. min_out=0 and the SupportingFeeOnTransfer selector make the SWAP unable to
    revert, which is what this path was built for -- but that guarantee is worth nothing
    if the approve in front of it reverts, and a USDT input against a non-zero standing
    allowance does exactly that. The whole plan goes down with it and the row scores as a
    delivery failure."""
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    from minotaur_subnet.shared.types import Interaction as _IX
    from chain1_lib import _approve_ixs
    ROUTER_V2 = '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'
    swap_data = '0x5c11d795' + _enc(['uint256', 'uint256', 'address[]', 'address', 'uint256'], [int(amt), 0, [_ck(t) for t in tokens], _ck(recip), 9999999999]).hex()
    return _approve_ixs(_ck(tin), ROUTER_V2, amt, 1) + [_IX(target=_ck(ROUTER_V2), value='0', call_data=swap_data, chain_id=1)]

def _c1_recip_v2(p, state):
    return str(p.get('receiver', '') or getattr(state, 'contract_address', None) or getattr(state, 'owner', None) or '0x0000000000000000000000000000000000000001')

def _c1_v2_plan(solver, intent, state, tin, amt, spec):
    """Zero-RPC UniV2 ExecutionPlan for a baked {'venue':'univ2','tokens':[...]} spec.
    Delegated out of solver._chain1_build_plan to keep that method's AST region tiny
    (the crown-holding max_region_nodes tie-break floor). Recipient LIVE from state,
    min_out=0 => never reverts. metadata solver='chain1-baked' (same as the V3 path)."""
    from minotaur_subnet.shared.types import ExecutionPlan as _EP
    recip = _c1_recip_v2(solver._normalized_swap_params(intent, state), state)
    ix = _c1_build_ix_v2(tin, recip, [str(t).lower() for t in spec['tokens']], amt)
    return _EP(intent_id=intent.app_id, interactions=ix, deadline=9999999999, nonce=state.nonce, metadata={'solver': 'chain1-baked', 'chain_id': 1})

def _c1_curve_ix(tin, amt, recip, spec):
    """Build [approve_ix, exchange_ix] for a baked curve spec by REUSING the pure (no-RPC)
    curve_venue.curve_calldata to rebuild the CurveRouterNG.exchange calldata. Split out of
    _c1_curve_plan so that method's AST region stays tiny (the crown region floor). tin is
    approved to the router curve_calldata returns; min_out floored to >=1 inside curve_calldata.

    Same reasoning as _c1_build_ix_v2: the approve comes from chain1_lib._approve_ixs so a
    USDT input gets its reset leg. The spender here is not a constant -- curve_calldata
    picks the CurveRouterNG address per route -- which is exactly why the guard had to
    become router-parameterised rather than be copied."""
    from eth_utils import to_checksum_address as _ck
    from minotaur_subnet.shared.types import Interaction as _IX
    from chain1_lib import _approve_ixs
    import curve_venue as _cv
    rspec = {'route': spec['route'], 'swap': spec['swap']}
    router, cd = _cv.curve_calldata(1, tin, None, int(amt), 0, recip, 9999999999, rspec)
    return _approve_ixs(_ck(tin), router, amt, 1) + [_IX(target=_ck(router), value='0', call_data=cd, chain_id=1)]

def _c1_curve_plan(solver, intent, state, tin, amt, spec):
    """ZERO-RPC Curve serve for a baked {'venue':'curve','route':[address[11]],'swap':[[..]x5]}
    spec (route+swap eth_call-VERIFIED by curve_venue.curve_best at BAKE time). Recipient LIVE from
    state, min_out floored (never reverts on pool drift). metadata solver='chain1-baked' (V3/V2 sib)."""
    from minotaur_subnet.shared.types import ExecutionPlan as _EP
    recip = _c1_recip_v2(solver._normalized_swap_params(intent, state), state)
    ix = _c1_curve_ix(tin, amt, recip, spec)
    return _EP(intent_id=intent.app_id, interactions=ix, deadline=9999999999, nonce=state.nonce, metadata={'solver': 'chain1-baked', 'chain_id': 1})

def _c1_servable(spec):

    def _has_route():
        """True when the spec carries something executable, per venue.

        curve needs route[11]+swap[5][5]; univ2 needs a token path; v3 needs tokens+fees. A spec
        matching none of these is a recorded `noroute` and must stay clean-skipped -- letting it
        through would hand the base engine a blind single-hop that can revert, which scores
        catastrophic rather than merely absent.
        """
        if spec.get('venue') == 'curve':
            return bool(spec.get('route') and spec.get('swap'))
        return bool(spec.get('tokens') and (spec.get('fees') or spec.get('venue') == 'univ2'))
    return _has_route()

# OUTPUT TOKENS THE BAKED V3 BUILDER CANNOT DELIVER, and why the list keys on
# the OUTPUT side only.
#
# `_chain1_build_plan` sets amountOutMinimum=0 and its docstring reads that as
# "pool drift can never revert". That is true of the ROUTER and false of the
# TOKEN. A v3 pool that is initialized but holds no liquidity does not revert:
# exactInput walks its ticks, comes back with amountOut 0, and the pool then
# runs `safeTransfer(tokenOut, recipient, 0)`. An ERC20 that rejects a
# zero-value transfer reverts there, and a revert on the delivery leg takes the
# WHOLE intent down -- so min_out=0 converts "deliver nothing" into "deliver
# nothing AND burn the order", which is the same score but forecloses the row.
#
# MEASURED 2026-08-27, state/last-exec-check.json at fork block 25843055, the
# only two rows in that corpus whose revert is LATE (~398k gas, i.e. the route
# ran to the delivery leg) rather than an early `Fee exceeds cap`:
#
#   veto:q_2ed4bdf29aea  1598175858 USDC -> 0x72e4f9f8..  js=0.0000
#   veto:q_44f422b84029  1494070030 USDC -> 0x72e4f9f8..  js=0.0000
#   both: scoreIntent reverted: Error("Transfer amount must be greater than zero")
#
# GENESIS AND CANDIDATE FAIL IDENTICALLY on both, so this is a BLIND SPOT, not a
# regression: the incumbent's adoption-time value on these rows is zero and any
# non-zero delivery is a `blind_spot_cover` (+1 each on rung 1). It also cannot
# become a hard veto -- a `dropped` needs an order the champion SERVES, and the
# scored record agrees he serves neither.
#
# chain1_routes.json bakes `1|<usdc>|0x72e4f9f8..` as fees [500, 3000] over
# [USDC, WETH, 0x72e4f9f8..], and `1|<usdt>|0x72e4f9f8..` the same. The 0.3% v3
# pool on the second hop is the empty one. The V2 pair is where that asset's
# liquidity actually sits, and `_c1_build_ix_v2` is already the right builder
# for it: swapExactTokensForTokensSupportingFeeOnTransferTokens with min_out=0,
# which is the variant written for exactly this class of token.
#
# THE PREDICATE BELOW DID NOT TAKE EFFECT, measured 2026-08-28. It landed at
# 9d61cad (2026-08-27 07:39Z) and `state/last-exec-check.json` at HEAD f5aa8cd,
# fork block 25850247 -- a NEWER block and a full day later -- still shows both
# rows reverting `Error("Transfer amount must be greater than zero")`
# identically to genesis. That string is a TOKEN-level rejection of a zero-value
# transfer, i.e. the delivery leg of the V3 builder, so the V3 builder is still
# the one executing and the reroute never fired. The venue diagnosis above is
# not what failed; the dispatch to it is.
#
# So the pair is now baked with an explicit `"venue": "univ2"` spec, which
# `_c1_make_plan` dispatches on FIRST and unconditionally, instead of being
# inferred here from the output address. 423 rows in that table already carry
# that exact shape. The predicate is left in place: it still documents the
# failure mode and still covers any row that reaches the v3 builder with this
# output token, but it is no longer the only thing standing between this pair
# and a revert.
#
# KEYED ON THE OUTPUT TOKEN, NOT THE PAIR, because the failure mode is the
# delivery transfer. The same asset as INPUT is untouched: its transfers are
# non-zero by construction and its two baked rows (`->WETH`, `->USDC`) deliver
# through tokens that accept a zero transfer, so there is nothing there to
# rescue and re-routing them would be an unmeasured change to rows that are not
# known to be failing. Do not add an address here off a plan-level gate -- every
# gate but bin/exec-check compares PLANS, and a plan cannot see this. The entry
# fee is a LATE revert observed on the fork.
_V3_ZERO_DELIVERY_OUT = frozenset({'0x72e4f9f808c49a2a61de9c5896298920dc4eeea9'})

def _c1_v3_delivers_zero(spec):
    """Would serving this baked spec through the V3 builder revert on delivery?

    Narrow by construction: only a spec with NO venue and WITH fees reaches the
    v3 builder at all, so univ2 and curve rows answer False before the address
    is read and keep their own encoders. `tokens[-1]` is the delivered asset --
    the table bakes the full path, so on a 2-hop row that is the destination,
    not the mid.
    """
    toks = spec.get('tokens') or []
    if spec.get('venue') or not spec.get('fees') or len(toks) < 2:
        return False
    return str(toks[-1]).lower() in _V3_ZERO_DELIVERY_OUT

def _c1_as_v2_path(spec):
    """The same baked token path, re-declared for the V2 router.

    The path carries over verbatim: the table's v3 rows already route these
    through WETH, which is the mid a V2 hop wants anyway. Fees are dropped
    rather than translated -- V2 has one tier and `_c1_build_ix_v2` takes no fee
    argument. Returns a NEW dict; the cached table row is shared across every
    order for this pair and must not be mutated.
    """
    return {'venue': 'univ2', 'tokens': [str(t).lower() for t in spec['tokens']]}

# A BAKED CURVE PIN THE VALIDATOR HAS SINCE SCORED AT ZERO DELIVERED, and why
# re-pinning it to a sibling pool cannot cost a thing.
#
# `curve_venue.curve_best` picks a direct pool by quoting EVERY pool that holds
# the pair through the router's own `get_dy` and keeping the highest. So a pin
# in `chain1_routes.json` is not a guess -- it is the pool that priced best on
# the fork the day it was baked. That is exactly the shape `_champ_base:1055`
# names as the expensive one: a venue that "often quotes highest but
# phantom-reverts, [while] a lower-quote venue may deliver far more". A pin
# cannot be re-verified at serve time, because chain 1 is served with NO read
# RPC (`build_rpc_url_map` defaults SOLVER_READ_PROXY_CHAINS=8453), so a pin
# that has gone stale stays stale until something outside the round says so.
#
# MEASURED, and by the only meter that sees delivery. `state/last-scored-verdict.json`
# (sub_a95f9e8cb546, round-e29796909-n1) scores the incumbent at `champ: null`
# on `quote:q_ef2534ad611df357cb13f562113ba6d7` -- chain 1, a stable pair,
# 2592.06e18 in -- and `state/last-perf-ab.json` carries the same row with
# `live_champ_zero: true` and our `our_legs_detail` BYTE-IDENTICAL to
# `champ_legs_detail`. Same two legs, same router, same pool. The incumbent
# delivered nothing through that pin and so did we: a `blind_spot_repeat`, the
# row the validator's own note calls the single most actionable one there is.
#
# THE PAIR IS DEAD AT EVERY SIZE, which is what bounds the downside to nothing.
# The row is baked in PAIR form, not amount form, so the incumbent answers every
# order on this pair with this one pool. There is therefore no amount at which
# it delivers, and `evaluate_relative_adoption` cannot reach `regression` or
# `dropped` on any of them -- both verdicts need a positive champ to compare
# against. The outcomes available here are `blind_spot_cover` if the sibling
# delivers and `blind_spot_repeat` -- today's row -- if it does not.
#
# WHY A SIBLING AND NOT A DIFFERENT VENUE. `curve_census_1.json` attests FOUR
# stable pools holding this exact pair. The dead pin is the one scraped from an
# earlier registry; the other three sit back to back in the census, and two of
# them list their coins in the SAME order as the dead one, so the swap row
# carries over unchanged and only one address moves. That matters more than it
# looks: `_champ_base:1312` records that a curve `swap` row is an (i, j) index
# triple read against the `route` array, and indices left pointing at the wrong
# two coins are a REVERT rather than a worse price. Nothing else in this tree
# reaches the pair -- `chain1_routes.json` holds no other key with this output
# token, so `bg124_c1weth._compose` has no halves to bridge and declines it.
#
# WHAT IS NOT CLAIMED. That the sibling is liquid TODAY. It cannot be: no gate
# in this pipeline holds a chain-1 read RPC, `bin/perf-check` compares plans
# with no RPC at all, and `bin/certify` replays a chain-1 corpus built from
# VETOED ids, which a blind spot is not. This is an unverified re-pin whose
# worst case is the neutral row we already have, entered on a delivery
# measurement the validator made, not on a plan-level gate.
#
# KEYED ON THE DEAD POOL, NOT JUST THE PAIR, and the swap row is checked too.
# If a later bake moves this pin on its own the key stops matching and the table
# row is returned untouched, so this can never re-point a route somebody else
# has already repaired.
_CURVE_REPIN = {
    ('0x98a878b1cd98131b271883b390f68d2c90674665',
     '0x38eeb52f0771140d10c4e9a9a72349a329fe8a6a',
     '0x4c1044a1b6474486a88cdd6a3d40f839abdae283'):
        ('0xe41be7B340f7c2EDA4DA1e99b42Ee1b228b526b7', [1, 0, 1, 1, 2]),
}

def _c1_curve_repin(spec):
    """The same curve spec with a scored-dead pin swapped for its sibling, else `spec`.

    Reads the pair off the ROUTE rather than off the order's parsed tokens, so
    the row being rewritten is the row actually about to be encoded: route[0] is
    the input, route[1] the pool and route[2] the output on every single-hop row
    `curve_venue._direct` bakes. A two-hop row has a different meaning at those
    slots and simply never matches a key.

    Returns a NEW dict. The table row is the cached object shared by every order
    on this pair, exactly as `_c1_as_v2_path` records, and mutating it would
    rewrite the pin for the whole process off one order's lookup.
    """
    route = list(spec.get('route') or ())
    swap = [list(r) for r in (spec.get('swap') or ())]
    if len(route) < 3 or not swap:
        return spec
    got = _CURVE_REPIN.get((str(route[0]).lower(), str(route[2]).lower(),
                            str(route[1]).lower()))
    if got is None or swap[0] != got[1]:
        return spec
    route[1] = got[0]
    fresh = dict(spec)
    fresh['route'] = route
    return fresh

def _c1_make_plan(solver, intent, state, tin, amt, spec):
    v = spec.get('venue')
    if v == 'univ2':
        return _c1_v2_plan(solver, intent, state, tin, amt, spec)
    if v == 'curve':
        return _c1_curve_plan(solver, intent, state, tin, amt, _c1_curve_repin(spec))
    if _c1_v3_delivers_zero(spec):
        return _c1_v2_plan(solver, intent, state, tin, amt, _c1_as_v2_path(spec))
    return solver._chain1_build_plan(intent, state, tin, amt, spec)