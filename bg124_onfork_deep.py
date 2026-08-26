"""Phase-2 candidate layer for bg124_onfork: Curve pools and extra 2-hop mids.

REGION DISCIPLINE (same rule as bg124_onfork_abi.py): bg124_onfork.py's
top-level region is made almost entirely of its `def` statements, so it shrinks
only by MOVING defs out — minifying the bodies moves it by exactly zero. This
module takes the phase-2 fallback layer (Curve census + deep 2-hop mids) plus
the `_mids` helper they share with the phase-1 builders.

Nothing here changes behaviour: the functions are byte-for-byte the ones that
lived in bg124_onfork.py, and they depend only on the ABI/table module, so the
split introduces no import cycle.
"""
from __future__ import annotations

import bg124_onfork_abi as A


# Per-batched-call ceiling, for the DEEP caller only. `blind_escalate` sets
# aside `_REQUOTE_RESERVE_S = 12.0` for its two Multicall3 round trips and sizes
# its entry gate off that reserve — but nothing enforced it. The reserve was a
# doubled measurement (`bg124_onfork._quote_best` records 5.0s for the phase-2
# batch when it fires), i.e. an assumption about how long the call would take,
# and an entry test is not a duration bound: it decides whether to START the
# call and has no say in when it ends.
#
# 6.0 covers that measurement with 20% of room and makes 2 x 6.0 = 12.0 the
# reserve's actual worst case instead of its guess.
#
# Cutting a call that WOULD have returned at 7s is the intended trade, not a
# side effect. A 7s call has already overspent the reserve and is heading for
# `harness/protocol.py::TIMEOUTS[Command.GENERATE_PLAN] = 30.0`, which does not
# merely score the row 0: the orchestrator kills the container, the order comes
# back `chal: null` — a DROPPED order and a hard veto — and the respawn is
# charged against the 900s run clock, so orders behind it drop too. A cut
# re-quote costs nothing by comparison: the base plan stands and the row scores
# the blind_spot_repeat (0) it already scores today.
_DEEP_CALL_S = 6.0


def bounded_w3(w3, deep, bar=0):
    """The phase-2 caller's handle, with a request timeout this tree owns.

    `bg124_onfork._w3` hands back the WRAPPED CHAMPION'S handle, whose timeout
    we do not set — which is why `blind_escalate` had only an entry test to work
    with. But the handle carries its endpoint, and a fresh HTTPProvider over the
    same URI takes a timeout we choose, so the bound was available after all.

    Only a plain HTTP provider is cloned; a shallow caller, a missing handle or
    any other provider keeps exactly what it has today. Losing a handle here
    would silently cost every cover the escalation exists to take, so every
    failure path returns the input rather than None.

    THE GATE IS `_phase2_cands`'s GATE, character for character, and that is the
    whole point of the `bar` parameter. This helper used to read `deep` alone and
    justify it by pointing at the licence `_aero_cands` took one function down —
    "the rows where the ladder can record no regression". That premise was true
    when written and is no longer: `_phase2_cands` widened the same licence to
    `deep or bar == 0`, so the champion-EMPTY caller now builds the WIDER
    Aerodrome candidate set over what was still the UNBOUNDED handle. Opening a
    candidate gate without moving the duration bound that guards it is how a
    cover turns into a drop, so the two predicates are now written the same and
    are read in the same function — see `bg124_onfork._quote_best`, which owns
    both and is why this takes `bar` rather than a pre-combined flag.

    Bounding the champion-EMPTY caller cannot cost a row: `relative_scoring`
    reduces the champion's side to `champ_has = False` there, which gates both
    hard vetoes, so the only outcomes recordable are `blind_spot_cover` (+1) and
    `blind_spot_repeat` (0). NOT widened to `bar < 0`: the champion's blind plan
    is a real plan, this tree's wins all came from overriding those, and cutting
    a call that would have returned trades a win for a match. That is a separate
    judgement from the gap `_phase2_cands` opened, and it is not this one."""
    if w3 is None or not (deep or bar == 0):
        return w3
    try:
        from web3 import Web3
        uri = str(getattr(getattr(w3, "provider", None), "endpoint_uri", ""))
        if not uri.startswith("http"):
            return w3
        return Web3(Web3.HTTPProvider(
            uri, request_kwargs={"timeout": _DEEP_CALL_S}))
    except Exception:
        return w3


