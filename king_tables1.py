"""king engine static exotic-route table — data lives in king_tables_data.txt
(exact repr via ast.literal_eval => identical objects). Re-exports _HOLE_ROUTES
for the original import surface."""
from king_tables2 import _D as _D2
from king_tables2 import _HOLE_ROUTES  # noqa: F401

_STATIC_EXOTIC_ROUTES = _D2["static_exotic_routes"]
