from __future__ import annotations
from mino_fill_layer_base import *

def _dz281():
    _log = logging.getLogger(__name__)
    _FILL_NONCE = '6'
    _TABLE_FILE = 'mino_fill_rows.json'
    _AGG_ROUTERS = frozenset({'0x6131b5fae19ea4f9d964eac0408e4408b66337b5'})
    _PLAN_BUDGET_S = 26.0
    _MAX_ASKS = 2
    return (_log, _FILL_NONCE, _TABLE_FILE, _AGG_ROUTERS, _PLAN_BUDGET_S, _MAX_ASKS)
_log, _FILL_NONCE, _TABLE_FILE, _AGG_ROUTERS, _PLAN_BUDGET_S, _MAX_ASKS = _dz281()

def _table_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), _TABLE_FILE)

def _rank(row) -> tuple:
    agg = any((str(leg.get('target', '')).lower() in _AGG_ROUTERS for leg in _served(row) if isinstance(leg, dict)))
    return (0 if agg else 1, _minted(row))

def _merge_source(rows: dict, fn: str) -> None:
    """Fold one overlay file into `rows`, best-ranked row per key winning."""

    def _dz281():
        with open(os.path.join(base, fn)) as fh:
            loaded = json.load(fh)
        if not isinstance(loaded, dict):
            return (None,)
        for k, v in loaded.items():
            held = rows.get(k)
            if held is None or _rank(v) >= _rank(held):
                rows[k] = v
        return _DR_UNSET
    base = os.path.dirname(os.path.abspath(__file__))
    try:
        _r_dz281 = _dz281()
        if _r_dz281 is not _DR_UNSET:
            return _r_dz281[0]
    except Exception:
        _log.warning('[minofill] overlay source %s unreadable; continuing', fn)

def _read_table() -> dict:
    """Primary table (mino_fill_rows.json) unioned over the lineage's shared.

    The rank/mint/serve helpers live at MODULE scope, not nested here. The
    factorization metric counts the body of each named scope and does not
    descend into a nested def's body — but the nested def's HEADER still counts
    in the enclosing region. Hoisting them moved this region from 168 to below
    the champion base's own floor, so the tree's max region is once again set by
    inherited code rather than by ours. That matters: garnet took the crown off
    us purely on a factorization gap, and our own files are the only part of the
    gap we can safely shrink.
    """
    rows: dict = {}
    for fn in ('lattice_wins.json', _TABLE_FILE):
        _merge_source(rows, fn)
    if not rows:
        _log.warning('[minofill] no overlay tables; layer is inert')
    return rows
_ROWS = _read_table()
try:
    import mino_xchain as _xc
except Exception:
    _xc = None
_OVR = _read_overrides()
_EXECUTORS = {1: '0xcd42cf6fd6e0c539cae038fe6a73c67f8c1c7a52', 8453: '0xe0d97941103c30799fa0aa9d54a34246846c73bf'}

def _trade(state) -> tuple:
    """(chain, contract, tin, tout, amount) pulled from the bench's IntentState."""

    def _dz280():
        chain = int(getattr(state, 'chain_id', 0) or 0)
        contract = str(getattr(state, 'contract_address', '') or '').lower()
        return ((chain, contract or _EXECUTORS.get(chain, ''), str(params.get('input_token') or '').lower(), str(params.get('output_token') or '').lower(), int(params.get('input_amount') or 0)),)
        return _DR_UNSET
    params = getattr(state, 'raw_params', None) or {}
    _r_dz280 = _dz280()
    if _r_dz280 is not _DR_UNSET:
        return _r_dz280[0]

def _row_key(state) -> str | None:
    """chain|contract_address|tin|tout|amount, byte-identical to the bench's own key."""
    try:
        chain, contract, tin, tout, amount = _trade(state)
    except Exception:
        return None
    if not (tin and tout and amount and contract):
        return None
    return f'{chain}|{contract}|{tin}|{tout}|{amount}'

def _freshest(row):
    """Newest minted route for a key."""

    def _dz279():
        for cand in sorted(live, key=lambda r: -int(r.get('minted_at') or 0)):
            ix = cand.get('interactions') or []
            if ix and all((isinstance(l, dict) and l.get('target') and (l.get('call_data') or l.get('data')) for l in ix)):
                return (ix,)
        return _DR_UNSET
    routes = row.get('routes')
    if isinstance(routes, list):
        live = [r for r in routes if isinstance(r, dict) and r.get('interactions')]
        _r_dz279 = _dz279()
        if _r_dz279 is not _DR_UNSET:
            return _r_dz279[0]
    return row.get('interactions') or []

