"""Pytest bootstrap for the reference solver test suite.

The solver depends on the ``minotaur_subnet`` SDK at runtime (it ships in
the ``solver-base`` Docker image). Locally there is no installed package,
so this conftest:

  1. puts the repo root on ``sys.path`` (so ``strategies`` / ``common``
     import as top-level packages), and
  2. best-effort locates a ``minotaur_subnet`` checkout for the
     solver-level tests — set ``MINOTAUR_SUBNET_PATH`` to a checkout, or
     keep one in a sibling directory. Tests needing the SDK use
     ``pytest.importorskip("minotaur_subnet")`` so the pure quoter tests
     still run without it.

CI only byte-compiles the repo (see .github/workflows/test.yml); these
tests are for local development against an SDK checkout.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _ensure_sdk_on_path() -> None:
    try:
        import minotaur_subnet  # noqa: F401

        return
    except ImportError:
        pass

    candidates = []
    env = os.environ.get("MINOTAUR_SUBNET_PATH")
    if env:
        candidates.append(env)
    parent = os.path.dirname(ROOT)
    candidates += [
        os.path.join(parent, "minotaur_dev"),
        os.path.join(parent, "minotaur_subnet"),
    ]
    for candidate in candidates:
        if candidate and os.path.isdir(os.path.join(candidate, "minotaur_subnet")):
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
            return


_ensure_sdk_on_path()
