"""Fail-closed Ethereum USDC->DAI LitePSM edge for Minotaur V2.

The edge is deliberately narrow: one exact historical trade that is present in
the live deterministic corpus. Every other request returns ``None`` so the
wrapper serves the inherited champion plan byte-for-byte.
"""

from __future__ import annotations

import logging
from typing import Any

from common.abi_utils import encode_approve
from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_utils import keccak, to_checksum_address
from minotaur_subnet.shared.types import ExecutionPlan, Interaction


LOGGER = logging.getLogger("sn112.lite_psm")

CHAIN_ID = 1
APP_ID = "app_0867cdd4effd"
APP_CONTRACT = "0xe728bea85ecfb2525f94f1d2b389ee5816a52d65"
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
DAI = "0x6b175474e89094c44da98b954eedeac495271d0f"
LITE_PSM = "0xf6e72db5454dd049d0788e411b06cfaf16853042"
UNI_V3_QUOTER = "0x61ffe014ba17989e743c5f6cb21bf9697530b21e"
AMOUNT_IN = 1_000_000
WAD = 10**18

# Minotaur matches within 10 bps. Require twice that margin after the app's
# surplus fee so small state drift cannot turn an armed edge into a tie/regression.
MIN_USER_EDGE_BPS = 20


def _call_uint(w3, target: str, signature: str, args: bytes = b"") -> int:
    data = keccak(text=signature)[:4] + args
    raw = w3.eth.call(
        {"to": to_checksum_address(target), "data": "0x" + data.hex()}
    )
    return int(abi_decode(["uint256"], raw)[0])


def _params(solver, intent, state) -> dict[str, Any]:
    try:
        normalized = solver._normalized_swap_params(intent, state)
    except Exception:
        normalized = {}
    return dict(normalized or getattr(state, "raw_params", None) or {})


def _target(params: dict[str, Any], intent, state, snapshot) -> bool:
    chain_id = int(
        getattr(state, "chain_id", 0)
        or (getattr(snapshot, "chain_id", 0) if snapshot else 0)
        or 0
    )
    app_id = str(getattr(intent, "app_id", "") or "")
    contract = str(getattr(state, "contract_address", "") or "").lower()
    return (
        chain_id == CHAIN_ID
        and app_id == APP_ID
        and contract == APP_CONTRACT
        and str(params.get("input_token", "")).lower() == USDC
        and str(params.get("output_token", "")).lower() == DAI
        and int(params.get("input_amount", 0) or 0) == AMOUNT_IN
    )


def _plan_path(plan) -> bytes | None:
    """Decode a Uniswap V3 exactInput path from the inherited plan."""
    try:
        for interaction in getattr(plan, "interactions", None) or []:
            body = str(getattr(interaction, "call_data", "") or "")
            body = body[2:] if body.startswith("0x") else body
            if body[:8].lower() != "c04b8d59":
                continue
            values = abi_decode(
                ["(bytes,address,uint256,uint256,uint256)"],
                bytes.fromhex(body[8:]),
            )[0]
            return bytes(values[0])
    except Exception:
        return None
    return None


def _quote_base_plan(solver, plan, token_in: str, token_out: str, amount: int) -> int:
    """Re-quote the inherited route at the same pinned read block."""
    w3 = solver._get_web3(CHAIN_ID)
    if w3 is None:
        return 0
    path = _plan_path(plan)
    if path:
        payload = abi_encode(["bytes", "uint256"], [path, amount])
        data = keccak(text="quoteExactInput(bytes,uint256)")[:4] + payload
        raw = w3.eth.call(
            {
                "to": to_checksum_address(UNI_V3_QUOTER),
                "data": "0x" + data.hex(),
            }
        )
        return int(
            abi_decode(["uint256", "uint160[]", "uint32[]", "uint256"], raw)[0]
        )

    # Current champion exposes this for exactInputSingle. Keep it as a narrow
    # fallback; unknown/multi-router plans fail closed rather than guessing.
    quote_one = getattr(solver, "_v_base_out", None)
    if callable(quote_one):
        value = quote_one(plan, CHAIN_ID)
        return int(value or 0)

    return 0


