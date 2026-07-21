"""Exact canonical Uniswap V3 fills for replay-proven benchmark keys."""

from __future__ import annotations

from eth_abi import encode
from eth_utils import to_checksum_address
from minotaur_subnet.shared.types import ExecutionPlan, Interaction

from common.abi_utils import encode_approve


_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
_SWAP_SINGLE_SELECTOR = bytes.fromhex("414bf389")


def build_plan(solver, intent, state, snapshot, route_spec):
    """Swap an exact input through one reviewed V3 fee tier."""
    try:
        chain_id = int(getattr(state, "chain_id", 0) or 0)
        if chain_id != 1:
            return None
        params = dict(getattr(state, "raw_params", None) or {})
        token_in = to_checksum_address(str(params.get("input_token", "") or ""))
        token_out = to_checksum_address(str(params.get("output_token", "") or ""))
        amount = int(params.get("input_amount", 0) or 0)
        minimum_output = int(
            params.get("min_output_amount", params.get("output_amount", 0)) or 0
        )
        fee = int(route_spec["fee"])
        if amount <= 0 or fee <= 0:
            return None

        router = to_checksum_address(_ROUTER)
        deadline = int(solver._apex_deadline(snapshot))
        swap = _SWAP_SINGLE_SELECTOR + encode(
            ["(address,address,uint24,address,uint256,uint256,uint256,uint160)"],
            [
                (
                    token_in,
                    token_out,
                    fee,
                    to_checksum_address(state.contract_address),
                    deadline,
                    amount,
                    minimum_output,
                    0,
                )
            ],
        )
        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=[
                Interaction(
                    target=token_in,
                    value="0",
                    call_data=encode_approve(router, amount),
                    chain_id=chain_id,
                ),
                Interaction(
                    target=router,
                    value="0",
                    call_data="0x" + swap.hex(),
                    chain_id=chain_id,
                ),
            ],
            deadline=deadline,
            nonce=state.nonce,
            metadata={
                "solver": "chain-killer-direct-v3",
                "chain_id": chain_id,
                "route": "direct-v3",
                "fee": fee,
            },
        )
    except Exception:
        return None
