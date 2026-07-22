"""Interaction builders for the labyrinth layer's winning route.

Plan shape mirrors the champion lineage exactly: [approve(input_token ->
router), router.swap(recipient=order recipient)], value '0', deadline
9999999999. The output token is delivered directly to the recipient so the
raw-output scorer credits it.
"""
from __future__ import annotations

from eth_abi import encode as abi_encode
from eth_utils import to_checksum_address as ck

from common.abi_utils import encode_approve
from minotaur_subnet.shared.types import Interaction
from strategies.dex_aggregator.v3_codec import (
    encode_exact_input,
    encode_exact_input_single,
    encode_swap_path,
)

import lab_data as D

DEADLINE = 9999999999


def _v3_call(cid, cand, amt, min_req, recip):
    tokens = [ck(t) for t in cand["tokens"]]
    fees = list(cand["fees"])
    if len(tokens) == 2:
        return encode_exact_input_single(
            tokens[0], tokens[1], fees[0], ck(recip), DEADLINE, amt, min_req, 0, cid
        )
    path = encode_swap_path(tokens, fees)
    if cid == 8453:
        # SwapRouter02 exactInput has no deadline field.
        params = abi_encode(
            ["(bytes,address,uint256,uint256)"], [(path, ck(recip), amt, min_req)]
        )
        return "0x" + (D.SEL_V3_EXACT_INPUT_02 + params).hex()
    return encode_exact_input(path, ck(recip), DEADLINE, amt, min_req)


def _v2_call(cand, amt, min_req, recip):
    params = abi_encode(
        ["uint256", "uint256", "address[]", "address", "uint256"],
        [amt, min_req, [ck(t) for t in cand["tokens"]], ck(recip), DEADLINE],
    )
    return "0x" + (D.SEL_V2_SWAP + params).hex()


def _aero_call(cand, amt, min_req, recip):
    params = abi_encode(
        ["uint256", "uint256", "(address,address,bool,address)[]", "address", "uint256"],
        [amt, min_req, list(cand["routes"]), ck(recip), DEADLINE],
    )
    return "0x" + (D.SEL_AERO_SWAP + params).hex()


def build_ix(cid: int, cand, tin: str, amt: int, min_req: int, recip: str):
    """[approve, swap] interactions for the winning candidate, or None."""
    kind = cand["kind"]
    if kind == "v3":
        call = _v3_call(cid, cand, amt, min_req, recip)
    elif kind == "v2":
        call = _v2_call(cand, amt, min_req, recip)
    elif kind == "aero":
        call = _aero_call(cand, amt, min_req, recip)
    else:
        return None
    router = ck(cand["router"])
    return [
        Interaction(
            target=ck(tin), value="0", call_data=encode_approve(router, amt), chain_id=cid
        ),
        Interaction(target=router, value="0", call_data=call, chain_id=cid),
    ]
