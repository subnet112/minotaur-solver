"""Lower layer of mino_fill_layer.py, split out to reduce max_region_nodes.

Dependency-closed: every module-level name these statements read is defined here
too, so this module never imports back from mino_fill_layer and no cycle is possible.
Semantics unchanged -- same objects, same names, same order.
"""
from __future__ import annotations
__all__ = ['_DR_UNSET', '_clears_floor', '_floor', '_is_empty', '_minted', '_read_overrides', '_served', 'annotations', 'json', 'logging', 'os', 'time']
'lattice fill layer — EMPTY-ONLY overlay above the reigning solver stack.'
_DR_UNSET = object()
import json
import logging
import os
import time
from _fx_mino_fill_layer import _clears_floor, _floor, _is_empty, _minted, _read_overrides, _served