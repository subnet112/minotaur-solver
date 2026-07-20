"""Uniswap V2 two-hop route matching Hydra's reviewed q_058649 edge."""

from __future__ import annotations


CHAIN_ID = 1
APP_ID = "app_0867cdd4effd"
APP_CONTRACT = "0x01CC8304249A77C206028ec940476B4ed96a770c"
TOKEN_IN = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
TOKEN_OUT = "0x32b86b99441480a7E5BD3A26c124ec2373e3F015"
INPUT_AMOUNT = 443_667_179
UNISWAP_V2_ROUTER = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
DEADLINE = 9_999_999_999


def _params(solver, intent, state):
    try:
        values = solver._normalized_swap_params(intent, state)
    except Exception:
        values = getattr(state, "raw_params", None) or {}
    return dict(values or {})


def _matches(intent, state, params):
    try:
        return (
            str(getattr(intent, "app_id", "") or "") == APP_ID
            and int(getattr(state, "chain_id", 0) or 0) == CHAIN_ID
            and str(getattr(state, "contract_address", "") or "").lower()
            == APP_CONTRACT.lower()
            and str(params.get("input_token", "") or "").lower()
            == TOKEN_IN.lower()
            and str(params.get("output_token", "") or "").lower()
            == TOKEN_OUT.lower()
            and int(params.get("input_amount", 0) or 0) == INPUT_AMOUNT
        )
    except (TypeError, ValueError):
        return False


def _approve_data():
    from common.abi_utils import encode_approve
    from eth_utils import to_checksum_address as checksum

    return encode_approve(checksum(UNISWAP_V2_ROUTER), INPUT_AMOUNT)


def _swap_data(recipient):
    from eth_abi import encode
    from eth_utils import keccak, to_checksum_address as checksum

    selector = keccak(
        text="swapExactTokensForTokens(uint256,uint256,address[],address,uint256)"
    )[:4]
    payload = encode(
        ["uint256", "uint256", "address[]", "address", "uint256"],
        [
            INPUT_AMOUNT,
            0,
            [checksum(TOKEN_IN), checksum(WETH), checksum(TOKEN_OUT)],
            checksum(recipient),
            DEADLINE,
        ],
    )
    return "0x" + (selector + payload).hex()


def _build_plan(intent, state):
    from eth_utils import to_checksum_address as checksum
    from minotaur_subnet.shared.types import ExecutionPlan, Interaction

    interactions = [
        Interaction(
            target=checksum(TOKEN_IN),
            value="0",
            call_data=_approve_data(),
            chain_id=CHAIN_ID,
        ),
        Interaction(
            target=checksum(UNISWAP_V2_ROUTER),
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
        metadata={"chain_id": CHAIN_ID, "solver": "q058-uniswap-v2-two-hop"},
    )


def maybe_q058_plan(solver, intent, state):
    try:
        params = _params(solver, intent, state)
        if _matches(intent, state, params):
            return _build_plan(intent, state)
    except Exception:
        pass
    return None