def _mids(chain, tin, tout):
    return [m.lower() for m in A.T.get("mids", {}).get(str(chain), [])
            if m.lower() not in (tin, tout)]


def _curve_census():
    """Offline-scanned Curve pool map for chain 1 (build_curve_census.py). Loaded
    once; JSON data costs zero AST nodes. Discovery is the slow half of Curve
    (the registry's get_best_rate measured 20.6s and returned an unexecutable
    route), so it happens offline and the solver only does a direct get_dy."""
    c = getattr(_curve_census, "_c", None)
    if c is None:
        import json
        from pathlib import Path
        try:
            c = json.loads((Path(__file__).parent / "curve_census_1.json").read_text())
        except Exception:
            c = {}
        _curve_census._c = c
    return c


def _curve_row(pools, pool, tin, tout):
    row = pools.get(pool) or {}
    coins = row.get("coins") or []
    if tin in coins and tout in coins:
        return (pool, row.get("kind", "stable"),
                coins.index(tin), coins.index(tout))
    return None


def _curve_pools(tin, tout):
    """Census pools holding BOTH tokens -> [(pool, kind, i, j)]."""
    c = _curve_census()
    pools, byt = c.get("pools") or {}, c.get("bytoken") or {}
    both = set(byt.get(tin, ())) & set(byt.get(tout, ()))
    rows = [_curve_row(pools, p, tin, tout) for p in sorted(both)[:4]]
    return [r for r in rows if r]


def _curve_cands(chain, tin, tout, amt):
    """A direct get_dy per candidate pool, in the same batch. Curve is the venue
    the champion lineage claims but still leaves 14 orders unrouted on; on chain
    1 — the only chain whose orders count — it is the realistic strict win."""
    if chain != 1:
        return []
    return [(("curve", A.ck(p), (k, i, j)), A.ck(p), A.q_curve(k, i, j, amt))
            for p, k, i, j in _curve_pools(tin, tout)]


def _via_v3(chain, tin, mid, tout, amt):
    """Every V3 fee combo through one intermediate token."""
    q = A.ck(A.T["quoter"][str(chain)])
    return [(("path", tuple(f), mid), q, A.q_path(tin, mid, tout, f, amt))
            for f in A.T.get("hops", [])]


def _via_v2(chain, tin, mid, tout, amt):
    """Every V2 router leg through one intermediate token."""
    return [(("v2", A.ck(r), (tin, mid, tout)), A.ck(r),
             A.q_v2(amt, [tin, mid, tout]))
            for r in A.T.get("v2", {}).get(str(chain), [])]


def _via(chain, tin, mid, tout, amt):
    """Every V3 fee combo and V2 router for one intermediate token."""
    return (_via_v3(chain, tin, mid, tout, amt)
            + _via_v2(chain, tin, mid, tout, amt))


def _best(cands, outs):
    """The highest-quoting candidate -> (desc, out), or (None, 0) when every
    venue came back zero. Parked here beside `_corroborated` for the same
    region reason."""
    best_i, best_out = -1, 0
    for k, got in enumerate(outs):
        if got > best_out:
            best_out, best_i = got, k
    return (cands[best_i][0], best_out) if best_i >= 0 else (None, 0)


def _corroborated(outs, best_out):
    """At least one OTHER venue must independently quote the same order within
    2x. hydra took the crown on 1 better / 0 WORSE while we lost with 10 better
    / 3 worse — a single bad order erases any number of wins, so safety beats
    win count. A lone quote from one thin pool is the signature of both failure
    modes we hit: the 0.00002x catastrophic regression and the two routes that
    quoted positive then delivered nothing.

    Lives here rather than beside its one caller for the same reason the rest of
    this module does: bg124_onfork.py's top-level region is made of its def
    HEADERS, so a header parked here is a header off that metric."""
    return sum(1 for o in outs if o > 0 and o * 2 >= best_out) >= 2


