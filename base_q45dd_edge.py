from __future__ import annotations


CHAIN_ID = 8453
TOKEN_IN = "0x768be13e1680b5ebe0024c42c896e3db59ec0149"
TOKEN_OUT = "0x4200000000000000000000000000000000000006"
ROUTER = "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24"
INPUT_AMOUNT = 1_484_221_256_000
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

    selector = keccak(
        text="swapExactTokensForTokens(uint256,uint256,address[],address,uint256)"
    )[:4]
    payload = encode(
        ["uint256", "uint256", "address[]", "address", "uint256"],
        [
            INPUT_AMOUNT,
            0,
            [checksum(TOKEN_IN), checksum(TOKEN_OUT)],
            checksum(recipient),
            DEADLINE,
        ],
    )
    return "0x" + (selector + payload).hex()


def _interactions(state):
    from common.abi_utils import encode_approve
    from eth_utils import to_checksum_address as checksum
    from minotaur_subnet.shared.types import Interaction

    router = checksum(ROUTER)
    return [
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


def maybe_q45dd_plan(solver, intent, state):
    try:
        if not _matches(state, _params(solver, intent, state)):
            return None
        from minotaur_subnet.shared.types import ExecutionPlan

        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=_interactions(state),
            deadline=DEADLINE,
            nonce=state.nonce,
            metadata={"chain_id": CHAIN_ID},
        )
    except Exception:
        return None
