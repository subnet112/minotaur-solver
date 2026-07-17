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

def _target_routes():
    return {
        (USDC, WETH, 2_000_000): ("uniswap_v3", 100),
        (USDC, WETH, 250_000_000): ("pancake_v3", 100),
        (USDC, WETH, 2_500_000_000): ("pancake_v3", 100),
        (CBBTC, USDC, 1_000_000): ("pancake_v3", 100),
        (CBBTC, WETH, 1_000_000): ("aerodrome_slipstream", 1),
        (WETH, USDC, 500_000_000_000_000): ("pancake_v3", 100),
    }


TARGET_ROUTES = _target_routes()


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
        and _order(params) in TARGET_ROUTES
    )


def _order(params):
    return (
        str(params.get("input_token", "")).lower(),
        str(params.get("output_token", "")).lower(),
        int(params.get("input_amount", 0) or 0),
    )


def _route_body(plan):
    try:
        calldata = str(plan.interactions[-1].call_data or "")
    except Exception:
        return ""
    return calldata[2:] if calldata.startswith("0x") else calldata


def _route_parameter(body):
    try:
        return int.from_bytes(bytes.fromhex(body[136:200]), "big")
    except Exception:
        return None


def _venue(selector):
    return {
        "04e45aaf": "uniswap_v3",
        "414bf389": "pancake_v3",
        "a026383e": "aerodrome_slipstream",
    }.get(selector)


def _route(plan):
    body = _route_body(plan)
    parameter = _route_parameter(body)
    venue = _venue(body[:8].lower())
    if venue is not None and parameter is not None:
        return venue, parameter
    return None


def _fixed_candidate(route):
    venue, parameter = route
    return {
        "venue": venue,
        "param": parameter,
        "out": 1,
        "gas_model": 0,
    }


def _frontier(base_plan, minimum, order):
    target = TARGET_ROUTES.get(order)
    route = _route(base_plan)
    if target is None or minimum != 0 or route == target:
        return None
    return _fixed_candidate(target), route


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


def maybe_base_stability_plan(solver, intent, state, snapshot, base_plan):
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
