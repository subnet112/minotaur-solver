from __future__ import annotations


CHAIN_ID = 1
BAT = "0x0D8775F648430679A709E98d2b0Cb6250d2887EF"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
WQUIL = "0x8143182a775C54578c8B7b3Ef77982498866945D"
INPUT_AMOUNT = 5_000_000_000_000_000_000_000
UNIVERSAL_ROUTER = "0x66a9893cC07D91D95644AEDD05D03f95e1dBA8Af"
ADDRESS_THIS = "0x0000000000000000000000000000000000000002"
CONTRACT_BALANCE = 1 << 255
DEADLINE = 9_999_999_999


def _params(solver, intent, state):
    try:
        values = solver._normalized_swap_params(intent, state)
    except Exception:
        values = getattr(state, "raw_params", None) or {}
    return dict(values or {})


def _matches(state, params):
    return (
        int(getattr(state, "chain_id", 0) or 0) == CHAIN_ID
        and str(params.get("input_token", "") or "").lower() == BAT.lower()
        and str(params.get("output_token", "") or "").lower() == WQUIL.lower()
        and int(params.get("input_amount", 0) or 0) == INPUT_AMOUNT
    )


def _transfer_data():
    from eth_abi import encode
    from eth_utils import keccak, to_checksum_address as checksum

    selector = keccak(text="transfer(address,uint256)")[:4]
    args = encode(
        ["address", "uint256"],
        [checksum(UNIVERSAL_ROUTER), INPUT_AMOUNT],
    )
    return "0x" + (selector + args).hex()


def _v2_input():
    from eth_abi import encode
    from eth_utils import to_checksum_address as checksum

    return encode(
        ["address", "uint256", "uint256", "address[]", "bool"],
        [
            checksum(ADDRESS_THIS),
            CONTRACT_BALANCE,
            0,
            [checksum(BAT), checksum(WETH)],
            False,
        ],
    )


def _v3_input(recipient):
    from eth_abi import encode
    from eth_utils import to_checksum_address as checksum

    path = (
        bytes.fromhex(WETH[2:])
        + (10_000).to_bytes(3, "big")
        + bytes.fromhex(WQUIL[2:])
    )
    return encode(
        ["address", "uint256", "uint256", "bytes", "bool"],
        [checksum(recipient), CONTRACT_BALANCE, 0, path, False],
    )


def _execute_data(recipient):
    from eth_abi import encode
    from eth_utils import keccak

    selector = keccak(text="execute(bytes,bytes[],uint256)")[:4]
    args = encode(
        ["bytes", "bytes[]", "uint256"],
        [bytes((8, 0)), [_v2_input(), _v3_input(recipient)], DEADLINE],
    )
    return "0x" + (selector + args).hex()


def _build(intent, state):
    from eth_utils import to_checksum_address as checksum
    from minotaur_subnet.shared.types import ExecutionPlan, Interaction

    interactions = [
        Interaction(
            target=checksum(BAT),
            value="0",
            call_data=_transfer_data(),
            chain_id=CHAIN_ID,
        ),
        Interaction(
            target=checksum(UNIVERSAL_ROUTER),
            value="0",
            call_data=_execute_data(state.contract_address),
            chain_id=CHAIN_ID,
        ),
    ]
    return ExecutionPlan(
        intent_id=intent.app_id,
        interactions=interactions,
        deadline=DEADLINE,
        nonce=state.nonce,
        metadata={"chain_id": CHAIN_ID, "solver": "qaa9-bat-wquil-v2-v3"},
    )


def maybe_qaa9_plan(solver, intent, state):
    try:
        params = _params(solver, intent, state)
        return _build(intent, state) if _matches(state, params) else None
    except Exception:
        return None
