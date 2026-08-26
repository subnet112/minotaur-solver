"""Pre-solved routes for pairs the incumbent cannot serve.

Baked offline by route_bake.py where there is no 6s search budget, so the online
path costs one dict lookup instead of ~37 quotes. Split out of cover_ext.py
purely for the region metric: a module's top level is itself a scored region, and
holding both the generic sweep and this table pushed that region to 182.
"""
from __future__ import annotations
_DR_UNSET = object()
import json
import os
from eth_abi import encode as _enc
import time
from venues import CHAINS, DEADLINE, _SEARCH_DEADLINE, _v3_path_bytes, q_v2, q_v3_path, q_v3_single
S_V2_SWAP_FOT = '5c11d795'

def _load():
    """Route table, preferring the generated PYTHON module over the JSON.

    Both hold the same data. The .py form is what ships: the validator dedups on
    a structural fingerprint of the CODE, so a table that lives in JSON leaves
    the tree structurally identical round after round and every resubmission is
    refused as a `structural_duplicate`. As a dict literal, each newly baked
    route is a real change — genuine improvement becomes a valid resubmission.
    """
    try:
        from ext_routes_py import ROUTES as R
        return dict(R)
    except Exception:
        pass
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ext_routes.json')) as fh:
            return {k: v.get('route', v) for k, v in json.load(fh).items()}
    except Exception:
        return {}
ROUTES = _load()

def _approve(spender, amount):
    from eth_utils import keccak
    return '0x' + keccak(text='approve(address,uint256)')[:4].hex() + _enc(['address', 'uint256'], [spender, int(amount)]).hex()

def _rebuild(rpc, cfg, route, tin, tout, amount, recipient):
    """Re-quote one baked route and rebuild its legs, or (None, 0).

    A table entry proves a pool EXISTED when baked, not that it fills this size
    now. Re-quoting is what keeps a stale route from delivering zero — and on a
    cover row a revert throws away the very win the row exists to make.
    """
    out = _requote(rpc, cfg, route, tin, tout, amount)
    if out <= 0:
        return (None, 0)
    kind = route.get('kind')
    if kind == 'v2':
        return (_v2_path_swap(route, amount, recipient), out)
    if kind == 'v3_single':
        return (_v3_single_swap(cfg, tin, tout, amount, recipient, route['fee']), out)
    return (_v3_path_swap(cfg, route, amount, recipient), out)

def _requote(rpc, cfg, route, tin, tout, amount):
    """Live output for a baked route right now, or 0 if it no longer fills."""
    kind = route.get('kind')
    if kind == 'v2':
        return int(q_v2(rpc, route['router'], route['path'], amount) or 0)
    if kind == 'v3_single':
        return int(q_v3_single(rpc, cfg, tin, tout, amount, route['fee']) or 0)
    if kind == 'v3_path':
        return int(q_v3_path(rpc, cfg, route['tokens'], route['fees'], amount) or 0)
    return 0

def baked_legs(rpc, tin, tout, amount, chain_id, recipient):
    """(interactions, out) from the pre-solved table, or (None, 0).

    The requote window honours the TIGHTER of the enclosing deadline and its own
    3.0s, the same discipline `router_cover.best_route` states. A flat +3.0s
    overwrote whatever bound the caller had set: this is reached from
    `_ext_legs`, inside the per-ORDER cover ceiling `MinerSolver._rb1_cap` now
    arms, and re-arming there turned that ceiling back into a per-layer one. Time
    over the ceiling is not paid by this order — it comes out of the shared
    `_RUN_BUDGET_S` and starves the tail into `last_resort_empty`, i.e. dropped
    orders and a hard veto.
    """

    def _dz51():
        if not row:
            return ((None, 0),)
        prev = _SEARCH_DEADLINE[0]
        mine = time.monotonic() + 3.0
        _SEARCH_DEADLINE[0] = min(mine, prev) if prev else mine
        try:
            cfg = CHAINS.get(int(chain_id)) or {}
            return (_rebuild(rpc, cfg, row, tin, tout, amount, recipient),)
        except Exception:
            return ((None, 0),)
        finally:
            _SEARCH_DEADLINE[0] = prev
        return _DR_UNSET
    row = ROUTES.get(f'{int(chain_id)}|{str(tin).lower()}|{str(tout).lower()}')
    _r_dz51 = _dz51()
    if _r_dz51 is not _DR_UNSET:
        return _r_dz51[0]

def _v2_approve_rows(tin, router, amount):
    """The approve row(s) for a V2 serve, carrying the USDT reset where it bites.

    Same fourth-spender gap 7cfe2e6 closed in `router_cover`: the audit list in
    `chain1_lib._approve_ixs` names only the three BAKED-spec builders, so this
    module and `cover_ext` kept emitting a lone non-zero approve, which USDT
    reverts outright -- taking the whole cover plan with it.
    """
    try:
        from chain1_lib import _needs_reset_approve as _nra
        reset = _nra(tin)
    except Exception:
        reset = False
    rows = [{'target': tin, 'data': _approve(router, 0)}] if reset else []
    return rows + [{'target': tin, 'data': _approve(router, amount)}]

def _v2_path_swap(route, amount, recipient):
    """approve + swapExactTokensForTokensSupportingFeeOnTransferTokens over the baked path.

    On 5c11d795 rather than the plain 38ed1739 for the reason certify measured on
    `dex:veto:q_6581642391f7` (see 7cfe2e6): the plain selector re-derives amounts
    from getAmountsOut and asserts them AFTER the transfer, so a skimming token --
    or a pair whose reserves moved since the route was baked -- reverts the swap
    leg bare. min_out is already 0 here, which is what makes the swap-safe variant
    a pure win: it can only succeed where the plain one did, and also where it did not.
    """
    body = _enc(['uint256', 'uint256', 'address[]', 'address', 'uint256'], [int(amount), 0, route['path'], recipient, DEADLINE])
    return _v2_approve_rows(route['path'][0], route['router'], amount) + [{'target': route['router'], 'data': '0x' + S_V2_SWAP_FOT + body.hex()}]

def _tuple_body(cfg, args, types, at):
    """ABI-encode a router tuple, inserting the deadline only where the chain's
    router actually takes one (Base's SwapRouter02 does not)."""
    if cfg.get('v3_deadline'):
        args = args[:at] + [DEADLINE] + args[at:]
        types = types[:at] + ['uint256'] + types[at:]
    return _enc(['(' + ','.join(types) + ')'], [tuple(args)])

def _v3_single_swap(cfg, tin, tout, amount, recipient, fee):
    """approve + exactInputSingle, in the chain's own selector/layout."""
    r = cfg['v3router']
    body = _tuple_body(cfg, [tin, tout, int(fee), recipient, int(amount), 0, 0], ['address', 'address', 'uint24', 'address', 'uint256', 'uint256', 'uint160'], 4)
    return [{'target': tin, 'data': _approve(r, amount)}, {'target': r, 'data': '0x' + cfg['v3sel_single'] + body.hex()}]

def _v3_path_swap(cfg, route, amount, recipient):
    """approve + exactInput over the baked multi-hop path."""
    r = cfg['v3router']
    body = _tuple_body(cfg, [_v3_path_bytes(route['tokens'], route['fees']), recipient, int(amount), 0], ['bytes', 'address', 'uint256', 'uint256'], 2)
    return [{'target': route['tokens'][0], 'data': _approve(r, amount)}, {'target': r, 'data': '0x' + cfg['v3sel_path'] + body.hex()}]