"""Route selection + plan building for SN112 covers.

Venue config and quoting live in `venues` (see the split rationale there).
Names used by champ_decode (CHAINS, q_v3_single, q_v3_path, q_v2) are
re-exported here so its `_rc.<name>` access keeps working unchanged.
"""
from __future__ import annotations
_DR_UNSET = object()
import time
from venues import DEADLINE, BUDGET_S, _SEARCH_DEADLINE, FEES, CHAINS, AERO_ROUTER, AERO_FACTORY, S_APPROVE, S_AERO_SWAP, S_CURVE_EXCH_RECV, S_V3_SINGLE_V1, S_V3_SINGLE_02, S_V3_PATH_V1, S_V3_PATH_02, eth_call, _approve, _v3_path_bytes, _aero_candidates, q_v3_single, q_v3_path, q_v2, q_aero, q_curve, _legs_curve
import venue_batch as _vb
import venue_serial as _vs
from eth_abi import encode as _enc

def _scan_venues(rpc, cfg, chain_id, tin, tout, amt, take, expired):
    """Batch first, serial only if the batch did not land, curve last on both paths.

    `venue_batch.scan_all` is all-or-nothing, so the fallback either replaces the
    whole venue scan or none of it — the two never contribute to one `best`.
    """
    if not _vb.scan_all(rpc, cfg, chain_id, tin, tout, amt, take):
        _vs.scan_serial(rpc, cfg, chain_id, tin, tout, amt, take, expired)
    _vs.scan_curve(rpc, cfg, tin, tout, amt, take, expired)

def best_route(rpc, chain_id, tin, tout, amt):
    """Quote every venue for this pair and keep the best; None if nothing quotes.

    SHARED-CELL DISCIPLINE. `_SEARCH_DEADLINE` is one mutable cell read by every
    `venues.eth_call` in the tree, so a window that does not hand it back exactly
    as it found it corrupts whatever search encloses it. `cover_ext._arm/_disarm`
    documents what that costs from the restrictive side — an expired deadline left
    behind refused the inherited solver's quotes on every LATER order, and
    sub_63ae4707f360 covered 38 blind spots while DROPPING 41 the champion served.

    This function used to clobber the cell to 0.0 on the way out, which is the same
    defect from the permissive side: 0.0 is falsy, so eth_call stops honouring any
    bound at all and an enclosing 3s cover window silently becomes unbounded — the
    per-plan overrun the budget exists to prevent, and an overrun turns planned
    orders into dropped ones. It also overwrote a tighter enclosing deadline with
    its own +6.0s, letting a nested scan outrun the budget its caller had set.

    Now: save `prev`, honour the TIGHTER of prev and our own window, restore `prev`
    on the way out. No enclosing search can be loosened, shortened or erased by us.

    DETERMINISM. The window above bounds wall time, but the serial scans spend it
    one `eth_call` at a time, so a slow machine reaches `best` having quoted fewer
    venues than a fast one and two validators replaying the same submission
    disagree about the route. `venue_batch.scan_all` removes that race by quoting
    the whole candidate set in one aggregate3 round trip; the serial scans stay as
    the fallback for a chain with no Multicall3, so nothing is lost when it fails.
    See venue_batch's module docstring for the follower verdict that measured it.
    Curve stays serial -- pool lookup, coin indices and get_dy are three DEPENDENT
    calls, so there is nothing to batch -- and stays deadline-gated as the tail.
    """

    def _dz101(tin, tout):
        tin = tin.lower()
        tout = tout.lower()
        best = None
        prev = _SEARCH_DEADLINE[0]
        deadline = time.monotonic() + BUDGET_S
        return (best, deadline, prev, tin, tout)
    cfg = CHAINS.get(int(chain_id))
    if not cfg:
        return None
    best, deadline, prev, tin, tout = _dz101(tin, tout)
    if prev:
        deadline = min(deadline, prev)
    _SEARCH_DEADLINE[0] = deadline

    def expired():
        return time.monotonic() > deadline

    def take(out, route):
        nonlocal best
        if out and out > 0 and (best is None or out > best[0]):
            best = (out, route)
    try:
        _scan_venues(rpc, cfg, chain_id, tin, tout, amt, take, expired)
    finally:
        _SEARCH_DEADLINE[0] = prev
    return best

