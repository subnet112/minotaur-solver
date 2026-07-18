from __future__ import annotations


UNIVERSAL_ROUTER = "0x66a9893cC07D91D95644AEDD05D03f95e1dBA8Af"
UNISWAP_V3_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
ADDRESS_THIS = "0x0000000000000000000000000000000000000002"
CONTRACT_BALANCE = 1 << 255
DEADLINE = 9999999999
_ROUTES = None


def _routes():
    global _ROUTES
    if _ROUTES is None:
        import json
        import os

        path = os.path.join(os.path.dirname(__file__), "quote_cover_routes.json")
        with open(path, encoding="utf-8") as handle:
            _ROUTES = json.load(handle)
    return _ROUTES


def _params(solver, intent, state):
    try:
        values = solver._normalized_swap_params(intent, state)
    except Exception:
        values = getattr(state, "raw_params", None) or {}
    return dict(values or {})


def _key(state, params):
    chain_id = int(getattr(state, "chain_id", 0) or 0)
    token_in = str(params.get("input_token", "") or "").lower()
    token_out = str(params.get("output_token", "") or "").lower()
    amount = int(params.get("input_amount", 0) or 0)
    return f"{chain_id}|{token_in}|{token_out}|{amount}"


def _path(spec):
    from eth_utils import to_checksum_address as checksum

    tokens = [checksum(token) for token in spec["v3_tokens"]]
    fees = [int(fee) for fee in spec["v3_fees"]]
    path = bytes.fromhex(tokens[0][2:])
    for fee, token in zip(fees, tokens[1:]):
        path += fee.to_bytes(3, "big") + bytes.fromhex(token[2:])
    return path


def _transfer_data(amount):
    from eth_abi import encode
    from eth_utils import keccak, to_checksum_address as checksum

    selector = keccak(text="transfer(address,uint256)")[:4]
    args = encode(["address", "uint256"], [checksum(UNIVERSAL_ROUTER), amount])
    return "0x" + (selector + args).hex()


def _v3_input(spec):
    from eth_abi import encode
    from eth_utils import to_checksum_address as checksum

    return encode(
        ["address", "uint256", "uint256", "bytes", "bool"],
        [checksum(ADDRESS_THIS), CONTRACT_BALANCE, 0, _path(spec), False],
    )


def _v2_input(spec, recipient):
    from eth_abi import encode
    from eth_utils import to_checksum_address as checksum

    tokens = [checksum(token) for token in spec["v2_tokens"]]
    return encode(
        ["address", "uint256", "uint256", "address[]", "bool"],
        [checksum(recipient), CONTRACT_BALANCE, 0, tokens, False],
    )


def _execute_data(spec, recipient):
    from eth_abi import encode
    from eth_utils import keccak

    selector = keccak(text="execute(bytes,bytes[],uint256)")[:4]
    inputs = [_v3_input(spec), _v2_input(spec, recipient)]
    args = encode(
        ["bytes", "bytes[]", "uint256"], [bytes((0, 8)), inputs, DEADLINE]
    )
    return "0x" + (selector + args).hex()


def _approve_data(spender, amount):
    from eth_abi import encode
    from eth_utils import keccak, to_checksum_address as checksum

    selector = keccak(text="approve(address,uint256)")[:4]
    args = encode(["address", "uint256"], [checksum(spender), amount])
    return "0x" + (selector + args).hex()


def _direct_v3_data(state, params, spec):
    from eth_abi import encode
    from eth_utils import to_checksum_address as checksum

    selector = bytes.fromhex("414bf389")
    values = (
        checksum(params["input_token"]),
        checksum(params["output_token"]),
        int(spec["fee"]),
        checksum(state.contract_address),
        DEADLINE,
        int(params["input_amount"]),
        0,
        0,
    )
    args = encode(
        ["(address,address,uint24,address,uint256,uint256,uint256,uint160)"],
        [values],
    )
    return "0x" + (selector + args).hex()


def _direct_v3_calls(state, params, spec):
    from eth_utils import to_checksum_address as checksum

    amount = int(params["input_amount"])
    router = checksum(UNISWAP_V3_ROUTER)
    token_in = checksum(params["input_token"])
    return (
        (token_in, _approve_data(router, amount)),
        (router, _direct_v3_data(state, params, spec)),
    )


def _calls(state, params, spec):
    from eth_utils import to_checksum_address as checksum

    if spec.get("kind") == "v3_direct":
        return _direct_v3_calls(state, params, spec)
    token_in = checksum(params["input_token"])
    amount = int(params["input_amount"])
    return (
        (token_in, _transfer_data(amount)),
        (checksum(UNIVERSAL_ROUTER), _execute_data(spec, state.contract_address)),
    )


def _build(intent, state, params, spec):
    from minotaur_subnet.shared.types import ExecutionPlan, Interaction

    chain_id = int(getattr(state, "chain_id", 0) or 0)
    interactions = [
        Interaction(target=target, value="0", call_data=data, chain_id=chain_id)
        for target, data in _calls(state, params, spec)
    ]
    return ExecutionPlan(
        intent_id=intent.app_id,
        interactions=interactions,
        deadline=DEADLINE,
        nonce=state.nonce,
        metadata={"chain_id": chain_id, "solver": spec["tag"]},
    )


def maybe_quote_cover(solver, intent, state):
    try:
        params = _params(solver, intent, state)
        spec = _routes().get(_key(state, params))
        return _build(intent, state, params, spec) if spec else None
    except Exception:
        return None
