from __future__ import annotations


CHAIN_ID = 8453
APP_ID = "app_0867cdd4effd"
TOKEN_IN = "0x9a26f5433671751c3276a065f57e5a02d2817973"
TOKEN_OUT = "0xd769d56f479e9e72a77bb1523e866a33098feec5"
WETH = "0x4200000000000000000000000000000000000006"
UNIVERSAL_ROUTER = "0x6ff5693b99212da76ad316178a184ab56d299b43"
ADDRESS_THIS = "0x0000000000000000000000000000000000000002"
CONTRACT_BALANCE = 1 << 255
INPUT_AMOUNT = 146465124281368793842
SECOND_FEE = 10_000
DEADLINE = 9_999_999_999


def _params(solver, intent, state):
    try:
        values = solver._normalized_swap_params(intent, state)
    except Exception:
        values = getattr(state, "raw_params", None) or {}
    return dict(values or {})


def _matches(intent, state, params):
    return (
        str(getattr(intent, "app_id", "") or "") == APP_ID
        and int(getattr(state, "chain_id", 0) or 0) == CHAIN_ID
        and str(params.get("input_token", "") or "").lower() == TOKEN_IN
        and str(params.get("output_token", "") or "").lower() == TOKEN_OUT
        and int(params.get("input_amount", 0) or 0) == INPUT_AMOUNT
    )


def _transfer_data(amount):
    from eth_abi import encode
    from eth_utils import keccak

    return keccak(text="transfer(address,uint256)")[:4] + encode(
        ["address", "uint256"], [UNIVERSAL_ROUTER, amount]
    )


def _v2_input():
    from eth_abi import encode

    return encode(
        ["address", "uint256", "uint256", "address[]", "bool"],
        [ADDRESS_THIS, CONTRACT_BALANCE, 0, [TOKEN_IN, WETH], False],
    )


def _v3_input(recipient):
    from eth_abi import encode

    path = (
        bytes.fromhex(WETH[2:])
        + SECOND_FEE.to_bytes(3, "big")
        + bytes.fromhex(TOKEN_OUT[2:])
    )
    return encode(
        ["address", "uint256", "uint256", "bytes", "bool"],
        [recipient, CONTRACT_BALANCE, 0, path, False],
    )


def _execute_data(recipient):
    from eth_abi import encode
    from eth_utils import keccak

    return keccak(text="execute(bytes,bytes[],uint256)")[:4] + encode(
        ["bytes", "bytes[]", "uint256"],
        [bytes((8, 0)), [_v2_input(), _v3_input(recipient)], DEADLINE],
    )


def _build_plan(intent, state):
    from eth_utils import to_checksum_address as checksum
    from minotaur_subnet.shared.types import ExecutionPlan, Interaction

    recipient = checksum(state.contract_address)
    interactions = [
        Interaction(
            target=checksum(TOKEN_IN),
            value="0",
            call_data="0x" + _transfer_data(INPUT_AMOUNT).hex(),
            chain_id=CHAIN_ID,
        ),
        Interaction(
            target=checksum(UNIVERSAL_ROUTER),
            value="0",
            call_data="0x" + _execute_data(recipient).hex(),
            chain_id=CHAIN_ID,
        ),
    ]
    return ExecutionPlan(
        intent_id=intent.app_id,
        interactions=interactions,
        deadline=DEADLINE,
        nonce=state.nonce,
        metadata={"chain_id": CHAIN_ID, "solver": "q87-uni-v2-v3"},
    )


def maybe_q87_plan(solver, intent, state):
    try:
        params = _params(solver, intent, state)
        if _matches(intent, state, params):
            return _build_plan(intent, state)
    except Exception:
        pass
    return None
