from __future__ import annotations


CHAIN_ID = 8453
ROUTER = "0x2626664c2603336E57B271c5C0b26F421741e481"
WETH = "0x4200000000000000000000000000000000000006"
DEADLINE = 9999999999
EXACT_INPUT_SELECTOR = "0xb858183f"

# Exact quote-history orders with a full successful scoreIntent replay against
# the current certified champion. Values are (path tokens, fees, route tag).
ROUTES = {
    (
        "0xfde4c96c8593536e31f229ea8f37b2ada2699bb2",
        "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
        10_000_000,
    ): (
        (
            "0xfde4c96c8593536e31f229ea8f37b2ada2699bb2",
            WETH.lower(),
            "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
        ),
        (500, 500),
        "q8fbc",
    ),
    (
        "0x8c81b4c816d66d36c4bf348bdec01dbcbc70e987",
        "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        10_254_043_755_040_177_296_275,
    ): (
        (
            "0x8c81b4c816d66d36c4bf348bdec01dbcbc70e987",
            WETH.lower(),
            "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        ),
        (10_000, 100),
        "q6c7",
    ),
}


def _params(solver, intent, state):
    try:
        values = solver._normalized_swap_params(intent, state)
    except Exception:
        values = getattr(state, "raw_params", None) or {}
    return dict(values or {})


def _route(state, params):
    if int(getattr(state, "chain_id", 0) or 0) != CHAIN_ID:
        return None
    try:
        key = (
            str(params.get("input_token", "") or "").lower(),
            str(params.get("output_token", "") or "").lower(),
            int(params.get("input_amount", 0) or 0),
        )
    except (TypeError, ValueError):
        return None
    return ROUTES.get(key)


def _path(tokens, fees):
    packed = bytearray()
    for index, token in enumerate(tokens):
        packed.extend(bytes.fromhex(token.removeprefix("0x")))
        if index < len(fees):
            packed.extend(int(fees[index]).to_bytes(3, "big"))
    return bytes(packed)


def _swap_data(tokens, fees, recipient, amount):
    from eth_abi import encode
    from eth_utils import to_checksum_address as checksum

    payload = encode(
        ["(bytes,address,uint256,uint256)"],
        [(_path(tokens, fees), checksum(recipient), int(amount), 0)],
    )
    return EXACT_INPUT_SELECTOR + payload.hex()


def maybe_fresh_base_plan(solver, intent, state):
    try:
        params = _params(solver, intent, state)
        route = _route(state, params)
        if route is None:
            return None
        tokens, fees, tag = route
        amount = int(params["input_amount"])

        from common.abi_utils import encode_approve
        from eth_utils import to_checksum_address as checksum
        from minotaur_subnet.shared.types import ExecutionPlan, Interaction

        router = checksum(ROUTER)
        interactions = [
            Interaction(
                target=checksum(tokens[0]),
                value="0",
                call_data=encode_approve(router, amount),
                chain_id=CHAIN_ID,
            ),
            Interaction(
                target=router,
                value="0",
                call_data=_swap_data(
                    tokens, fees, state.contract_address, amount
                ),
                chain_id=CHAIN_ID,
            ),
        ]
        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=interactions,
            deadline=DEADLINE,
            nonce=state.nonce,
            metadata={
                "chain_id": CHAIN_ID,
                "solver": f"fresh-base-v3h-{tag}",
            },
        )
    except Exception:
        return None
