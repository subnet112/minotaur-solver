"""Unit tests for the exact on-chain quoting + route resolution engine.

These are PURE — they don't need the ``minotaur_subnet`` SDK. The
``eth_call`` layer is exercised with a fake Web3; the routing logic with a
fake per-hop quote function, so the behaviour under test is the
enumeration / chaining / pick-best / fail-loud logic, not RPC.
"""
import pytest
from strategies.dex_aggregator import quoter as q
from strategies.dex_aggregator.quoter import DEX_AERODROME_SLIPSTREAM, DEX_UNISWAP_V3, NoRouteError, QuoteHopError, QuoterUnavailable
TOKEN_A = '0x000000000000000000000000000000000000000A'
TOKEN_B = '0x000000000000000000000000000000000000000B'
WETH = '0x4200000000000000000000000000000000000006'

def _pool(token0, token1, dex, *, fee=3000, tick_spacing=None, liquidity=1000, rate=1.0):
    """A synthetic pool_state. ``rate`` is read by the fake quote fn — the
    per-hop output is amount_in * rate."""
    state = {'token0': token0, 'token1': token1, 'dex': dex, 'fee': fee, 'liquidity': str(liquidity), 'test_rate': rate}
    if tick_spacing is not None:
        state['tickSpacing'] = tick_spacing
    return state

def _fake_quote(fail_pools=()):
    """Fake per-hop quoter: output = amount_in * pool.test_rate, raising a
    skippable QuoteHopError for any pool in ``fail_pools``."""

    def quote_hop(hop, amount_in):
        addr = hop['pool_addr']
        if addr in fail_pools:
            raise QuoteHopError(f'forced fail {addr}')
        rate = hop['pool_state']['test_rate']
        return int(amount_in * rate)
    return quote_hop

def test_enumerate_includes_direct_and_two_hop_cross_dex():

    def _dr3():
        pools = {'0xDIRECT': _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3), '0xLEG1': _pool(TOKEN_A, WETH, DEX_UNISWAP_V3), '0xLEG2': _pool(WETH, TOKEN_B, DEX_AERODROME_SLIPSTREAM, tick_spacing=100)}
        routes = q.enumerate_candidate_routes(pools, TOKEN_A, TOKEN_B, [WETH])
        lengths = sorted((len(r) for r in routes))
        assert 1 in lengths and 2 in lengths
        two_hop = [r for r in routes if len(r) == 2][0]
        assert q.hop_dex(two_hop[0]) == DEX_UNISWAP_V3
        return two_hop
    two_hop = _dr3()
    assert q.hop_dex(two_hop[1]) == DEX_AERODROME_SLIPSTREAM

def test_enumerate_skips_intermediary_equal_to_endpoint():
    pools = {'0xDIRECT': _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3)}
    routes = q.enumerate_candidate_routes(pools, TOKEN_A, TOKEN_B, [TOKEN_B])
    assert all((len(r) == 1 for r in routes))

def test_resolve_single_dex_picks_higher_exact_output():
    pools = {'0xLOW': _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, fee=3000, rate=100.0), '0xHIGH': _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, fee=500, rate=110.0)}
    out, desc, hops = q.resolve_best_route(_fake_quote(), pools, TOKEN_A, TOKEN_B, 1000, intermediaries=[])
    assert len(hops) == 1
    assert hops[0]['pool_addr'] == '0xHIGH'
    assert out == 1000 * 110
    assert hops[0]['amount_in'] == 1000
    assert hops[0]['amount_out'] == out

def test_resolve_cross_dex_chains_and_beats_direct():

    def _dr2():
        pools = {'0xDIRECT': _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, rate=100.0, liquidity=1000), '0xLEG1': _pool(TOKEN_A, WETH, DEX_UNISWAP_V3, fee=500, rate=10.0, liquidity=5000), '0xLEG2': _pool(WETH, TOKEN_B, DEX_AERODROME_SLIPSTREAM, tick_spacing=100, rate=12.0, liquidity=5000)}
        out, desc, hops = q.resolve_best_route(_fake_quote(), pools, TOKEN_A, TOKEN_B, 1000, intermediaries=[WETH])
        assert [h['pool_addr'] for h in hops] == ['0xLEG1', '0xLEG2']
        assert out == 120000
        assert hops[0]['amount_in'] == 1000
        return hops
    hops = _dr2()
    assert hops[0]['amount_out'] == 10000
    assert hops[1]['amount_in'] == 10000
    assert hops[1]['amount_out'] == 120000

def test_resolve_falls_back_to_best_executable_route():
    pools = {'0xDIRECT': _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, rate=100.0), '0xLEG1': _pool(TOKEN_A, WETH, DEX_AERODROME_SLIPSTREAM, tick_spacing=100, rate=10.0), '0xLEG2': _pool(WETH, TOKEN_B, DEX_UNISWAP_V3, fee=500, rate=30.0)}

    def is_executable(hops):
        if len(hops) <= 1:
            return True
        dexes = {q.hop_dex(h) for h in hops}
        if len(dexes) == 1:
            return True
        return all((q.hop_dex(h) == DEX_UNISWAP_V3 for h in hops[:-1]))
    out, desc, hops = q.resolve_best_route(_fake_quote(), pools, TOKEN_A, TOKEN_B, 1000, intermediaries=[WETH], is_executable=is_executable)
    assert len(hops) == 1 and hops[0]['pool_addr'] == '0xDIRECT'
    assert out == 100000