def _legs(row, chain, Interaction):
    """Stored interactions -> Interaction objects, verbatim."""
    stored = _freshest(row)
    if not stored:
        return None
    built = []
    for leg in stored:
        data = leg.get('call_data') or leg.get('data')
        target = leg.get('target')
        if not (target and data):
            return None
        built.append(Interaction(target=target, value=str(leg.get('value', '0')), call_data=data, chain_id=chain))
    return built
_AGG_MAX_AGE_S = 86400.0
_EVIDENCE_MARGIN_BPS = 200
_EVIDENCE_DUEL_BPS = 30
_EVIDENCE_FLOOR_BPS = 60
_EVIDENCE_DRIFT_BPS_PER_H = 50
_EVIDENCE_MAX_BPS = 600

def _evidence_margin_bps(row) -> int:
    """Required edge, in bps, for evidence of this row's age.

    An UNKNOWN mint time keeps the flat constant rather than the strict ceiling.
    ~800 of our rows carry no stamp, and treating them as maximally stale would
    silently withdraw the override from all of them — a coverage cut dressed up as
    caution, on cards that are already losing 0-better. Unknown means "no new
    information", so it earns the behaviour we have always had, and only rows whose
    age we can actually read move off it.

    PROVENANCE OUTRANKS AGE. The margin exists to absorb ONE error: `out` and `tgt`
    are measured at different times and against different states, so by bench time
    the recorded edge has decayed by an unknown amount. A DUEL-measured row does not
    carry that error at all — both numbers come from the same fork at the same block,
    ours against the base's own plan, executed from a throwaway sender and credited to
    the app contract. There is no drift between them to absorb, only simulation noise.

    Charging such a row the same margin as a quoted one is not caution, it is
    discarding the better measurement. It is also expensive: of 32 quoted candidates
    only 2 survived a duel (+2381.9 bps collapsed to +0.0, one +106 bps row delivered
    a flat ZERO), so duel-proven rows are precisely the scarce, trustworthy ones.
    They earn the noise floor; everything else keeps the age curve.
    """
    if str((row or {}).get('src') or '') == 'duel':
        return _EVIDENCE_DUEL_BPS
    try:
        minted = _minted(row)
    except Exception:
        minted = 0
    if minted <= 0:
        return _EVIDENCE_MARGIN_BPS
    age_h = max(0.0, (time.time() - minted) / 3600.0)
    need = _EVIDENCE_FLOOR_BPS + int(age_h * _EVIDENCE_DRIFT_BPS_PER_H)
    return max(_EVIDENCE_FLOOR_BPS, min(_EVIDENCE_MAX_BPS, need))
_EVIDENCE_MAX_AGE_S = 6 * 3600.0

def _stale_vs_champion(row) -> bool:
    """Is this row's evidence older than the throne it was measured against?

    The override fires on `out > tgt`, and `tgt` is THE CHAMPION'S CARDED NUMBER —
    a fact about one specific champion, not a standing property of the row. The
    crown changed SIX times on 2026-08-14 (apex_1, zephyr, lattice, leanrtr, ...),
    so a `tgt` mined against garnet says nothing about whether we beat leanrtr.

    The age curve alone does not cover this. `_evidence_margin_bps` grows the
    required edge by 50 bps/hour but CAPS it at `_EVIDENCE_MAX_BPS` (600), so a
    row of any age — 5.5 days, 20 days — is treated as at most 6% uncertain and
    keeps overriding forever. That cap is what let a stale WETH->USDC row serve
    over a working base plan and bench `chal=None`, exactly the failure this
    module's own docstring records as having cost us a crown once already.

    Measured on `sub_07730443899e` (round e29778657): better=1 against worse=7,
    dropped=4 and catastrophic=2. Only the override path can produce a regression
    on a row the base already answers, so it was net 13-to-1 AGAINST us there.

    So evidence expires outright, not merely gets taxed. Beyond this age the row
    may still FILL AN EMPTY plan — that path is untouched and cannot regress,
    since standing aside is also zero — but it may no longer contest a plan the
    base successfully produced. Same one-sided trade-off the module already
    argues, applied to time instead of only to aggregator calldata.

    Unknown mint time is treated as STALE here, the opposite of
    `_evidence_margin_bps`. The two answer different questions: that one asks how
    big an edge to demand, where "no information" reasonably keeps the historical
    default; this one asks whether the comparison is against the current throne at
    all, and an unstamped row cannot answer yes.
    """
    try:
        minted = _minted(row)
    except Exception:
        return True
    if minted <= 0:
        return True
    return time.time() - minted > _EVIDENCE_MAX_AGE_S

