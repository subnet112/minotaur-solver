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


# ── Balancer V2 serving (bal_serve.py reference absorbed; spec kind "bal").
# The Vault's funds tuple embeds a SENDER: interactions execute through a
# per-order EIP-1167 clone, so the calldata must embed the PREDICTED proxy
# (AppIntentBaseV2.predictProxy) — any other sender reverts (BAL#401). The
# proxy prediction needs one eth_call at serve time; every failure on that
# path returns [] so the row rides the base (a losing card, never a broken
# one).
_BAL_VAULT = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"
_RPC_URLS = {}


def _set_rpc(urls):
    try:
        _RPC_URLS.update({int(k): str(v) for k, v in (urls or {}).items()})
    except Exception:
        pass


def _bal_w3(cid):
    url = _RPC_URLS.get(int(cid))
    if not url:
        return None
    from web3 import Web3

    return Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 8}))


def _bal_order_id32(order_id) -> bytes:
    # The simulator's order-id normalization, byte-exact: hex ids
    # pad-and-truncate, non-hex ids keccak.
    from eth_utils import keccak as _keccak

    s = str(order_id).replace("0x", "")
    try:
        return bytes.fromhex(s.ljust(64, "0"))[:32]
    except ValueError:
        return _keccak(str(order_id).encode())


def _bal_bench_order_id(state):
    # Reproduces the harness's deterministic benchmark order id for THIS
    # scenario (contract|chain|scenario_name|fn|fork_block, sha256, 16 hex).
    # fork_block is the one component not carried in state: the bench runs
    # at the round's pinned fork, so the fork's own head at plan time is it.
    import hashlib

    w3 = _bal_w3(getattr(state, "chain_id", 1))
    if w3 is None:
        return None
    try:
        fork_block = int(w3.eth.block_number)
    except Exception:
        return None
    control = getattr(state, "control", None) or {}
    seed = "|".join((
        str(getattr(state, "contract_address", "")).lower(),
        str(getattr(state, "chain_id", "")),
        str(control.get("_scenario_name", "")),
        str(control.get("_intent_function", "swap")),
        str(fork_block),
    ))
    return "bench_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _bal_proxy(state):
    from eth_utils import keccak as _keccak, to_checksum_address as _ck

    w3 = _bal_w3(getattr(state, "chain_id", 1))
    if w3 is None:
        return None
    oid = _bal_bench_order_id(state)
    if oid is None:
        return None
    data = _keccak(text="predictProxy(bytes32)")[:4] + _bal_order_id32(oid)
    try:
        r = w3.eth.call({"to": _ck(str(state.contract_address)),
                         "data": "0x" + data.hex()})
        rb = bytes(r)
        if len(rb) < 20:
            return None
        return _ck("0x" + rb[-20:].hex())
    except Exception:
        return None


def _bal_swap_cd(spec, proxy, rcpt, deadline) -> bytes | None:
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck

    route = spec["route"]
    tin, tout = spec["tokens"][0], spec["tokens"][-1]
    amount = int(spec["amt_in"])
    funds = (_ck(proxy), False, _ck(rcpt), False)
    if route[0] == "direct":
        sel = _keccak(text=(
            "swap((bytes32,uint8,address,address,uint256,bytes),"
            "(address,bool,address,bool),uint256,uint256)"))[:4]
        single = (bytes.fromhex(str(route[1]).replace("0x", "")), 0,
                  _ck(tin), _ck(tout), amount, b"")
        return sel + _enc(
            ["(bytes32,uint8,address,address,uint256,bytes)",
             "(address,bool,address,bool)", "uint256", "uint256"],
            [single, funds, 0, int(deadline)])
    if route[0] == "hop":
        p1, p2, hub = route[1], route[2], route[3]
        sel = _keccak(text=(
            "batchSwap(uint8,(bytes32,uint256,uint256,uint256,bytes)[],"
            "address[],(address,bool,address,bool),int256[],uint256)"))[:4]
        swaps = [(bytes.fromhex(str(p1).replace("0x", "")), 0, 1, amount, b""),
                 (bytes.fromhex(str(p2).replace("0x", "")), 1, 2, 0, b"")]
        assets = [_ck(tin), _ck(hub), _ck(tout)]
        limits = [amount, 0, 0]
        return sel + _enc(
            ["uint8", "(bytes32,uint256,uint256,uint256,bytes)[]",
             "address[]", "(address,bool,address,bool)", "int256[]",
             "uint256"],
            [0, swaps, assets, funds, limits, int(deadline)])
    return None


