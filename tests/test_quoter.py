"""Unit tests for the exact on-chain quoting + route resolution engine.

These are PURE — they don't need the ``minotaur_subnet`` SDK. The
``eth_call`` layer is exercised with a fake Web3; the routing logic with a
fake per-hop quote function, so the behaviour under test is the
enumeration / chaining / pick-best / fail-loud logic, not RPC.
"""

import pytest

from strategies.dex_aggregator import quoter as q
from strategies.dex_aggregator.quoter import (
    DEX_AERODROME_SLIPSTREAM,
    DEX_UNISWAP_V3,
    NoRouteError,
    QuoteHopError,
    QuoterUnavailable,
)

TOKEN_A = "0x000000000000000000000000000000000000000A"
TOKEN_B = "0x000000000000000000000000000000000000000B"
WETH = "0x4200000000000000000000000000000000000006"


def _pool(token0, token1, dex, *, fee=3000, tick_spacing=None, liquidity=1_000, rate=1.0):
    """A synthetic pool_state. ``rate`` is read by the fake quote fn — the
    per-hop output is amount_in * rate."""
    state = {
        "token0": token0,
        "token1": token1,
        "dex": dex,
        "fee": fee,
        "liquidity": str(liquidity),
        "test_rate": rate,
    }
    if tick_spacing is not None:
        state["tickSpacing"] = tick_spacing
    return state


def _fake_quote(fail_pools=()):
    """Fake per-hop quoter: output = amount_in * pool.test_rate, raising a
    skippable QuoteHopError for any pool in ``fail_pools``."""

    def quote_hop(hop, amount_in):
        addr = hop["pool_addr"]
        if addr in fail_pools:
            raise QuoteHopError(f"forced fail {addr}")
        rate = hop["pool_state"]["test_rate"]
        return int(amount_in * rate)

    return quote_hop


# ── enumeration ────────────────────────────────────────────────────────────


def test_enumerate_includes_direct_and_two_hop_cross_dex():
    pools = {
        "0xDIRECT": _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3),
        "0xLEG1": _pool(TOKEN_A, WETH, DEX_UNISWAP_V3),
        "0xLEG2": _pool(WETH, TOKEN_B, DEX_AERODROME_SLIPSTREAM, tick_spacing=100),
    }
    routes = q.enumerate_candidate_routes(pools, TOKEN_A, TOKEN_B, [WETH])
    lengths = sorted(len(r) for r in routes)
    assert 1 in lengths and 2 in lengths
    # The two-hop route is naturally cross-DEX (Uni leg 1 + Aero leg 2).
    two_hop = [r for r in routes if len(r) == 2][0]
    assert q.hop_dex(two_hop[0]) == DEX_UNISWAP_V3
    assert q.hop_dex(two_hop[1]) == DEX_AERODROME_SLIPSTREAM


def test_enumerate_skips_intermediary_equal_to_endpoint():
    pools = {"0xDIRECT": _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3)}
    # WETH==token_out: intermediary collapses, only the direct route remains.
    routes = q.enumerate_candidate_routes(pools, TOKEN_A, TOKEN_B, [TOKEN_B])
    assert all(len(r) == 1 for r in routes)


# ── (a) single-DEX route exact-quoted ──────────────────────────────────────


def test_resolve_single_dex_picks_higher_exact_output():
    pools = {
        "0xLOW": _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, fee=3000, rate=100.0),
        "0xHIGH": _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, fee=500, rate=110.0),
    }
    out, desc, hops = q.resolve_best_route(
        _fake_quote(), pools, TOKEN_A, TOKEN_B, 1_000, intermediaries=[]
    )
    assert len(hops) == 1
    assert hops[0]["pool_addr"] == "0xHIGH"
    assert out == 1_000 * 110
    assert hops[0]["amount_in"] == 1_000
    assert hops[0]["amount_out"] == out


# ── (b) cross-DEX route chains across both Quoters, best-by-output ──────────


def test_resolve_cross_dex_chains_and_beats_direct():
    pools = {
        "0xDIRECT": _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, rate=100.0, liquidity=1_000),
        "0xLEG1": _pool(TOKEN_A, WETH, DEX_UNISWAP_V3, fee=500, rate=10.0, liquidity=5_000),
        "0xLEG2": _pool(
            WETH, TOKEN_B, DEX_AERODROME_SLIPSTREAM, tick_spacing=100, rate=12.0, liquidity=5_000
        ),
    }
    out, desc, hops = q.resolve_best_route(
        _fake_quote(), pools, TOKEN_A, TOKEN_B, 1_000, intermediaries=[WETH]
    )
    # 2-hop = 1000*10*12 = 120_000 beats direct 1000*100 = 100_000.
    assert [h["pool_addr"] for h in hops] == ["0xLEG1", "0xLEG2"]
    assert out == 120_000
    # Amounts chain: in→10x→120x.
    assert hops[0]["amount_in"] == 1_000
    assert hops[0]["amount_out"] == 10_000
    assert hops[1]["amount_in"] == 10_000
    assert hops[1]["amount_out"] == 120_000