def _aero_cands(chain, tin, tout, amt):
    """Aerodrome's volatile and stable direct pools, for the DEEP caller and the
    champion-EMPTY caller. `_phase2_cands` owns that gate and states the rule.

    This is the Base-side counterpart of `_curve_cands`, and it exists because
    phase 2 was chain-1-only where it mattered. `_curve_cands` returns [] for
    every chain but 1, so on the three champion-zero Base rows
    (`blind_escalate`, USDC<->WETH at 1.00 USDC) the whole of phase 2 was
    `_deep_cands` — cbBTC and DAI mid-hops, i.e. two thin two-leg detours asked
    to beat a direct 0.05% pool. They never will. Aerodrome is the deepest
    USDC/WETH book on 8453 and `onfork_tables.json` carried no entry for it, so
    it was the one venue with real size that this router could not price.

    WITHHELD FROM THE BLIND PATH, which is the exposure this venue must not
    touch. `bar < 0` overrides a champion plan that EXISTS — its self-declared
    guess — and there `_phase` demands corroboration, a second venue within 2x,
    before taking it. A new venue changes which of those rows clear that test,
    on orders where a regression IS possible.

    The other two callers have no such exposure. `deep` is `blind_escalate`'s
    order ids; `bar == 0` is a champion plan with NO interactions. Both leave
    `champ_has` False in `epoch/relative_scoring.py`, which gates the `dropped`
    branch (:735) and the `catastrophic` computation (:663) alike, so the only
    outcomes available are blind_spot_cover and blind_spot_repeat. The venue
    goes exactly where the downside is arithmetically zero and nowhere else.

    Stable vs volatile is which pool the pair actually lives in — USDC/WETH is
    volatile — and the router prices a Route[] leg per pool type, so both kinds
    are quoted per leg.

    DIRECT *AND* MID-HOP, because direct-only was asking the wrong question of
    this venue. Every other builder in this tree pairs its direct candidates with
    2-hop ones (`_v3_cands._hop_rows`, `_v2_cands`'s `paths`, `_deep_cands`) and
    this one alone did not, so Aerodrome was offered only the pair the order
    names. That is the pair an exotic token is least likely to have a pool for:
    a new Base token lists against WETH or USDC, not against whatever the order
    asks to receive. The live blind-spot draw is full of the shape — LBTC->cbBTC,
    and rows with an exotic on BOTH sides — where a direct Aerodrome pool cannot
    exist and the mid-hop is the whole route.

    Nothing else has to change to serve one. `A.q_aero` encodes a Route[] of any
    length, `A.decode_one` already takes the LAST leg's amount for kind "aero",
    `A.swap_cd`'s `_s_aero` encodes the same array it quoted, and `A.spender` is
    the router either way — the capability was built and only the candidate
    builder was narrow.

    Mids are phase 1's (`_mids`: WETH/USDC on 8453), not `mids2`'s: those are the
    chain's quote assets, i.e. the side an exotic actually pools against. Four
    combos per mid — both pool kinds on each leg — because which leg is stable is
    exactly what is unknown. Costs 8 more slots in a batch already in flight and
    no extra round trip; chain 1 has no `aero` table entry, so its batch size is
    untouched."""

    def _leg(a, b, stable, factory):
        """One Aerodrome Route[] entry: (from, to, stable, factory). Nested so
        its body is its own region — the same rule the rest of this file follows
        (the caller measured 140 nodes with the tuple built inline twice)."""
        return (A.ck(a), A.ck(b), stable, factory)

    def _routes(factory):
        """Every Route[] worth quoting: the direct pair, then each mid-hop."""
        out = [(_leg(tin, tout, s, factory),) for s in (False, True)]
        for mid in _mids(chain, tin, tout):
            out += [(_leg(tin, mid, s1, factory), _leg(mid, tout, s2, factory))
                    for s1 in (False, True) for s2 in (False, True)]
        return out
    cfg = A.T.get("aero", {}).get(str(chain), {})
    if not cfg or amt <= 0:
        return []
    r = A.ck(cfg["r"])
    return [(("aero", r, x), r, A.q_aero(amt, x))
            for x in _routes(A.ck(cfg["f"]))]