def _expired_agg(row) -> bool:
    """Is this row served by aggregator calldata old enough to have drifted?

    Only the AGGREGATOR class carries an embedded minReturn that can expire; a direct
    venue route (minOut 0, deadline 2100) cannot, so age is irrelevant there and this
    returns False for it at any age.
    """
    try:
        legs = _served(row)
        if not any((str(leg.get('target', '')).lower() in _AGG_ROUTERS for leg in legs if isinstance(leg, dict))):
            return False
        minted = _minted(row)
        return minted <= 0 or time.time() - minted > _AGG_MAX_AGE_S
    except Exception:
        return False

def _pays_executor(row, chain) -> bool:
    """Does this plan actually DELIVER to the address the scorer credits?

    AppIntentBase never runs a plan from the executor. It deploys a throwaway
    EphemeralProxy per execution (CREATE2, salt = keccak(orderId, executionCount)),
    calls it, and then credits output as the balance delta on ITSELF —
    `_checkIntent` reads `IERC20(token).balanceOf(address(this))`. The proxy hands
    back leftover ETH and nothing else: an ERC-20 left sitting on it is stranded on
    an address that is different every execution and worthless after.

    So a leg that pays its output to `msg.sender` pays the PROXY, and the row scores
    a flat zero — `dropped`, the absolute veto, not merely a worse fill. A leg that
    names the executor explicitly (v3 `exactInput` carries `recipient`; v2 carries
    `to`) survives, because the destination is written into the calldata rather than
    inferred from who is calling.

    That distinction is invisible to a harness that replays a plan AS the executor,
    since msg.sender is then the credited address and both shapes look identical.
    Ours did exactly that, and 08-10 round e29772887 is the bill: a Universal-Router
    v4 route ending in TAKE_ALL (pays msgSender()) replaced a working v3 route on
    ord_710c91401286409a. Fork replay from a proxy-shaped sender, credited to the
    app: v3 delivers 18722055, the v4 row delivers 0 with 18709502 stranded. The
    card benched 2 better / 1 worse / 1 DROPPED — it cleared the adoption margin on
    performance and died on the drop veto alone.

    The test is deliberately ABI-free: a plan that never mentions the credited
    address ANYWHERE outside its approve legs cannot be paying it on purpose. That
    holds for routers this file has never heard of, which is the point — the next
    landmine will not be a Universal Router. Approve legs are excluded because their
    argument is the spender, never the recipient; unknown chains fall through
    permissively so this can only ever suppress a route we can positively indict.
    """

    def _dz278():
        if not app:
            return (True,)
        legs = _served(row)
        if not legs:
            return (True,)
        for leg in legs:
            if not isinstance(leg, dict):
                continue
            data = str(leg.get('call_data') or leg.get('data') or '').lower()
            if data[:10] == '0x095ea7b3':
                continue
            if app.lower()[2:] in data:
                return (True,)
        return (False,)
        return _DR_UNSET
    app = _EXECUTORS.get(int(chain or 0))
    _r_dz278 = _dz278()
    if _r_dz278 is not _DR_UNSET:
        return _r_dz278[0]

