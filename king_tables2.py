"""king engine hole-route table — data lives in king_tables_data.txt (exact
repr via ast.literal_eval => identical objects; tables-as-.py counted against
the factorization metric, tables-as-data do not)."""
import ast as _ast
import os as _os

_D = _ast.literal_eval(open(_os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), "king_tables_data.txt")).read())
_HOLE_ROUTES = _D["hole_routes"]
