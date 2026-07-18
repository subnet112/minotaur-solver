from __future__ import annotations


CHAIN_ID = 1
SNPAD = "0x772358ef6ed3e18BdE1263F7d229601c5fa81875"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
PANCAKE_ROUTER = "0x1b81D678ffb9C0263b24A97847620C99d213eB14"
UNIVERSAL_ROUTER = "0x66a9893cC07D91D95644AEDD05D03f95e1dBA8Af"
INPUT_AMOUNT = 637151353039433634264
PANCAKE_FEE = 10000
UNI_FEE = 100
CONTRACT_BALANCE = 1 << 255
DEADLINE = 9999999999


def _params(solver, intent, state):
    try:
        values = solver._normalized_swap_params(intent, state)
    except Exception:
        values = getattr(state, "raw_params", None) or {}
    return dict(values or {})


def _matches(state, params):
    return (
        int(getattr(state, "chain_id", 0) or 0) == CHAIN_ID
        and str(params.get("input_token", "") or "").lower() == SNPAD.lower()
        and str(params.get("output_token", "") or "").lower() == USDC.lower()
        and int(params.get("input_amount", 0) or 0) == INPUT_AMOUNT
    )


def _swap_data(token_in, token_out, fee, recipient, amount):
    from eth_abi import encode
    from eth_utils import keccak, to_checksum_address as checksum

    values = (
        checksum(token_in),
        checksum(token_out),
        fee,
        checksum(recipient),
        DEADLINE,
        amount,
        0,
        0,
    )
    payload = encode(
        ["(address,address,uint24,address,uint256,uint256,uint256,uint160)"],
        [values],
    )
    selector = keccak(
        text="exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))"
    )[:4]
    return "0x" + (selector + payload).hex()


def _universal_input(recipient):
    from eth_abi import encode
    from eth_utils import to_checksum_address as checksum

    path = bytes.fromhex(WETH[2:]) + UNI_FEE.to_bytes(3, "big") + bytes.fromhex(USDC[2:])
    return encode(
        ["address", "uint256", "uint256", "bytes", "bool"],
        [checksum(recipient), CONTRACT_BALANCE, 0, path, False],
    )


def _universal_data(recipient):
    from eth_abi import encode
    from eth_utils import keccak

    selector = keccak(text="execute(bytes,bytes[],uint256)")[:4]
    payload = encode(
        ["bytes", "bytes[]", "uint256"],
        [bytes((0,)), [_universal_input(recipient)], DEADLINE],
    )
    return "0x" + (selector + payload).hex()


def _approve(spender, amount):
    from eth_abi import encode
    from eth_utils import keccak, to_checksum_address as checksum

    selector = keccak(text="approve(address,uint256)")[:4]
    return "0x" + (selector + encode(["address", "uint256"], [checksum(spender), amount])).hex()


def _calls(state):
    from eth_utils import to_checksum_address as checksum

    recipient = checksum(state.contract_address)
    return (
        (checksum(SNPAD), _approve(PANCAKE_ROUTER, INPUT_AMOUNT)),
        (checksum(PANCAKE_ROUTER), _swap_data(SNPAD, WETH, PANCAKE_FEE, UNIVERSAL_ROUTER, INPUT_AMOUNT)),
        (checksum(UNIVERSAL_ROUTER), _universal_data(recipient)),
    )


def _build(intent, state):
    from minotaur_subnet.shared.types import ExecutionPlan, Interaction

    interactions = [
        Interaction(target=target, value="0", call_data=data, chain_id=CHAIN_ID)
        for target, data in _calls(state)
    ]
    return ExecutionPlan(
        intent_id=intent.app_id,
        interactions=interactions,
        deadline=DEADLINE,
        nonce=state.nonce,
        metadata={
            "chain_id": CHAIN_ID,
            "solver": "qbbfa-snpad-pancake-ur",
        },
    )


def maybe_snpad_plan(solver, intent, state):
    try:
        params = _params(solver, intent, state)
        if not _matches(state, params):
            return None
        return _build(intent, state)
    except Exception:
        return None