def _legs_v3_single(cfg, tin, tout, amt, app_addr, route):

    def _dz290():
        nonlocal body
        body = _enc(['address', 'address', 'uint24', 'address', 'uint256', 'uint256', 'uint256', 'uint160'], [tin, tout, int(route['fee']), app_addr, DEADLINE, int(amt), 0, 0])
    r = cfg['v3router']
    if cfg['v3_deadline']:
        _dz290()
    else:
        body = _enc(['address', 'address', 'uint24', 'address', 'uint256', 'uint256', 'uint160'], [tin, tout, int(route['fee']), app_addr, int(amt), 0, 0])
    return [(tin, _approve(tin, r, amt)), (r, '0x' + cfg['v3sel_single'] + body.hex())]

def _legs_v3_path(cfg, tin, amt, app_addr, route):
    """exactInput takes a STRUCT, so the args must be tuple-encoded, not flat.

    MEASURED BUG (every 2-hop cover we ever built was dead on arrival):
      keccak("exactInput((bytes,address,uint256,uint256,uint256))")[:4] = c04b8d59
      keccak("exactInput(bytes,address,uint256,uint256,uint256)")[:4]   = 41f9ad65
    consts.py pins c04b8d59 (the struct form), but we encoded FLAT. Because the
    struct contains a dynamic member (`bytes path`), the two differ: flat is 256
    bytes starting 0x...a0, struct is 288 bytes starting 0x...20 (the head offset
    to the tuple). The router's ABI decoder aborts on the flat body -> BARE revert,
    so the swap never even reaches the token pull. Fixed calldata reverts with STF
    instead (decoded fine, failed only on allowance) — see test_v3path_exec.py.

    `_legs_v3_single` deliberately stays flat: its tuple is ALL-STATIC, so flat and
    struct encodings are byte-identical there (asserted in the test). That is why
    single-hop covers always worked and only 2-hop ones silently died.
    """

    def _dz289():
        if cfg['v3_deadline']:
            body = _enc(['(bytes,address,uint256,uint256,uint256)'], [(path, app_addr, DEADLINE, int(amt), 0)])
        else:
            body = _enc(['(bytes,address,uint256,uint256)'], [(path, app_addr, int(amt), 0)])
        return ([(tin, _approve(tin, r, amt)), (r, '0x' + cfg['v3sel_path'] + body.hex())],)
        return _DR_UNSET
    r = cfg['v3router']
    path = _v3_path_bytes(route['tokens'], route['fees'])
    _r_dz289 = _dz289()
    if _r_dz289 is not _DR_UNSET:
        return _r_dz289[0]
S_V2_SWAP_FOT = '5c11d795'

def _v2_approve_legs(tin, r, amt):
    """The approve leg(s) for a V2 serve, carrying the USDT reset where it is load-bearing.

    `chain1_lib._approve_ixs` already audited chain-1's baked builders for the bare
    non-zero approve that USDT reverts on -- but its list names only
    `chain1_lib._build`, `chain1_v2._c1_build_ix_v2` and `chain1_v2._c1_curve_ix`.
    THIS builder is a fourth spender it never enumerated, so the guard skipped the
    one V2 path that live-quotes its own route. Reused rather than re-derived:
    `_needs_reset_approve` owns the token test, and it normalises case, so the
    lowercased `tin` this module carries compares correctly.
    """
    try:
        from chain1_lib import _needs_reset_approve as _nra
        reset = _nra(tin)
    except Exception:
        reset = False
    legs = [(tin, _approve(tin, r, 0))] if reset else []
    return legs + [(tin, _approve(tin, r, amt))]

