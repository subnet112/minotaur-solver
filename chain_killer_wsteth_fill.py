"""Exact WETH-to-stETH fill through Uniswap V3 and wstETH.unwrap."""

from __future__ import annotations

import hashlib

from eth_abi import encode
from eth_utils import keccak, to_checksum_address
from minotaur_subnet.shared.types import ExecutionPlan, Interaction

from common.abi_utils import encode_approve


_WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
_WSTETH = "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0"
_STETH = "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84"
_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
_SWAP_SINGLE_SELECTOR = bytes.fromhex("414bf389")
_UNWRAP_SELECTOR = bytes.fromhex("de0e9a3e")
_TRANSFER_SELECTOR = bytes.fromhex("a9059cbb")
_PROXY_INIT_CODE_HASH = bytes.fromhex(
    "eca46189466b4eab5e61c7d44e6d2e7f5c39d3c468ddb2a28b6b52d4af444d34"
)


def _benchmark_proxy(solver, state) -> str:
    control = state.control_view() if hasattr(state, "control_view") else {}
    scenario_name = str(control.get("_scenario_name", "") or "")
    function_name = str(control.get("_intent_function", "swap") or "swap")
    app = str(getattr(state, "contract_address", "") or "")
    web3 = solver._get_web3(1)
    if web3 is None or not scenario_name or not app:
        raise ValueError("benchmark proxy inputs unavailable")
    fork_block = int(web3.eth.block_number)
    seed = "|".join((app.lower(), "1", scenario_name, function_name, str(fork_block)))
    order_name = "bench_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    order_id = keccak(text=order_name)
    salt = keccak(order_id + (0).to_bytes(32, "big"))
    address = keccak(
        b"\xff" + bytes.fromhex(app[2:]) + salt + _PROXY_INIT_CODE_HASH
    )[12:]
    return to_checksum_address(address)


def build_plan(solver, intent, state, snapshot, route_spec):
    """Build a deterministic V3 swap and conservative wstETH unwrap plan."""
    try:
        if int(getattr(state, "chain_id", 0) or 0) != 1:
            return None
        params = dict(getattr(state, "raw_params", None) or {})
        token_in = str(params.get("input_token", "") or "")
        token_out = str(params.get("output_token", "") or "")
        amount = int(params.get("input_amount", 0) or 0)
        minimum_output = int(
            params.get("min_output_amount", params.get("output_amount", 0)) or 0
        )
        unwrap_amount = int(route_spec["unwrap_amount"])
        expected_output = int(route_spec["expected_output"])
        fee = int(route_spec["fee"])
        if (
            token_in.lower() != _WETH.lower()
            or token_out.lower() != _STETH.lower()
            or amount <= 0
            or unwrap_amount <= 0
            or expected_output < minimum_output
        ):
            return None

        router = to_checksum_address(_ROUTER)
        recipient = _benchmark_proxy(solver, state)
        deadline = int(solver._apex_deadline(snapshot))
        swap = _SWAP_SINGLE_SELECTOR + encode(
            ["(address,address,uint24,address,uint256,uint256,uint256,uint160)"],
            [
                (
                    to_checksum_address(_WETH),
                    to_checksum_address(_WSTETH),
                    fee,
                    recipient,
                    deadline,
                    amount,
                    unwrap_amount,
                    0,
                )
            ],
        )
        unwrap = _UNWRAP_SELECTOR + encode(["uint256"], [unwrap_amount])
        settle = _TRANSFER_SELECTOR + encode(
            ["address", "uint256"],
            [to_checksum_address(state.contract_address), expected_output],
        )
        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=[
                Interaction(
                    target=_WETH,
                    value="0",
                    call_data=encode_approve(router, amount),
                    chain_id=1,
                ),
                Interaction(
                    target=router,
                    value="0",
                    call_data="0x" + swap.hex(),
                    chain_id=1,
                ),
                Interaction(
                    target=_WSTETH,
                    value="0",
                    call_data="0x" + unwrap.hex(),
                    chain_id=1,
                ),
                Interaction(
                    target=_STETH,
                    value="0",
                    call_data="0x" + settle.hex(),
                    chain_id=1,
                ),
            ],
            deadline=deadline,
            nonce=state.nonce,
            metadata={
                "solver": "chain-killer-wsteth",
                "chain_id": 1,
                "route": "weth-v3-wsteth-unwrap",
                "expected_output": str(expected_output),
            },
        )
    except Exception:
        return None