def test_resolve_falls_back_to_best_executable_route():
    # Best raw route (Aero→Uni 2-hop, rate 10*30=300) is NOT executable;
    # resolver must return the best EXECUTABLE one (direct Uni, rate 100).
    pools = {
        "0xDIRECT": _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, rate=100.0),
        "0xLEG1": _pool(TOKEN_A, WETH, DEX_AERODROME_SLIPSTREAM, tick_spacing=100, rate=10.0),
        "0xLEG2": _pool(WETH, TOKEN_B, DEX_UNISWAP_V3, fee=500, rate=30.0),
    }

    def is_executable(hops):
        if len(hops) <= 1:
            return True
        dexes = {q.hop_dex(h) for h in hops}
        if len(dexes) == 1:
            return True
        # Mirror the solver: non-final hops must be Uniswap (sentinel-routable).
        return all(q.hop_dex(h) == DEX_UNISWAP_V3 for h in hops[:-1])

    out, desc, hops = q.resolve_best_route(
        _fake_quote(), pools, TOKEN_A, TOKEN_B, 1_000,
        intermediaries=[WETH], is_executable=is_executable,
    )
    assert len(hops) == 1 and hops[0]["pool_addr"] == "0xDIRECT"
    assert out == 100_000


def test_resolve_skips_reverting_pool_and_uses_next():
    pools = {
        "0xBAD": _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, fee=3000, rate=999.0),
        "0xGOOD": _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, fee=500, rate=50.0),
    }
    out, desc, hops = q.resolve_best_route(
        _fake_quote(fail_pools={"0xBAD"}), pools, TOKEN_A, TOKEN_B, 1_000, intermediaries=[]
    )
    assert hops[0]["pool_addr"] == "0xGOOD"
    assert out == 50_000


def test_resolve_winner_hops_not_corrupted_by_shared_leg():
    # Regression: two 2-hop candidates share the SAME leg-2 pool dict. The
    # winner ([LEG1A, LEG2]) is ranked/quoted first; a losing sibling
    # ([LEG1B, LEG2]) is quoted afterward. The winner's chained per-hop
    # amounts must NOT be corrupted by the sibling's mutation of the shared
    # hop (the cross-DEX plan reads these for each hop's amountIn).
    pools = {
        "0xLEG1A": _pool(TOKEN_A, WETH, DEX_UNISWAP_V3, fee=500, rate=10.0, liquidity=9_000),
        "0xLEG1B": _pool(TOKEN_A, WETH, DEX_UNISWAP_V3, fee=3000, rate=2.0, liquidity=8_000),
        "0xLEG2": _pool(WETH, TOKEN_B, DEX_UNISWAP_V3, fee=500, rate=5.0, liquidity=10_000),
    }
    out, desc, hops = q.resolve_best_route(
        _fake_quote(), pools, TOKEN_A, TOKEN_B, 1_000, intermediaries=[WETH]
    )
    # Winner LEG1A→LEG2 = 1000*10*5 = 50_000 (beats LEG1B→LEG2 = 1000*2*5 = 10_000).
    assert out == 50_000
    assert [h["pool_addr"] for h in hops] == ["0xLEG1A", "0xLEG2"]
    assert hops[0]["amount_in"] == 1_000 and hops[0]["amount_out"] == 10_000
    # Must be the WINNER's chained amounts (10_000 → 50_000), NOT the loser's
    # (2_000 → 10_000) that would leak in via the shared leg-2 dict.
    assert hops[1]["amount_in"] == 10_000 and hops[1]["amount_out"] == 50_000


def test_resolve_budget_not_consumed_by_reverts():
    # Regression: the MAX_QUOTE_CANDIDATES budget must count SUCCESSFUL quotes
    # only. Here the 6 highest-liquidity candidates all revert; a viable but
    # thinner 7th route must still be found (not a false NoRouteError).
    pools = {}
    fail = set()
    for i in range(6):
        addr = f"0xHI{i}"
        pools[addr] = _pool(
            TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, fee=100 + i, rate=999.0, liquidity=10_000 - i
        )
        fail.add(addr)
    pools["0xLOW"] = _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, fee=9000, rate=42.0, liquidity=1)

    out, desc, hops = q.resolve_best_route(
        _fake_quote(fail_pools=fail), pools, TOKEN_A, TOKEN_B, 1_000,
        intermediaries=[], max_candidates=6,
    )
    assert hops[0]["pool_addr"] == "0xLOW"
    assert out == 42_000


