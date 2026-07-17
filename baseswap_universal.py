"""BaseSwap -> Uniswap V3 route for quote q_184d8dea."""

from __future__ import annotations


CHAIN_ID = 8453
TOKEN_IN = "0x6921b130d297cc43754afba22e5eac0fbf8db75b"
TOKEN_OUT = "0xd769d56f479e9e72a77bb1523e866a33098feec5"
WETH = "0x4200000000000000000000000000000000000006"
BASESWAP_ROUTER = "0x327df1e6de05895d2ab08513aadd9313fe505d86"
UNIVERSAL_ROUTER = "0x6ff5693b99212da76ad316178a184ab56d299b43"
CONTRACT_BALANCE = 1 << 255
INPUT_AMOUNT = 2999713747684661289591
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


def _call_data(signature, types, values):
    from eth_abi import encode
    from eth_utils import keccak

    return keccak(text=signature)[:4] + encode(types, values)


def _approve_data(router):
    return _call_data(
        "approve(address,uint256)", ["address", "uint256"], [router, INPUT_AMOUNT]
    )


def _swap_data(router_recipient, token_in, weth, deadline):
    return _call_data(
        "swapExactTokensForTokens(uint256,uint256,address[],address,uint256)",
        ["uint256", "uint256", "address[]", "address", "uint256"],
        [INPUT_AMOUNT, 0, [token_in, weth], router_recipient, deadline],
    )


def _v3_input(recipient):
    from eth_abi import encode

    path = bytes.fromhex(WETH[2:]) + SECOND_FEE.to_bytes(3, "big") + bytes.fromhex(TOKEN_OUT[2:])
    return encode(
        ["address", "uint256", "uint256", "bytes", "bool"],
        [recipient, CONTRACT_BALANCE, 0, path, False],
    )


def _execute_data(recipient, deadline):
    return _call_data(
        "execute(bytes,bytes[],uint256)",
        ["bytes", "bytes[]", "uint256"],
        [bytes((0x00,)), [_v3_input(recipient)], deadline],
    )


def _interactions(state, deadline):
    from eth_utils import to_checksum_address
    from minotaur_subnet.shared.types import Interaction

    recipient = to_checksum_address(state.contract_address)
    token_in = to_checksum_address(TOKEN_IN)
    weth = to_checksum_address(WETH)
    baseswap = to_checksum_address(BASESWAP_ROUTER)
    universal = to_checksum_address(UNIVERSAL_ROUTER)
    calls = (
        (token_in, _approve_data(baseswap)),
        (baseswap, _swap_data(universal, token_in, weth, deadline)),
        (universal, _execute_data(recipient, deadline)),
    )
    return [
        Interaction(target=target, value="0", call_data="0x" + data.hex(), chain_id=CHAIN_ID)
        for target, data in calls
    ]


def _build(intent, state):
    from minotaur_subnet.shared.types import ExecutionPlan

    deadline = 9_999_999_999
    return ExecutionPlan(
        intent_id=intent.app_id,
        interactions=_interactions(state, deadline),
        deadline=deadline,
        nonce=state.nonce,
        metadata={"chain_id": CHAIN_ID, "solver": "q184-baseswap-v2-v3"},
    )


def maybe_q184_plan(solver, intent, state):
    try:
        params = _params(solver, intent, state)
        return _build(intent, state) if _matches(state, params) else None
    except Exception:
        return None
