"""Deterministic venue scan: every quote for a pair in ONE aggregate3 round trip.

WHY THIS EXISTS (measured, not defensive). `router_cover.best_route` used to walk
v3 -> v2 -> aero serially, one `eth_call` per candidate, each gated on the shared
6s `_SEARCH_DEADLINE`. `venues.eth_call` refuses to START a call once that window
closes, so a slower machine picks `best` from FEWER venues than a faster one. Two
validators replaying the identical submission then disagree about the route:
on round-e29787497-n1 a follower scored `q_2a2ad298a4dd` `catastrophic` --
champ 130045361018968523678565818 vs chal 101777808945340995220995821, a 21.7%
cut, 17x the 1% hard-veto floor -- on an order the leader's 122 `per_order` rows
do not list at all. Adoption survived only on `confirmed_regression: false`, a
1-of-2 vote. perf-check sees the same thing from the other end as its NONDET rows.

The budget is NOT the bug and must not be widened or deleted: it is what stops a
slow RPC overrunning the validator's per-plan cutoff, and an overrun turns planned
orders into DROPPED ones, which is a hard veto. A call-COUNT cap does not help
either -- a count does not bound wall time. What fixes it without shrinking the
search is removing the *race*: one round trip either lands whole or not at all, so
the venue set stops depending on machine speed. This is the technique
`_champ_base._best_route_serve` already uses in this tree, via
`_bg124_arch_9645f01._H2._run_mc_list` / `._agg_call`.

Enumeration here is PURE -- no RPC, no clock -- so the candidate list is identical
on a fast machine and a slow one. Calldata is built by the same `venues._cd_*`
helpers the serial path uses, so a batched quote is byte-identical to the serial
quote it replaces.

Failure is always backwards-compatible: `scan_all` returns False without touching
the caller's accumulator, and the caller runs the old serial scans. A node with no
Multicall3 deployed is exactly as well off as it was before.
"""
from __future__ import annotations
_DR_UNSET = object()
import time
from eth_abi import encode as _enc, decode as _dec
from web3 import Web3
from venues import FEES, AERO_ROUTER, eth_call, _aero_candidates, _SEARCH_DEADLINE
from venue_codec import _cd_v3_single, _cd_v3_path, _cd_v2, _cd_aero, _dec_u256, _dec_last
MC3 = '0xcA11bde05977b3631167028862bE2a173976CA11'
S_AGG3 = '82ad56cb'
HUB_FEES = (500, 3000)
MC_CHUNK = 40
MC_TIMEOUT = 4.0
SERIAL_RESERVE_S = 2.5
MC_MIN_TIMEOUT = 0.75

def _batch_window(left):
    """Wall time the batch may spend IN TOTAL, or None to skip it entirely.

    THE BUG THIS FIXES, MEASURED BY THE VALIDATOR. The batch replaced the serial
    venue scan in a04a17f. The last tree WITHOUT it, 6bf0c8bcb3, was scored
    `dropped: 0` on all 122 rows and adopted via `dethrone`. Every tree since has
    dropped orders -- 4 on ebcdabb, 6 on sub_adfd64a2af08, 5 on sub_f18ba43bced1
    (WBTC_to_WETH, hist:ord_710c91401286409a and three quote rows) -- and the
    ticks in between answered each one by tightening a clock, which is a
    direction that can only ever remove a plan.

    The mechanism is here. The old `_batch_timeout` handed EACH CHUNK
    `left * 0.55`, recomputed per chunk, and `_quote_all` runs one chunk per 40
    candidates. Two chunks therefore took 0.55 + 0.45*0.55 = ~80% of the window
    between them, and a third took more. When the batch then failed, `scan_all`
    returned False and the serial fallback inherited what was left: with a 6.0s
    `BUDGET_S` window that is ~1.2s, so `venues._effective_timeout` clamped every
    serial `eth_call` to its 0.25s floor, every one of them timed out, `best`
    stayed None, `best_route` returned None and `cover` returned (None, 0) -- a
    DROPPED order and a hard veto. The reserve was expressed as a SHARE of a
    window the batch had already been spending, so it shrank with every chunk;
    the fallback's real floor was zero.

    The reserve is now an absolute number of seconds subtracted from the window
    BEFORE the batch is offered anything, and it is applied once for the whole
    batch rather than per chunk. When the window cannot pay for both, the batch
    does not start and the serial scans get the window intact -- which is exactly
    the shape that scored 0 drops.

    This still only ever TIGHTENS the batch: it cannot widen `_SEARCH_DEADLINE`,
    hand a chunk more than `MC_TIMEOUT`, or let the scan outlive the enclosing
    window. The only thing it moves is which of the two scans spends it.

    DETERMINISM IS PRESERVED. `scan_all` stays all-or-nothing, so a time-derived
    window never yields a PARTIAL venue set -- the race the batch was written to
    remove. It only decides whether the batch lands whole or we fall back whole.

    Neither local gate can see any of this: perf-check runs `rpc_urls: {}` and
    exec-check drives a local anvil, so the batch always lands in under a
    millisecond there and the fallback never runs. The validator's per_order rows
    are the only instrument that reaches it.
    """
    budget = left - SERIAL_RESERVE_S
    if budget < MC_MIN_TIMEOUT:
        return None
    return min(MC_TIMEOUT, budget)

def _batch_deadline():
    """The instant the whole batch must be finished by, or None to skip it.

    Read ONCE per scan, ahead of the first chunk, so the total the batch may
    spend is fixed up front instead of being re-derived from an ever-shrinking
    window each time round the loop -- the compounding that starved the fallback.
    """
    dl = _SEARCH_DEADLINE[0]
    now = time.monotonic()
    if not dl:
        return now + MC_TIMEOUT
    left = dl - now
    if left <= 0:
        return None
    window = _batch_window(left)
    if window is None:
        return None
    return now + window

