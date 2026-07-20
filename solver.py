"""minoPot entry point — Part 1 (champion base, fetched fresh each round) +
Part 2 (fixed max-water-flow overlay).

The current champion's original solver.py is preserved verbatim as
`_champion_entry.py`; this file wraps whatever class it exports as SOLVER_CLASS
with the fixed FlowEnhanceMixin. Nothing here changes round to round — only
`_champion_entry` (Part 1) does, which is exactly what gives each round a fresh
code fingerprint while keeping the flow edge (Part 2) constant.
"""
from __future__ import annotations

from _champion_entry import SOLVER_CLASS as _ChampionBase
from minopot_flow import FlowEnhanceMixin


class MinoPotRouter(FlowEnhanceMixin, _ChampionBase):
    """Current champion + fixed N-way water-fill split (best-of-two)."""


SOLVER_CLASS = MinoPotRouter
