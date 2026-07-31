"""UR command assembly for the V3->V4 combo legs. Split from exotic_v4 for the
AST-region budget.
"""
from __future__ import annotations

from cr_exotic_v4 import _CMD_UNWRAP, _CMD_V3, _CMD_V4, _v4_actions, CONTRACT_BALANCE, UR_ADDRESS_THIS


def _v3_leg(spec, ck):
    """V3_SWAP_EXACT_IN input: route into UR (has_v4), balance-in, packed path."""
    from cr_abi_util import encode_path
    from eth_abi import encode
    path = encode_path(list(spec["v3_tokens"]), [int(f) for f in spec["v3_fees"]])
    return encode(
        ["address", "uint256", "uint256", "bytes", "bool"],
        [ck(UR_ADDRESS_THIS), CONTRACT_BALANCE, 0, path, False],
    )


def _unwrap_input(ck) -> bytes:
    from eth_abi import encode
    return encode(["address", "uint256"], [ck(UR_ADDRESS_THIS), 0])


def _v4_input(spec, tout, recipient) -> bytes:
    from eth_abi import encode
    actions, params = _v4_actions(spec, tout, recipient)
    return encode(["bytes", "bytes[]"], [actions, params])


def build_commands(spec, tout, recipient, ck):
    """(commands_bytes, inputs[]) in the champion's order: v3 -> unwrap -> v4."""
    cmds, inputs = bytearray(), []
    if spec.get("v3_tokens"):
        cmds.append(_CMD_V3)
        inputs.append(_v3_leg(spec, ck))
    if spec.get("unwrap_weth"):
        cmds.append(_CMD_UNWRAP)
        inputs.append(_unwrap_input(ck))
    cmds.append(_CMD_V4)
    inputs.append(_v4_input(spec, tout, recipient))
    return bytes(cmds), inputs