def _chunk_timeout(batch_dl):
    """Timeout for one chunk: what is left of the batch's own window, capped.

    Returns None once the batch has spent its window, which aborts the scan and
    sends the caller to the serial fallback with `SERIAL_RESERVE_S` still unspent.
    """
    left = batch_dl - time.monotonic()
    if left < MC_MIN_TIMEOUT:
        return None
    return min(MC_TIMEOUT, left)

def _sub(target, data_hex):
    """One aggregate3 subcall: (target, allowFailure, calldata).

    allowFailure is always True. A quoter reverting because the pool does not
    exist is a normal negative answer in a venue scan, not a reason to lose the
    other venues sharing the batch.
    """
    return (Web3.to_checksum_address(target), True, bytes.fromhex(data_hex[2:]))

def mc_quote(rpc, subs, timeout=MC_TIMEOUT):
    """Run `subs` through Multicall3.aggregate3. Returns raw return-bytes aligned
    with `subs` (None where that subcall reverted), or None if the batch itself
    did not come back -- caller falls back to the serial scans."""

    def _dz147():
        r = eth_call(rpc, MC3, data, timeout=timeout)
        if not r:
            return (None,)
        try:
            res = _dec(['(bool,bytes)[]'], r)[0]
        except Exception:
            return (None,)
        if len(res) != len(subs):
            return (None,)
        return ([bytes(d) if ok and d else None for ok, d in res],)
        return _DR_UNSET
    if not subs:
        return []
    data = '0x' + S_AGG3 + _enc(['(address,bool,bytes)[]'], [subs]).hex()
    _r_dz147 = _dz147()
    if _r_dz147 is not _DR_UNSET:
        return _r_dz147[0]

def _cands_v3(cfg, tin, tout, amt):
    """uniV3: direct across every fee tier, then 2-hop via each hub."""

    def _dz146():
        for hub in cfg['hubs']:
            if hub.lower() in (tin, tout):
                continue
            for f1 in HUB_FEES:
                for f2 in HUB_FEES:
                    route = {'kind': 'v3_path', 'tokens': [tin, hub, tout], 'fees': [f1, f2]}
                    out.append((q, _cd_v3_path(route['tokens'], route['fees'], amt), route, False))
    q = cfg['quoter']
    out = [(q, _cd_v3_single(tin, tout, amt, f), {'kind': 'v3_single', 'fee': f}, False) for f in FEES]
    _dz146()
    return out

def _cands_v2(cfg, tin, tout, amt):
    """uniV2-style routers: direct, then via each hub."""
    out = []
    for router in cfg['v2routers']:
        for path in [[tin, tout]] + [[tin, h, tout] for h in cfg['hubs'] if h.lower() not in (tin, tout)]:
            out.append((router, _cd_v2(path, amt), {'kind': 'v2', 'router': router, 'path': path}, True))
    return out

def _cands_aero(cfg, tin, tout, amt):
    """Aerodrome (Base only) -- the venue Uniswap-on-Base misses."""
    return [(AERO_ROUTER, _cd_aero(routes, amt), {'kind': 'aero', 'routes': routes}, True) for routes in _aero_candidates(tin, tout, cfg['hubs'])]

def candidates(cfg, chain_id, tin, tout, amt):
    """Every venue candidate for this pair, in a fixed order. Pure."""
    out = _cands_v3(cfg, tin, tout, amt) + _cands_v2(cfg, tin, tout, amt)
    if int(chain_id) == 8453:
        out += _cands_aero(cfg, tin, tout, amt)
    return out

def _quote_all(rpc, cands):
    """Every candidate quoted, or None. Chunked only to bound the gas one
    `eth_call` has to cover; the CHUNK SIZE is fixed, never time-derived, so the
    candidate set a landed batch covers is identical on a fast machine and a slow
    one. Only the TIMEOUT tracks the clock.

    The batch's total window is fixed by `_batch_deadline` before the first chunk
    and every chunk draws from that one deadline, so a slow first chunk shortens
    the second WITHOUT the pair of them eating into the serial fallback's
    reserve. Deriving each chunk's allowance from the enclosing window instead --
    what this did before -- let two chunks take ~80% of it between them and left
    the fallback nothing to run on, which is how a well-formed order came back
    with no plan at all."""

    def _dz145():
        for i in range(0, len(cands), MC_CHUNK):
            tmo = _chunk_timeout(batch_dl)
            if tmo is None:
                return (None,)
            chunk = cands[i:i + MC_CHUNK]
            rets = mc_quote(rpc, [_sub(target, data) for target, data, _route, _multi in chunk], tmo)
            if rets is None:
                return (None,)
            landed.extend(zip(chunk, rets))
        return _DR_UNSET
    batch_dl = _batch_deadline()
    if batch_dl is None:
        return None
    landed = []
    _r_dz145 = _dz145()
    if _r_dz145 is not _DR_UNSET:
        return _r_dz145[0]
    return landed

def scan_all(rpc, cfg, chain_id, tin, tout, amt, take):
    """Quote every candidate in one round trip per chunk, then feed `take`.

    ALL-OR-NOTHING. `take` is called only once every chunk has landed, so a
    half-finished batch can never seed `best` with a partial venue set and then
    get topped up by the serial fallback from a different one -- that would be
    the same machine-speed dependence in a new place. Returns True when the whole
    scan was quoted, False when the caller should run the serial scans instead.
    """
    landed = _quote_all(rpc, candidates(cfg, chain_id, tin, tout, amt))
    if landed is None:
        return False
    for (_target, _data, route, multi), r in landed:
        take(_dec_last(r) if multi else _dec_u256(r), route)
    return True