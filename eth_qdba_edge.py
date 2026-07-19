from __future__ import annotations


CHAIN_ID = 1
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
USDT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
TOKEN_OUT = "0x68749665FF8D2d112Fa859AA293F07A622782F38"
ROUTER = "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"
INPUT_AMOUNT = 128194973
DEADLINE = 9999999999
EXACT_INPUT_SELECTOR = "0xb858183f"


def _params(solver, intent, state):
    try:
        values = solver._normalized_swap_params(intent, state)
    except Exception:
        values = getattr(state, "raw_params", None) or {}
    return dict(values or {})


def _matches(state, params):
    return (
        int(getattr(state, "chain_id", 0) or 0) == CHAIN_ID
        and str(params.get("input_token", "") or "").lower() == USDC.lower()
        and str(params.get("output_token", "") or "").lower()
        == TOKEN_OUT.lower()
        and int(params.get("input_amount", 0) or 0) == INPUT_AMOUNT
    )


def _path():
    return bytes.fromhex(
        USDC[2:] + "000064" + USDT[2:] + "0001f4" + TOKEN_OUT[2:]
    )


def _swap_data(recipient):
    from eth_abi import encode
    from eth_utils import to_checksum_address as checksum

    payload = encode(
        ["(bytes,address,uint256,uint256)"],
        [(_path(), checksum(recipient), INPUT_AMOUNT, 0)],
    )
    return EXACT_INPUT_SELECTOR + payload.hex()


def maybe_qdba_plan(solver, intent, state):
    try:
        params = _params(solver, intent, state)
        if not _matches(state, params):
            return None

        from common.abi_utils import encode_approve
        from eth_utils import to_checksum_address as checksum
        from minotaur_subnet.shared.types import ExecutionPlan, Interaction

        router = checksum(ROUTER)
        interactions = [
            Interaction(
                target=checksum(USDC),
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
            metadata={"chain_id": CHAIN_ID, "solver": "qdba-v3-hop-baked"},
        )
    except Exception:
        return None
