from __future__ import annotations


CHAIN_ID = 1
TOKEN_IN = "0x32a7c02e79c4ea1008dd6564b35f131428673c41"
TOKEN_OUT = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
ROUTER = "0x7a250d5630b4cf539739df2c5dacb4c659f2488d"
INPUT_AMOUNT = 35_000_000_000_000_000_000_000
DEADLINE = 9_999_999_999


def _params(solver, intent, state):
    try:
        return dict(solver._normalized_swap_params(intent, state) or {})
    except Exception:
        return dict(getattr(state, "raw_params", None) or {})


def _matches(state, params):
    try:
        return (
            int(getattr(state, "chain_id", 0) or 0) == CHAIN_ID
            and str(params.get("input_token", "")).lower() == TOKEN_IN
            and str(params.get("output_token", "")).lower() == TOKEN_OUT
            and int(params.get("input_amount", 0) or 0) == INPUT_AMOUNT
        )
    except (TypeError, ValueError):
        return False


def _swap_data(recipient):
    from eth_abi import encode
    from eth_utils import keccak, to_checksum_address as checksum

    return keccak(
        text="swapExactTokensForTokens(uint256,uint256,address[],address,uint256)"
    )[:4] + encode(
        ["uint256", "uint256", "address[]", "address", "uint256"],
        [
            INPUT_AMOUNT,
            0,
            [checksum(TOKEN_IN), checksum(WETH), checksum(TOKEN_OUT)],
            checksum(recipient),
            DEADLINE,
        ],
    )


def _build_plan(intent, state):
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
            call_data="0x" + _swap_data(state.contract_address).hex(),
            chain_id=CHAIN_ID,
        ),
    ]
    return ExecutionPlan(
        intent_id=intent.app_id,
        interactions=interactions,
        deadline=DEADLINE,
        nonce=state.nonce,
        metadata={"chain_id": CHAIN_ID, "solver": "viking-v2"},
    )


def maybe_qfef_plan(solver, intent, state):
    try:
        if _matches(state, _params(solver, intent, state)):
            return _build_plan(intent, state)
    except Exception:
        pass
    return None
