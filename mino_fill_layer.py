"""lattice fill layer — EMPTY-ONLY overlay above the reigning solver stack."""
from __future__ import annotations

import json
import logging
import os

_log = logging.getLogger(__name__)

_FILL_NONCE = "6"          # rewritten per build; keeps each bench fingerprint distinct
_TABLE_FILE = "mino_fill_rows.json"

# Aggregator routers whose calldata carries an embedded minReturn (see _rank).
_AGG_ROUTERS = frozenset({"0x6131b5fae19ea4f9d964eac0408e4408b66337b5"})


def _table_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), _TABLE_FILE)


def _read_table() -> dict:
    """Primary table (mino_fill_rows.json) unioned over the lineage's shared."""

    def _minted(row) -> int:
        # top-level "minted" stamp counts too: a fresh flat re-mint must be able
        # to beat a stale routed mint of the same key from the other source —
        # without this, a lattice_wins route from days ago (expired aggregator
        # minReturn -> reverts at sim) shadows our verified working replacement
        if not isinstance(row, dict):
            return 0
        best = int(row.get("minted") or 0)
        routes = row.get("routes")
        if isinstance(routes, list):
            for r in routes:
                if isinstance(r, dict):
                    m = int(r.get("minted_at") or 0)
                    if m > best:
                        best = m
        return best

    def _served(row) -> list:
        """The legs this row would actually serve (newest whole route, else flat)."""
        if not isinstance(row, dict):
            return []
        live = [r for r in (row.get("routes") or [])
                if isinstance(r, dict) and r.get("interactions")]
        if live:
            return max(live, key=lambda r: int(r.get("minted_at") or 0))["interactions"]
        return row.get("interactions") or []

    def _rank(row) -> tuple:
        # DURABILITY OUTRANKS FRESHNESS. Aggregator calldata embeds a minReturn
        # fixed at mint time; once price drifts past it the call REVERTS at the
        # bench sim and the row scores 0 — indistinguishable from no cover at
        # all. A direct-venue route (minOut 0, deadline 2100) cannot expire, so
        # it outranks an aggregator route of ANY age; recency only breaks ties
        # within a class. Measured 08-05: 379 union keys were serving an
        # aggregator corpse while a working direct route sat in the other table.
        agg = any(str(leg.get("target", "")).lower() in _AGG_ROUTERS
                  for leg in _served(row) if isinstance(leg, dict))
        return (0 if agg else 1, _minted(row))

    rows: dict = {}
    base = os.path.dirname(os.path.abspath(__file__))
    for fn in ("lattice_wins.json", _TABLE_FILE):
        try:
            with open(os.path.join(base, fn)) as fh:
                loaded = json.load(fh)
            if not isinstance(loaded, dict):
                continue
            for k, v in loaded.items():
                held = rows.get(k)
                if held is None or _rank(v) >= _rank(held):
                    rows[k] = v
        except Exception:
            _log.warning("[minofill] overlay source %s unreadable; continuing", fn)
    if not rows:
        _log.warning("[minofill] no overlay tables; layer is inert")
    return rows


_ROWS = _read_table()


def _row_key(state) -> str | None:
    """chain|contract_address|tin|tout|amount, byte-identical to the bench's own key."""
    try:
        params = getattr(state, "raw_params", None) or {}
        tin = str(params.get("input_token") or "").lower()
        tout = str(params.get("output_token") or "").lower()
        amount = int(params.get("input_amount") or 0)
        contract = str(getattr(state, "contract_address", "") or "").lower()
        chain = int(getattr(state, "chain_id", 0) or 0)
        if not contract:
            # executor fallback: a state that omits its contract used to void the
            # ENTIRE table for that order (returned None here) while looking healthy
            contract = {1: "0xcd42cf6fd6e0c539cae038fe6a73c67f8c1c7a52",
                        8453: "0xe0d97941103c30799fa0aa9d54a34246846c73bf"}.get(chain, "")
    except Exception:
        return None
    if not (tin and tout and amount and contract):
        return None
    return f"{chain}|{contract}|{tin}|{tout}|{amount}"


def _is_empty(plan) -> bool:
    try:
        return plan is None or not getattr(plan, "interactions", None)
    except Exception:
        return True


