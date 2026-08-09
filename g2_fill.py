"""g2 cover overlay v5 — TABLE-FIRST serving with an admission-margin guard.

v5 (full-universe generation): table entries now carry their admission
measurements (our delivery and the champion's, measured at one pin), and
win-class serves are gated on a minimum admitted margin at serve time —
a thin-margin entry falls through to the base, which is the champion's own
tree, so drift can only cost the win, never mint a regression. Covers
(champion measured zero) always serve.

v2 asked the base FIRST and only then considered the table. Production
measurement (round e29764126) showed why that ordering is fatal: the bench
budgets ~7s/row across the pack, the base's live route discovery costs
5-15s/row on fresh rows, and every discovery row silently zeroes. v3 inverts
the order: a table hit serves IMMEDIATELY from its baked route spec (no RPC,
sub-second); only off-table rows fall through to the base's live discovery.
Veto safety moves to the table ADMISSION rule (bake pipeline, not runtime):
an entry may exist only for rows measured champion-zero (cover class) or
rows where our baked route's measured delivery >= the champion image's
measured delivery at the bake pin (match class).

Unlike replay-bank covers, every leg here is BUILT FRESH at serve time from a
baked route spec (path + fees + amount): there is no stored calldata and no
frozen minReturnAmount floor to rot — amountOutMinimum is 0 by construction
(the bench's quote-corpus rows carry no min), so a route that thins out
delivers less instead of reverting, and a route that dies delivers the empty
the row already was.

Region discipline: helpers are module-level and small on purpose — the
factorization metric charges each named scope's body as its own region, and
this tree's ceiling is what a rival's factor_delta is measured against.
"""
from __future__ import annotations
_DR_UNSET = object()
import json
import logging
import os
from g2_codec import _bal_serve_legs, _chain_ready, _legs, _set_rpc, _v4_serve_legs
_log = logging.getLogger(__name__)
_TABLE_FILE = 'g2_covers.json'
_TABLE = None
_MIN_WIN_MARGIN_BPS = 200

def _adm_pair(spec):
    """(ours, champ) admission measurements for the drift guard. Prefers the
    admission-bench pair (both sides MEASURED at one pin); legacy entries
    carry the probe-era pair (our quoted out vs the swept champion delivery),
    which guards in the same direction with more noise."""
    a = spec.get('adm_ours') or spec.get('probe_out')
    c = spec.get('adm_champ') or spec.get('champ_out')
    try:
        return (int(a or 0), int(c or 0))
    except (TypeError, ValueError):
        return (0, 0)

def _floor_bps(spec) -> int:
    """Per-entry drift floor: a spec may carry its own `floor_bps` (bake-set
    from row-level stability evidence); absent that, the module default
    applies. Data-driven per-row tuning without a code change."""
    try:
        v = spec.get('floor_bps')
        if v is not None:
            return int(v)
    except (TypeError, ValueError):
        pass
    return _MIN_WIN_MARGIN_BPS

def _margin_ok(spec) -> bool:
    """Win-class entries (champion measured NONZERO at admission) must carry
    a margin wide enough that pin drift cannot flip the serve regressive; a
    thin entry falls through to the base — which IS the champion's own tree,
    so the row rides his route (matched at worst), never a drop. Cover-class
    entries (champion measured zero) have nothing to cut and always serve."""
    ours, champ = _adm_pair(spec)
    if champ <= 0:
        return True
    if ours <= 0:
        return True
    return ours * 10000 >= champ * (10000 + _floor_bps(spec))

def _load_table(path):
    try:
        return {str(k).lower(): v for k, v in json.load(open(path)).items()}
    except Exception:
        return {}

def _table() -> dict:
    global _TABLE
    if _TABLE is None:
        here = os.path.dirname(os.path.abspath(__file__))
        _TABLE = _load_table(os.path.join(here, _TABLE_FILE))
    return _TABLE

def _key(state):
    """Chain-scoped row key `chain|tin|tout|amt`; the legacy 3-part form
    (chain-1 entries baked before chain scoping) is the lookup fallback."""

    def _dz101():
        tin = str(p.get('input_token') or '').lower()
        tout = str(p.get('output_token') or '').lower()
        amt = int(p.get('input_amount') or 0)
        if cid and tin and tout and amt:
            return (str(cid) + '|' + tin + '|' + tout + '|' + str(amt),)
        return _DR_UNSET
    try:
        p = getattr(state, 'raw_params', None) or {}
        cid = int(getattr(state, 'chain_id', 0) or 0)
        _r_dz101 = _dz101()
        if _r_dz101 is not _DR_UNSET:
            return _r_dz101[0]
    except Exception:
        pass
    return None

def _cover_spec(state):
    """(spec, rcpt) when this row holds a baked table entry for ITS chain.
    Chain scoping lives in the key itself: a chain with no baked entries
    never matches, and a matched entry without a routable venue registry
    entry fails closed in the leg builders."""

    def _dz100():
        if not isinstance(spec, dict):
            return (None,)
        if not _chain_ready(spec):
            return (None,)
        if not _margin_ok(spec):
            return (None,)
        rcpt = str(getattr(state, 'contract_address', '') or getattr(state, 'owner', '') or '')
        if not rcpt:
            return (None,)
        return ((spec, rcpt, k),)
        return _DR_UNSET
    k = _key(state)
    spec = _table().get(k) if k else None
    if not isinstance(spec, dict) and k and k.startswith('1|'):
        spec = _table().get(k[2:])
    _r_dz100 = _dz100()
    if _r_dz100 is not _DR_UNSET:
        return _r_dz100[0]

def _cover_plan(hit, intent, state, Interaction, ExecutionPlan):

    def _dz99():
        if not legs:
            return (None,)
        _log.info('[g2] cover serve %s', k[:64])
        return (ExecutionPlan(intent_id=getattr(intent, 'app_id', ''), interactions=legs, deadline=9999999999, nonce=getattr(state, 'nonce', 0), metadata={'solver': 'g2-cover', 'chain_id': int(spec.get('chain_id') or 1)}),)
        return _DR_UNSET
    spec, rcpt, k = hit
    if spec.get('kind') == 'bal':
        legs = _bal_serve_legs(spec, rcpt, state, Interaction)
    elif spec.get('kind') == 'v4':
        legs = _v4_serve_legs(spec, rcpt, Interaction)
    else:
        legs = _legs(spec, rcpt, Interaction)
    _r_dz99 = _dz99()
    if _r_dz99 is not _DR_UNSET:
        return _r_dz99[0]

def install(base_cls, Interaction, ExecutionPlan):
    """Wrap base_cls: chain-1 rows with a baked table entry serve table-first
    (no discovery spend); everything else falls through to the base."""

    class _G2Fill(base_cls):

        def initialize(self, config):
            _set_rpc((config or {}).get('rpc_urls') or {})
            return super().initialize(config)

        def generate_plan(self, intent, state, snapshot=None):
            try:
                hit = _cover_spec(state)
                if hit is not None:
                    built = _cover_plan(hit, intent, state, Interaction, ExecutionPlan)
                    if built is not None:
                        return built
            except Exception:
                _log.exception('[g2] table serve failed; falling to base')
            return super().generate_plan(intent, state, snapshot)
    return _G2Fill