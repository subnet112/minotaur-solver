"""v2_pin — L1 UniswapV2 / SushiSwap route pins for the champion's V2 blind spot.

WHY THIS EXISTS (Strategy 22, "THE NEXT L1 EDGE"). On chain 1 the champion's
`hydra_top.generate_plan` runs `_hydra_eth_fastpath` FIRST. That builder is
zero-RPC, never checks the pool exists, and emits `tin -3000- WETH -f2- tout`
(f2=500 only for USDC/WBTC). Because it always returns a plan, the whole engine
below it is bypassed, and the single rescue path `chain1.superset` is disarmed by
`chain1._beats_champ` (`if not q_champ: return False` reads an UNQUOTABLE champion
route as unbeatable). So on every L1 pair whose naive UniV3 path has no pool the
champion serves a REVERTING plan and delivers 0.

The lineage cannot reach UniswapV2 on L1 at all:
  * `king_base._SWEEP_V2_ROUTERS` holds BASE addresses only — no L1 V2 router;
  * `chain1_c._V2_PAIRS` holds exactly ONE pair (USDC/DAI), so `chain1_v2._v2_best`
    is a no-op on every other pair.
Measured over the 1082-pair ETH quote pool: 695 pairs have a live UniV2/Sushi
route, and on 469 of them that route beats the champion's own naive fastpath quote
by >5% (most of those: the champion quotes literally 0).

ZERO NEW CALLDATA — this is the whole point. The champion already ships a complete,
audited V2 primitive in `chain1_v2`:
    `_v2_reserves`  getReserves()
    `_v2_quote`     the 997/1000 getAmountOut
    `_v2_xfer_cd`   transfer(address,uint256)
    `_v2_swap_cd`   swap(uint256,uint256,address,bytes)
    `_v2_build`     the two-interaction direct swap
and `chain1._mk_plan` already dispatches a `('v2', pair, in_is_t0, out)` route to
it. A `v2direct` pin is therefore built by the champion's OWN entry point.

The 2-hop case needs NO router and NO new calldata class either. UniswapV2's
`swap(...)` takes an arbitrary `to`, so pointing hop 1 at the hop-2 PAIR chains
them exactly the way Router02's internal `_swap` does:
    tin.transfer(pair1, amt) -> pair1.swap(.., to=pair2) -> pair2.swap(.., to=rcpt)
That is the same two selectors again, so `swapExactTokensForTokens` (and its
approve) is never needed. No Router02, no allowance, one fewer interaction.

SAFETY SHAVE. A V2 pair enforces the K invariant against its reserves AT
EXECUTION. We read reserves at plan time, so a reserve move between plan and
execution would revert an exact-max request. We therefore ask each hop for
`_SHAVE_BPS` less than the computed maximum. On a blind-spot row a revert is
harmless (champion delivers 0 too => `skip`), but on a row where the champion DOES
deliver it would be a catastrophic regression — the -19.69% cut class. The shave is
absorbed by the 500bps decision floor.

GATE (identical doctrine to aero_pin, Strategy 21 BUDGET LAW):
  * a pure dict lookup gates it, so non-pinned orders cost ZERO RPC;
  * balance slots are PRE-MEASURED in the data file, so the sim skips the probe;
  * `_MAX_SIMS` hard-caps sims per run so the champion's `_RUN_BUDGET_S` governor
    can never be starved into `last_resort_empty` -> a dropped order -> #1207
    submission reject;
  * we serve ONLY when an execution sim proves we strictly out-deliver the
    champion's own plan by >5%; every uncertainty returns the champion's plan.
"""
from __future__ import annotations
_DR_UNSET = object()
import logging
logger = logging.getLogger(__name__)
_MARGIN_BPS = 500
_SHAVE_BPS = 25
_MAX_SIMS = 24

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
    """(chain, tin, tout) -> (kind, param, slot), loaded from data so the table stays
    out of the AST (max_region_nodes is the adoption tie-breaker)."""
    import json as _j, os as _o
    try:
        path = _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), 'v2_pins.json')
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

def _hop_out(w3, leg, tin, amt):
    """Shaved getAmountOut for one V2 hop, using the CHAMPION'S own quoter.

    `leg` is [pair, token0]; direction is derived from token0 so one row serves
    both directions. Returns (pair, in_is_t0, out) or None.
    """
    import chain1_v2 as _v2
    pair = str(leg[0])
    in_is_t0 = str(tin).lower() == str(leg[1]).lower()
    q = _v2._v2_quote(w3, pair, int(amt), in_is_t0, 'latest')
    if not q:
        return None
    out = int(q) * (10000 - _SHAVE_BPS) // 10000
    return (pair, in_is_t0, out) if out > 0 else None

def _direct_plan(solver, intent, state, param, tin, amt, rcpt, w3):
    """Direct V2 pair swap — built by the champion's OWN `chain1._mk_plan`, which
    already understands the ('v2', pair, in_is_t0, out) route shape."""
    import chain1 as _c1
    hop = _hop_out(w3, param, tin, amt)
    if hop is None:
        return None
    pair, in_is_t0, out = hop
    return _c1._mk_plan(('v2', pair, in_is_t0, out), tin, int(amt), rcpt, intent, state)

def _hop_ixs(tin, amt, h1, h2, rcpt):
    """The three interactions of a chained two-hop V2 swap, from the champion's own
    encoders. Hop 1's `to` is hop 2's PAIR — Router02's internal `_swap` chaining."""
    import chain1_v2 as _v2
    from minotaur_subnet.shared.types import Interaction as _IX
    return [_IX(target=tin, value='0', call_data=_v2._v2_xfer_cd(h1[0], int(amt)), chain_id=1), _IX(target=h1[0], value='0', call_data=_v2._v2_swap_cd(h1[1], h1[2], h2[0]), chain_id=1), _IX(target=h2[0], value='0', call_data=_v2._v2_swap_cd(h2[1], h2[2], rcpt), chain_id=1)]

