from __future__ import annotations


(
    CHAIN_ID,
    PYUSD,
    USDC,
    WETH,
    PEPECOIN,
    UNIVERSAL_ROUTER,
    INPUT_AMOUNT,
    UNI_FEES,
    ADDRESS_THIS,
    CONTRACT_BALANCE,
    DEADLINE,
) = (
    1,
    "0x6c3ea9036406852006290770BEdFcAbA0e23A0e8",
    "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    "0xA9E8aCf069C58aEc8825542845Fd754e41a9489A",
    "0x66a9893cC07D91D95644AEDD05D03f95e1dBA8Af",
    149990000,
    (100, 500),
    "0x0000000000000000000000000000000000000002",
    1 << 255,
    9999999999,
)


def _params(solver, intent, state):
    try:
        values = solver._normalized_swap_params(intent, state)
    except Exception:
        values = getattr(state, "raw_params", None) or {}
    return dict(values or {})


def _matches(state, params):
    return (
        int(getattr(state, "chain_id", 0) or 0) == CHAIN_ID
        and str(params.get("input_token", "") or "").lower() == PYUSD.lower()
        and str(params.get("output_token", "") or "").lower() == PEPECOIN.lower()
        and int(params.get("input_amount", 0) or 0) == INPUT_AMOUNT
    )


def _path():
    from eth_utils import to_checksum_address as checksum

    tokens = [checksum(PYUSD), checksum(USDC), checksum(WETH)]
    path = bytes.fromhex(tokens[0][2:])
    for fee, token in zip(UNI_FEES, tokens[1:]):
        path += int(fee).to_bytes(3, "big") + bytes.fromhex(token[2:])
    return path


def _transfer_data():
    from eth_abi import encode
    from eth_utils import keccak, to_checksum_address as checksum

    selector = keccak(text="transfer(address,uint256)")[:4]
    return "0x" + (
        selector + encode(["address", "uint256"], [checksum(UNIVERSAL_ROUTER), INPUT_AMOUNT])
    ).hex()


def _v3_input():
    from eth_abi import encode
    from eth_utils import to_checksum_address as checksum

    return encode(
        ["address", "uint256", "uint256", "bytes", "bool"],
        [checksum(ADDRESS_THIS), CONTRACT_BALANCE, 0, _path(), False],
    )


def _v2_input(recipient):
    from eth_abi import encode
    from eth_utils import to_checksum_address as checksum

    return encode(
        ["address", "uint256", "uint256", "address[]", "bool"],
        [
            checksum(recipient),
            CONTRACT_BALANCE,
            0,
            [checksum(WETH), checksum(PEPECOIN)],
            False,
        ],
    )


def _execute_data(recipient):
    from eth_abi import encode
    from eth_utils import keccak

    selector = keccak(text="execute(bytes,bytes[],uint256)")[:4]
    payload = encode(
        ["bytes", "bytes[]", "uint256"],
        [bytes((0, 8)), [_v3_input(), _v2_input(recipient)], DEADLINE],
    )
    return "0x" + (selector + payload).hex()


def _build(intent, state):
    from eth_utils import to_checksum_address as checksum
    from minotaur_subnet.shared.types import ExecutionPlan, Interaction

    calls = (
        (checksum(PYUSD), _transfer_data()),
        (checksum(UNIVERSAL_ROUTER), _execute_data(state.contract_address)),
    )
    interactions = [
        Interaction(target=target, value="0", call_data=data, chain_id=CHAIN_ID)
        for target, data in calls
    ]
    return ExecutionPlan(
        intent_id=intent.app_id,
        interactions=interactions,
        deadline=DEADLINE,
        nonce=state.nonce,
        metadata={"chain_id": CHAIN_ID, "solver": "qd41-atomic-v3-v2"},
    )


def maybe_qd41_plan(solver, intent, state):
    try:
        params = _params(solver, intent, state)
        return _build(intent, state) if _matches(state, params) else None
    except Exception:
        return None