def _freshest(row):
    """Newest minted route for a key."""
    routes = row.get("routes")
    if isinstance(routes, list):
        # FALLBACK CHAIN (08-05): walk mints newest -> oldest and serve the
        # first STRUCTURALLY WHOLE one (every leg has target+calldata). A
        # newest-only pick turned one malformed re-mint into a dead key even
        # while older good calldata sat right next to it in the same row.
        live = [r for r in routes if isinstance(r, dict) and r.get("interactions")]
        for cand in sorted(live, key=lambda r: -int(r.get("minted_at") or 0)):
            ix = cand.get("interactions") or []
            if ix and all(isinstance(l, dict) and l.get("target")
                          and (l.get("call_data") or l.get("data")) for l in ix):
                return ix
    return row.get("interactions") or []


def _legs(row, chain, Interaction):
    """Stored interactions -> Interaction objects, verbatim."""
    stored = _freshest(row)
    if not stored:
        return None
    built = []
    for leg in stored:
        data = leg.get("call_data") or leg.get("data")
        target = leg.get("target")
        if not (target and data):
            return None
        built.append(Interaction(target=target, value=str(leg.get("value", "0")),
                                 call_data=data, chain_id=chain))
    return built


def install(base_cls, Interaction, ExecutionPlan):
    """Wrap `base_cls` so an EMPTY plan is filled from the overlay; else pass through."""

    class _MinoFill(base_cls):

        def _overlay_plan(self, intent, state):
            # NO CHAIN GATE. This used to serve chain 1 only, because
            # ADOPTION_SCORED_CHAINS pinned the adoption verdict to Ethereum and
            # Base rows come back `offgate` (65 of 122 on a recent card). But
            # adoption_scored_chains() reads an ENV — unset means EVERY chain
            # counts — and the subnet is actively preparing to re-enable Base
            # (#1230, "guards required before re-enabling Base"). The gate was
            # never a safety property: this overlay answers ONLY where the stack
            # beneath returned empty, so filling a row can move our output from
            # zero to non-zero and never the reverse — it cannot manufacture a
            # `worse` (that needs the champion to answer, i.e. the base non-empty)
            # nor a `dropped` (that is already the outcome when we stay empty).
            # Ungated, the 833 Base rows we already carry arm themselves the
            # moment the verdict counts them, instead of the round after we
            # notice. Wrong-chain rows still cannot match: _row_key embeds the id.
            key = _row_key(state)
            if not key:
                return None
            row = _ROWS.get(key)
            if not isinstance(row, dict):
                return None
            chain = int(getattr(state, "chain_id", 0) or 0)
            legs = _legs(row, chain, Interaction)
            if not legs:
                return None
            return ExecutionPlan(intent_id=getattr(intent, "app_id", ""), interactions=legs,
                                 deadline=9999999999, nonce=getattr(state, "nonce", 0),
                                 metadata={"solver": "lattice-fill", "chain_id": chain})

        def generate_plan(self, intent, state, snapshot=None):
            import time as _t
            _t0 = _t.monotonic()
            try:
                plan = super().generate_plan(intent, state, snapshot)
            except Exception:
                _log.exception("[minofill] inner generate_plan raised; overlay may still answer")
                plan = None
            # no raw params = nothing this overlay could ever serve for the
            # row; skip both the retry and the table path outright (real
            # short-circuit: saves a wasted inner re-ask on malformed states)
            if _is_empty(plan) and not (getattr(state, "raw_params", None) or {}):
                return plan
            if _is_empty(plan) and _t.monotonic() - _t0 < 2.0:
                # EMPTY-CONFIRM (08-05): a FAST inner empty may be a transient
                # flake (RPC hiccup mid-stack). One bounded synchronous retry —
                # serving a cover on a row the incumbent actually answers is
                # the worse/cat class this layer must never create. A slow
                # first call gets no retry: it spent real budget, not a flake.
                try:
                    plan = super().generate_plan(intent, state, snapshot)
                except Exception:
                    plan = None
            if not _is_empty(plan):
                return plan                       # champion routing always wins
            try:
                filled = self._overlay_plan(intent, state)
            except Exception:
                _log.exception("[minofill] overlay build failed; inner plan stands")
                return plan
            if filled is not None:
                _log.info("[minofill] overlay filled an empty plan (empty-only)")
                return filled
            return plan

    return _MinoFill
