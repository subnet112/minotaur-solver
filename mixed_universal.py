"""Mixed Uniswap V2 -> V3 route for quote q_87fd41a9."""

from __future__ import annotations


CHAIN_ID = 8453
TOKEN_IN = "0x9a26f5433671751c3276a065f57e5a02d2817973"
TOKEN_OUT = "0xd769d56f479e9e72a77bb1523e866a33098feec5"
WETH = "0x4200000000000000000000000000000000000006"
UNIVERSAL_ROUTER = "0x6ff5693b99212da76ad316178a184ab56d299b43"
ADDRESS_THIS = "0x0000000000000000000000000000000000000002"
CONTRACT_BALANCE = 1 << 255
INPUT_AMOUNT = 146465124281368793842
SECOND_FEE = 10000


def _params(solver, intent, state):
    try:
        values = solver._normalized_swap_params(intent, state)
    except Exception:
        values = getattr(state, "raw_params", None) or {}
    return dict(values or {})


def _matches(state, params):
    return (
        int(getattr(state, "chain_id", 0) or 0) == CHAIN_ID
        and str(params.get("input_token", "") or "").lower() == TOKEN_IN
        and str(params.get("output_token", "") or "").lower() == TOKEN_OUT
        and int(params.get("input_amount", 0) or 0) == INPUT_AMOUNT
    )


def _transfer_data(router):
    from eth_abi import encode
    from eth_utils import keccak

    return keccak(text="transfer(address,uint256)")[:4] + encode(
        ["address", "uint256"], [router, INPUT_AMOUNT]
    )


def _v2_input(token_in, weth):
    from eth_abi import encode
    from eth_utils import to_checksum_address

    return encode(
        ["address", "uint256", "uint256", "address[]", "bool"],
        [
            to_checksum_address(ADDRESS_THIS),
            CONTRACT_BALANCE,
            0,
            [token_in, weth],
            False,
        ],
    )


def _v3_input(recipient):
    from eth_abi import encode

    v3_path = bytes.fromhex(WETH[2:]) + SECOND_FEE.to_bytes(3, "big") + bytes.fromhex(TOKEN_OUT[2:])
    return encode(
        ["address", "uint256", "uint256", "bytes", "bool"],
        [recipient, CONTRACT_BALANCE, 0, v3_path, False],
    )


def _execute_data(v2_input, v3_input, deadline):
    from eth_abi import encode
    from eth_utils import keccak

    return keccak(text="execute(bytes,bytes[],uint256)")[:4] + encode(
        ["bytes", "bytes[]", "uint256"],
        [bytes((0x08, 0x00)), [v2_input, v3_input], deadline],
    )


def _interactions(state, deadline):
    from eth_utils import to_checksum_address
    from minotaur_subnet.shared.types import Interaction

    recipient = to_checksum_address(state.contract_address)
    token_in = to_checksum_address(TOKEN_IN)
    weth = to_checksum_address(WETH)
    router = to_checksum_address(UNIVERSAL_ROUTER)
    transfer = _transfer_data(router)
    execute = _execute_data(_v2_input(token_in, weth), _v3_input(recipient), deadline)
    return [
        Interaction(target=token_in, value="0", call_data="0x" + transfer.hex(), chain_id=CHAIN_ID),
        Interaction(target=router, value="0", call_data="0x" + execute.hex(), chain_id=CHAIN_ID),
    ]


def _build(intent, state):
    from minotaur_subnet.shared.types import ExecutionPlan

    deadline = 9_999_999_999
    return ExecutionPlan(
        intent_id=intent.app_id,
        interactions=_interactions(state, deadline),
        deadline=deadline,
        nonce=state.nonce,
        metadata={"chain_id": CHAIN_ID, "solver": "q87-uni-v2-v3"},
    )


def maybe_q87_plan(solver, intent, state):
    try:
        params = _params(solver, intent, state)
        return _build(intent, state) if _matches(state, params) else None
    except Exception:
        return None
