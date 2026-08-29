from __future__ import annotations
import os
from _champ_base import SOLVER_CLASS as _Base
from minotaur_subnet.sdk.intent_solver import SolverMetadata
from minotaur_subnet.shared.types import ExecutionPlan, Interaction
import router_cover as _rc
import os as _gos
from minotaur_subnet.sdk.intent_solver import SolverMetadata as _GSolverMetadata
import json as _hjson
from minotaur_subnet.shared.types import ExecutionPlan as _HEP, Interaction as _HIX
SAFE_TOKENS = frozenset({'0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2', '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48', '0xdac17f958d2ee523a2206206994597c13d831ec7', '0x6b175474e89094c44da98b954eedeac495271d0f', '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599', '0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0', '0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf', '0x4200000000000000000000000000000000000006', '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', '0x50c5725949a6f0c72e6c4a641f24049a917db0cb', '0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca', '0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22'})
SOLVER_NAME = os.environ.get('MINOTAUR_SOLVER_NAME', "leanrtr")
SOLVER_VERSION = os.environ.get('MINOTAUR_SOLVER_VERSION', '0.455.0')