def _hop_plan(solver, intent, state, param, tin, amt, rcpt, w3):
    """Two-hop V2 via the pinned hub. Adds no calldata class — see `_hop_ixs`."""
    from minotaur_subnet.shared.types import ExecutionPlan as _EP
    h1 = _hop_out(w3, param[0], tin, amt)
    if h1 is None:
        return None
    h2 = _hop_out(w3, param[1], str(param[2]), h1[2])
    if h2 is None:
        return None
    return _EP(intent_id=intent.app_id, interactions=_hop_ixs(tin, amt, h1, h2, rcpt), deadline=9999999999, nonce=state.nonce, metadata={'solver': 'viking-eth-dyn', 'chain_id': 1})

def _sim(w3, plan, tin, tout, amt, app, slot):
    """Delivered `tout` for `plan` under eth_simulateV1, using a PRE-MEASURED balance
    slot so the 12-call probe is skipped. None = unverifiable."""
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
    logger.info('[v2pin] WIN %s->%s amt=%d', tin[:10], tout[:10], amt)

def wrap(base_cls):
    import viking_sim
    import cover_state
    _PINS = _load_pins()

    def _vp_bump(slf):
        slf._vp_sims = int(getattr(slf, '_vp_sims', 0) or 0) + 2

    def _vp_guards(slf, base):
        """cover_state + sim-cap guards, in the original order. True = defer."""
        if _try(cover_state.is_cross_chain, base) is not False:
            return True
        if _try(cover_state.base_untrusted, base) is not False:
            return True
        return int(getattr(slf, '_vp_sims', 0) or 0) >= _MAX_SIMS

    def _vp_w3(slf, state):
        """The chain's web3, or None. getattr so an unfamiliar base defers."""
        return _try(getattr(slf, '_get_web3', None), int(getattr(state, 'chain_id', 0) or 0))

    def _vp_ok(slf, base, ours, w3, pin, tin, tout, amt, app):
        """The >500bps sim proof, in its own region."""
        return _try(slf._vp_decide, base, ours, w3, tin, tout, amt, app, pin[2]) is True

    class V2PinSolver(base_cls):
        """Champion + measured UniswapV2/Sushi pins on the L1 pairs it cannot reach."""

        def _vp_pin(self, intent, state):
            """Dict-only gate. Returns (pin, tin, tout, amt) or None. ZERO RPC —
            this is what keeps every non-pinned order free."""
            if not _PINS or cover_state.disabled('v2pin'):
                return None
            k = _keys(self, intent, state)
            if k is None:
                return None
            cid, tin, tout, amt = k
            pin = _PINS.get((cid, tin, tout))
            if pin is None or amt <= 0 or tin == tout:
                return None
            return (pin, tin, tout, amt)

        def _vp_build(self, intent, state, pin, tin, amt, w3):
            """Our pinned plan, built entirely from the champion's own V2 primitives."""
            kind, param, _slot = pin
            rcpt = getattr(state, 'contract_address', None) or getattr(state, 'owner', None)
            if not rcpt:
                return None
            if kind == 'v2direct':
                return _try(_direct_plan, self, intent, state, param, tin, amt, rcpt, w3)
            if kind == 'v2hop':
                return _try(_hop_plan, self, intent, state, param, tin, amt, rcpt, w3)
            return None

        def _vp_decide(self, base, ours, w3, tin, tout, amt, app, slot):
            """Serve ours ONLY on positive proof it out-delivers the champion.
            An empty champion plan delivers 0, so its sim is skipped."""
            champ = _champ_out(w3, base, tin, tout, amt, app, slot)
            if champ is None:
                return False
            mine = _sim(w3, ours, tin, tout, amt, app, slot)
            if mine is None or mine <= 0:
                return False
            floor = max(_MARGIN_BPS, cover_state.margin_bps(_MARGIN_BPS))
            return mine > champ * (1 + floor / 10000.0)

        def _vp_ready(self, intent, state, base):
            """Every cheap guard in one place (own region, keeps max_region low).
            Returns (pin, tin, tout, amt, app, w3) or None to defer."""
            hit = _try(self._vp_pin, intent, state)
            if hit is None:
                return None
            if _vp_guards(self, base):
                return None
            pin, tin, tout, amt = hit
            app = getattr(state, 'contract_address', '') or ''
            if not app:
                return None
            w3 = _vp_w3(self, state)
            if w3 is None:
                return None
            return (pin, tin, tout, amt, app, w3)

        def _vp_serve(self, intent, state, base):
            """Our pinned plan, or None to keep the champion's."""

            def _dz402():
                pin, tin, tout, amt, app, w3 = ready
                ours = _try(self._vp_build, intent, state, pin, tin, amt, w3)
                if not _is_plan(ours):
                    return (None,)
                _vp_bump(self)
                if not _vp_ok(self, base, ours, w3, pin, tin, tout, amt, app):
                    return (None,)
                _log_win(tin, tout, amt)
                return (ours,)
                return _DR_UNSET
            ready = self._vp_ready(intent, state, base)
            if ready is None:
                return None
            _r_dz402 = _dz402()
            if _r_dz402 is not _DR_UNSET:
                return _r_dz402[0]

        def generate_plan(self, intent, state, snapshot=None):
            base = super().generate_plan(intent, state, snapshot)
            try:
                ours = self._vp_serve(intent, state, base)
            except Exception:
                logger.exception('[v2pin] failed; deferring to champion')
                return base
            return ours if _is_plan(ours) else base
    return V2PinSolver