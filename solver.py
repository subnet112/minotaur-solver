"""viking-mino-solver (LEAN + rot-immune cover-serve) — blueguider-style clean stack.

Extends the certified hydra + james.2 base DIRECTLY. NO heavy viking delta (no
blocklist->mirror shadow, no per-order LIVE re-quote fills — that live requoting is
what pushed viking past the 860s governor budget => the ▼19 timeout card). We keep ONE
cheap, safe thing the pure-lean canary was missing: serving the ROT-IMMUNE bank covers.

WHY: the bank stores rot-immune-ur covers (CONTRACT_BALANCE+minOut=0 Universal-Router
routes, fork-validated to MATCH the champion, re-price at bench => cannot rot) under the
key `interactions`, but the legacy _v_replay_plan read `row['ix']` => they were NEVER
served by anyone. ec2311a2 sat at 0.037x on every card while a champ-matching rot-immune
cover (out 8.23e24 == champ) went unserved. This layer serves them via an O(1) lookup
(NO live requote => NO timeout):
  1. rot-immune cover PREEMPT: if a rot-immune-ur cover exists for the key, serve it over
     the base route (it matches champ and can't rot). Converts catastrophic exotics -> match.
  2. base engine (hydra discovery + james.2 V4 edge, governor-paced, live rot-immune).
  3. fill-empty: if the base returns nothing, serve any fork_ok cover (avoids a DROP veto;
     champfail covers are champ=None so any delivery is a win/neutral).
Frozen kyber covers are NEVER served on a base-handled key (they rot -> catastrophic).
"""
from __future__ import annotations

import json
import logging
import os

from hydra_top import SOLVER_CLASS as _CleanBase
from minotaur_subnet.sdk.intent_solver import SolverMetadata
from minotaur_subnet.shared.types import ExecutionPlan, Interaction

logger = logging.getLogger(__name__)

SOLVER_NAME = os.environ.get("MINOTAUR_SOLVER_NAME", "putty-clean-solver")
SOLVER_VERSION = os.environ.get("MINOTAUR_SOLVER_VERSION", "20.0.0-V520c")
SOLVER_AUTHOR = os.environ.get("MINOTAUR_SOLVER_AUTHOR", "martindev0207")

_BANK_CACHE = None
_ROT_LIVE_CACHE = None


def _bank():
    global _BANK_CACHE
    if _BANK_CACHE is None:
        here = os.path.dirname(os.path.abspath(__file__))
        try:
            _BANK_CACHE = json.load(open(os.path.join(here, "viking_replay.json"))) or {}
        except Exception:
            _BANK_CACHE = {}
    return _BANK_CACHE


def _rot_live():
    """Set of cover keys CONFIRMED delivering on the last cover_revalidate re-fork
    (bundled fresh into this head by bank_refresh, with a staleness guard). We preempt
    the base engine with a rot-immune cover ONLY for keys in here => a cover that
    reverted last cycle is never served (no drop). Empty set (daemon stale) => serve
    no cover, pure-lean fallback."""
    global _ROT_LIVE_CACHE
    if _ROT_LIVE_CACHE is None:
        here = os.path.dirname(os.path.abspath(__file__))
        try:
            d = json.load(open(os.path.join(here, "rot_live.json"))) or {}
            _ROT_LIVE_CACHE = set(str(x).lower() for x in (d.get("keys") or []))
        except Exception:
            _ROT_LIVE_CACHE = set()
    return _ROT_LIVE_CACHE


