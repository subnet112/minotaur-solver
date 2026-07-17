"""Uniswap V4 via the Universal Router — pure single-pool case of the
champion's `_shp_uniswap_v4_ur` (king_base.py:686-793).

Spec {pool, settle, zero_for_one, sweep_settle} -> one UR V4_SWAP command whose
actions are SETTLE, SWAP_EXACT_IN_SINGLE, TAKE (+SWEEP). Funded by transfer, not
approve; amountIn is the CONTRACT_BALANCE sentinel. Byte-verified vs the champion
on the 13 pure-shape pairs; combo specs (v3/v2/multi-pool) return None and fall
through — worse route, never a veto.
"""
from __future__ import annotations

UNIVERSAL_ROUTER = "0x6ff5693b99212da76ad316178a184ab56d299b43"
UR_ADDRESS_THIS = "0x0000000000000000000000000000000000000002"  # UR "route to self" sink
CONTRACT_BALANCE = 1 << 255  # UR sentinel: "use the router's full balance"
DEADLINE = 9999999999

# UR command opcodes: V3_SWAP_EXACT_IN=0x00, UNWRAP_WETH=0x0c, V4_SWAP=0x10.
_CMD_V3, _CMD_UNWRAP, _CMD_V4 = 0x00, 0x0C, 0x10
# V4 action opcodes (king_base.py:686-770): SETTLE, SWAP, TAKE, SWEEP.
_ACT = (11, 6, 14, 14)
_SWAP_SIG = "((address,address,uint24,int24,address),bool,uint128,uint128,bytes)"
# Kinds we still don't build (v2 leg, multi-pool v4) -> fall through.
_UNBUILT_KEYS = ("v2_tokens", "pools")


def _swap_param(spec, ck):
    from eth_abi import encode
    c0, c1, fee, tick, hooks = spec["pool"]
    pool = (ck(c0), ck(c1), int(fee), int(tick), ck(hooks))
    return encode([_SWAP_SIG], [(pool, bool(spec["zero_for_one"]), 0, 0, b"")])


def _addr_amt(a, b, ck, amt=0):
    """The SETTLE/TAKE/SWEEP param shape: (address, uint256-or-address, uint256)."""
    from eth_abi import encode
    if isinstance(b, int):
        return encode(["address", "uint256", "bool"], [ck(a), b, False])
    return encode(["address", "address", "uint256"], [ck(a), ck(b), amt])


def _v4_actions(spec, tout, recipient):
    """(actions_bytes, params[]) for a single-pool exact-in V4 swap."""
    from eth_utils import to_checksum_address as ck
    settle_a, swap_a, take_a, sweep_a = _ACT
    actions = [settle_a, swap_a, take_a]
    params = [_addr_amt(spec["settle"], CONTRACT_BALANCE, ck),
              _swap_param(spec, ck),
              _addr_amt(tout, recipient, ck)]
    if spec.get("sweep_settle"):
        actions.append(sweep_a)
        params.append(_addr_amt(spec["settle"], recipient, ck))
    return bytes(actions), params




def _transfer(tin, amount):
    """ERC-20 transfer(UR, amount) — the UR funds each leg from its own balance."""
    from eth_abi import encode
    from eth_utils import keccak, to_checksum_address as ck
    sel = keccak(text="transfer(address,uint256)")[:4]
    payload = encode(["address", "uint256"], [ck(UNIVERSAL_ROUTER), int(amount)])
    return "0x" + (sel + payload).hex()


def _wrap_execute(cmds, inputs) -> str:
    """UR.execute(commands, inputs, deadline) calldata."""
    from eth_abi import encode
    from eth_utils import keccak
    sel = keccak(text="execute(bytes,bytes[],uint256)")[:4]
    return "0x" + (sel + encode(["bytes", "bytes[]", "uint256"], [cmds, inputs, DEADLINE])).hex()


def build(spec, tin: str, tout: str, amount: int, recipient: str):
    """[transfer tin->UR, UR.execute(...)], or None to fall through.

    Handles the pure single-pool V4 shape and the V3->V4 combo (with optional
    WETH unwrap). A V2 leg or multi-pool V4 (`pools`) still isn't built — those
    return None; a wrong-shape plan drops the order (a hard veto), so falling
    through to the live sweep is the safe direction. Byte-verified vs the champion.
    """
    from eth_utils import to_checksum_address as ck
    from ur_commands import build_commands
    if not isinstance(spec, dict) or not spec.get("pool"):
        return None
    if any(spec.get(k) for k in _UNBUILT_KEYS):
        return None
    try:
        cmds, inputs = build_commands(spec, tout, recipient, ck)
        exec_call = _wrap_execute(cmds, inputs)
        transfer = _transfer(tin, amount)
    except Exception:
        return None
    return [
        {"target": tin, "value": "0", "data": transfer},
        {"target": UNIVERSAL_ROUTER, "value": "0", "data": exec_call},
    ]
