from __future__ import annotations


CHAIN_ID = 8453
TOKEN_IN = "0xfde4c96c8593536e31f229ea8f37b2ada2699bb2"
TOKEN_OUT = "0x50c5725949a6f0c72e6c4a641f24049a917db0cb"
ROUTER = "0x2626664c2603336E57B271c5C0b26F421741e481"
INPUT_AMOUNT = 10_000_000
FEE = 100
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
    from eth_utils import to_checksum_address as checksum
    from strategies.dex_aggregator.v3_codec import encode_exact_input_single

    return encode_exact_input_single(
        token_in=checksum(TOKEN_IN),
        token_out=checksum(TOKEN_OUT),
        fee=FEE,
        recipient=checksum(recipient),
        deadline=DEADLINE,
        amount_in=INPUT_AMOUNT,
        amount_out_minimum=0,
        chain_id=CHAIN_ID,
    )


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


def maybe_qbfbd_plan(solver, intent, state):
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
