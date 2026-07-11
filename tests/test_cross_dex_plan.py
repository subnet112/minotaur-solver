"""Solver-level tests: cross-DEX plan structure + route dispatch.

These need the ``minotaur_subnet`` SDK (for the shared types) — skipped if
it isn't importable. They verify (d) from the task: a mixed cross-DEX route
emits sequential per-hop approve+swap interactions with the correct
recipients (MSG_SENDER sentinel for the intermediate hop so its output
returns to the proxy; the app contract for the final hop), the chained
amounts, and the loose-intermediate / signed-final min split.
"""

import pytest

pytest.importorskip("minotaur_subnet")

from eth_abi import decode  # noqa: E402

from minotaur_subnet.shared.types import (  # noqa: E402
    AppIntentDefinition,
    IntentState,
)
from minotaur_subnet.sdk.processor_context import ProcessorContext  # noqa: E402

from strategies.dex_aggregator.baseline_solver import (  # noqa: E402
    BaselineSwapSolver,
    _MSG_SENDER_SENTINEL,
)
from strategies.dex_aggregator.quoter import (  # noqa: E402
    DEX_AERODROME_SLIPSTREAM,
    DEX_UNISWAP_V3,
)
from strategies.dex_aggregator.swap_solver import UNISWAP_V3_ROUTERS  # noqa: E402
from strategies.dex_aggregator import aerodrome as _aero  # noqa: E402

CHAIN = 8453
WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
DAI = "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb"
CONTRACT = "0x00000000000000000000000000000000C0FFEE01"
OWNER = "0x00000000000000000000000000000000000A11CE"
ORDER_MIN = 990_000_000_000_000_000  # the user's signed min (final-hop guard)


def _addr_eq(a, b):
    return a.lower() == b.lower()


def _decode_approve(call_data):
    raw = bytes.fromhex(call_data[2:])
    assert raw[:4].hex() == "095ea7b3"
    spender, amount = decode(["address", "uint256"], raw[4:])
    return spender, amount


def _decode_uni_v2_swap(call_data):
    raw = bytes.fromhex(call_data[2:])
    assert raw[:4].hex() == "04e45aaf"  # SwapRouter02 exactInputSingle (no deadline)
    (token_in, token_out, fee, recipient, amount_in, min_out, sqrt_limit) = decode(
        ["(address,address,uint24,address,uint256,uint256,uint160)"], raw[4:]
    )[0]
    return dict(
        token_in=token_in, token_out=token_out, fee=fee, recipient=recipient,
        amount_in=amount_in, min_out=min_out,
    )


def _decode_aero_swap(call_data):
    raw = bytes.fromhex(call_data[2:])
    assert raw[:4].hex() == "a026383e"  # Slipstream exactInputSingle (with deadline)
    (token_in, token_out, tick_spacing, recipient, deadline, amount_in, min_out, sqrt_limit) = decode(
        ["(address,address,int24,address,uint256,uint256,uint256,uint160)"], raw[4:]
    )[0]
    return dict(
        token_in=token_in, token_out=token_out, tick_spacing=tick_spacing,
        recipient=recipient, amount_in=amount_in, min_out=min_out,
    )


def _solver():
    s = BaselineSwapSolver()
    s.initialize({"chain_ids": [CHAIN], "rpc_urls": {CHAIN: "http://anvil"}})
    return s


def _intent():
    return AppIntentDefinition(
        app_id="dex", name="dex", version="1", intent_type="swap", js_code=""
    )


def _state():
    return IntentState(
        contract_address=CONTRACT, chain_id=CHAIN, nonce=7, owner=OWNER,
        raw_params={
            "input_token": WETH, "output_token": DAI,
            "input_amount": str(10 ** 18), "min_output_amount": str(ORDER_MIN),
            "receiver": OWNER,
        },
    )


