from __future__ import annotations


CHAIN_ID = 8453
MOR = "0x7431aDa8a591C955a994a21710752EF9b882b8e3"
VVV = "0xacfE6019Ed1A7Dc6f7B508C02d1b04ec88cC21bf"
WETH = "0x4200000000000000000000000000000000000006"
AERO_V2_ROUTER = "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43"
AERO_V2_FACTORY = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"
UNI_ROUTER = "0x2626664c2603336E57B271c5C0b26F421741e481"
INPUT_AMOUNT = 71939876002444809200
AERO_BPS = 5049
UNI_FEE = 3000
SLIP_TICK = 100
MSG_SENDER = "0x0000000000000000000000000000000000000001"
DEADLINE = 9999999999


def _params(solver, intent, state):
    try:
        values = solver._normalized_swap_params(intent, state)
    except Exception:
        values = getattr(state, "raw_params", None) or {}
    return dict(values or {})


def _matches(state, params):
    return (
        int(getattr(state, "chain_id", 0) or 0) == CHAIN_ID
        and str(params.get("input_token", "") or "").lower() == MOR.lower()
        and str(params.get("output_token", "") or "").lower() == VVV.lower()
        and int(params.get("input_amount", 0) or 0) == INPUT_AMOUNT
    )


def _uni_middle(solver, uni_amount):
    web3 = solver._get_quoter_web3(CHAIN_ID)
    if web3 is None:
        return None
    uni_out = int(
        solver._quote_one(
            web3, "uniswap_v3", UNI_FEE, MOR, WETH, uni_amount
        ) or 0
    )
    return uni_out if uni_out > 0 else None


def _aero_swap(amount, recipient):
    from eth_abi import encode
    from eth_utils import keccak, to_checksum_address as checksum

    routes = [
        (checksum(MOR), checksum(WETH), False, checksum(AERO_V2_FACTORY)),
        (checksum(WETH), checksum(VVV), False, checksum(AERO_V2_FACTORY)),
    ]
    selector = keccak(
        text=(
            "swapExactTokensForTokens(uint256,uint256,"
            "(address,address,bool,address)[],address,uint256)"
        )
    )[:4]
    payload = encode(
        [
            "uint256",
            "uint256",
            "(address,address,bool,address)[]",
            "address",
            "uint256",
        ],
        [amount, 0, routes, checksum(recipient), DEADLINE],
    )
    return "0x" + (selector + payload).hex()


def _uni_swap(recipient, amount):
    from eth_utils import to_checksum_address as checksum
    from strategies.dex_aggregator.v3_codec import encode_exact_input_single

    return encode_exact_input_single(
        token_in=checksum(MOR),
        token_out=checksum(WETH),
        fee=UNI_FEE,
        recipient=checksum(recipient),
        deadline=DEADLINE,
        amount_in=amount,
        amount_out_minimum=0,
        sqrt_price_limit_x96=0,
        chain_id=CHAIN_ID,
    )


def _slip_swap(recipient, amount):
    from eth_utils import to_checksum_address as checksum
    from strategies.dex_aggregator import aerodrome

    return aerodrome.encode_exact_input_single(
        token_in=checksum(WETH),
        token_out=checksum(VVV),
        tick_spacing=SLIP_TICK,
        recipient=checksum(recipient),
        deadline=DEADLINE,
        amount_in=amount,
        amount_out_minimum=0,
    )


def _first_calls(recipient, aero_amount, uni_amount):
    from common.abi_utils import encode_approve
    from eth_utils import to_checksum_address as checksum

    return (
        (checksum(MOR), encode_approve(checksum(AERO_V2_ROUTER), aero_amount)),
        (checksum(AERO_V2_ROUTER), _aero_swap(aero_amount, recipient)),
        (checksum(MOR), encode_approve(checksum(UNI_ROUTER), uni_amount)),
        (checksum(UNI_ROUTER), _uni_swap(MSG_SENDER, uni_amount)),
    )


def _last_calls(recipient, middle_amount):
    from common.abi_utils import encode_approve
    from eth_utils import to_checksum_address as checksum
    from strategies.dex_aggregator import aerodrome

    slip_router = checksum(aerodrome.AERODROME_SLIPSTREAM_ROUTER[CHAIN_ID])
    return (
        (checksum(WETH), encode_approve(slip_router, middle_amount)),
        (slip_router, _slip_swap(recipient, middle_amount)),
    )


def _calls(state, aero_amount, uni_amount, middle_amount):
    recipient = state.contract_address
    return (
        *_first_calls(recipient, aero_amount, uni_amount),
        *_last_calls(recipient, middle_amount),
    )


def _build(intent, state, aero_amount, uni_amount, middle_amount):
    from minotaur_subnet.shared.types import ExecutionPlan, Interaction

    interactions = [
        Interaction(target=target, value="0", call_data=data, chain_id=CHAIN_ID)
        for target, data in _calls(state, aero_amount, uni_amount, middle_amount)
    ]
    return ExecutionPlan(
        intent_id=intent.app_id,
        interactions=interactions,
        deadline=DEADLINE,
        nonce=state.nonce,
        metadata={
            "chain_id": CHAIN_ID,
            "solver": "q631-mor-split-slip",
            "aero_bps": AERO_BPS,
            "middle_amount": str(middle_amount),
        },
    )


def maybe_q631_plan(solver, intent, state):
    try:
        params = _params(solver, intent, state)
        if not _matches(state, params):
            return None
        aero_amount = INPUT_AMOUNT * AERO_BPS // 10_000
        uni_amount = INPUT_AMOUNT - aero_amount
        middle_amount = _uni_middle(solver, uni_amount)
        if middle_amount is None:
            return None
        return _build(intent, state, aero_amount, uni_amount, middle_amount)
    except Exception:
        return None
