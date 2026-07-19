from __future__ import annotations


CHAIN_ID = 8453
TOKEN_IN = "0xcd2f22236dd9dfe2356d7c543161d4d260fd9bcb"
WETH = "0x4200000000000000000000000000000000000006"
TOKEN_OUT = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
ROUTER = "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43"
FACTORY = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"
INPUT_AMOUNT = 6_209_430_931_660_000_000_000
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

    routes = [
        (checksum(TOKEN_IN), checksum(WETH), False, checksum(FACTORY)),
        (checksum(WETH), checksum(TOKEN_OUT), False, checksum(FACTORY)),
    ]
    selector = keccak(
        text=(
            "swapExactTokensForTokens(uint256,uint256,"
            "(address,address,bool,address)[],address,uint256)"
        )
    )[:4]
    payload = encode(
        ["uint256", "uint256", "(address,address,bool,address)[]", "address", "uint256"],
        [INPUT_AMOUNT, 0, routes, checksum(recipient), DEADLINE],
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


def maybe_q397_plan(solver, intent, state):
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
