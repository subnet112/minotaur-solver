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

THAT PARAGRAPH IS FALSE FOR ANY ROUTE THAT ENDS IN A TRANSFER, and the false
half is what v6 below closes. `g2_codec._final_transfer` appends a leg moving
`spec['out'] * transfer_bps // 10000` (default 9500) — a FROZEN amount taken
from the bake, not the executor's realised balance. So a curve/v2-final route
does carry a floor that rots, in both directions:

  realised < baked*0.95   the transfer reverts, the row delivers NOTHING
  realised > baked*0.95   we ship 95% of what we hold and bin the rest

MEASURED, round-e29787312-n1 / sub_80abe187e984 (commit ef7e599), the first
scored round after 160d98b made this layer live — 160d98b bound `_keccak`/
`_enc`/`_ck` in `g2_codec._v3_swap_cd`, which until then raised NameError on
every chain-1 v3 row, so `_legs` always threw and the overlay always fell to
the base. Fixing the NameError did not change routing; it switched this whole
table on for the first time:

  3 dropped  q_6f0816a4cf29d43f31d1430524303347 (USDT->USDC, champ 480839489)
             q_e26967cc89c91d9e621203d6105db5bb, q_fa02680000b6ca0bf1f248291fe1a794
  1 cut >1%  q_1cd2d633eabf1cfb95c9489b424759a6 ratio 0.950101 — 9500 bps to
             four decimal places, i.e. the frozen transfer, not a routing loss
  5 worse    the same shape, under the 1% floor

  verdict "regressed", reason "reject: 1 order(s) cut >1% (hard floor)".

bin/self-regression-check A/Bs those same rows against 89a11b6 (the tree behind
sub_78abfab90894: 0 dropped, 0 worse, 2 better) and reads the shape directly —
USDT->USDC ours 3 legs vs 2, and 5000 FXS->wstETH ours 4 legs vs 2. Three legs
is approve + swap + `_final_transfer`; four is the two-hop form. Every one of
those rows is an order the CHAMPION SERVES, which is the shape every hard veto
in this lineage has come from.

v6 — FILL-ONLY-EMPTY FOR WIN-CLASS ROWS. Table-first is kept exactly where it
was justified: a cover-class entry is one the champion measured ZERO on at
admission, so it has no delivery to cut and no round to lose, and it keeps the
sub-second no-discovery serve that v3 was inverted for. A win-class entry —
champion measured NONZERO, i.e. he serves this row — now asks the base FIRST
and only serves the table if the base comes back empty. `_margin_ok` stays, but
it cannot be the whole guard: it compares two numbers frozen at the BAKE pin,
and the round runs at a different block, so it is blind to exactly the drift
that produced the three drops. The base plan is the champion's own route; a row
that rides it is matched at worst.

This is not a pace regression. Before 160d98b every chain-1 v3 row already paid
the base's discovery (the NameError threw and the `except` called it), so
win-class v3 rows return to the cost profile 89a11b6 completed inside — minus
the leg-build that used to be thrown away. The wins are untouched: this tree's
scored `better` rows are all blind_spot_cover on `champ: null`, which is the
cover class, which still serves first.

v7 — A MISSING MEASUREMENT IS NOT A ZERO, and the v6 block above misreads its
own evidence. `_final_transfer` is reachable ONLY from `_route_legs`, which
`_legs` calls only when `venue == 'route'`. Both rows v6 blamed it for are
`venue: "v3"`, so neither has ever built a transfer leg:

  q_1cd2d633eabf1cfb95c9489b424759a6  the >1% cut — venue v3, fees [100],
    17326125737 USDT -> DAI, quote_pin 17316836659331400079151. A single
    0.01%-tier pool with amountOutMinimum 0, paying rcpt directly. It delivered
    16448368852203603189356 against the champion's 17312232856335968615917:
    that is the ONE POOL being 5% thinner at the round block than at the bake
    pin. 0.950101 next to a 9500bps default is a coincidence, and v6 read the
    coincidence as the mechanism.
  q_6f0816a4cf29d43f31d1430524303347  a drop — venue v3 as well, USDT -> USDC.

What both rows DO share is the real defect. Neither carries `adm_champ`,
`adm_ours`, `probe_out` or `champ_out` — they are `class: provisional` bakes,
keyed off a `quote_pin` alone, with no champion reading of any kind. `_adm_pair`
returns 0 for an absent key exactly as it does for a measured zero, so v6's
`champ <= 0` test put every unmeasured row in the COVER class and served it
table-first. 219 of the 1885 baked rows carry no champion reading; the table was
overriding the base on all of them, on the strength of a measurement nobody
took.

`_cover_class` now requires the KEY to be PRESENT before it will read a zero as
blindness, and `_champ_adm` parses the champion side alone so an unparseable
`adm_ours` can no longer zero it by association. Unmeasured rows route
win-class: base first, table only where the base comes back empty. This does
not touch the proven blind spots — a bake that benched the champion and got
nothing WROTE the key ("None"/0), so it still serves first, and those are the
`champ: null` rows every scored `better` in this tree has come from.

The direction of the error matters more than its size. Serving the table over a
route the champion serves is a drop or a cut, and both are hard vetoes that
sink the whole submission; riding his own route on a row we could have covered
costs at most one `+1` we were never sure of.

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

