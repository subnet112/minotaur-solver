"""Miner overlay tests for the June 17 exact-Quoter baseline."""

from collections import Counter

from solver import MIN_ROUTE_HEADROOM_BPS, MinerSolver, SCORE_SCALE
from strategies.dex_aggregator.baseline_solver import BaselineSwapSolver


TOKEN_IN = "0x0000000000000000000000000000000000000001"
TOKEN_OUT = "0x0000000000000000000000000000000000000002"
MID = "0x0000000000000000000000000000000000000003"


def _pool(token0, token1, *, liquidity, dex="uniswap_v3", fee=500, **extra):
    return {
        "token0": token0,
        "token1": token1,
        "liquidity": liquidity,
        "dex": dex,
        "fee": fee,
        **extra,
    }


def test_exact_route_overlay_prefers_cheaper_near_equal_output():
    solver = MinerSolver()
    solver._active_min_output = 9_900
    solver._active_quoted_output = 10_000
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

    assert route[0] == 9_999
    assert len(route[2]) == 1


def test_exact_route_overlay_keeps_materially_better_output():
    solver = MinerSolver()
    solver._active_min_output = 9_900
    solver._active_quoted_output = 10_000
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
            return 10_601
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

    assert route[0] == 10_601
    assert len(route[2]) == 2


def test_route_score_matches_current_quote_anchored_curve():
    solver = MinerSolver()
    solver._active_min_output = 9_500
    solver._active_quoted_output = 10_000
    route = (
        9_800,
        "direct",
        [{"pool_addr": "0x0000000000000000000000000000000000000010"}],
    )

    output_score = 9_800 * (SCORE_SCALE // 2) // 10_000
    gas_score = SCORE_SCALE - 430_000

    assert solver._route_score_scaled(route) == 8 * output_score + 2 * gas_score


def test_selector_rejects_every_route_below_execution_minimum():
    solver = MinerSolver()
    solver._active_min_output = 9_900
    solver._active_quoted_output = 10_000

    assert solver._best_scored_route([
        (
            9_899,
            "below min",
            [{"pool_addr": "0x0000000000000000000000000000000000000010"}],
        ),
    ]) is None


def test_selector_requires_measured_headroom_above_minimum():
    solver = MinerSolver()
    solver._active_min_output = 10_000
    solver._active_quoted_output = 10_100

    too_close = (
        10_024,
        "14-24 bps headroom",
        [{"pool_addr": "0x0000000000000000000000000000000000000010"}],
    )
    safe = (
        10_025,
        "25 bps headroom",
        [{"pool_addr": "0x0000000000000000000000000000000000000020"}],
    )

    assert MIN_ROUTE_HEADROOM_BPS == 25
    assert solver._best_scored_route([too_close]) is None
    assert solver._best_scored_route([too_close, safe]) == safe


def test_route_description_is_local_and_stable():
    solver = MinerSolver()
    direct = [{
        "dex": "uniswap_v3",
        "fee": 500,
        "pool_state": {"dex": "uniswap_v3", "fee": 500},
    }]
    mixed = [
        {
            "dex": "uniswap_v3",
            "fee": 500,
            "pool_state": {"dex": "uniswap_v3", "fee": 500},
        },
        {
            "dex": "aerodrome_slipstream",
            "fee": 100,
            "pool_state": {
                "dex": "aerodrome_slipstream",
                "tickSpacing": 100,
            },
        },
    ]

    assert solver._exact_route_description(direct) == "direct via v3 0.05% pool"
    assert solver._exact_route_description(mixed) == "2-hop via v3:500 + aero:100"


def test_full_resolution_memoizes_duplicate_hop_quotes(monkeypatch):
    from strategies.dex_aggregator import quoter

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
        "0x0000000000000000000000000000000000000040": _pool(
            MID, TOKEN_OUT, liquidity=800, fee=3_000,
        ),
    }
    calls: Counter[tuple[str, int]] = Counter()

    def quote_hop(hop, amount):
        key = (hop["pool_addr"].lower(), int(amount))
        calls[key] += 1
        return amount

    monkeypatch.setattr(quoter, "make_quote_fn", lambda w3, chain_id: quote_hop)
    monkeypatch.setattr(solver, "_get_web3", lambda chain_id: object())
    monkeypatch.setattr(
        solver,
        "_intermediaries_for_chain",
        lambda chain_id: [MID],
    )

    route = solver._resolve_best_route(
        pools,
        TOKEN_IN,
        TOKEN_OUT,
        10_000,
        8453,
    )

    assert route[0] == 10_000
    assert calls
    assert max(calls.values()) == 1
    assert sum(calls.values()) == 4
    assert solver._last_route_analysis is not None
    assert solver._last_route_analysis["candidate_set"] == "canonical"
    assert solver._last_route_analysis["selected_output"] == 10_000


def test_quote_cache_is_scoped_to_one_resolution(monkeypatch):
    from strategies.dex_aggregator import quoter

    solver = MinerSolver()
    pools = {
        "0x0000000000000000000000000000000000000010": _pool(
            TOKEN_IN, TOKEN_OUT, liquidity=1_000,
        ),
    }
    calls = 0

    def quote_hop(hop, amount):
        nonlocal calls
        calls += 1
        return amount

    monkeypatch.setattr(quoter, "make_quote_fn", lambda w3, chain_id: quote_hop)
    monkeypatch.setattr(solver, "_get_web3", lambda chain_id: object())
    monkeypatch.setattr(
        solver,
        "_intermediaries_for_chain",
        lambda chain_id: [],
    )

    solver._resolve_best_route(pools, TOKEN_IN, TOKEN_OUT, 10_000, 8453)
    solver._resolve_best_route(pools, TOKEN_IN, TOKEN_OUT, 10_000, 8453)

    assert calls == 2


