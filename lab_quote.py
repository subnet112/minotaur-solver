"""Batched venue quoting for the labyrinth layer.

Every candidate route for an order is quoted in ONE Multicall3 aggregate3
eth_call at the round's PINNED block, through the champion's own RPC channel
(the caller supplies w3 + block). One RPC roundtrip per blind order keeps the
layer inside the per-plan budget even on empty-heavy corpora.

A candidate that reverts (nonexistent pool, wrong venue for the pair) simply
comes back ok=False and quotes 0 — fail-closed, never fatal.
"""
from __future__ import annotations

from eth_abi import decode as abi_decode, encode as abi_encode
from eth_utils import to_checksum_address as ck

import lab_data as D


def _pack_path(tokens, fees) -> bytes:
    path = b""
    for i, token in enumerate(tokens):
        path += bytes.fromhex(token[2:] if token.startswith("0x") else token)
        if i < len(fees):
            path += int(fees[i]).to_bytes(3, byteorder="big")
    return path


def _v3_cand(cfg, tokens, fees, amt):
    path = _pack_path([ck(t) for t in tokens], fees)
    data = D.SEL_V3_QUOTE_PATH + abi_encode(["bytes", "uint256"], [path, int(amt)])
    return {
        "kind": "v3",
        "quote_to": cfg["v3_quoter"],
        "data": data,
        "decode": "first32",
        "router": cfg["v3_router"],
        "tokens": tuple(tokens),
        "fees": tuple(fees),
    }


def _v2_cand(router, tokens, amt):
    data = D.SEL_V2_AMOUNTS + abi_encode(
        ["uint256", "address[]"], [int(amt), [ck(t) for t in tokens]]
    )
    return {
        "kind": "v2",
        "quote_to": router,
        "data": data,
        "decode": "amounts",
        "router": router,
        "tokens": tuple(tokens),
    }


def _aero_cand(cfg, routes, amt):
    rts = [(ck(f), ck(t), bool(s), ck(cfg["aero_factory"])) for f, t, s in routes]
    data = D.SEL_AERO_AMOUNTS + abi_encode(
        ["uint256", "(address,address,bool,address)[]"], [int(amt), rts]
    )
    return {
        "kind": "aero",
        "quote_to": cfg["aero_router"],
        "data": data,
        "decode": "amounts",
        "router": cfg["aero_router"],
        "routes": tuple(rts),
    }


def candidates(cid: int, tin: str, tout: str, amt: int):
    """Enumerate candidate routes for (tin -> tout, amt) on this chain."""
    cfg = D.CH.get(cid)
    if not cfg:
        return []
    tin_l, tout_l = tin.lower(), tout.lower()
    cands = []

    for fee in cfg["v3_single_fees"]:
        cands.append(_v3_cand(cfg, (tin, tout), (fee,), amt))
    for hub in cfg["v3_hubs"]:
        if hub.lower() in (tin_l, tout_l):
            continue
        for f1 in cfg["v3_hub_fees"]:
            for f2 in cfg["v3_hub_fees"]:
                cands.append(_v3_cand(cfg, (tin, hub, tout), (f1, f2), amt))

    for router in cfg["v2_routers"]:
        cands.append(_v2_cand(router, (tin, tout), amt))
        for hub in cfg["v2_hubs"]:
            if hub.lower() in (tin_l, tout_l):
                continue
            cands.append(_v2_cand(router, (tin, hub, tout), amt))
        for m1, m2 in cfg["v2_three_hop"]:
            if m1.lower() in (tin_l, tout_l) or m2.lower() in (tin_l, tout_l):
                continue
            cands.append(_v2_cand(router, (tin, m1, m2, tout), amt))

    if cfg["aero_router"]:
        cands.append(_aero_cand(cfg, ((tin, tout, False),), amt))
        cands.append(_aero_cand(cfg, ((tin, tout, True),), amt))
        for hub in cfg["aero_hubs"]:
            if hub.lower() in (tin_l, tout_l):
                continue
            for s1, s2 in ((False, False), (False, True), (True, False)):
                cands.append(
                    _aero_cand(cfg, ((tin, hub, s1), (hub, tout, s2)), amt)
                )
    return cands


def batch_quote(w3, block, cands):
    """One aggregate3 eth_call; returns per-candidate quoted output (0 = dead)."""
    calls = [(ck(c["quote_to"]), True, c["data"]) for c in cands]
    payload = D.SEL_AGG3 + abi_encode(["(address,bool,bytes)[]"], [calls])
    raw = w3.eth.call({"to": ck(D.MULTICALL3), "data": "0x" + payload.hex()}, block)
    results = abi_decode(["(bool,bytes)[]"], bytes(raw))[0]
    outs = []
    for cand, (ok, rb) in zip(cands, results):
        out = 0
        if ok and len(rb) >= 32:
            try:
                if cand["decode"] == "first32":
                    out = int.from_bytes(rb[:32], "big")
                else:
                    amounts = abi_decode(["uint256[]"], bytes(rb))[0]
                    out = int(amounts[-1]) if amounts else 0
            except Exception:
                out = 0
        outs.append(out)
    return outs


def best_cover(w3, block, cid: int, tin: str, tout: str, amt: int):
    """Best live route for the order, or (0, None). Exceptions bubble up."""
    cands = candidates(cid, tin, tout, amt)
    if not cands:
        return 0, None
    outs = batch_quote(w3, block, cands)
    best_i, best_out = -1, 0
    for i, out in enumerate(outs):
        if out > best_out:
            best_i, best_out = i, out
    if best_i < 0:
        return 0, None
    return best_out, cands[best_i]
