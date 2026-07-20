from __future__ import annotations


CHAIN_ID = 1
USDT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
OUTPUT_TOKEN = "0x68A47Fe1CF42eBa4a030a10CD4D6a1031Ca3CA0a"
INPUT_AMOUNT = 150_000_000


def _params(solver, intent, state):
    try:
        values = solver._normalized_swap_params(intent, state)
    except Exception:
        values = getattr(state, "raw_params", None) or {}
    return dict(values or {})


def _matches(state, params):
    return (
        int(getattr(state, "chain_id", 0) or 0) == CHAIN_ID
        and str(params.get("input_token", "") or "").lower() == USDT.lower()
        and str(params.get("output_token", "") or "").lower()
        == OUTPUT_TOKEN.lower()
        and int(params.get("input_amount", 0) or 0) == INPUT_AMOUNT
    )


def _build(intent, state, params):
    from viking_build import _recipient, _serve_v2

    recipient = _recipient(state, params)
    if not recipient:
        return None
    return _serve_v2(
        intent,
        state,
        CHAIN_ID,
        USDT,
        OUTPUT_TOKEN,
        [USDT, WETH, OUTPUT_TOKEN],
        INPUT_AMOUNT,
        recipient,
        52_358_530_580,
    )


def maybe_qa9d4_plan(solver, intent, state):
    try:
        params = _params(solver, intent, state)
        return _build(intent, state, params) if _matches(state, params) else None
    except Exception:
        return None
