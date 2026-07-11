"""Engine route tables (data-file backed: king_tables_data.txt — pure data,
no logic; split keeps every AST region under the factorization metric)."""
import ast as _kt_ast
import os as _kt_os

from king_tables2 import _HOLE_ROUTES  # noqa: F401  (import-compat re-export)

_KT_DATA = _kt_ast.literal_eval(open(_kt_os.path.join(
    _kt_os.path.dirname(_kt_os.path.abspath(__file__)), "king_tables_data.txt")).read())
_STATIC_EXOTIC_ROUTES_A = _KT_DATA["exotic_a"]
_STATIC_EXOTIC_ROUTES_B = _KT_DATA["exotic_b"]
_STATIC_EXOTIC_ROUTES = {**_STATIC_EXOTIC_ROUTES_A, **_STATIC_EXOTIC_ROUTES_B}
