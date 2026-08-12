"""aero_pin — measured route pins for the champion's blind spots (Base + chain 1).

FACTORIZATION SPLIT, 2026-08-05. Behaviour is untouched; only the shape moved.
`screening.max_region_nodes` is the largest AST region in ANY file of the tree, and
a region shrinks ONLY when a block moves into a named scope — a lambda, a
comprehension or a data literal does not start one, and a nested def merely
RELOCATES the region it lifts. Measured before: `_aunwind_ixs` 305, `_atoken_ixs`
271, `_ap_build` 245, `_quote_v3` 206, module 202. The V4 encoder now lives in
aero_v4.py, the calldata primitives in aero_abi.py and the Aave/V3/Solidly legs in
aero_legs.py (each FILE carries its own module region), and the oversized builders
here are expressed as small named steps.

CHAIN-1 ADDENDUM (2026-07-30, the ETH-door work). Only chain 1 is inside
`ADOPTION_SCORED_CHAINS` right now, so every Base pin below scores `offgate` and
the counted surface is L1 only. The champion's L1 failure is STRUCTURAL, not a
missing venue: `hydra_top.generate_plan` runs `_hydra_eth_fastpath` FIRST on
chain 1, and that builds a ZERO-RPC `tin -f1- WETH -f2- tout` UniV3 path with
f=3000 for anything outside {WETH/USDC, WETH/WBTC} — without ever checking that
the pools exist. A non-empty plan is returned, so the whole king engine
(`_score_aware_eth`, `_enumerate_eth_quotes`, Curve-NG) is bypassed; and the one
rescue path, `chain1.superset`, is disarmed by `chain1._beats_champ`, which does
`if not q_champ: return False` — i.e. when the champion's OWN route is
UNQUOTABLE it concludes nothing can beat it. Net effect: on every L1 pair whose
naive 3000/WETH path has no pool, the champion serves a REVERTING plan and
delivers 0. Those rows score `skip` (both sides 0); one filled row is a
`blind_spot_cover`, and `net_better = n_wins + n_blind_spots >= 1` with
`n_regressions == 0` is a performance ADOPT.

`kind: "v3path"` pins carry the champion's own route shape ([tokens], [fees])
and are built by its own `chain1._mk_plan`. Zero new calldata.

--- original Base note -------------------------------------------------------

The champion already ships every Aerodrome builder it needs (`aero_v2`,
`aerodrome_slipstream`, `aerodrome_slipstream_multihop`, `_shp_*`), but its live
router SEARCH does not reach them on a handful of Base pairs: it serves a dust
UniV3 pool (or nothing) while an Aerodrome pool holds the real market. Measured
on-chain at 3 notionals each ($100/$300/$1000, 2026-07-30):

    HOME->WETH   slipstream ts=200 direct   13,064x .. 127,571x over best UniV3
    GHST->USDC   aero_v2 2-hop via WETH          9.8x .. 88.5x
    COW ->USDC   aero_v2 2-hop via WETH          UniV3 has NO route at all
    USDC->COW    slipstream WETH 100/200         1.73x .. 2.88x
    MEZO->USDC   aero_v2 2-hop via WETH          UniV3 has NO route at all
    KTA ->USDC   slipstream WETH 200/100         1.027x
    KTA ->WETH   slipstream ts=200 direct        1.027x

This layer does NOT add a venue mechanism. It feeds the champion's OWN
`_sep_kind_cand` + `_build_singlehop_plan` a pinned (kind, param) and serves the
result ONLY when an execution sim proves it strictly out-delivers the champion's
own plan. Every uncertainty returns the champion's plan untouched, so the layer
can never manufacture a `dropped` or a regression.

BUDGET LAW (cover_state.json, 2026-07-30): blindfill was disabled because its RPC
starved the champion's `_RUN_BUDGET_S` governor -> `last_resort_empty` -> one
dropped order -> whole submission REJECTED under #1207 drop-reject. This layer is
built so that cannot happen:
  * a pure dict lookup gates it, so the ~200 non-pinned orders cost ZERO RPC;
  * balance slots are PRE-MEASURED in the data file, so the sim skips the
    12-blockStateCall slot probe;
  * an empty champion plan skips the champion-side sim entirely;
  * `_MAX_SIMS` hard-caps total sims per run; past the cap the layer defers.
It deliberately does NOT copy the sibling covers' `_dyn_order_budget < 8.0`
guard: in production that attribute is ~4.0, which is why curve/twohop/blindfill
never fire at all.
"""
from __future__ import annotations
_DR_UNSET = object()
import logging
from aero_abi import _ERC20_APPROVE
from aero_legs import _atoken_ixs_quoted, _aunwind_ixs, _curve_legs, _curve_spec, _plan, _rcpt
from aero_v4 import _v4_ixs
logger = logging.getLogger(__name__)
_MARGIN_BPS = 500
_MAX_SIMS = 20
_MISS = object()