def _champ_adm(spec):
    """(measured, value) for the CHAMPION side of the admission bench.

    `measured` is whether the bake carries a champion reading at all. The key
    being PRESENT is the evidence, whatever it holds: a bench that came back
    empty writes `"None"`/`0`, and that is a measurement OF A BLIND CHAMPION.
    An absent key means nobody ever looked at him on this row.

    Parsed on its own rather than through `_adm_pair`, which zeroes BOTH sides
    when EITHER fails to parse — so a row carrying a real `adm_champ` beside an
    unparseable `adm_ours` used to read as "champion delivered zero" and hand a
    row he serves to the table-first path."""
    for k in ('adm_champ', 'champ_out'):
        if k in spec:
            try:
                return (True, int(spec.get(k) or 0))
            except (TypeError, ValueError):
                return (True, 0)
    return (False, 0)

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

    def _dz76():
        tin = str(p.get('input_token') or '').lower()
        tout = str(p.get('output_token') or '').lower()
        amt = int(p.get('input_amount') or 0)
        if cid and tin and tout and amt:
            return (str(cid) + '|' + tin + '|' + tout + '|' + str(amt),)
        return _DR_UNSET
    try:
        p = getattr(state, 'raw_params', None) or {}
        cid = int(getattr(state, 'chain_id', 0) or 0)
        _r_dz76 = _dz76()
        if _r_dz76 is not _DR_UNSET:
            return _r_dz76[0]
    except Exception:
        pass
    return None

def _cover_spec(state):
    """(spec, rcpt) when this row holds a baked table entry for ITS chain.
    Chain scoping lives in the key itself: a chain with no baked entries
    never matches, and a matched entry without a routable venue registry
    entry fails closed in the leg builders."""

    def _dz75():
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
    _r_dz75 = _dz75()
    if _r_dz75 is not _DR_UNSET:
        return _r_dz75[0]

def _cover_class(spec) -> bool:
    """True only where the bake MEASURED the champion at zero on this row.

    v6 split the table on `champ <= 0` read through `_adm_pair`, which returns
    0 for a row that carries no champion reading at all — so "nobody measured
    him" and "he delivered nothing" were the same answer, and every unmeasured
    row was served table-first on the strength of a measurement that does not
    exist. 219 of the 1885 baked rows carry none.

    An absent reading is not evidence the champion is blind; it is the absence
    of evidence, and it now routes win-class: ask the base first, fill only
    where the base comes back empty. That is safe in the direction that costs
    rounds — the base IS the champion's tree, so a row riding it is matched at
    worst, whereas serving the table over a route he does serve is a drop or a
    cut, and both are hard vetoes. The proven blind spots are untouched: a bake
    that benched him and got nothing wrote the key, so it still serves first."""
    measured, champ = _champ_adm(spec)
    return measured and champ <= 0

def _served(plan) -> bool:
    """Structurally non-empty: the base delivered a route for this row."""
    try:
        return plan is not None and bool(getattr(plan, 'interactions', None))
    except Exception:
        return plan is not None

def _try_cover(hit, intent, state, Interaction, ExecutionPlan):
    """`_cover_plan` with the leg-build failure contained. A raise here means
    the baked spec cannot be assembled at all, so the caller drops the hit
    rather than re-attempting it on the second pass."""
    try:
        return _cover_plan(hit, intent, state, Interaction, ExecutionPlan)
    except Exception:
        _log.exception('[g2] table serve failed; falling to base')
        return None

def _cover_hit(state):
    """`_cover_spec` with lookup failure contained; None when this row has no
    usable baked entry."""
    try:
        return _cover_spec(state)
    except Exception:
        _log.exception('[g2] table lookup failed; falling to base')
        return None

def _cover_plan(hit, intent, state, Interaction, ExecutionPlan):

    def _dz74():
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
    _r_dz74 = _dz74()
    if _r_dz74 is not _DR_UNSET:
        return _r_dz74[0]

def install(base_cls, Interaction, ExecutionPlan):
    """Wrap base_cls: a COVER-class baked entry (champion measured zero) serves
    table-first with no discovery spend; a WIN-class entry asks the base first
    and only fills where the base comes back empty; everything off-table falls
    through to the base untouched. See the v6 block in the module docstring for
    the round that separated the two classes."""

    class _G2Fill(base_cls):

        def initialize(self, config):
            _set_rpc((config or {}).get('rpc_urls') or {})
            return super().initialize(config)

        def generate_plan(self, intent, state, snapshot=None):

            def _dz51():
                nonlocal built, hit
                if hit is not None and _cover_class(hit[0]):
                    built = _try_cover(hit, intent, state, Interaction, ExecutionPlan)
                    if built is not None:
                        return (built,)
                    hit = None
                return _DR_UNSET
            hit = _cover_hit(state)
            _r_dz51 = _dz51()
            if _r_dz51 is not _DR_UNSET:
                return _r_dz51[0]
            base = super().generate_plan(intent, state, snapshot)
            if _served(base):
                return base
            if hit is not None:
                built = _try_cover(hit, intent, state, Interaction, ExecutionPlan)
                if built is not None:
                    return built
            return base
    return _G2Fill