# ── (c) fail loud ──────────────────────────────────────────────────────────


def test_make_quote_fn_raises_when_no_web3():
    with pytest.raises(QuoterUnavailable):
        q.make_quote_fn(None, 8453)


def test_make_quote_fn_raises_for_chain_without_quoter():
    # Chain 964 (BT EVM) has no standard Quoter → fail loud.
    fake_w3 = object()
    with pytest.raises(QuoterUnavailable):
        q.make_quote_fn(fake_w3, 964)


def test_resolve_raises_no_route_when_all_candidates_fail():
    pools = {
        "0xP1": _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, fee=3000, rate=1.0),
        "0xP2": _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, fee=500, rate=1.0),
    }
    with pytest.raises(NoRouteError):
        q.resolve_best_route(
            _fake_quote(fail_pools={"0xP1", "0xP2"}),
            pools, TOKEN_A, TOKEN_B, 1_000, intermediaries=[],
        )


def test_resolve_raises_no_route_when_no_pools():
    with pytest.raises(NoRouteError):
        q.resolve_best_route(_fake_quote(), {}, TOKEN_A, TOKEN_B, 1_000, intermediaries=[])


def test_resolve_propagates_non_revert_errors():
    # A transport-level failure (not a Quoter revert) must NOT be swallowed
    # as a skippable candidate — it propagates (fail loud, no silent fallback).
    pools = {"0xP1": _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3)}

    def exploding_quote(hop, amount_in):
        raise RuntimeError("RPC timeout")

    with pytest.raises(RuntimeError):
        q.resolve_best_route(
            exploding_quote, pools, TOKEN_A, TOKEN_B, 1_000, intermediaries=[]
        )


# ── make_quote_fn eth_call layer (fake Web3) ───────────────────────────────


class _FakeFn:
    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc

    def call(self):
        if self._exc is not None:
            raise self._exc
        return self._result


class _FakeContractFns:
    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc

    def quoteExactInputSingle(self, params):  # noqa: N802 (mirror ABI name)
        self.last_params = params
        return _FakeFn(self._result, self._exc)


class _FakeContract:
    def __init__(self, result=None, exc=None):
        self.functions = _FakeContractFns(result, exc)


class _FakeEth:
    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc
        self.contracts = []

    def contract(self, address, abi):
        c = _FakeContract(self._result, self._exc)
        self.contracts.append((address, abi, c))
        return c


class _FakeW3:
    def __init__(self, result=None, exc=None):
        self.eth = _FakeEth(result, exc)

    def to_checksum_address(self, a):
        return a


def _uni_hop():
    return {
        "pool_addr": "0xP",
        "pool_state": {"dex": DEX_UNISWAP_V3, "fee": 500},
        "dex": DEX_UNISWAP_V3,
        "fee": 500,
        "token_in": TOKEN_A,
        "token_out": TOKEN_B,
    }


def test_make_quote_fn_returns_amount_out():
    w3 = _FakeW3(result=[12345, 0, 1, 0])
    quote_hop = q.make_quote_fn(w3, 8453)
    assert quote_hop(_uni_hop(), 1_000) == 12345


def test_make_quote_fn_wraps_contract_revert_as_skippable():
    from web3.exceptions import ContractLogicError

    w3 = _FakeW3(exc=ContractLogicError("execution reverted"))
    quote_hop = q.make_quote_fn(w3, 8453)
    with pytest.raises(QuoteHopError):
        quote_hop(_uni_hop(), 1_000)


def test_make_quote_fn_zero_output_is_skippable():
    w3 = _FakeW3(result=[0, 0, 0, 0])
    quote_hop = q.make_quote_fn(w3, 8453)
    with pytest.raises(QuoteHopError):
        quote_hop(_uni_hop(), 1_000)


def test_make_quote_fn_uses_tickspacing_for_aerodrome():
    w3 = _FakeW3(result=[777, 0, 1, 0])
    quote_hop = q.make_quote_fn(w3, 8453)
    aero_hop = {
        "pool_addr": "0xA",
        "pool_state": {"dex": DEX_AERODROME_SLIPSTREAM, "tickSpacing": 100, "fee": 100},
        "dex": DEX_AERODROME_SLIPSTREAM,
        "fee": 100,
        "token_in": TOKEN_A,
        "token_out": TOKEN_B,
    }
    assert quote_hop(aero_hop, 1_000) == 777
    # The Aerodrome Quoter param is tickSpacing (100), not the fee.
    fns = w3.eth.contracts[-1][2].functions
    assert fns.last_params[3] == 100