def test_resolve_skips_reverting_pool_and_uses_next():
    pools = {'0xBAD': _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, fee=3000, rate=999.0), '0xGOOD': _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, fee=500, rate=50.0)}
    out, desc, hops = q.resolve_best_route(_fake_quote(fail_pools={'0xBAD'}), pools, TOKEN_A, TOKEN_B, 1000, intermediaries=[])
    assert hops[0]['pool_addr'] == '0xGOOD'
    assert out == 50000

def test_resolve_winner_hops_not_corrupted_by_shared_leg():
    pools = {'0xLEG1A': _pool(TOKEN_A, WETH, DEX_UNISWAP_V3, fee=500, rate=10.0, liquidity=9000), '0xLEG1B': _pool(TOKEN_A, WETH, DEX_UNISWAP_V3, fee=3000, rate=2.0, liquidity=8000), '0xLEG2': _pool(WETH, TOKEN_B, DEX_UNISWAP_V3, fee=500, rate=5.0, liquidity=10000)}

    def _dr1():
        out, desc, hops = q.resolve_best_route(_fake_quote(), pools, TOKEN_A, TOKEN_B, 1000, intermediaries=[WETH])
        assert out == 50000
        assert [h['pool_addr'] for h in hops] == ['0xLEG1A', '0xLEG2']
        assert hops[0]['amount_in'] == 1000 and hops[0]['amount_out'] == 10000
        assert hops[1]['amount_in'] == 10000 and hops[1]['amount_out'] == 50000
    _dr1()

def test_resolve_budget_not_consumed_by_reverts():
    pools = {}
    fail = set()

    def _dr4():
        for i in range(6):
            addr = f'0xHI{i}'
            pools[addr] = _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, fee=100 + i, rate=999.0, liquidity=10000 - i)
            fail.add(addr)
        pools['0xLOW'] = _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, fee=9000, rate=42.0, liquidity=1)
        out, desc, hops = q.resolve_best_route(_fake_quote(fail_pools=fail), pools, TOKEN_A, TOKEN_B, 1000, intermediaries=[], max_candidates=6)
        assert hops[0]['pool_addr'] == '0xLOW'
        assert out == 42000
    _dr4()

def test_make_quote_fn_raises_when_no_web3():
    with pytest.raises(QuoterUnavailable):
        q.make_quote_fn(None, 8453)

def test_make_quote_fn_raises_for_chain_without_quoter():
    fake_w3 = object()
    with pytest.raises(QuoterUnavailable):
        q.make_quote_fn(fake_w3, 964)

def test_resolve_raises_no_route_when_all_candidates_fail():
    pools = {'0xP1': _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, fee=3000, rate=1.0), '0xP2': _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3, fee=500, rate=1.0)}
    with pytest.raises(NoRouteError):
        q.resolve_best_route(_fake_quote(fail_pools={'0xP1', '0xP2'}), pools, TOKEN_A, TOKEN_B, 1000, intermediaries=[])

def test_resolve_raises_no_route_when_no_pools():
    with pytest.raises(NoRouteError):
        q.resolve_best_route(_fake_quote(), {}, TOKEN_A, TOKEN_B, 1000, intermediaries=[])

def test_resolve_propagates_non_revert_errors():
    pools = {'0xP1': _pool(TOKEN_A, TOKEN_B, DEX_UNISWAP_V3)}

    def exploding_quote(hop, amount_in):
        raise RuntimeError('RPC timeout')
    with pytest.raises(RuntimeError):
        q.resolve_best_route(exploding_quote, pools, TOKEN_A, TOKEN_B, 1000, intermediaries=[])

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

    def quoteExactInputSingle(self, params):
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
    return {'pool_addr': '0xP', 'pool_state': {'dex': DEX_UNISWAP_V3, 'fee': 500}, 'dex': DEX_UNISWAP_V3, 'fee': 500, 'token_in': TOKEN_A, 'token_out': TOKEN_B}

def test_make_quote_fn_returns_amount_out():
    w3 = _FakeW3(result=[12345, 0, 1, 0])
    quote_hop = q.make_quote_fn(w3, 8453)
    assert quote_hop(_uni_hop(), 1000) == 12345

def test_make_quote_fn_wraps_contract_revert_as_skippable():
    from web3.exceptions import ContractLogicError
    w3 = _FakeW3(exc=ContractLogicError('execution reverted'))
    quote_hop = q.make_quote_fn(w3, 8453)
    with pytest.raises(QuoteHopError):
        quote_hop(_uni_hop(), 1000)

def test_make_quote_fn_zero_output_is_skippable():
    w3 = _FakeW3(result=[0, 0, 0, 0])
    quote_hop = q.make_quote_fn(w3, 8453)
    with pytest.raises(QuoteHopError):
        quote_hop(_uni_hop(), 1000)

def test_make_quote_fn_uses_tickspacing_for_aerodrome():
    w3 = _FakeW3(result=[777, 0, 1, 0])
    quote_hop = q.make_quote_fn(w3, 8453)
    aero_hop = {'pool_addr': '0xA', 'pool_state': {'dex': DEX_AERODROME_SLIPSTREAM, 'tickSpacing': 100, 'fee': 100}, 'dex': DEX_AERODROME_SLIPSTREAM, 'fee': 100, 'token_in': TOKEN_A, 'token_out': TOKEN_B}
    assert quote_hop(aero_hop, 1000) == 777
    fns = w3.eth.contracts[-1][2].functions
    assert fns.last_params[3] == 100
