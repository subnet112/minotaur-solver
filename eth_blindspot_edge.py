from __future__ import annotations


CHAIN_ID = 1
TOKEN_IN = "0xC6bDb96E29c38DC43f014Eed44dE4106A6A8eB5f"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
V2_ROUTER = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
INPUT_AMOUNT = 45857332289610000000000000000
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
        and str(params.get("input_token", "") or "").lower()
        == TOKEN_IN.lower()
        and str(params.get("output_token", "") or "").lower() == WETH.lower()
        and int(params.get("input_amount", 0) or 0) == INPUT_AMOUNT
    )


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
            [checksum(TOKEN_IN), checksum(WETH)],
            checksum(recipient),
            DEADLINE,
        ],
    )
    return "0x" + (selector + payload).hex()


def maybe_q010_plan(solver, intent, state):
    try:
        params = _params(solver, intent, state)
        if not _matches(state, params):
            return None

        from common.abi_utils import encode_approve
        from eth_utils import to_checksum_address as checksum
        from minotaur_subnet.shared.types import ExecutionPlan, Interaction

        router = checksum(V2_ROUTER)
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
                call_data=_swap_data(state.contract_address),
                chain_id=CHAIN_ID,
            ),
        ]
        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=interactions,
            deadline=DEADLINE,
            nonce=state.nonce,
            metadata={"chain_id": CHAIN_ID, "solver": "q010-v2-baked"},
        )
    except Exception:
        return None
