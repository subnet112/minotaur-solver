"""Auto-generated shim: re-exports the wrapped champion base module."""
import _bg124_arch_b91aacb as base_module
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
