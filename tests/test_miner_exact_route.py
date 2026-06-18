"""Miner overlay tests for the June 17 exact-Quoter baseline."""

from solver import GAS_AWARE_MIN_OUTPUT_BPS, MinerSolver


TOKEN_IN = "0x0000000000000000000000000000000000000001"
TOKEN_OUT = "0x0000000000000000000000000000000000000002"
MID = "0x0000000000000000000000000000000000000003"


def _pool(token0, token1, *, liquidity, dex="uniswap_v3", fee=500):
    return {
        "token0": token0,
        "token1": token1,
        "liquidity": liquidity,
        "dex": dex,
        "fee": fee,
    }


def test_exact_route_overlay_prefers_cheaper_near_equal_output():
    solver = MinerSolver()
    pools = {
        "0x0000000000000000000000000000000000000010": _pool(
            TOKEN_IN, TOKEN_OUT, liquidity=1_000,
        ),
        "0x0000000000000000000000000000000000000020": _pool(
            TOKEN_IN, MID, liquidity=900,
        ),
        "0x0000000000000000000000000000000000000030": _pool(
            MID, TOKEN_OUT, liquidity=900,
        ),
    }

    def quote_hop(hop, amount):
        if hop["token_out"].lower() == MID.lower():
            return amount
        if hop["token_in"].lower() == MID.lower():
            return 10_000
        return 9_999

    route = solver._resolve_exact_route_set(
        quote_hop,
        pools,
        TOKEN_IN,
        TOKEN_OUT,
        10_000,
        8453,
        [MID],
    )

    assert GAS_AWARE_MIN_OUTPUT_BPS == 9_998
    assert route[0] == 9_999
    assert len(route[2]) == 1


def test_exact_route_overlay_keeps_materially_better_output():
    solver = MinerSolver()
    pools = {
        "0x0000000000000000000000000000000000000010": _pool(
            TOKEN_IN, TOKEN_OUT, liquidity=1_000,
        ),
        "0x0000000000000000000000000000000000000020": _pool(
            TOKEN_IN, MID, liquidity=900,
        ),
        "0x0000000000000000000000000000000000000030": _pool(
            MID, TOKEN_OUT, liquidity=900,
        ),
    }

    def quote_hop(hop, amount):
        if hop["token_out"].lower() == MID.lower():
            return amount
        if hop["token_in"].lower() == MID.lower():
            return 10_100
        return 10_000

    route = solver._resolve_exact_route_set(
        quote_hop,
        pools,
        TOKEN_IN,
        TOKEN_OUT,
        10_000,
        8453,
        [MID],
    )

    assert route[0] == 10_100
    assert len(route[2]) == 2
