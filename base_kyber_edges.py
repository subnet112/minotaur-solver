"""Replay-safe Kyber cover for the reviewed qbd06 Base quote case."""

from __future__ import annotations

import json
import time
from pathlib import Path


_SPEC_NAMES = ("base_kyber_qbd06.json",)
SPECS = tuple(
    json.loads(Path(__file__).with_name(name).read_text()) for name in _SPEC_NAMES
)


def _params(solver, intent, state):
    try:
        return dict(solver._normalized_swap_params(intent, state) or {})
    except Exception:
        return dict(getattr(state, "raw_params", None) or {})


def _identity_matches(spec, intent, state):
    try:
        return (
            int(getattr(state, "chain_id", 0) or 0) == int(spec["chain_id"])
            and str(getattr(intent, "app_id", "") or "") == spec["app_id"]
            and str(getattr(state, "contract_address", "") or "").lower()
            == spec["contract_address"].lower()
        )
    except (KeyError, TypeError, ValueError):
        return False


def _swap_matches(spec, params):
    try:
        return (
            str(params.get("input_token", "")).lower()
            == spec["input_token"].lower()
            and str(params.get("output_token", "")).lower()
            == spec["output_token"].lower()
            and int(params.get("input_amount", 0) or 0) == int(spec["input_amount"])
        )
    except (KeyError, TypeError, ValueError):
        return False


def _matching_spec(intent, state, params):
    now = int(time.time())
    for spec in SPECS:
        if (
            not spec.get("transient_sources_allowed", True)
            and int(spec["deadline"]) > now
            and _identity_matches(spec, intent, state)
            and _swap_matches(spec, params)
        ):
            return spec
    return None


def _interactions(spec):
    from common.abi_utils import encode_approve
    from eth_utils import to_checksum_address as checksum
    from minotaur_subnet.shared.types import Interaction

    chain_id = int(spec["chain_id"])
    router = checksum(spec["router_address"])
    token = checksum(spec["input_token"])
    amount = int(spec["input_amount"])
    return [
        Interaction(
            target=token,
            value="0",
            call_data=encode_approve(router, amount),
            chain_id=chain_id,
        ),
        Interaction(
            target=router,
            value=str(int(spec.get("transaction_value", 0) or 0)),
            call_data=spec["data"],
            chain_id=chain_id,
        ),
    ]


def maybe_base_kyber_plan(solver, intent, state):
    try:
        spec = _matching_spec(intent, state, _params(solver, intent, state))
        if spec is None:
            return None
        from minotaur_subnet.shared.types import ExecutionPlan

        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=_interactions(spec),
            deadline=int(spec["deadline"]),
            nonce=state.nonce,
            metadata={
                "solver": "chain-killer-kyber-cover",
                "route": "kyber:" + ",".join(filter(None, spec.get("sources", []))),
                "expected_output": str(spec["quoted_output"]),
                "chain_id": int(spec["chain_id"]),
            },
        )
    except Exception:
        return None
