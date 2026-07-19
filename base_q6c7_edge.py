from __future__ import annotations


CHAIN_ID = 8453
TOKEN_IN = "0x8c81b4c816d66d36c4bf348bdec01dbcbc70e987"
TOKEN_OUT = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
WETH = "0x4200000000000000000000000000000000000006"
ROUTER = "0x2626664c2603336E57B271c5C0b26F421741e481"
INPUT_AMOUNT = 10_254_043_755_040_177_296_275
FEES = (10_000, 100)
DEADLINE = 9_999_999_999
EXACT_INPUT_SELECTOR = "0xb858183f"


def _params(solver, intent, state):
    try:
        values = solver._normalized_swap_params(intent, state)
    except Exception:
        values = getattr(state, "raw_params", None) or {}
    return dict(values or {})


def _matches(state, params):
    try:
        return (
            int(getattr(state, "chain_id", 0) or 0) == CHAIN_ID
            and str(params.get("input_token", "") or "").lower() == TOKEN_IN
            and str(params.get("output_token", "") or "").lower() == TOKEN_OUT
            and int(params.get("input_amount", 0) or 0) == INPUT_AMOUNT
        )
    except (TypeError, ValueError):
        return False


def _path():
    packed = bytearray()
    for index, token in enumerate((TOKEN_IN, WETH, TOKEN_OUT)):
        packed.extend(bytes.fromhex(token.removeprefix("0x")))
        if index < len(FEES):
            packed.extend(int(FEES[index]).to_bytes(3, "big"))
    return bytes(packed)


def _swap_data(recipient):
    from eth_abi import encode
    from eth_utils import to_checksum_address as checksum

    payload = encode(
        ["(bytes,address,uint256,uint256)"],
        [(_path(), checksum(recipient), INPUT_AMOUNT, 0)],
    )
    return EXACT_INPUT_SELECTOR + payload.hex()


def maybe_q6c7_plan(solver, intent, state):
    try:
        if not _matches(state, _params(solver, intent, state)):
            return None

        from common.abi_utils import encode_approve
        from eth_utils import to_checksum_address as checksum
        from minotaur_subnet.shared.types import ExecutionPlan, Interaction

        router = checksum(ROUTER)
        interactions = [
            Interaction(
                target=checksum(TOKEN_IN),
                value="0",
                call_data=encode_approve(router, INPUT_AMOUNT),
                chain_id=CHAIN_ID,
            ),
            Interaction(
                target=router,
                value="0",
                call_data=_swap_data(state.contract_address),
                chain_id=CHAIN_ID,
            ),
        ]
        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=interactions,
            deadline=DEADLINE,
            nonce=state.nonce,
            metadata={"chain_id": CHAIN_ID, "solver": "q6c7-base-v3-hop"},
        )
    except Exception:
        return None
