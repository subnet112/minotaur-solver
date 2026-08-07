"""g2 codec + leg builders — split from g2_fill (region hygiene: each
module top is its own region; the serve/table/guard logic stays in g2_fill).
Routing constants live here with the builders that consume them."""
from __future__ import annotations

_ROUTER_V3 = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
_ROUTER_V2 = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
# Per-chain router registry: table entries carry chain_id; a chain absent
# here cannot serve (the spec's own "router" field overrides per entry).
# Base (8453) rides the same multi-hop exactInput layout — SwapRouter02
# keeps the deadline-included exactInput on every deployed chain; addresses
# are the reigning tree's own deployment constants.
_ROUTERS = {
    1: {"v3": _ROUTER_V3, "v2": _ROUTER_V2},
    8453: {"v3": "0x2626664c2603336E57B271c5C0b26F421741e481",
           "v2": "0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24"},
}
_USDT = "0xdac17f958d2ee523a2206206994597c13d831ec7"


def _chain_ready(spec) -> bool:
    """Early per-chain capability gate: a spec row on a chain with neither a
    registry entry nor its own router override cannot build legs — fail
    closed before any leg assembly instead of inside the builders."""
    if spec.get("router"):
        return True
    cid = int(spec.get("chain_id") or 1)
    return cid in _ROUTERS


def _router_for(spec, venue):
    r = spec.get("router")
    if r:
        return str(r)
    cid = int(spec.get("chain_id") or 1)
    return (_ROUTERS.get(cid) or {}).get(venue)


def _pack_path(tokens, fees) -> bytes:
    b = b""
    for i, t in enumerate(tokens):
        b += bytes.fromhex(str(t)[2:])
        if i < len(fees):
            b += int(fees[i]).to_bytes(3, "big")
    return b


def _v3_swap_cd(spec, rcpt) -> str:
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck

    sel = _keccak(text="exactInput((bytes,address,uint256,uint256,uint256))")[:4]
    args = _enc(
        ["(bytes,address,uint256,uint256,uint256)"],
        [(_pack_path(spec["tokens"], spec.get("fees") or []), _ck(rcpt),
          9999999999, int(spec["amt_in"]), 0)],
    )
    return "0x" + (sel + args).hex()


def _v2_swap_cd(spec, rcpt) -> str:
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck

    args = _enc(
        ["uint256", "uint256", "address[]", "address", "uint256"],
        [int(spec["amt_in"]), 0, [_ck(t) for t in spec["tokens"]],
         _ck(rcpt), 9999999999],
    )
    return "0x5c11d795" + args.hex()


def _curve_abi(flavor, recv=False):
    """(signature, arg types) for a curve pool's exchange entrypoint. The
    int128 index width is the stable/underlying convention; crypto pools take
    uint256 indices — a mismatch encodes a valid-looking call that reverts.

    recv=True selects the RECEIVER overload, which pays an explicit address
    instead of msg.sender. That matters beyond convenience: without it a
    curve-final route must append a transfer of a BAKED amount, and a route
    that thins past that amount reverts and delivers nothing — a dropped row,
    which is an un-nettable veto. Paying the recipient inside the swap removes
    that failure mode entirely. Only pools whose bytecode carries the overload
    may set it (checked at bake time); assuming it would encode a call the
    pool cannot answer."""
    idx = "uint256" if flavor == "crypto" else "int128"
    name = "exchange_underlying" if flavor == "underlying" else "exchange"
    if recv == "6a":
        # NG crypto pools: exchange(i, j, dx, min_dy, use_eth, receiver) —
        # the only receiver form their bytecode carries (ce7d6503).
        args = [idx, idx, "uint256", "uint256", "bool", "address"]
    else:
        args = [idx, idx, "uint256", "uint256"] + (["address"] if recv else [])
    return (f"{name}({','.join(args)})", args)


def _curve_swap_cd(hop, rcpt=None) -> str:
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck

    dx, i, j = int(hop["dx"]), int(hop["i"]), int(hop["j"])
    recv = hop.get("recv") if rcpt is not None else None
    recv = "6a" if recv == "6a" else bool(recv)
    sig, types = _curve_abi(hop.get("flavor") or "stable", recv)
    sel = _keccak(text=sig)[:4]
    if recv == "6a":
        args = [i, j, dx, 0, False, _ck(rcpt)]
    else:
        args = [i, j, dx, 0] + ([_ck(rcpt)] if recv else [])
    return "0x" + (sel + _enc(types, args)).hex()


