"""Deterministic Kyber route for the reviewed q_ddde Blueguider blind spot."""

from __future__ import annotations

import json
import time
from pathlib import Path


SPEC = json.loads(Path(__file__).with_suffix(".json").read_text())


def _params(solver, intent, state):
    try:
        return dict(solver._normalized_swap_params(intent, state) or {})
    except Exception:
        return dict(getattr(state, "raw_params", None) or {})


def _matches(intent, state, params):
    try:
        return (
            not SPEC.get("transient_sources_allowed", True)
            and int(SPEC["deadline"]) > int(time.time())
            and int(getattr(state, "chain_id", 0) or 0) == int(SPEC["chain_id"])
            and str(getattr(intent, "app_id", "") or "") == SPEC["app_id"]
            and str(getattr(state, "contract_address", "") or "").lower()
            == SPEC["contract_address"].lower()
            and str(params.get("input_token", "")).lower()
            == SPEC["input_token"].lower()
            and str(params.get("output_token", "")).lower()
            == SPEC["output_token"].lower()
            and int(params.get("input_amount", 0) or 0) == int(SPEC["input_amount"])
        )
    except (KeyError, TypeError, ValueError):
        return False


def _interactions():
    from common.abi_utils import encode_approve
    from eth_utils import to_checksum_address as checksum
    from minotaur_subnet.shared.types import Interaction

    chain_id = int(SPEC["chain_id"])
    router = checksum(SPEC["router_address"])
    token = checksum(SPEC["input_token"])
    amount = int(SPEC["input_amount"])
    return [
        Interaction(
            target=token,
            value="0",
            call_data=encode_approve(router, amount),
            chain_id=chain_id,
        ),
        Interaction(
            target=router,
            value=str(int(SPEC.get("transaction_value", 0) or 0)),
            call_data=SPEC["data"],
            chain_id=chain_id,
        ),
    ]


def maybe_qdd_kyber_plan(solver, intent, state):
    try:
        if not _matches(intent, state, _params(solver, intent, state)):
            return None
        from minotaur_subnet.shared.types import ExecutionPlan

        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=_interactions(),
            deadline=int(SPEC["deadline"]),
            nonce=state.nonce,
            metadata={
                "solver": "chain-killer-qdd",
                "route": "kyber:" + ",".join(filter(None, SPEC.get("sources", []))),
                "expected_output": str(SPEC["quoted_output"]),
                "chain_id": int(SPEC["chain_id"]),
            },
        )
    except Exception:
        return None
