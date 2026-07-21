"""Live Ethereum V3 route fills for scorecard-proven Harvey gaps."""

from __future__ import annotations

from eth_abi import decode, encode


_MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"
_QUOTER = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"
_WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
_USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
_SINGLE_SELECTOR = bytes.fromhex("c6a5026a")
_PATH_SELECTOR = bytes.fromhex("cdca1753")
_AGGREGATE3_SELECTOR = bytes.fromhex("82ad56cb")
_FEE_TIERS = (100, 500, 3000, 10000)


def _address_bytes(address: str) -> bytes:
    return bytes.fromhex(address[2:].rjust(40, "0"))


def _single_calldata(token_in: str, token_out: str, amount: int, fee: int) -> bytes:
    params = (token_in, token_out, amount, fee, 0)
    return _SINGLE_SELECTOR + encode(
        ["(address,address,uint256,uint24,uint160)"], [params]
    )


def _path_calldata(tokens: list[str], fees: list[int], amount: int) -> bytes:
    path = b""
    for index, token in enumerate(tokens):
        path += _address_bytes(token)
        if index < len(fees):
            path += fees[index].to_bytes(3, "big")
    return _PATH_SELECTOR + encode(["bytes", "uint256"], [path, amount])


def _multicall_outputs(web3, calls: list[bytes]) -> list[int]:
    subcalls = [(_QUOTER, True, call) for call in calls]
    payload = _AGGREGATE3_SELECTOR + encode(
        ["(address,bool,bytes)[]"], [subcalls]
    )
    raw = web3.eth.call(
        {"to": web3.to_checksum_address(_MULTICALL3), "data": "0x" + payload.hex()}
    )
    (results,) = decode(["(bool,bytes)[]"], raw)
    outputs = []
    for ok, data in results:
        try:
            outputs.append(decode(["uint256"], data[:32])[0] if ok and len(data) >= 32 else 0)
        except Exception:
            outputs.append(0)
    return outputs


def _best_route(web3, token_in: str, token_out: str, amount: int):
    best = None
    direct_calls = [
        _single_calldata(token_in, token_out, amount, fee) for fee in _FEE_TIERS
    ]
    for fee, output in zip(_FEE_TIERS, _multicall_outputs(web3, direct_calls)):
        if output > 0 and (best is None or output > best["out"]):
            best = {"kind": "direct", "fee": fee, "out": output}

    for hub in (_USDC, _WETH):
        if hub.lower() in (token_in.lower(), token_out.lower()):
            continue
        combos = (
            ((500, 100), (3000, 100), (100, 500), (100, 3000))
            if hub == _USDC
            else ((500, 500), (3000, 3000), (500, 3000), (3000, 500))
        )
        calls = [
            _path_calldata([token_in, hub, token_out], [fee1, fee2], amount)
            for fee1, fee2 in combos
        ]
        for (fee1, fee2), output in zip(combos, _multicall_outputs(web3, calls)):
            if output > 0 and (best is None or output > best["out"]):
                best = {
                    "kind": "2hop",
                    "hub": hub,
                    "fee1": fee1,
                    "fee2": fee2,
                    "out": output,
                }
    return best


def build_plan(solver, intent, state, snapshot, minimum_output: int):
    """Return a live-quoted V3 plan, or None so the Harvey plan remains exact."""
    try:
        if int(getattr(state, "chain_id", 0) or 0) != 1:
            return None
        params = solver._normalized_swap_params(intent, state)
        token_in = str(params.get("input_token", "") or "")
        token_out = str(params.get("output_token", "") or "")
        amount = int(params.get("input_amount", 0) or 0)
        try:
            amount = solver._effective_swap_amount(
                solver._fee_params(state, params), token_in, amount
            )
        except Exception:
            pass
        if not token_in or not token_out or amount <= 0:
            return None
        web3 = solver._get_web3(1)
        if web3 is None:
            return None
        route = _best_route(web3, token_in, token_out, amount)
        required = max(
            minimum_output,
            int(params.get("min_output_amount", 0) or 0),
        )
        if not route or int(route["out"]) < required:
            return None
        if route["kind"] == "direct":
            candidate = {
                "venue": "uniswap_v3",
                "param": route["fee"],
                "out": int(route["out"]),
                "gas_est": 120000,
                "gas_model": 120000,
                "spend_amount": amount,
            }
        else:
            candidate = {
                "venue": "uni_v3_path",
                "param": "path",
                "tokens": [token_in, route["hub"], token_out],
                "fees": [route["fee1"], route["fee2"]],
                "out": int(route["out"]),
                "gas_est": 240000,
                "gas_model": 240000,
                "spend_amount": amount,
            }
        plan = solver._build_singlehop_plan(
            intent, state, snapshot, candidate, token_in, token_out, amount, 1
        )
        return plan if plan is not None and getattr(plan, "interactions", None) else None
    except Exception:
        return None
