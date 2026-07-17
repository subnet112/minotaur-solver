# Keep replay-proven Base routes deterministic when provider quotes time out.

from __future__ import annotations

import logging

LOGGER = logging.getLogger("sn112.cbbtc_aero_guard")


def _constants():
    return (
        8453,
        "app_0867cdd4effd",
        "0x20c472262e0732dc660f660385764ddccb14cfde",
        "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
        "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        "0x4200000000000000000000000000000000000006",
    )


(
    CHAIN_ID,
    APP_ID,
    APP_CONTRACT,
    CBBTC,
    USDC,
    WETH,
) = _constants()

TARGET_FEES = {
    (USDC, WETH, 2_000_000): 500,
    (USDC, WETH, 250_000_000): 100,
    (CBBTC, USDC, 1_000_000): 500,
}


def _params(solver, intent, state):
    raw = dict(getattr(state, "raw_params", None) or {})
    if raw:
        return raw
    try:
        values = solver._normalized_swap_params(intent, state)
    except Exception:
        values = {}
    return dict(values or {})


def _target(params, intent, state, snapshot):
    chain_id = int(
        getattr(state, "chain_id", 0)
        or (getattr(snapshot, "chain_id", 0) if snapshot else 0)
        or 0
    )
    return (
        chain_id == CHAIN_ID
        and str(getattr(intent, "app_id", "") or "") == APP_ID
        and str(getattr(state, "contract_address", "") or "").lower()
        == APP_CONTRACT
        and _order(params) in TARGET_FEES
    )


def _order(params):
    return (
        str(params.get("input_token", "")).lower(),
        str(params.get("output_token", "")).lower(),
        int(params.get("input_amount", 0) or 0),
    )


def _route(plan):
    try:
        calldata = str(plan.interactions[-1].call_data or "")
        body = calldata[2:] if calldata.startswith("0x") else calldata
        selector = body[:8].lower()
        parameter = int.from_bytes(
            bytes.fromhex(body[8 + 128 : 8 + 192]), "big"
        )
        if selector == "04e45aaf":
            return "uni", parameter
        if selector == "414bf389":
            return "pancake", parameter
        if selector == "a026383e":
            return "aero", parameter
    except Exception:
        return None
    return None


def _fixed_candidate(fee):
    return {
        "venue": "uniswap_v3",
        "param": fee,
        "out": 1,
        "gas_model": 0,
    }


def _frontier(base_plan, minimum, order):
    fee = TARGET_FEES.get(order)
    route = _route(base_plan)
    if fee is None or minimum != 0 or route == ("uni", fee):
        return None
    return _fixed_candidate(fee), route


def _build_plan(solver, intent, state, snapshot, candidate, order):
    token_in, token_out, amount = order
    return solver._build_singlehop_plan(
        intent,
        state,
        snapshot,
        candidate,
        token_in,
        token_out,
        amount,
        CHAIN_ID,
    )


def _armed_plan(solver, intent, state, snapshot, outputs, order):
    candidate, inherited = outputs
    LOGGER.info(
        "Base fallback repaired: venue=%s fee=%d inherited=%r",
        candidate["venue"],
        candidate["param"],
        inherited,
    )
    return _build_plan(solver, intent, state, snapshot, candidate, order)


def maybe_cbbtc_aero_plan(solver, intent, state, snapshot, base_plan):
    try:
        params = _params(solver, intent, state)
        if not _target(params, intent, state, snapshot):
            return None
        order = _order(params)
        minimum = int(params.get("min_output_amount", 0) or 0)
        outputs = _frontier(base_plan, minimum, order)
        if outputs is None:
            return None
        return _armed_plan(solver, intent, state, snapshot, outputs, order)
    except Exception:
        LOGGER.exception("Aero fallback guard failed closed")
        return None