def _uni_then_aero_hops():
    """Uni WETH→USDC then Aero USDC→DAI, with exact chained amounts."""
    hop1 = {
        "pool_addr": "0xUNI",
        "pool_state": {"dex": DEX_UNISWAP_V3, "token0": WETH, "token1": USDC, "fee": 500},
        "dex": DEX_UNISWAP_V3, "fee": 500,
        "token_in": WETH, "token_out": USDC,
        "amount_in": 10 ** 18, "amount_out": 175_000_000,
    }
    hop2 = {
        "pool_addr": "0xAERO",
        "pool_state": {
            "dex": DEX_AERODROME_SLIPSTREAM, "token0": USDC, "token1": DAI,
            "tickSpacing": 100, "fee": 100,
        },
        "dex": DEX_AERODROME_SLIPSTREAM, "fee": 100,
        "token_in": USDC, "token_out": DAI,
        "amount_in": 175_000_000, "amount_out": 174_000_000,
    }
    return [hop1, hop2]


# ── (d) cross-DEX plan structure ───────────────────────────────────────────


def test_cross_dex_plan_emits_sequential_per_hop_with_correct_recipients():
    s = _solver()
    s._normalized_swap_params = lambda intent, state: {
        "input_token": WETH, "output_token": DAI, "input_amount": 10 ** 18,
        "min_output_amount": ORDER_MIN, "receiver": OWNER, "fee_tier": 500,
    }
    ctx = ProcessorContext(chain_id=CHAIN, timestamp=1_000, block_number=0)
    hops = _uni_then_aero_hops()

    plan = s._build_cross_dex_plan(
        _intent(), _state(), ctx, hops, WETH, DAI, 10 ** 18, 174_000_000, CHAIN
    )

    # Two hops → 4 interactions: approve+swap, approve+swap.
    assert len(plan.interactions) == 4
    uni_router = UNISWAP_V3_ROUTERS[CHAIN]
    aero_router = _aero.AERODROME_SLIPSTREAM_ROUTER[CHAIN]

    # Hop 1 (Uniswap): approve the Uni router for the FULL input amount.
    spender1, amount1 = _decode_approve(plan.interactions[0].call_data)
    assert _addr_eq(plan.interactions[0].target, WETH)
    assert _addr_eq(spender1, uni_router)
    assert amount1 == 10 ** 18

    swap1 = _decode_uni_v2_swap(plan.interactions[1].call_data)
    assert _addr_eq(plan.interactions[1].target, uni_router)
    assert _addr_eq(swap1["token_in"], WETH) and _addr_eq(swap1["token_out"], USDC)
    assert swap1["amount_in"] == 10 ** 18
    assert swap1["fee"] == 500
    # Intermediate hop → MSG_SENDER sentinel (output back to the proxy).
    assert _addr_eq(swap1["recipient"], _MSG_SENDER_SENTINEL)
    # Intermediate min is loose (atomic tx; contract min guards the end).
    assert swap1["min_out"] == 0

    # Hop 2 (Aerodrome): approve the Aero router for hop-1's EXACT output.
    spender2, amount2 = _decode_approve(plan.interactions[2].call_data)
    assert _addr_eq(plan.interactions[2].target, USDC)
    assert _addr_eq(spender2, aero_router)
    assert amount2 == 175_000_000  # amountIn(hop2) == amountOut(hop1)

    swap2 = _decode_aero_swap(plan.interactions[3].call_data)
    assert _addr_eq(plan.interactions[3].target, aero_router)
    assert _addr_eq(swap2["token_in"], USDC) and _addr_eq(swap2["token_out"], DAI)
    assert swap2["amount_in"] == 175_000_000
    assert swap2["tick_spacing"] == 100
    # Final hop → the app contract (so AppIntentBase._gained() measures it).
    assert _addr_eq(swap2["recipient"], CONTRACT)
    # Final min = the user's signed order min.
    assert swap2["min_out"] == ORDER_MIN

    assert plan.metadata["route"] == "cross_dex_sequential"
    assert plan.metadata["dexes"] == [DEX_UNISWAP_V3, DEX_AERODROME_SLIPSTREAM]