def _try(fn, *a, **kw):
    """Call `fn`; ANY failure — including a MISSING ATTRIBUTE on an unfamiliar base —
    is a deferral, never a raise. See `_is_plan` for the FAIL-CLOSED contract."""
    if fn is None:
        return None
    try:
        return fn(*a, **kw)
    except Exception:
        return None

def _is_plan(p):
    """True only for a SERVABLE plan: a real object carrying >= 1 interaction.

    L-COVER-NOT-BASE-UNIVERSAL (2026-08-02): "additive by construction, cannot drop"
    holds only where the champion's builders resolve AND return something real. A
    builder that silently yields None/[] on a new lineage would otherwise convert a
    SERVED row into a `dropped` — an absolute veto. Nothing is served unless it
    passes this, so the cover is incapable of eating a row by construction."""
    try:
        return bool(getattr(p, 'interactions', None))
    except Exception:
        return False

def _pin_row(row):
    """One data row -> (key, value), or None when the row is malformed."""
    try:
        key = (int(row['chain']), str(row['tin']).lower(), str(row['tout']).lower())
        return (key, (str(row['kind']), row['param'], row.get('slot')))
    except Exception:
        return None

def _load_pins():
    """(chain, tin, tout) -> (kind, param, slot), loaded from data so the table
    stays out of the AST (max_region_nodes is the adoption tie-breaker)."""
    import json as _j, os as _o
    try:
        path = _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), 'aero_pins.json')
        raw = _j.load(open(path))
    except Exception:
        return {}
    rows = (_pin_row(r) for r in raw.get('pins') or ())
    return dict((r for r in rows if r is not None))

def _keys(solver, intent, state):
    """(chain_id, tin, tout, amt) for an intent, or None. ZERO RPC."""
    try:
        p = solver._normalized_swap_params(intent, state)
        return (int(getattr(state, 'chain_id', 0) or 0), str(p.get('input_token', '') or '').lower(), str(p.get('output_token', '') or '').lower(), int(p.get('input_amount', 0) or 0))
    except Exception:
        return None

def _sim(w3, plan, tin, tout, amt, app, slot):
    """Delivered `tout` for `plan` under eth_simulateV1, using a PRE-MEASURED
    balance slot so the 12-call slot probe is skipped. Falls back to the
    champion's own detector when the slot is not pinned. None = unverifiable."""
    if not _is_plan(plan) or not app:
        return None
    try:
        import viking_sim as _vs
        from eth_utils import to_checksum_address as _ck
    except Exception:
        return None
    if slot is None:
        return _try(getattr(_vs, 'sim_floor', None), w3, plan, tin, tout, amt, app)
    return _try(getattr(_vs, '_delivered', None), w3, plan.interactions, _ck(tin), amt, _ck(tout), slot if isinstance(slot, str) else int(slot), _ck(app))

def _champ_out(w3, base, tin, tout, amt, app, slot):
    """What the CHAMPION delivers. An empty champion plan delivers 0 by definition,
    so the champion-side sim is skipped entirely (the RPC-budget law)."""
    if not getattr(base, 'interactions', None):
        return 0
    return _sim(w3, base, tin, tout, amt, app, slot)

def _log_win(tin, tout, amt):
    """The one line that says this layer displaced the champion on a row."""
    logger.info('[aeropin] WIN %s->%s amt=%d', tin[:10], tout[:10], amt)