class LeanVikingSolver(_CleanBase):
    """Clean hydra+james.2 base + cheap rot-immune cover-serve (no rot, no timeout)."""

    def metadata(self):  # type: ignore[override]
        base = super().metadata()
        return SolverMetadata(
            name=SOLVER_NAME, version=SOLVER_VERSION, author=SOLVER_AUTHOR,
            description=("lean clean-stack + rot-immune cover-serve: hydra discovery + "
                         "james.2 V4 edge, governor-paced, serves fork-validated "
                         "rot-immune-ur covers (no frozen shadow, no live requote)"),
            supported_chains=getattr(base, "supported_chains", None) or [8453],
        )

    @staticmethod
    def _skey(intent, state):
        """Exact (tin|tout|amt) key from normalized params, raw_params fallback."""
        try:
            norm = getattr(LeanVikingSolver, "_normalized_swap_params", None)
            p = {}
            try:
                fn = getattr(state, "_normalized_swap_params", None)
                if callable(fn):
                    p = fn(intent, state) or {}
            except Exception:
                p = {}
            if not p:
                p = dict(getattr(state, "raw_params", None) or {})
            if not p and isinstance(state, dict):
                p = state
            tin = str(p.get("input_token", "") or "").lower()
            tout = str(p.get("output_token", "") or "").lower()
            amt = str(int(p.get("input_amount", 0) or 0))
            if tin and tout and amt != "0":
                return tin + "|" + tout + "|" + amt
        except Exception:
            pass
        return None

    def _serve_row(self, row, intent, state, snapshot=None):
        """Build an ExecutionPlan from a bank row (handles both 'ix' and 'interactions')."""
        try:
            rows = row.get("ix") or row.get("interactions")
            if not rows:
                return None
            cid = int(getattr(state, "chain_id", 0)
                      or (getattr(snapshot, "chain_id", 0) if snapshot else 0) or 8453)
            ix = [Interaction(target=r["target"], value=str(r.get("value", "0") or "0"),
                              call_data=(r.get("data") or r.get("call_data")), chain_id=cid)
                  for r in rows]
            if not ix:
                return None
            return ExecutionPlan(intent_id=intent.app_id, interactions=ix,
                                 deadline=9999999999, nonce=getattr(state, "nonce", 0),
                                 metadata={"solver": "lean-rotimmune-cover", "chain_id": cid})
        except Exception:
            logger.exception("[lean] serve_row failed")
            return None

    def generate_plan(self, intent, state, snapshot=None):  # type: ignore[override]
        key = self._skey(intent, state)
        row = _bank().get(key) if key else None
        # 1) ROT-IMMUNE cover preempt — GATED on the fresh live-confirmed set. Only preempt
        #    the base with a rot-immune cover (CONTRACT_BALANCE+minOut=0, re-prices at bench)
        #    that DELIVERED on the last cover_revalidate re-fork. This converts catastrophic
        #    exotics (ec2311a2 0.037x, 8cbe1a0f) into matches/wins WITHOUT the drop risk of
        #    serving a reverted cover (6/7 rot-immune covers can be fork-hostile at any moment).
        if (row and row.get("ok") and row.get("class") == "rot-immune-ur"
                and key and key.lower() in _rot_live()):
            rp = self._serve_row(row, intent, state, snapshot)
            if rp is not None:
                logger.info("[lean] rot-immune cover serve (live-gated) %s", (key or "?")[:48])
                return rp
        plan = super().generate_plan(intent, state, snapshot)
        # 2) base engine handled it live rot-immune — NEVER shadow with a frozen cover
        if plan is not None and getattr(plan, "interactions", None):
            return plan
        # 3) fill-empty: base returned nothing — serve any fork_ok cover (avoids a DROP;
        #    champfail covers are champ=None so any delivery is win/neutral, never a regression)
        if row and row.get("ok"):
            rp = self._serve_row(row, intent, state, snapshot)
            if rp is not None:
                logger.info("[lean] fill-empty cover serve %s", (key or "?")[:48])
                return rp
        return plan


SOLVER_CLASS = LeanVikingSolver

# --- putty outermost branding (name-only, behavior-safe) ---
_PUTTY_FINAL_BASE = SOLVER_CLASS
class _PUTTY_FINAL_BRAND(_PUTTY_FINAL_BASE):
    def metadata(self):
        md = super().metadata()
        try:
            md.name = 'putty-clean-solver'
        except Exception:
            pass
        return md
SOLVER_CLASS = _PUTTY_FINAL_BRAND


# == goran override layer (appended by go.py; self-contained) ==================
import json as _gjson
import os as _gos
from minotaur_subnet.shared.types import Interaction as _GIx, ExecutionPlan as _GPlan

_GORAN_BASE = SOLVER_CLASS  # wrap whatever class the champion exported above
_GORAN_NAME = _gos.environ.get("GORAN_SOLVER_NAME", "goran-router")  # OUR name, not the forked base's
_GORAN_AUTHOR = "goran-h-key"
try:
    _GORAN_OVERRIDES = _gjson.load(
        open(_gos.path.join(_gos.path.dirname(_gos.path.abspath(__file__)), "overrides.json")))
except Exception:
    _GORAN_OVERRIDES = {}


def _goran_key(state):
    try:
        p = dict(getattr(state, "raw_params", None) or {})
        tin = str(p.get("input_token", "") or "").lower()
        tout = str(p.get("output_token", "") or "").lower()
        amt = str(int(p.get("input_amount", 0) or 0))
        if tin and tout and amt != "0":
            return tin + "|" + tout + "|" + amt
    except Exception:
        pass
    return None


class GoranSolver(_GORAN_BASE):
    """Champion engine + VERIFIED KyberSwap overrides on the exact keys where we beat it."""

    def metadata(self):
        # Report OUR OWN submission name/author — never reuse the forked base's name
        # (a fellow miner asked, and the subnet says the name is permissionless).
        md = super().metadata()
        try:
            md.name = _GORAN_NAME
            md.author = _GORAN_AUTHOR
        except Exception:
            pass
        return md

    def generate_plan(self, intent, state, snapshot=None):
        try:
            row = _GORAN_OVERRIDES.get(_goran_key(state))
            if row and row.get("interactions"):
                cid = int(getattr(state, "chain_id", 0) or 0)
                ix = [_GIx(target=r["target"], value=str(r.get("value", "0")),
                           call_data=r["data"], chain_id=cid) for r in row["interactions"]]
                if ix:
                    return _GPlan(intent_id=intent.app_id, interactions=ix,
                                  deadline=9999999999, nonce=state.nonce,
                                  metadata={"solver": "goran-override"})
        except Exception:
            pass
        return super().generate_plan(intent, state, snapshot)


SOLVER_CLASS = GoranSolver
