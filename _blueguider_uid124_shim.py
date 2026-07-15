"""Auto-generated shim: re-exports the wrapped champion base module.

Repointed 2026-07-14 from _blueguider_uid124_archived_entry (apex-split-router,
an experimental FAT layer whose _apex_route_plan is a single 1738-node region ⇒
max_region_nodes=1738, 9x goran's 196, locking us out of every tie-break lane
and too slow to bench inside the soak window) to _apex_incumbent — the verbatim
lean re-fork of the certified hydra champion (goran lineage). Same matching
engine (hydra_top underneath), a fraction of the region size."""
import _apex_incumbent as base_module
SOLVER_CLASS = base_module.SOLVER_CLASS
SOLVER_VERSION = getattr(base_module, "SOLVER_VERSION", "")
if not SOLVER_VERSION:  # entry modules often re-export an engine that has it
    for _m in ("king_solver", "king_base"):
        try:
            SOLVER_VERSION = getattr(__import__(_m), "SOLVER_VERSION", "")
        except Exception:
            SOLVER_VERSION = ""
        if SOLVER_VERSION:
            break
SOLVER_VERSION = SOLVER_VERSION or "unknown"