def test_uniswap_singlehop_anchors_min_to_exact_output_not_input():
    # Regression: the single-hop Uniswap V3 plan must anchor amountOutMinimum
    # to the EXACT Quoter output, NOT delegate to the processor's input-derived
    # fallback (input*(1-slippage)) — which for WETH→USDC would be ~1e18, far
    # above the ~1.75e8 achievable output, guaranteeing a "Too little received"
    # revert.
    s = _solver()
    s._normalized_swap_params = lambda intent, state: {
        "input_token": WETH, "output_token": USDC, "input_amount": 10 ** 18,
        "min_output_amount": 0, "receiver": OWNER, "fee_tier": 500,
    }
    ctx = ProcessorContext(chain_id=CHAIN, timestamp=1_000, block_number=0)
    hop = {
        "dex": DEX_UNISWAP_V3, "pool_state": {"dex": DEX_UNISWAP_V3, "fee": 500},
        "fee": 500, "token_in": WETH, "token_out": USDC,
        "amount_in": 10 ** 18, "amount_out": 175_000_000,
    }
    expected = 175_000_000
    plan = s._build_uniswap_singlehop_plan(
        _intent(), _state(), ctx, hop, WETH, USDC, 10 ** 18, expected, CHAIN
    )
    assert len(plan.interactions) == 2
    spender, amount = _decode_approve(plan.interactions[0].call_data)
    assert _addr_eq(plan.interactions[0].target, WETH)
    assert _addr_eq(spender, UNISWAP_V3_ROUTERS[CHAIN])
    assert amount == 10 ** 18

    swap = _decode_uni_v2_swap(plan.interactions[1].call_data)
    assert _addr_eq(swap["token_in"], WETH) and _addr_eq(swap["token_out"], USDC)
    assert swap["fee"] == 500
    # Output goes to the app contract so AppIntentBase._gained() can measure it.
    assert _addr_eq(swap["recipient"], CONTRACT)
    slippage = s._processor.slippage_bps
    assert swap["min_out"] == expected * (10000 - slippage) // 10000
    # And critically NOT the input-denominated min (~1e18) that reverts.
    assert swap["min_out"] < 10 ** 9


def test_uniswap_singlehop_uses_order_min_when_present():
    s = _solver()
    s._normalized_swap_params = lambda intent, state: {
        "input_token": WETH, "output_token": USDC, "input_amount": 10 ** 18,
        "min_output_amount": 170_000_000, "receiver": OWNER, "fee_tier": 500,
    }
    ctx = ProcessorContext(chain_id=CHAIN, timestamp=1_000, block_number=0)
    hop = {
        "dex": DEX_UNISWAP_V3, "pool_state": {"dex": DEX_UNISWAP_V3, "fee": 500},
        "fee": 500, "token_in": WETH, "token_out": USDC,
        "amount_in": 10 ** 18, "amount_out": 175_000_000,
    }
    plan = s._build_uniswap_singlehop_plan(
        _intent(), _state(), ctx, hop, WETH, USDC, 10 ** 18, 175_000_000, CHAIN
    )
    swap = _decode_uni_v2_swap(plan.interactions[1].call_data)
    assert swap["min_out"] == 170_000_000  # the user's signed min


def test_cross_dex_plan_uses_slippage_when_no_order_min():
    s = _solver()
    s._normalized_swap_params = lambda intent, state: {
        "input_token": WETH, "output_token": DAI, "input_amount": 10 ** 18,
        "min_output_amount": 0, "receiver": OWNER, "fee_tier": 500,
    }
    ctx = ProcessorContext(chain_id=CHAIN, timestamp=1_000, block_number=0)
    expected = 174_000_000
    plan = s._build_cross_dex_plan(
        _intent(), _state(), ctx, _uni_then_aero_hops(), WETH, DAI, 10 ** 18, expected, CHAIN
    )
    swap2 = _decode_aero_swap(plan.interactions[3].call_data)
    slippage = s._processor.slippage_bps
    assert swap2["min_out"] == expected * (10000 - slippage) // 10000


# ── executability matrix ───────────────────────────────────────────────────


def _hop(dex):
    return {"dex": dex, "pool_state": {"dex": dex}, "fee": 500}