def test_best_route_uses_one_canonical_candidate_pass(monkeypatch):
    from strategies.dex_aggregator import quoter

    solver = MinerSolver()
    route = (
        10_000,
        "direct via v3 0.05% pool",
        [{"pool_addr": "0x0000000000000000000000000000000000000010"}],
    )
    analysis = {
        "selected_category": "single_dex",
        "selected_output": 10_000,
    }
    calls = 0

    def analyze(*args, **kwargs):
        nonlocal calls
        calls += 1
        return route, analysis

    monkeypatch.setattr(quoter, "make_quote_fn", lambda w3, chain_id: lambda hop, amount: amount)
    monkeypatch.setattr(solver, "_get_web3", lambda chain_id: object())
    monkeypatch.setattr(solver, "_intermediaries_for_chain", lambda chain_id: [MID])
    monkeypatch.setattr(solver, "_analyze_exact_route_set", analyze)

    selected = solver._resolve_best_route(
        {},
        TOKEN_IN,
        TOKEN_OUT,
        10_000,
        8453,
    )

    assert selected == route
    assert calls == 1
    assert solver._last_route_analysis["candidate_set"] == "canonical"


def test_cross_dex_output_edge_is_selected_and_measured():
    solver = MinerSolver()
    solver._active_min_output = 9_900
    solver._active_quoted_output = 10_000
    pools = {
        "0x0000000000000000000000000000000000000010": _pool(
            TOKEN_IN, TOKEN_OUT, liquidity=1_000,
        ),
        "0x0000000000000000000000000000000000000020": _pool(
            TOKEN_IN, MID, liquidity=900,
        ),
        "0x0000000000000000000000000000000000000030": _pool(
            MID,
            TOKEN_OUT,
            liquidity=900,
            dex="aerodrome_slipstream",
            fee=0,
            tickSpacing=100,
        ),
    }

    def quote_hop(hop, amount):
        if hop["token_out"].lower() == MID.lower():
            return amount
        if hop["token_in"].lower() == MID.lower():
            return 10_700
        return 10_000

    route, analysis = solver._analyze_exact_route_set(
        quote_hop,
        pools,
        TOKEN_IN,
        TOKEN_OUT,
        10_000,
        8453,
        [MID],
    )

    assert route[0] == 10_700
    assert analysis["selected_category"] == "cross_dex"
    assert analysis["single_dex_output"] == 10_000
    assert analysis["cross_dex_output"] == 10_700
    assert analysis["cross_dex_output_delta"] == 700
    assert analysis["cross_dex_output_edge_bps"] == 700
    assert analysis["cross_dex_gas_delta"] > 0
    assert analysis["cross_dex_min_headroom_bps"] == 808
    assert analysis["cross_dex_quote_ratio_bps"] == 10_700
    assert analysis["cross_dex_quote_edge_bps"] == 700


def test_near_equal_cross_dex_route_is_reported_but_not_selected():
    solver = MinerSolver()
    solver._active_min_output = 9_900
    solver._active_quoted_output = 10_000
    pools = {
        "0x0000000000000000000000000000000000000010": _pool(
            TOKEN_IN, TOKEN_OUT, liquidity=1_000,
        ),
        "0x0000000000000000000000000000000000000020": _pool(
            TOKEN_IN, MID, liquidity=900,
        ),
        "0x0000000000000000000000000000000000000030": _pool(
            MID,
            TOKEN_OUT,
            liquidity=900,
            dex="aerodrome_slipstream",
            fee=0,
            tickSpacing=100,
        ),
    }

    def quote_hop(hop, amount):
        if hop["token_out"].lower() == MID.lower():
            return amount
        if hop["token_in"].lower() == MID.lower():
            return 10_001
        return 10_000

    route, analysis = solver._analyze_exact_route_set(
        quote_hop,
        pools,
        TOKEN_IN,
        TOKEN_OUT,
        10_000,
        8453,
        [MID],
    )

    assert route[0] == 10_000
    assert len(route[2]) == 1
    assert analysis["selected_category"] == "single_dex"
    assert analysis["cross_dex_output_edge_bps"] == 1
    assert analysis["cross_dex_quote_edge_bps"] == 1
    assert analysis["cross_dex_gas_delta"] > 0


def test_active_context_reads_raw_quoted_output_with_typed_minimum():
    solver = MinerSolver()

    class Typed:
        min_output_amount = 9_900

    class State:
        typed_context = Typed()

        @staticmethod
        def raw_params_view():
            return {"min_output_amount": 9_800, "quoted_output": 10_000}

    solver._set_active_route_from_state(State())

    assert solver._active_min_output == 9_900
    assert solver._active_quoted_output == 10_000


def test_generate_plan_exposes_route_analysis(monkeypatch):
    solver = MinerSolver()

    class Plan:
        def __init__(self):
            self.metadata = {"route": "test"}

    def generate_plan(self, intent, state, snapshot=None):
        self._last_route_analysis = {
            "selected_category": "cross_dex",
            "cross_dex_output_edge_bps": 25,
        }
        return Plan()

    monkeypatch.setattr(BaselineSwapSolver, "generate_plan", generate_plan)
    plan = solver.generate_plan(object(), object())

    assert plan.metadata["route"] == "test"
    assert plan.metadata["miner_route_analysis"] == {
        "selected_category": "cross_dex",
        "cross_dex_output_edge_bps": 25,
    }