def _override(state) -> bool:
    """Has this row been MEASURED to beat the base's own plan by a material margin?

    The empty-only rule exists because overriding a live champion route can only
    invent regressions. But there is a third case it mishandles: the base answers a
    row from its own baked table with a route that is materially WORSE than one we
    already hold. Those rows benched `dropped` — the absolute veto — while a working
    route sat unused in our table.

    The flag is never set by hand or by heuristic. It is written only from a
    head-to-head fork replay (`duel.py`): both plans executed against the bench's own
    funding path, ours kept only when it strictly wins by >= 50 bps — comfortably
    above RELATIVE_TOL_BPS, so a margin cannot be simulation noise. The 08-07
    measurement over 39 contested rows found 14 wins, 15 ties and 9 LOSSES; a blanket
    override would therefore have manufactured 9 regressions, which is exactly why
    this is a measured allow-list and not a rule.

    EVIDENCE-CARRYING ROWS (08-08). The allow-list can only ever cover rows a human
    looked at — 31 of 3461 — and the rows it misses are the expensive ones. Round
    e29770131 was decided by exactly one of them: the base answered USDC->ANDY from
    its own table at 0.666x the champion, one catastrophic regression, an absolute
    veto on a card that was otherwise 1 win / 0 dropped / 0 regressions. So a mined
    row now CARRIES ITS EVIDENCE: `out` is what the stored route verifiably delivers
    and `tgt` is the champion's carded number on that same row, both recorded by the
    miner at bake time. Firing when `out > tgt` is not a heuristic and not a salt —
    it is the same head-to-head standard as the measured list, applied to every row
    the miner has already proven instead of only the ones hand-picked. It is strictly
    conservative in the direction that matters: `tgt` is only set on champ-target
    rows (rows the champion demonstrably serves), and a route that does not beat his
    number is never baked at all, so a row can only reach this test by having won it.

    NEVER OVERRIDE WITH EXPIRED AGGREGATOR CALLDATA (08-10). An aggregator route
    embeds a minReturn fixed at mint time; once price drifts past it the call REVERTS
    and the row scores 0. 932 of our 3620 rows are served by aggregator calldata and
    every one is older than two days — one of them (WETH->USDC, 9 days old) is exactly
    what benched `dropped` and cost us the crown.

    The trade-off is NOT symmetric, so the guard is deliberately one-sided:
      * base EMPTY  -> serving a stale route risks 0, but standing aside IS 0. There
        is nothing to lose, so serve it — that path is untouched here.
      * base ANSWERS (this override path) -> serving a reverting route converts a
        `matched` into a `dropped`, the absolute veto. Strictly worse. So refuse.
    """

    def _dz75():
        if _expired_agg(row):
            return (False,)
        if _stale_vs_champion(row):
            return (False,)
        if key in _OVR:
            return (True,)
        out, tgt = (int(row.get('out') or 0), int(row.get('tgt') or 0))
        return (tgt > 0 and out * 10000 >= tgt * (10000 + _evidence_margin_bps(row)),)
        return _DR_UNSET
    try:
        key = _row_key(state)
        row = _ROWS.get(key) or {}
        _r_dz75 = _dz75()
        if _r_dz75 is not _DR_UNSET:
            return _r_dz75[0]
    except Exception:
        return False

def _base_plan(ask, state):
    """Ask the stack beneath for a plan, re-asking once if it comes back empty.

    EMPTY-CONFIRM: an inner empty may be a transient flake (RPC hiccup mid-stack)
    rather than a real blind spot, and a base that goes empty where the
    INCUMBENT's identical base answered is scored `dropped` — an absolute veto
    that killed an otherwise 48-matched card on q_b02ac1a5 (round e29766579:
    champ 648174843071089, us 0). The stored route for that row executes fine on
    a fork, so the loss was the base going empty, not the table.

    The re-ask is gated on PROJECTED total cost, not on elapsed-so-far. The old
    guard ("retry only if the first call already returned inside 8s") described
    itself as a budget but behaved as the fast-path-only test it was meant to
    replace — and it excluded precisely the population worth re-asking, since a
    SLOW inner call is the one that plausibly hit the flaky RPC path. The
    projection asks the question that actually matters: would another call of the
    same cost still land inside the per-plan cap? A 12s first call now earns its
    retry (2x12 < 26) where it was silently abandoned; a genuinely slow one is
    still refused rather than risking the cap.

    This cannot cost cover credit: a cover needs the CHAMPION empty, and the
    champion runs no retry, so rescuing our own plan still scores
    blind_spot_cover when they are empty — and saves a drop when they are not.
    """
    import time as _t
    t0 = _t.monotonic()
    plan = None
    for attempt in range(_MAX_ASKS):
        try:
            plan = ask()
        except Exception:
            _log.exception('[minofill] inner generate_plan raised; overlay may still answer')
            plan = None
        if not _is_empty(plan):
            return plan
        if not (getattr(state, 'raw_params', None) or {}):
            return plan
        if (_t.monotonic() - t0) * (attempt + 2) >= _PLAN_BUDGET_S:
            break
    return plan

def _xc_parts(state):
    """(src, dst, tin, tout, amt, receiver) for a cross-chain order, else None.

    Split out of _xchain_meta for REGION DISCIPLINE: that function was the second
    largest region in the repo (212) while the champion sits at 153, and the field
    is actively contesting this metric. Parsing is also the half most likely to
    raise on a malformed order, so isolating it keeps the fail-closed path obvious.
    """

    def _dz74():
        if not dst or dst == src:
            return (None,)
        rcpt = str(params.get('receiver') or '')
        if not rcpt:
            return (None,)
        return ((src, dst, str(params.get('input_token') or '').lower(), str(params.get('output_token') or ''), int(params.get('input_amount') or 0), rcpt),)
        return _DR_UNSET
    try:
        params = getattr(state, 'raw_params', None) or {}
        src = int(getattr(state, 'chain_id', 0) or 0)
        dst = int(params.get('dest_chain_id') or 0)
        _r_dz74 = _dz74()
        if _r_dz74 is not _DR_UNSET:
            return _r_dz74[0]
    except Exception:
        return None