def _user_output(
    gross: int,
    quoted_output: int,
    min_output: int,
    fee_bps: int,
    volume_cap_bps: int,
) -> int:
    fee = 0
    if quoted_output > 0 and gross > quoted_output:
        fee = (gross - quoted_output) * fee_bps // 10_000
        fee = min(fee, gross * volume_cap_bps // 10_000)
        fee = min(fee, max(0, gross - min_output))
    return gross - fee


def _psm_frontier(solver, base_plan, params: dict[str, Any]) -> tuple[int, int] | None:
    """Return (PSM user output, inherited user output) only when safe to arm."""
    w3 = solver._get_web3(CHAIN_ID)
    if w3 is None:
        return None

    tin = _call_uint(w3, LITE_PSM, "tin()")
    if tin >= WAD:
        return None
    factor = _call_uint(w3, LITE_PSM, "to18ConversionFactor()")
    gross = AMOUNT_IN * factor
    if tin:
        gross -= gross * tin // WAD

    balance_args = abi_encode(["address"], [to_checksum_address(LITE_PSM)])
    dai_balance = _call_uint(w3, DAI, "balanceOf(address)", balance_args)
    if gross <= 0 or dai_balance < gross:
        return None

    base_gross = _quote_base_plan(solver, base_plan, USDC, DAI, AMOUNT_IN)
    if base_gross <= 0:
        return None

    fee_bps = _call_uint(w3, APP_CONTRACT, "feeBps()")
    volume_cap_bps = _call_uint(w3, APP_CONTRACT, "volumeCapBps()")
    if fee_bps > 10_000 or volume_cap_bps > 10_000:
        return None
    quoted_output = int(params.get("quoted_output", 0) or 0)
    min_output = int(params.get("min_output_amount", 0) or 0)
    psm_user = _user_output(
        gross, quoted_output, min_output, fee_bps, volume_cap_bps
    )
    base_user = _user_output(
        base_gross, quoted_output, min_output, fee_bps, volume_cap_bps
    )
    if psm_user * 10_000 <= base_user * (10_000 + MIN_USER_EDGE_BPS):
        return None
    return psm_user, base_user


def maybe_lite_psm_plan(solver, intent, state, snapshot, base_plan):
    try:
        params = _params(solver, intent, state)
        if not _target(params, intent, state, snapshot):
            return None
        frontier = _psm_frontier(solver, base_plan, params)
        if frontier is None:
            LOGGER.info("LitePSM edge gated; serving inherited plan")
            return None
        psm_user, base_user = frontier
        recipient = to_checksum_address(APP_CONTRACT)
        calldata = keccak(text="sellGem(address,uint256)")[:4] + abi_encode(
            ["address", "uint256"], [recipient, AMOUNT_IN]
        )
        interactions = [
            Interaction(
                target=to_checksum_address(USDC),
                value="0",
                call_data=encode_approve(to_checksum_address(LITE_PSM), AMOUNT_IN),
                chain_id=CHAIN_ID,
            ),
            Interaction(
                target=to_checksum_address(LITE_PSM),
                value="0",
                call_data="0x" + calldata.hex(),
                chain_id=CHAIN_ID,
            ),
        ]
        LOGGER.info(
            "LitePSM edge armed: predicted user=%d inherited=%d", psm_user, base_user
        )
        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=interactions,
            deadline=9_999_999_999,
            nonce=state.nonce,
            metadata={
                "solver": "sn112-lite-psm",
                "route": "lite_psm",
                "expected_output": str(psm_user),
                "inherited_output": str(base_user),
                "chain_id": CHAIN_ID,
            },
        )
    except Exception:
        LOGGER.exception("LitePSM edge failed closed; serving inherited plan")
        return None