# The benchmark's interaction executor (the account plans run AS): every
# non-final leg's proceeds must land HERE so the next leg can spend them —
# the scored recipient only receives from the FINAL leg.
_EXECUTOR = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


def _hop_target_cd(spec, hop, is_last, rcpt):
    """(target, calldata) for one hop. v3 hops carry an explicit recipient:
    the FINAL hop pays rcpt, a MID hop pays the executor so the next hop's
    input is actually held by the spender. Curve exchange pays msg.sender
    (the executor), never the scored recipient."""
    if hop["kind"] == "v3":
        cd = _v3_swap_cd({"tokens": hop["tokens"],
                          "fees": hop.get("fees") or [],
                          "amt_in": int(hop["dx"])},
                         rcpt if is_last else _EXECUTOR)
        return _router_for(spec, "v3"), cd
    return hop["pool"], _curve_swap_cd(hop, rcpt if is_last else None)


def _hop_legs(spec, hop, is_last, rcpt, Interaction, cid):
    """Approve + swap legs for one hop; [] when the hop has no routable
    target (fails the whole route closed)."""
    target, cd = _hop_target_cd(spec, hop, is_last, rcpt)
    if not target:
        return []
    legs = _approve_legs(str(hop["tokens"][0]).lower(), int(hop["dx"]),
                         target, Interaction, cid)
    legs.append(Interaction(target=target, value="0", call_data=cd,
                            chain_id=cid))
    return legs


def _final_transfer(spec, rcpt, Interaction, cid):
    """Curve-FINAL routes need an explicit transfer moving the output from
    the executor to rcpt, or the scorer measures zero (measured: 3 curve
    routes executed clean, on-chain score 5000, raw_output 0)."""
    last = spec["hops"][-1]
    if last["kind"] == "v3" or not spec.get("out"):
        return None
    if last.get("recv"):
        return None  # the swap paid rcpt directly — no baked amount to revert on
    bps = int(spec.get("transfer_bps") or 9500)
    return _transfer_leg(str(last["tokens"][-1]),
                         int(spec["out"]) * bps // 10000,
                         rcpt, Interaction, cid)


def _route_legs(spec, rcpt, Interaction):
    # Multi-hop covers (curve and/or v3 legs) with per-hop exact inputs
    # baked at probe time (3% haircut per intermediate).
    legs = []
    cid = int(spec.get("chain_id") or 1)
    n = len(spec["hops"])
    for idx, hop in enumerate(spec["hops"]):
        built = _hop_legs(spec, hop, idx == n - 1, rcpt, Interaction, cid)
        if not built:
            return []
        legs += built
    extra = _final_transfer(spec, rcpt, Interaction, cid)
    if extra is not None:
        legs.append(extra)
    return legs


def _transfer_leg(token, amt, rcpt, Interaction, cid=1):
    # Plain ERC20 transfer(rcpt, amt) from the executor's balance: 95% of the
    # discovery-quoted out (pin-frozen state makes the realized out
    # deterministic; the 5% margin absorbs discovery-vs-pin drift so the
    # transfer never pulls more than the route produced).
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck

    cd = "0xa9059cbb" + _enc(["address", "uint256"], [_ck(rcpt), amt]).hex()
    return Interaction(target=token, value="0", call_data=cd, chain_id=cid)


def _approve_legs(tin, amt, router, Interaction, cid=1):
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve

    legs = []
    if cid == 1 and tin == _USDT:
        legs.append(Interaction(target=tin, value="0",
                                call_data=encode_approve(_ck(router), 0),
                                chain_id=cid))
    legs.append(Interaction(target=tin, value="0",
                            call_data=encode_approve(_ck(router), amt),
                            chain_id=cid))
    return legs


def _legs(spec, rcpt, Interaction):
    if spec.get("venue") == "route":
        return _route_legs(spec, rcpt, Interaction)
    cid = int(spec.get("chain_id") or 1)
    tin = str(spec["tokens"][0]).lower()
    amt = int(spec["amt_in"])
    if spec.get("venue") == "v2":
        router, swap_cd = _router_for(spec, "v2"), _v2_swap_cd(spec, rcpt)
    else:
        router, swap_cd = _router_for(spec, "v3"), _v3_swap_cd(spec, rcpt)
    if not router:
        return []
    legs = _approve_legs(tin, amt, router, Interaction, cid)
    legs.append(Interaction(target=router, value="0", call_data=swap_cd,
                            chain_id=cid))
    return legs
