"""Auto-generated shim: re-exports the wrapped champion base module."""
import os
import _bg124_arch_9645f01 as base_module
SOLVER_CLASS = base_module.SOLVER_CLASS
SOLVER_VERSION = getattr(base_module, 'SOLVER_VERSION', '')
if not SOLVER_VERSION:
    try:
        import king_solver as _kmod
        SOLVER_VERSION = getattr(_kmod, 'SOLVER_VERSION', '')
    except Exception:
        SOLVER_VERSION = os.environ.get('MINOTAUR_SOLVER_VERSION', '')
if not SOLVER_VERSION:
    try:
        import king_base as _kmod
        SOLVER_VERSION = getattr(_kmod, 'SOLVER_VERSION', '')
    except Exception:
        SOLVER_VERSION = os.environ.get('MINOTAUR_SOLVER_VERSION', '')
SOLVER_VERSION = SOLVER_VERSION or 'unknown'