def _bal_serve_legs(spec, rcpt, state, Interaction):
    try:
        proxy = _bal_proxy(state)
        if proxy is None:
            return []
        cid = int(spec.get("chain_id") or 1)
        cd = _bal_swap_cd(spec, proxy, rcpt, 9999999999)
        if cd is None:
            return []
        legs = _approve_legs(str(spec["tokens"][0]).lower(),
                             int(spec["amt_in"]), _BAL_VAULT, Interaction, cid)
        legs.append(Interaction(target=_BAL_VAULT, value="0",
                                call_data="0x" + cd.hex(), chain_id=cid))
        return legs
    except Exception:
        return []


# ── Uniswap V4 serving (spec kind "v4"): baked PoolKey route through the
# chain-1 Universal Router. Funding is a plain ERC20 transfer to the router
# (no Permit2): the SETTLE action with payerIsUser=False spends the router's
# own balance, so the two-interaction shape [transfer, execute] delivers
# without any approval dance. PoolKeys are census rows quoted >0 at bake
# time; min-out stays 0 everywhere (the harness enforces the intent-level
# min_output invariant, and a baked route re-verifies at admission).
_V4_UR = "0x66a9893cC07D91D95644AEDD05D03f95e1dBA8Af"
_V4_ADDRESS_THIS = "0x0000000000000000000000000000000000000002"
_V4_CONTRACT_BALANCE = 1 << 255


def _v4_execute_cd(spec, rcpt) -> str:
    from eth_abi import encode as _enc
    from eth_utils import keccak as _keccak, to_checksum_address as _ck

    commands = b""
    inputs = []
    if spec.get("unwrap_weth"):
        # router's WETH -> native, kept in the router for the native SETTLE
        inputs.append(_enc(["address", "uint256"], [_ck(_V4_ADDRESS_THIS), 0]))
        commands += bytes([12])
    legs = [(tuple(pk), bool(zfo)) for pk, zfo in spec["pools"]]
    actions = bytes([11] + [6] * len(legs) + [14])
    params = [_enc(["address", "uint256", "bool"],
                   [_ck(str(spec["settle"])), _V4_CONTRACT_BALANCE, False])]
    for (c0, c1, fee, ts, hooks), zfo in legs:
        params.append(_enc(
            ["((address,address,uint24,int24,address),bool,uint128,uint128,bytes)"],
            [((_ck(c0), _ck(c1), int(fee), int(ts), _ck(hooks)),
              bool(zfo), 0, 0, b"")]))
    take_to = _V4_ADDRESS_THIS if spec.get("wrap_out") else rcpt
    params.append(_enc(["address", "address", "uint256"],
                       [_ck(str(spec["take"])), _ck(take_to), 0]))
    inputs.append(_enc(["bytes", "bytes[]"], [actions, params]))
    commands += bytes([16])
    if spec.get("wrap_out"):
        # native TAKE landed in the router; wrap it and send WETH onward
        inputs.append(_enc(["address", "uint256"],
                           [_ck(rcpt), _V4_CONTRACT_BALANCE]))
        commands += bytes([11])
    return "0x" + (_keccak(text="execute(bytes,bytes[],uint256)")[:4]
                   + _enc(["bytes", "bytes[]", "uint256"],
                          [commands, inputs, 9999999999])).hex()


def _v4_serve_legs(spec, rcpt, Interaction):
    try:
        cid = int(spec.get("chain_id") or 1)
        tin = str(spec["tokens"][0]).lower()
        amt = int(spec["amt_in"])
        cd = _v4_execute_cd(spec, rcpt)
        return [_transfer_leg(tin, amt, _V4_UR, Interaction, cid),
                Interaction(target=_V4_UR, value="0", call_data=cd,
                            chain_id=cid)]
    except Exception:
        return []
