"""Curve live-pool cover for blueguider (fill-only-empty).

Loaded by solver.py; fires ONLY when the wrapped champion returns empty/blind.
Census (curve_census.json, offline factory enumeration) gives candidate pools
containing both tokens; we quote get_dy on the SOLVER'S w3 (the round-pinned
fork, so the quote is exactly what will execute) and, if it clears the order's
min_output, emit approve(pool)+exchange — pulls from msg.sender (the app proxy)
exactly like the champion's own V2/V3 swaps, so it executes through scoreIntent.

Curve is uncontested: the champion lineage carries only a hardcoded per-pool
`curve_full` static table, and Balancer's Vault (the other absent venue) needs
an explicit funds.sender = the unknowable per-exec proxy, so it can't execute
this way. Every function stays under the factorization region floor.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _types():
    from minotaur_subnet.shared.types import ExecutionPlan, Interaction
    return ExecutionPlan, Interaction


def _load():
    try:
        p = Path(__file__).parent / "curve_census.json"
        if p.is_file():
            d = json.loads(p.read_text())
            return d.get("pools", {}), d.get("bytoken", {})
    except Exception:
        logger.exception("[curve] census load failed")
    return {}, {}


_POOLS, _BYTOKEN = _load()
_IDX = {"stable": "int128", "crypto": "uint256"}


def _w3(solver):
    w3 = getattr(solver, "_curve_w3", None)
    if w3 is not None:
        return w3
    import os
    from web3 import Web3
    urls = getattr(solver, "rpc_urls", {}) or {}
    url = (urls.get("8453") or urls.get(8453)
           or os.environ.get("BASE_RPC_URL", "https://mainnet.base.org"))
    w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 4}))
    solver._curve_w3 = w3
    return w3


def _sel(sig):
    from eth_utils import keccak
    return keccak(sig.encode())[:4]


def _call(w3, to, sig, argtypes, args, rettypes):
    from eth_abi import encode as enc, decode as dec
    from eth_utils import to_checksum_address as ck
    data = _sel(sig) + (enc(argtypes, args) if argtypes else b"")
    return dec(rettypes, w3.eth.call({"to": ck(to), "data": data}))


def _candidates(tin, tout):
    return list(set(_BYTOKEN.get(tin, ())) & set(_BYTOKEN.get(tout, ())))


def _quote(w3, pool, kind, i, j, amt):
    x = _IDX[kind]
    try:
        return _call(w3, pool, "get_dy(%s,%s,uint256)" % (x, x),
                     [x, x, "uint256"], [i, j, amt], ["uint256"])[0]
    except Exception:
        return 0


def _pool_ij(pool, tin, tout):
    info = _POOLS.get(pool) or {}
    coins = info.get("coins") or []
    if tin not in coins or tout not in coins:
        return None
    return coins.index(tin), coins.index(tout), info.get("kind", "stable")


def _best_pool(w3, tin, tout, amt):
    best = (0, None, None, None, None)  # out, pool, kind, i, j
    for pool in _candidates(tin, tout)[:6]:
        ij = _pool_ij(pool, tin, tout)
        if ij is None:
            continue
        i, j, kind = ij
        out = _quote(w3, pool, kind, i, j, amt)
        if out > best[0]:
            best = (out, pool, kind, i, j)
    return best


def _approve_ix(tin, pool, amt, chain_id):
    from eth_abi import encode as enc
    from eth_utils import to_checksum_address as ck
    cd = "0x095ea7b3" + enc(["address", "uint256"], [ck(pool), amt]).hex()
    _, Interaction = _types()
    return Interaction(target=ck(tin), value="0", call_data=cd, chain_id=chain_id)


def _exchange_ix(pool, kind, i, j, amt, min_dy, recipient, chain_id):
    from eth_abi import encode as enc
    from eth_utils import to_checksum_address as ck
    x = _IDX[kind]
    sig = "exchange(%s,%s,uint256,uint256,address)" % (x, x)
    body = enc([x, x, "uint256", "uint256", "address"],
               [i, j, amt, min_dy, ck(recipient)])
    cd = "0x" + (_sel(sig) + body).hex()
    _, Interaction = _types()
    return Interaction(target=ck(pool), value="0", call_data=cd, chain_id=chain_id)


def _lc(p, key):
    return str(p.get(key, "") or "").lower()


def _iv(p, key):
    try:
        return int(p.get(key, 0) or 0)
    except (TypeError, ValueError):
        return -1


def _ok(chain_id, amt, min_out, tin, tout):
    return chain_id == 8453 and amt > 0 and min_out >= 0 and bool(tin) and bool(tout)


def _parse(state):
    p = dict(getattr(state, "raw_params", {}) or {})
    tin, tout = _lc(p, "input_token"), _lc(p, "output_token")
    amt, min_out = _iv(p, "input_amount"), _iv(p, "min_output_amount")
    chain_id = int(getattr(state, "chain_id", 0) or 0)
    if not _ok(chain_id, amt, min_out, tin, tout):
        return None
    return p, tin, tout, amt, min_out, chain_id


def _recipient(state, p):
    return str(getattr(state, "contract_address", "") or p.get("receiver", "")
               or getattr(state, "owner", "")
               or "0x0000000000000000000000000000000000000001")


def _plan(intent, state, ix, chain_id):
    ExecutionPlan, _ = _types()
    return ExecutionPlan(intent_id=intent.app_id, interactions=ix,
                         deadline=9999999999, nonce=state.nonce,
                         metadata={"solver": "bg124-curve", "chain_id": chain_id})


def _route(solver, state):
    """(p, tin, pool, kind, i, j, amt, min_dy, chain_id) or None."""
    parsed = _parse(state)
    if parsed is None:
        return None
    p, tin, tout, amt, min_out, chain_id = parsed
    out, pool, kind, i, j = _best_pool(_w3(solver), tin, tout, amt)
    if not pool or out < max(min_out, 1):
        return None
    return p, tin, pool, kind, i, j, amt, max(min_out, 1), chain_id


def _cover(solver, intent, state):
    r = _route(solver, state)
    if r is None:
        return None
    p, tin, pool, kind, i, j, amt, min_dy, chain_id = r
    ix = [_approve_ix(tin, pool, amt, chain_id),
          _exchange_ix(pool, kind, i, j, amt, min_dy, _recipient(state, p), chain_id)]
    return _plan(intent, state, ix, chain_id)


def try_cover(solver, intent, state):
    """Champion-empty Curve cover. Returns an ExecutionPlan or None."""
    if not _BYTOKEN:
        return None
    try:
        return _cover(solver, intent, state)
    except Exception:
        logger.exception("[curve] cover failed; champion plan stands")
        return None