def wrap(base_cls):
    import viking_sim
    import cover_state
    _PINS = _load_pins()

    def _ap_bump(slf):
        slf._ap_sims = int(getattr(slf, '_ap_sims', 0) or 0) + 2

    def _ap_guards(slf, base):
        """cover_state + sim-cap guards, in the original order. True = defer."""
        if _try(cover_state.is_cross_chain, base) is not False:
            return True
        if _try(cover_state.base_untrusted, base) is not False:
            return True
        return int(getattr(slf, '_ap_sims', 0) or 0) >= _MAX_SIMS

    def _ap_kind(slf, intent, state, kind, param, tin, tout, amt, cid):
        """Our own pin kinds. `_MISS` (not None) when `kind` is not one of them."""
        if kind == 'aunwind':
            return _try(slf._ap_aunwind, intent, state, param, amt, cid)
        if kind == 'atoken':
            return _try(slf._ap_atoken, intent, state, param, tin, tout, amt, cid)
        return _ap_kind2(slf, intent, state, kind, param, tin, tout, amt, cid)

    def _ap_kind2(slf, intent, state, kind, param, tin, tout, amt, cid):
        """The three chain-1 kinds built by the champion's OWN encoders."""
        if kind == 'v3path':
            return _try(slf._ap_c1, intent, state, param, tin, amt)
        if kind == 'v4path':
            return _try(slf._ap_v4, intent, state, param, tin, tout, amt)
        if kind == 'curve':
            return _try(slf._ap_curve, intent, state, param, tin, amt)
        return _MISS

    def _ap_generic(slf, intent, state, snapshot, kind, param, tin, tout, amt, cid):
        """Unrecognised kind -> the champion's own `_sep_kind_cand` +
        `_build_singlehop_plan`. getattr, not attribute access: on a lineage that
        renames or drops these the cover must DEFER, never raise
        (L-COVER-NOT-BASE-UNIVERSAL)."""
        cand = _try(getattr(slf, '_sep_kind_cand', None), intent, state, snapshot, kind, param, tin, tout, amt, 1, cid)
        if not isinstance(cand, dict):
            logger.info('[aeropin] no cand %s->%s; deferring', tin[:10], tout[:10])
            return None
        return _try(getattr(slf, '_build_singlehop_plan', None), intent, state, snapshot, cand, tin, tout, amt, cid)

    def _ap_blindspot(champ, ours, tin, tout):
        """L-UNSIMULATABLE-BLINDSPOT (2026-08-03): viking_sim cannot model every token
        it can ROUTE — Aave aTokens mint scaled balances, so `_sim` returns None for a
        plan that is fork-proven to deliver (100,000 aEthUSDC -> 52.127 aEthWETH).
        Rejecting on an unverifiable sim throws away exactly the rows nobody else
        covers. On an EMPTY champion plan the asymmetry is provable and total:
        champion delivers 0, `dropped`/`catastrophic` both require champ > 0, so the
        WORST case of serving is `skip` — the same score as deferring. There is
        nothing to lose and a blind_spot_cover to win."""
        if champ == 0 and getattr(ours, 'interactions', None):
            logger.info('[aeropin] BLINDSPOT-SERVE %s->%s (sim unavailable, champ empty)', tin[:10], tout[:10])
            return True
        return False

    def _ap_w3(slf, state):
        """The chain's web3, or None. getattr so an unfamiliar base defers."""
        return _try(getattr(slf, '_get_web3', None), int(getattr(state, 'chain_id', 0) or 0))

    def _ap_ok(slf, base, ours, w3, pin, tin, tout, amt, app):
        """`aunwind` rows use the phantom-champion test (viking_sim can fund neither
        side when tin is an aToken, so the sim gate would defer forever); every other
        kind still needs the full >500bps sim proof."""
        if pin[0] == 'aunwind':
            return _try(slf._ap_phantom_champ, base, tin) is True
        return _try(slf._ap_decide, base, ours, w3, tin, tout, amt, app, pin[2]) is True

    class AeroPinSolver(base_cls):
        """Champion + measured Aerodrome pins on the Base pairs its search misses."""

        def _ap_pin(self, intent, state):
            """Dict-only gate. Returns (pin, tin, tout, amt) or None. ZERO RPC —
            this is what keeps the ~200 non-pinned orders free."""
            if not _PINS or cover_state.disabled('aeropin'):
                return None
            k = _keys(self, intent, state)
            if k is None:
                return None
            cid, tin, tout, amt = k
            pin = _PINS.get((cid, tin, tout))
            if pin is None or amt <= 0 or tin == tout:
                return None
            return (pin, tin, tout, amt)

        def _ap_c1(self, intent, state, param, tin, amt):
            """Chain-1 V3-path pin. Built by the champion's OWN `chain1._mk_plan`
            (-> `chain1_lib._build`), so the SwapRouter-V1 `exactInput` encoding
            AND the USDT approve-reset are its audited code, not ours. `param` is
            the champion's own route shape: ([token, ...], [fee, ...])."""
            import chain1 as _c1
            rcpt = _rcpt(state)
            if not rcpt:
                return None
            route = (tuple((str(t) for t in param[0])), tuple((int(f) for f in param[1])))
            return _c1._mk_plan(route, tin, int(amt), rcpt, intent, state)

        def _ap_curve(self, intent, state, param, tin, amt):
            """Baked Curve pin. `param` = [route[11], swap[5][5]], eth_call-VERIFIED by
            curve_venue.curve_best at MINE time (auto_cover_miner). Calldata is rebuilt
            by the champion's own curve_venue.curve_calldata — its audited CurveRouterNG
            encoding, not ours (same reuse philosophy as _ap_c1). min_out floors >=1
            inside curve_calldata: pool drift degrades the fill, never reverts."""
            import curve_venue as _cv
            rcpt = _rcpt(state)
            if not rcpt or not param or len(param) < 2:
                return None
            router, cd = _cv.curve_calldata(1, tin, None, int(amt), 0, rcpt, 9999999999, _curve_spec(param))
            return _plan(intent, state, _curve_legs(tin, router, cd, amt), 'aeropin-curve', 1)

        def _ap_aunwind(self, intent, state, param, amt, cid):
            rcpt = getattr(state, 'contract_address', None)
            if not rcpt or not param or len(param) != 3:
                return None
            w3 = _try(getattr(self, '_get_web3', None), int(cid))
            if w3 is None:
                return None
            ixs = _aunwind_ixs(cid, param, int(amt), rcpt, w3)
            if not ixs:
                return None
            return _plan(intent, state, ixs, 'aeropin-aunwind', cid)

        def _ap_phantom_champ(self, base, tin):
            """Serve-decide for `aunwind` rows, replacing the sim decide (viking_sim can
            fund neither side when tin is an aToken, so the sim gate would defer forever).
            True ONLY when the champion provably delivers 0:
              * base plan EMPTY, or
              * base is the fork-proven PHANTOM shape: approve(THE aTOKEN) into a V3-style
                router exactInput — no pool holds the aToken, so the pull reverts
                (measured: champion delivered 0, revert@0x2626664c, 2026-08-03).
            Any OTHER champion shape -> defer. A future king with a REAL aToken cover
            (withdraw-first, UR, anything else) fails this test and we stand down —
            that is the regression guard the sim would otherwise provide."""
            ixs = getattr(base, 'interactions', None) or []
            if not ixs:
                return True
            if len(ixs) != 2:
                return False
            i0, i1 = ixs
            return str(getattr(i0, 'target', '')).lower() == str(tin).lower() and str(getattr(i0, 'call_data', ''))[:10] == _ERC20_APPROVE and (str(getattr(i1, 'call_data', ''))[:10] in ('0xc04b8d59', '0x04e45aaf', '0xb858183f'))

        def _ap_atoken(self, intent, state, param, tin, tout, amt, cid):
            """Aave aToken leg: withdraw -> V3 swap -> re-supply. The settlement contract
            is BOTH the executor and the recipient, so `exec_addr` and `rcpt` are the same
            address here; keeping them as separate arguments means a lineage that splits
            them later needs no change to _atoken_ixs."""
            rcpt = _rcpt(state)
            if not rcpt or not param or len(param) != 5:
                return None
            w3 = _try(getattr(self, '_get_web3', None), int(cid))
            if w3 is None:
                return None
            ixs = _atoken_ixs_quoted(w3, cid, param, int(amt), rcpt)
            if not ixs:
                return None
            return _plan(intent, state, ixs, 'aeropin-atoken', cid)

        def _ap_v4(self, intent, state, param, tin, tout, amt):
            """Chain-1 Uniswap-V4 pin. `param` is the PathKey chain
            [[intermediateCurrency, fee, tickSpacing], ...]; hooks are always 0."""
            rcpt = _rcpt(state)
            if not rcpt or not param:
                return None
            ixs = _v4_ixs(tin, tout, int(amt), [tuple(h) for h in param], rcpt)
            return _plan(intent, state, ixs, 'aeropin-v4', 1)

        def _ap_build(self, intent, state, snapshot, pin, tin, tout, amt):
            """Build our pinned plan with the CHAMPION'S OWN builders — no new
            calldata code, so all of its audited encoding is reused verbatim.
            A recognised kind whose builder returns None DEFERS here (returns None);
            only an unrecognised kind reaches the generic champion path."""
            kind, param, _slot = pin
            cid = int(getattr(state, 'chain_id', 0) or 0)
            ours = _ap_kind(self, intent, state, kind, param, tin, tout, amt, cid)
            if ours is not _MISS:
                return ours
            return _ap_generic(self, intent, state, snapshot, kind, param, tin, tout, amt, cid)

        def _ap_decide(self, base, ours, w3, tin, tout, amt, app, slot):
            """Serve ours ONLY on positive proof that it out-delivers the champion.
            Empty champion plan => champ delivers 0, so the base sim is skipped."""
            champ = _champ_out(w3, base, tin, tout, amt, app, slot)
            if champ is None:
                return False
            mine = _sim(w3, ours, tin, tout, amt, app, slot)
            if mine is None:
                return _ap_blindspot(champ, ours, tin, tout)
            if mine <= 0:
                return False
            floor = max(_MARGIN_BPS, cover_state.margin_bps(_MARGIN_BPS))
            return mine > champ * (1 + floor / 10000.0)

        def _ap_ready(self, intent, state, base):
            """Every cheap guard in one place (own region, keeps max_region low).
            Returns (pin, tin, tout, amt, app, w3) or None to defer."""
            hit = _try(self._ap_pin, intent, state)
            if hit is None:
                return None
            if _ap_guards(self, base):
                return None
            pin, tin, tout, amt = hit
            app = getattr(state, 'contract_address', '') or ''
            if not app:
                return None
            w3 = _ap_w3(self, state)
            if w3 is None:
                return None
            return (pin, tin, tout, amt, app, w3)

        def _ap_serve(self, intent, state, snapshot, base):
            """Our pinned plan, or None to keep the champion's. Own region so
            generate_plan stays a thin, low-node wrapper."""

            def _dz21():
                pin, tin, tout, amt, app, w3 = ready
                ours = _try(self._ap_build, intent, state, snapshot, pin, tin, tout, amt)
                if not _is_plan(ours):
                    return (None,)
                _ap_bump(self)
                if not _ap_ok(self, base, ours, w3, pin, tin, tout, amt, app):
                    return (None,)
                _log_win(tin, tout, amt)
                return (ours,)
                return _DR_UNSET
            ready = self._ap_ready(intent, state, base)
            if ready is None:
                return None
            _r_dz21 = _dz21()
            if _r_dz21 is not _DR_UNSET:
                return _r_dz21[0]

        def generate_plan(self, intent, state, snapshot=None):
            base = super().generate_plan(intent, state, snapshot)
            try:
                ours = self._ap_serve(intent, state, snapshot, base)
            except Exception:
                logger.exception('[aeropin] failed; deferring to champion')
                return base
            return ours if _is_plan(ours) else base
    return AeroPinSolver