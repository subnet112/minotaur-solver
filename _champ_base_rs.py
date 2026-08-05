from __future__ import annotations
import logging
import os
from hydra_top import SOLVER_CLASS as _HydraBase
from minotaur_subnet.sdk.intent_solver import SolverMetadata
from minotaur_subnet.shared.types import ExecutionPlan, Interaction
import shape_lib as _sl, shape_est2 as _se, shape_build as _sb, shape_lib3 as _sl3
import viking_gate as _vg, viking_data as _vd, shape_base as _sba, chain1 as _c1
import viking_tables as _vt, viking_serve as _vs, mc_lib as _mcl
from mc_data import _MC_ADDR, _MC_AGG3, _MC_QUOTER, _MC_ROUTER, _MC_QSEL, _MC_QIN, _MC_QOUT, _MC_FEES, _MC_FORCE_PAIR, _MC_FORCE_ORDER, _MC_CAND_ORDER
logger = logging.getLogger(__name__)