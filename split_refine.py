"""split-refine v1 — Pareto-safe finer-grid 2-venue split cover.

The champion's `king_base.MinerSolver._try_split_plan` probes a 2-venue split of
an order across the top-2 deep V3-style venues, but over a COARSE 3-point ratio
grid only: a1 in {amount/3, amount/2, 2*amount/3}. The optimal split between two
pools of differing depth/curvature is almost never exactly 33/50/67%, so on large
orders the champion leaves basis points on the table.

This module overrides `_try_split_plan` in a new outermost subclass. It:

  1. Calls `super()._try_split_plan(...)` — the CHAMPION's own split result (a
     split ExecutionPlan or None). This is the SAFETY FLOOR we defer to.
  2. Re-derives the same top-2 splittable venues and runs a FINER concurrent
     ratio search (a superset grid that includes the champion's 3 ratios, plus a
     local refine around the best point) on the round's own fork, re-quoting with
     the champion's own `_quote_one`.
  3. Returns the refined split ONLY when its summed on-chain quote STRICTLY beats
     the champion's own chosen output by a safety buffer; otherwise returns the
     champion's plan verbatim.

Pareto-safety (why it can never regress or drop an order):
  * Any error / missing venue / w3 unavailable -> return the champion plan.
  * We NEVER emit a split whose summed quote does not beat the champion's own
    output; when it doesn't, we return exactly what the champion returned.
  * The refined split reuses the champion's PROVEN `_build_split_plan` /
    `_encode_v3_leg` with legs on the same `_SPLITTABLE` venues, so it carries
    identical quote->delivery fidelity and revert surface as champion splits.
  => delivered output >= champion on EVERY order; strictly greater only where a
     finer ratio genuinely helps. That is a clean per-order performance win under
     the adoption rule (output-based), with zero regression/drop risk.

Only the split decision is touched; every other routing/quoting/plan path is
inherited unchanged. Every named region is kept <=110 AST nodes to match the
codebase's factorization discipline (see harness/screening.max_region_nodes).
"""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)
_SPLIT_MIN_GAIN = 1.0005
_REFINE_EDGE = 1.0003
_REFINE_WINDOW = 0.95
_COARSE_FRACS = tuple((n / 24 for n in (3, 6, 8, 10, 12, 14, 16, 18, 21)))
_REFINE_OFFS = tuple((n / 48 for n in (1, 2, 4)))
_MAX_WORKERS = 16

def _clamp(a, amount_in):
    return max(1, min(amount_in - 1, int(a)))

def _dedup_top2(sorted_cands):
    """First two distinct-venue candidates from an out-desc-sorted list."""
    top, seen = ([], set())
    for c in sorted_cands:
        v = c.get('venue')
        if v in seen:
            continue
        seen.add(v)
        top.append(c)
        if len(top) == 2:
            return (top[0], top[1])
    return None

def _top2_splittable(splittable, cands):
    """The top-2 DISTINCT splittable venues by full-amount output, or None."""
    sp = [c for c in cands if c.get('venue') in splittable]
    sp.sort(key=lambda c: int(c.get('out', 0) or 0), reverse=True)
    return _dedup_top2(sp)

def _champ_output(champ_plan, ref_out):
    """Champion's own chosen output: its split's expected_output, else ref_out."""
    if champ_plan is None:
        return ref_out
    meta = getattr(champ_plan, 'metadata', None) or {}
    try:
        return max(ref_out, int(meta.get('expected_output', ref_out)))
    except (TypeError, ValueError):
        return ref_out

class _Refiner:
    """Concurrent finer-grid search for the best a1 of a 2-venue split, with a
    per-order quote cache (champion's `_quote_one`; 0 on revert)."""

    def __init__(self, solver, w3, v1, v2, tin, tout, amount_in):
        self.solver = solver
        self.w3 = w3
        self.v1 = v1
        self.v2 = v2
        self.tin = tin
        self.tout = tout
        self.amount_in = amount_in
        self._cache: dict[tuple, int] = {}

    def _quote(self, venue, param, amount):
        if amount <= 0 or amount >= self.amount_in:
            return 0
        key = (venue, amount)
        r = self._cache.get(key)
        if r is None:
            r = int(self.solver._quote_one(self.w3, venue, param, self.tin, self.tout, amount))
            self._cache[key] = r
        return r

    def _pair_jobs(self, a1):
        """The two (venue, param, amount) probes for split ratio a1."""
        a2 = self.amount_in - a1
        out = []
        if 0 < a1 < self.amount_in:
            out.append((self.v1['venue'], self.v1['param'], a1))
        if 0 < a2 < self.amount_in:
            out.append((self.v2['venue'], self.v2['param'], a2))
        return out

    def _jobs_for(self, a1_values):
        need = set()
        for a1 in a1_values:
            need.update(self._pair_jobs(a1))
        return [job for job in need if (job[0], job[2]) not in self._cache]

    def _prime(self, a1_values):
        """Fire needed quotes concurrently (mirrors the champion's ThreadPool)."""
        import concurrent.futures
        need = self._jobs_for(a1_values)
        if not need:
            return
        workers = min(_MAX_WORKERS, len(need))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(self._quote, v, p, a) for v, p, a in need]
            for f in concurrent.futures.as_completed(futs):
                try:
                    f.result()
                except Exception:
                    pass

    def _total(self, a1):
        o1 = self._quote(self.v1['venue'], self.v1['param'], a1)
        o2 = self._quote(self.v2['venue'], self.v2['param'], self.amount_in - a1)
        return o1 + o2 if o1 > 0 and o2 > 0 else 0

    def _best_over(self, a1_values, best_a1, best_total):
        for a1 in a1_values:
            t = self._total(a1)
            if t > best_total:
                best_a1, best_total = (a1, t)
        return (best_a1, best_total)

    def _coarse_grid(self):
        amt = self.amount_in
        return sorted({_clamp(amt * f, amt) for f in _COARSE_FRACS})

    def _refine_grid(self, best_a1):
        amt = self.amount_in
        out = set()
        for off in _REFINE_OFFS:
            d = max(1, int(amt * off))
            out.add(_clamp(best_a1 - d, amt))
            out.add(_clamp(best_a1 + d, amt))
        return sorted(out)

    def search(self):
        """(best_a1, best_total) over the coarse grid + a local refine."""
        coarse = self._coarse_grid()
        self._prime(coarse)
        best_a1, best_total = self._best_over(coarse, None, 0)
        if best_a1 is None:
            return (None, 0)
        refine = self._refine_grid(best_a1)
        self._prime(refine)
        return self._best_over(refine, best_a1, best_total)