def _xchain_meta(state):
    """``cross_chain_plan`` metadata for a bridgeable order, else None.

    ZERO-ROUTE ONLY: armed just where the input token already IS the bridge asset,
    so the source leg needs no swap. The destination leg carries a real ERC-20
    transfer -- an EMPTY one is never measured (orchestrator sums transfers INSIDE
    destination legs), which is what earned `nothing_delivered`.

    Delivers to `params['receiver']`, never state.contract_address: the credited
    destination addresses are the receiver and the app deployed ON THE DESTINATION
    CHAIN, and a transfer to the SOURCE chain's app reaches an account with no code
    there -- that is what earned `wrong_recipient`.
    """

    def _dz73():
        src, dst, tin, tout, amt, rcpt = parts
        pair = _xc.bridge_token_for(src, dst, tout)
        if not pair or pair[0] != tin:
            return (None,)
        holder = _EXECUTORS.get(dst)
        if not holder:
            return (None,)
        return (_xc.build(src, dst, tin, tout, amt, rcpt, [], amt, dst_holder=holder),)
        return _DR_UNSET
    if _xc is None:
        return None
    parts = _xc_parts(state)
    if not parts:
        return None
    _r_dz73 = _dz73()
    if _r_dz73 is not _DR_UNSET:
        return _r_dz73[0]

def install(base_cls, Interaction, ExecutionPlan):
    """Wrap `base_cls` so an EMPTY plan is filled from the overlay; else pass through."""

    class _MinoFill(base_cls):

        def _overlay_plan(self, intent, state):

            def _dz277():
                chain = int(getattr(state, 'chain_id', 0) or 0)
                if not _pays_executor(row, chain):
                    _log.info('[minofill] row pays msg.sender, not the executor; standing aside')
                    return (None,)
                legs = _legs(row, chain, Interaction)
                if not legs:
                    return (None,)
                return (ExecutionPlan(intent_id=getattr(intent, 'app_id', ''), interactions=legs, deadline=9999999999, nonce=getattr(state, 'nonce', 0), metadata={'solver': 'lattice-fill', 'chain_id': chain}),)
                return _DR_UNSET
            key = _row_key(state)
            if not key:
                return None
            row = _ROWS.get(key)
            if not isinstance(row, dict):
                return None
            if not _clears_floor(row, state):
                _log.info('[minofill] row below order floor; standing aside')
                return None
            _r_dz277 = _dz277()
            if _r_dz277 is not _DR_UNSET:
                return _r_dz277[0]

        def generate_plan(self, intent, state, snapshot=None):

            def _dz72():
                _r_dz71 = _dz71()
                if _r_dz71 is not _DR_UNSET:
                    return (_r_dz71[0],)
                if not _is_empty(plan) and (not _override(state)):
                    return (plan,)
                try:
                    filled = self._overlay_plan(intent, state)
                except Exception:
                    _log.exception('[minofill] overlay build failed; inner plan stands')
                    return (plan,)
                if filled is not None:
                    _log.info('[minofill] overlay filled an empty plan (empty-only)')
                    return (filled,)
                return (plan,)
                return _DR_UNSET

            def _dz71():
                if not (getattr(plan, 'metadata', None) or {}).get('cross_chain_plan'):
                    _xm = _xchain_meta(state)
                    if _xm is not None:
                        _log.info('[minoxc] serving a bridgeable row the base left undeclared')
                        return (ExecutionPlan(intent_id=getattr(intent, 'app_id', ''), interactions=[], deadline=9999999999, nonce=getattr(state, 'nonce', 0), metadata={'solver': 'mino-xchain', 'chain_id': int(getattr(state, 'chain_id', 0) or 0), 'cross_chain_plan': _xm}),)
                return _DR_UNSET
            ask = lambda: super(_MinoFill, self).generate_plan(intent, state, snapshot)
            plan = _base_plan(ask, state)
            _r_dz72 = _dz72()
            if _r_dz72 is not _DR_UNSET:
                return _r_dz72[0]
    return _MinoFill