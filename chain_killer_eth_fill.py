"""Live Ethereum V3 route fills for scorecard-proven Harvey gaps."""

from __future__ import annotations

from eth_abi import decode, encode
from eth_utils import to_checksum_address
from minotaur_subnet.shared.types import ExecutionPlan, Interaction

from common.abi_utils import encode_approve


_MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"
_QUOTER = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"
_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
_WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
_USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
_SINGLE_SELECTOR = bytes.fromhex("c6a5026a")
_PATH_SELECTOR = bytes.fromhex("cdca1753")
_AGGREGATE3_SELECTOR = bytes.fromhex("82ad56cb")
_SWAP_SINGLE_SELECTOR = bytes.fromhex("414bf389")
_SWAP_PATH_SELECTOR = bytes.fromhex("c04b8d59")
_FEE_TIERS = (100, 500, 3000, 10000)


def _address_bytes(address: str) -> bytes:
    return bytes.fromhex(address[2:].rjust(40, "0"))


def _single_calldata(token_in: str, token_out: str, amount: int, fee: int) -> bytes:
    params = (token_in, token_out, amount, fee, 0)
    return _SINGLE_SELECTOR + encode(
        ["(address,address,uint256,uint24,uint160)"], [params]
    )


def _path_calldata(tokens: list[str], fees: list[int], amount: int) -> bytes:
    path = b""
    for index, token in enumerate(tokens):
        path += _address_bytes(token)
        if index < len(fees):
            path += fees[index].to_bytes(3, "big")
    return _PATH_SELECTOR + encode(["bytes", "uint256"], [path, amount])


def _path_bytes(tokens: list[str], fees: list[int]) -> bytes:
    path = b""
    for index, token in enumerate(tokens):
        path += _address_bytes(token)
        if index < len(fees):
            path += fees[index].to_bytes(3, "big")
    return path


def _multicall_outputs(web3, calls: list[bytes]) -> list[int]:
    subcalls = [(_QUOTER, True, call) for call in calls]
    payload = _AGGREGATE3_SELECTOR + encode(
        ["(address,bool,bytes)[]"], [subcalls]
    )
    raw = web3.eth.call(
        {"to": web3.to_checksum_address(_MULTICALL3), "data": "0x" + payload.hex()}
    )
    (results,) = decode(["(bool,bytes)[]"], raw)
    outputs = []
    for ok, data in results:
        try:
            outputs.append(decode(["uint256"], data[:32])[0] if ok and len(data) >= 32 else 0)
        except Exception:
            outputs.append(0)
    return outputs


def _best_route(web3, token_in: str, token_out: str, amount: int):
    best = None
    direct_calls = [
        _single_calldata(token_in, token_out, amount, fee) for fee in _FEE_TIERS
    ]
    try:
        direct_outputs = _multicall_outputs(web3, direct_calls)
    except Exception:
        direct_outputs = []
    for fee, output in zip(_FEE_TIERS, direct_outputs):
        if output > 0 and (best is None or output > best["out"]):
            best = {"kind": "direct", "fee": fee, "out": output}

    for hub in (_USDC, _WETH):
        if hub.lower() in (token_in.lower(), token_out.lower()):
            continue
        combos = (
            ((500, 100), (3000, 100), (100, 500), (100, 3000))
            if hub == _USDC
            else ((500, 500), (3000, 3000), (500, 3000), (3000, 500))
        )
        calls = [
            _path_calldata([token_in, hub, token_out], [fee1, fee2], amount)
            for fee1, fee2 in combos
        ]
        try:
            path_outputs = _multicall_outputs(web3, calls)
        except Exception:
            path_outputs = []
        for (fee1, fee2), output in zip(combos, path_outputs):
            if output > 0 and (best is None or output > best["out"]):
                best = {
                    "kind": "2hop",
                    "hub": hub,
                    "fee1": fee1,
                    "fee2": fee2,
                    "out": output,
                }
    return best


def _execution_plan(
    solver,
    intent,
    state,
    snapshot,
    params,
    token_in: str,
    token_out: str,
    amount: int,
    route,
):
    router = to_checksum_address(_ROUTER)
    token_in = to_checksum_address(token_in)
    token_out = to_checksum_address(token_out)
    recipient = to_checksum_address(solver._apex_recipient(state, params))
    deadline = int(solver._apex_deadline(snapshot))
    amount_out_minimum = int(params.get("min_output_amount", 0) or 0)
    if route["kind"] == "direct":
        swap_data = _SWAP_SINGLE_SELECTOR + encode(
            ["(address,address,uint24,address,uint256,uint256,uint256,uint160)"],
            [
                (
                    token_in,
                    token_out,
                    int(route["fee"]),
                    recipient,
                    deadline,
                    amount,
                    amount_out_minimum,
                    0,
                )
            ],
        )
    else:
        path = _path_bytes(
            [token_in, to_checksum_address(route["hub"]), token_out],
            [int(route["fee1"]), int(route["fee2"])],
        )
        swap_data = _SWAP_PATH_SELECTOR + encode(
            ["(bytes,address,uint256,uint256,uint256)"],
            [(path, recipient, deadline, amount, amount_out_minimum)],
        )
    interactions = [
        Interaction(
            target=token_in,
            value="0",
            call_data=encode_approve(router, amount),
            chain_id=1,
        ),
        Interaction(
            target=router,
            value="0",
            call_data="0x" + swap_data.hex(),
            chain_id=1,
        ),
    ]
    return ExecutionPlan(
        intent_id=intent.app_id,
        interactions=interactions,
        deadline=deadline,
        nonce=state.nonce,
        metadata={
            "solver": "chain-killer-eth-v3",
            "chain_id": 1,
            "route": route["kind"],
            "expected_output": str(route["out"]),
        },
    )


def build_plan(solver, intent, state, snapshot, minimum_output: int):
    """Return a live-quoted V3 plan, or None so the Harvey plan remains exact."""
    try:
        if int(getattr(state, "chain_id", 0) or 0) != 1:
            return None
        params = solver._normalized_swap_params(intent, state)
        token_in = str(params.get("input_token", "") or "")
        token_out = str(params.get("output_token", "") or "")
        amount = int(params.get("input_amount", 0) or 0)
        try:
            amount = solver._effective_swap_amount(
                solver._fee_params(state, params), token_in, amount
            )
        except Exception:
            pass
        if not token_in or not token_out or amount <= 0:
            return None
        web3 = solver._get_web3(1)
        if web3 is None:
            return None
        route = _best_route(web3, token_in, token_out, amount)
        required = max(
            minimum_output,
            int(params.get("min_output_amount", 0) or 0),
        )
        if not route or int(route["out"]) < required:
            return None
        return _execution_plan(
            solver,
            intent,
            state,
            snapshot,
            params,
            token_in,
            token_out,
            amount,
            route,
        )
    except Exception:
        return None