def _pick_pair(solver, cands, best, amount_in):
    """Validate the order and pick the top-2 splittable venues, or None."""
    ref_out = int(best.get('out', 0) or 0)
    if ref_out <= 0 or amount_in < 8:
        return None
    pair = _top2_splittable(solver._SPLITTABLE, cands)
    if pair is None:
        return None
    v1, v2 = pair
    if int(v2.get('out', 0) or 0) < int(v1.get('out', 0) or 0) * _REFINE_WINDOW:
        return None
    return (v1, v2, ref_out)

def _emit_split(solver, ctx, v1, v2, best_a1, best_total, ref_out, champ_out):
    """Assemble the two legs and build the split plan (champion's builder)."""
    intent, state, snapshot, tin, tout, amount_in, chain_id = ctx
    legs = [(v1['venue'], v1['param'], best_a1), (v2['venue'], v2['param'], amount_in - best_a1)]
    logger.info('[split-refine] override: total=%d > champ=%d (single=%d) a1=%d/%d', best_total, champ_out, ref_out, best_a1, amount_in)
    return solver._build_split_plan(intent, state, snapshot, legs, tin, tout, amount_in, chain_id, best_total, ref_out)

def _gated_plan(solver, ctx, v1, v2, found, ref_out, champ_plan):
    """Build the refined split iff it strictly beats the champion, else None."""
    best_a1, best_total = found
    champ_out = _champ_output(champ_plan, ref_out)
    bar = max(int(champ_out * _REFINE_EDGE), int(ref_out * _SPLIT_MIN_GAIN))
    if best_a1 is None or best_total <= bar:
        return None
    return _emit_split(solver, ctx, v1, v2, best_a1, best_total, ref_out, champ_out)

def _run_search(solver, ctx, v1, v2):
    """Fork web3 + finer-grid search -> (best_a1, best_total), or None on no fork."""
    tin, tout, amount_in, chain_id = (ctx[3], ctx[4], ctx[5], ctx[6])
    w3 = solver._get_web3(int(chain_id))
    if w3 is None:
        return None
    return _Refiner(solver, w3, v1, v2, tin, tout, amount_in).search()

def _refine_split(solver, ctx, cands, best, champ_plan):
    """Orchestrate: pick pair -> fork web3 -> finer search -> gated build.
    `ctx` = (intent, state, snapshot, tin, tout, amount_in, chain_id)."""
    picked = _pick_pair(solver, cands, best, ctx[5])
    if picked is None:
        return None
    v1, v2, ref_out = picked
    found = _run_search(solver, ctx, v1, v2)
    if found is None:
        return None
    return _gated_plan(solver, ctx, v1, v2, found, ref_out, champ_plan)

def install(base_cls):
    """Return a subclass of `base_cls` that refines the champion's split.

    A factory so `solver.py` can wrap whatever the final champion `SOLVER_CLASS`
    is without this module importing it (avoids a cycle)."""

    class _MinoSplitRefine(base_cls):
        """Champion stack + finer-grid 2-venue split refinement (Pareto-safe:
        defers to the champion's own split on any doubt)."""

        def _try_split_plan(self, intent, state, snapshot, cands, tin, tout, amount_in, chain_id, best):
            champ_plan = super()._try_split_plan(intent, state, snapshot, cands, tin, tout, amount_in, chain_id, best)
            try:
                ctx = (intent, state, snapshot, tin, tout, amount_in, chain_id)
                refined = _refine_split(self, ctx, cands, best, champ_plan)
                return refined if refined is not None else champ_plan
            except Exception:
                logger.exception('[split-refine] refine failed; keeping champion split')
                return champ_plan
    return _MinoSplitRefine