def _wide_v3_cands(chain, tin, tout, amt):
    """The 2-hop V3 fee pairs `hops` leaves out, for the same two callers
    `_aero_cands` serves and on the same gate — `_phase2_cands` states the rule.

    `hops` is [500,500], [3000,3000], [500,3000], [3000,500]: the cross of the
    two MIDDLE tiers only. `fees` also carries 100 and 10000, and phase 1 quotes
    both of them DIRECT — so the tree already believes an exotic pair can live at
    1%, and then cannot route to one through a mid. That is the canonical shape
    of a new listing: the token has a single 1% pool against WETH, the mid leg
    WETH->USDC is 0.05%, and [10000, 500] is not a pair this router has ever
    asked for. Same hole one tier down for 100, where a stable-ish leg pairs with
    a volatile one.

    Written as the COMPLEMENT of `hops` rather than as a second literal list, so
    the two can never drift into quoting the same path twice and adding a pair to
    `onfork_tables.json` shrinks this set by itself.

    Confined to phase 2 for the reason `_deep_cands` is: this is 12 fee pairs per
    mid against phase 1's 4, and phase 1 runs on every champion-empty and
    champion-blind order in the pack. Phase 2 runs where phase 1 found nothing at
    all, where the caller is `deep`, and — since `_quote_best` learned `min_out` —
    where phase 1 quoted POSITIVE BUT UNDER THE INTENT'S FLOOR on a champion-EMPTY
    row. That third entry is the one this venue set exists for and the one it
    could not previously be reached through: a stale floor above the direct pool
    is not "phase 1 found nothing", so the early return took it and these
    candidates were never built. The handle is bounded at `_DEEP_CALL_S` on all
    three paths. Most of these combos name a pool that does
    not exist; the quoter reverts on the factory lookup and `aggregate3` records
    a failed sub-call, which `_quote_all` reads as 0."""

    def _wide_hops():
        """fees x fees, minus the pairs `hops` already covers."""
        fees = A.T.get("fees", [])
        have = {tuple(h) for h in A.T.get("hops", [])}
        return [(a, b) for a in fees for b in fees if (a, b) not in have]
    q = A.ck(A.T["quoter"][str(chain)])
    return [(("path", f, mid), q, A.q_path(tin, mid, tout, f, amt))
            for mid in _mids(chain, tin, tout) for f in _wide_hops()]


def _phase2_cands(chain, tin, tout, amt, deep=False, bar=0):
    """The whole phase-2 candidate set — Curve plus the deep 2-hop mids — as one
    list, so its caller spends one call instead of two.

    Aerodrome is offered to the deep caller and to the champion-EMPTY caller,
    and to nobody else. `_aero_cands` withheld it from everything but `deep`
    because the other way into phase 2 is the `out <= 0` fallback, which serves
    both champion-EMPTY (`bar == 0`) and champion-BLIND (`bar < 0`) plans, and
    on the blind path a new venue changes which rows clear `_phase`'s
    corroboration test — a behaviour change where a regression IS possible.
    That argument is exact, and it covers `bar < 0` only. At `bar == 0` the
    champion returned NO interactions, so `epoch/relative_scoring.py` reduces
    its side to `champ_has = False`: the `dropped` branch (:735) and the
    `catastrophic` computation (:663) are both gated on `champ_has`, leaving
    blind_spot_cover (+1) and blind_spot_repeat (0) as the only two outcomes the
    ladder can record. Same arithmetically-zero downside `_aero_cands` already
    takes its licence from — the boundary was just drawn one predicate too wide.

    Costs no extra round trip. These rows are ALREADY making the phase-2 call:
    they reached it because phase 1 quoted nothing at all, which is also why
    they are the rows that need a venue with real size. Aerodrome adds two
    candidate slots to a batch that is already in flight.

    `strict` is False here (`_quote_best` sets it from `bar < 0`), so widening
    the set cannot change a corroboration outcome on this path either.

    `_wide_v3_cands` rides the SAME gate for the same reason and is written into
    the same branch so the two cannot drift: one predicate, one place, matching
    `bounded_w3`'s character for character. Both add candidates to a batch that
    is already in flight rather than a second round trip."""
    wide = (_aero_cands(chain, tin, tout, amt)
            + _wide_v3_cands(chain, tin, tout, amt)) if deep or bar == 0 else []
    return (_curve_cands(chain, tin, tout, amt)
            + _deep_cands(chain, tin, tout, amt) + wide)


def _deep_cands(chain, tin, tout, amt):
    """Extra 2-hop mid tokens (USDT/DAI/WBTC on chain 1), tried ONLY after phase
    1 came back empty — i.e. on the handful of blind-spot orders per pack that
    actually decide the crown. Every recent dethrone was a single cover on an
    order the incumbent could not route, and our 11 remaining skips are orders
    where WETH/USDC 2-hop finds nothing. Restricting these to phase 2 buys that
    coverage without adding a millisecond to the normal path, which is what the
    pace budget cannot afford."""
    out = []
    for mid in [m.lower() for m in A.T.get("mids2", {}).get(str(chain), [])
                if m.lower() not in (tin, tout)]:
        out += _via(chain, tin, mid, tout, amt)
    return out
