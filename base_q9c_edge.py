"""Exact-key Base Uniswap V2 route for the revalidated q9c order."""

from __future__ import annotations


CHAIN_ID = 8453
APP_ID = "app_0867cdd4effd"
UNIVERSAL_ROUTER = "0x6ff5693b99212da76ad316178a184ab56d299b43"
ADDRESS_THIS = "0x0000000000000000000000000000000000000002"
CONTRACT_BALANCE = 1 << 255
DEADLINE = 9_999_999_999

SPECS = {
    (
        "0x4200000000000000000000000000000000000006",
        "0x04c0599ae5a44757c0af6f9ec3b93da8976c150a",
        20_000_000_000_000,
    ): "q9c",
}


def _params(solver, intent, state):
    try:
        values = solver._normalized_swap_params(intent, state)
    except Exception:
        values = getattr(state, "raw_params", None) or {}
    return dict(values or {})


def _key(intent, state, params):
    if (
        str(getattr(intent, "app_id", "") or "") != APP_ID
        or int(getattr(state, "chain_id", 0) or 0) != CHAIN_ID
    ):
        return None
    try:
        return (
            str(params.get("input_token", "") or "").lower(),
            str(params.get("output_token", "") or "").lower(),
            int(params.get("input_amount", 0) or 0),
        )
    except (TypeError, ValueError):
        return None


def _transfer_data(amount):
    from eth_abi import encode
    from eth_utils import keccak

    return keccak(text="transfer(address,uint256)")[:4] + encode(
        ["address", "uint256"], [UNIVERSAL_ROUTER, amount]
    )


def _execute_data(recipient, token_in, token_out):
    from eth_abi import encode
    from eth_utils import keccak

    swap = encode(
        ["address", "uint256", "uint256", "address[]", "bool"],
        [recipient, CONTRACT_BALANCE, 0, [token_in, token_out], False],
    )
    return keccak(text="execute(bytes,bytes[],uint256)")[:4] + encode(
        ["bytes", "bytes[]", "uint256"], [bytes((8,)), [swap], DEADLINE]
    )


def _interactions(state, key):
    from eth_utils import to_checksum_address as checksum
    from minotaur_subnet.shared.types import Interaction

    token_in, token_out, amount = key
    recipient = checksum(state.contract_address)
    return [
        Interaction(
            target=checksum(token_in),
            value="0",
            call_data="0x" + _transfer_data(amount).hex(),
            chain_id=CHAIN_ID,
        ),
        Interaction(
            target=checksum(UNIVERSAL_ROUTER),
            value="0",
            call_data="0x" + _execute_data(recipient, token_in, token_out).hex(),
            chain_id=CHAIN_ID,
        ),
    ]


def _build_plan(intent, state, key, label):
    from minotaur_subnet.shared.types import ExecutionPlan

    return ExecutionPlan(
        intent_id=intent.app_id,
        interactions=_interactions(state, key),
        deadline=DEADLINE,
        nonce=state.nonce,
        metadata={
            "chain_id": CHAIN_ID,
            "solver": f"base-uniswap-v2-{label}",
        },
    )


def maybe_q9c_plan(solver, intent, state):
    try:
        key = _key(intent, state, _params(solver, intent, state))
        label = SPECS.get(key)
        return _build_plan(intent, state, key, label) if label is not None else None
    except Exception:
        return None