def _legs_v2(tin, amt, app_addr, route):
    """UniV2 serve on the SupportingFeeOnTransfer selector, min_out=0.

    MEASURED DROP (b1 sub_e171b56c05b5, certify `dex:veto:q_6581642391f7`): this
    builder emitted the plain `swapExactTokensForTokens` (38ed1739) against a USDT
    input and the fork answered `CallFailed(index=1)` -- the SWAP leg, bare, with no
    inner reason -- while the champion's V3 route delivered 322964655456509649921 on
    the same block. `chain1_v2._c1_build_ix_v2` had already established why on this
    exact venue: the SupportingFeeOnTransfer variant plus min_out=0 "make the SWAP
    unable to revert", because the plain selector re-derives amounts from
    `getAmountsOut` and asserts them after the transfer, so any token that skims on
    transfer -- or any pair whose reserves moved between our quote and the fork's
    block -- takes the whole plan down. That guarantee never reached this module
    because this is the live-quoting builder, not one of the baked ones.

    A plan-level gate cannot see this: both trees build two well-formed legs, which
    is why perf-check cleared the row and only bin/exec-check caught it.
    """
    r = route['router']
    body = _enc(['uint256', 'uint256', 'address[]', 'address', 'uint256'], [int(amt), 0, route['path'], app_addr, DEADLINE])
    return _v2_approve_legs(tin, r, amt) + [(r, '0x' + S_V2_SWAP_FOT + body.hex())]

def _legs_aero(tin, amt, app_addr, route):
    body = _enc(['uint256', 'uint256', '(address,address,bool,address)[]', 'address', 'uint256'], [int(amt), 0, route['routes'], app_addr, DEADLINE])
    return [(tin, _approve(tin, AERO_ROUTER, amt)), (AERO_ROUTER, '0x' + S_AERO_SWAP + body.hex())]

def _legs_for(cfg, kind, tin, tout, amt, app_addr, route):
    if kind == 'v3_single':
        return _legs_v3_single(cfg, tin, tout, amt, app_addr, route)
    if kind == 'v3_path':
        return _legs_v3_path(cfg, tin, amt, app_addr, route)
    if kind == 'v2':
        return _legs_v2(tin, amt, app_addr, route)
    if kind == 'aero':
        return _legs_aero(tin, amt, app_addr, route)
    if kind == 'curve':
        return _legs_curve(tin, amt, app_addr, route)
    return None

def build_plan(app_id, chain_id, tin, tout, amt, app_addr, nonce, route, ExecutionPlan, Interaction):

    def _dz288():
        nonlocal tin, tout
        tin = tin.lower()
        tout = tout.lower()
        legs = _legs_for(cfg, route['kind'], tin, tout, amt, app_addr, route)
        if not legs:
            return (None,)
        ix = [Interaction(target=t, value='0', call_data=d, chain_id=int(chain_id)) for t, d in legs]
        return (ExecutionPlan(intent_id=app_id, interactions=ix, deadline=DEADLINE, nonce=nonce, metadata={'chain_id': int(chain_id)}),)
        return _DR_UNSET
    cfg = CHAINS[int(chain_id)]
    _r_dz288 = _dz288()
    if _r_dz288 is not _DR_UNSET:
        return _r_dz288[0]

def cover(app_id, chain_id, tin, tout, amt, app_addr, nonce, rpc_url, ExecutionPlan, Interaction):
    """Full path: live-quote best route, build plan. Returns (plan, expected_out) or (None, 0)."""
    br = best_route(rpc_url, chain_id, tin, tout, amt)
    if not br:
        return (None, 0)
    out, route = br
    plan = build_plan(app_id, chain_id, tin, tout, amt, app_addr, nonce, route, ExecutionPlan, Interaction)
    return (plan, out)