def test_executability_matrix():
    s = _solver()
    uni, aero = _hop(DEX_UNISWAP_V3), _hop(DEX_AERODROME_SLIPSTREAM)
    assert s._is_executable_route([uni], CHAIN) is True
    assert s._is_executable_route([aero], CHAIN) is True
    assert s._is_executable_route([uni, uni], CHAIN) is True  # same-DEX packed path
    assert s._is_executable_route([aero, aero], CHAIN) is True
    assert s._is_executable_route([uni, aero], CHAIN) is True  # Uni intermediate OK
    assert s._is_executable_route([aero, uni], CHAIN) is False  # Aero intermediate not routable
    # Mainnet Uni V1 router has no MSG_SENDER (and Aero isn't there anyway).
    assert s._is_executable_route([uni, aero], 1) is False


# ── generate_plan dispatch (route resolution mocked) ───────────────────────


def _dispatch_solver(monkeypatch_route):
    s = _solver()
    s._normalized_swap_params = lambda intent, state: {
        "input_token": WETH, "output_token": DAI, "input_amount": 10 ** 18,
        "min_output_amount": ORDER_MIN, "receiver": OWNER, "fee_tier": 500,
    }
    s._get_pool_states = lambda chain_id, snapshot: {"0xP": {"token0": WETH, "token1": DAI}}
    s._ensure_pools_for_route = lambda *a, **k: None
    s._derive_prices = lambda *a, **k: {}
    s._resolve_best_route = monkeypatch_route
    return s


def test_dispatch_routes_mixed_to_cross_dex_builder():
    hops = _uni_then_aero_hops()
    s = _dispatch_solver(lambda *a, **k: (174_000_000, "mixed", hops))
    called = {}
    s._build_cross_dex_plan = lambda *a, **k: called.setdefault("cross", True) or _Plan()
    s.generate_plan(_intent(), _state())
    assert called.get("cross") is True


def test_dispatch_routes_single_uni_to_uni_builder():
    hop = {
        "dex": DEX_UNISWAP_V3, "pool_state": {"dex": DEX_UNISWAP_V3, "fee": 500},
        "fee": 500, "token_in": WETH, "token_out": USDC,
        "amount_in": 10 ** 18, "amount_out": 175_000_000,
    }
    s = _dispatch_solver(lambda *a, **k: (175_000_000, "v3 direct", [hop]))
    called = {}
    s._build_uniswap_singlehop_plan = lambda *a, **k: called.setdefault("uni", True) or _Plan()
    s.generate_plan(_intent(), _state())
    assert called.get("uni") is True


def test_dispatch_routes_single_aero_to_aero_builder():
    hop = _uni_then_aero_hops()[1]
    hop = dict(hop)
    s = _dispatch_solver(lambda *a, **k: (174_000_000, "aero", [hop]))
    called = {}
    s._build_aerodrome_singlehop_plan = lambda *a, **k: called.setdefault("aero", True) or _Plan()
    s.generate_plan(_intent(), _state())
    assert called.get("aero") is True


def test_dispatch_routes_same_dex_multihop_to_uni_builder():
    h1 = {"dex": DEX_UNISWAP_V3, "pool_state": {"dex": DEX_UNISWAP_V3, "token0": WETH, "token1": USDC}, "fee": 500, "token_in": WETH, "token_out": USDC, "amount_in": 10 ** 18, "amount_out": 175_000_000}
    h2 = {"dex": DEX_UNISWAP_V3, "pool_state": {"dex": DEX_UNISWAP_V3, "token0": USDC, "token1": DAI}, "fee": 3000, "token_in": USDC, "token_out": DAI, "amount_in": 175_000_000, "amount_out": 174_000_000}
    s = _dispatch_solver(lambda *a, **k: (174_000_000, "v3 2-hop", [h1, h2]))
    called = {}
    s._build_multihop_plan = lambda *a, **k: called.setdefault("uni_mh", True) or _Plan()
    s.generate_plan(_intent(), _state())
    assert called.get("uni_mh") is True


class _Plan:
    """Stand-in plan returned by mocked builders; only metadata is touched."""

    def __init__(self):
        self.metadata = {}
        self.interactions = []
