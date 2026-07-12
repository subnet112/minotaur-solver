"""Engine hole-route table (data-file backed: king_tables_data.txt)."""
import ast as _kt_ast
import os as _kt_os

_HOLE_ROUTES = _kt_ast.literal_eval(open(_kt_os.path.join(
    _kt_os.path.dirname(_kt_os.path.abspath(__file__)), "king_tables_data.txt")).read())["holes"]
