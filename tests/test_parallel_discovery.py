"""Tests for the pair-level RPC parallelization of pool discovery.

Three groups:

  (a) ``parallel_map`` — input-order preservation, exception-in-place,
      and the 0/1-task inline fast paths (no thread pool).
  (b) ``thread_web3`` — same instance within a thread, lazy build.
  (c) ``_ensure_pools_for_route`` parallel merge == serial reference —
      a mock-based proof that fanning discovery out over the thread pool
      produces the SAME merged ``pool_states`` (same set of addresses +
      same states) as a serial walk over the same pairs, so concurrency
      never drops, duplicates, or reorders the discovered pool set
      (determinism is load-bearing for a champion solver).

(a) and (b) are pure (no SDK). (c) needs the ``minotaur_subnet`` SDK to
import ``BaselineSwapSolver`` and is skipped if it isn't importable.
"""

import threading

import pytest

from strategies.dex_aggregator.parallel import parallel_map, thread_web3


# ── (a) parallel_map ──────────────────────────────────────────────────────


def test_parallel_map_preserves_input_order():
    # Tasks finish out of order (later index sleeps less) but results must
    # come back keyed by INPUT index, not completion order.
    import time

    def make(i):
        def run():
            time.sleep((10 - i) * 0.005)
            return i
        return run

    tasks = [make(i) for i in range(10)]
    assert parallel_map(tasks) == list(range(10))


def test_parallel_map_captures_exception_in_place():
    boom = RuntimeError("boom")

    def ok():
        return "ok"

    def fail():
        raise boom

    results = parallel_map([ok, fail, ok])
    assert results[0] == "ok"
    assert results[2] == "ok"
    assert isinstance(results[1], Exception)
    assert results[1] is boom  # the actual exception object, surfaced in place


def test_parallel_map_empty_returns_empty():
    assert parallel_map([]) == []


def test_parallel_map_single_task_runs_inline():
    # n==1 takes the inline fast path: it must NOT spin up a pool thread.
    main = threading.get_ident()
    seen = {}

    def run():
        seen["tid"] = threading.get_ident()
        return 42

    assert parallel_map([run]) == [42]
    assert seen["tid"] == main


def test_parallel_map_single_task_exception_in_place():
    boom = ValueError("nope")

    def fail():
        raise boom

    results = parallel_map([fail])
    assert len(results) == 1
    assert results[0] is boom


def test_parallel_map_respects_max_workers():
    # With max_workers=1 every task runs on the same single pool thread.
    tids = []
    lock = threading.Lock()

    def make():
        def run():
            with lock:
                tids.append(threading.get_ident())
            return None
        return run

    parallel_map([make() for _ in range(5)], max_workers=1)
    assert len(set(tids)) == 1


# ── (b) thread_web3 ───────────────────────────────────────────────────────


def test_thread_web3_same_instance_within_thread(monkeypatch):
    # Build is lazy (only constructs a Web3 on first request) and cached per
    # thread + rpc_url, so two calls on the SAME thread return the SAME object.
    built = []

    class FakeWeb3:
        @staticmethod
        def HTTPProvider(url):
            return ("provider", url)

        def __init__(self, provider):
            built.append(provider)
            self.provider = provider

    import web3
    monkeypatch.setattr(web3, "Web3", FakeWeb3)

    # Fresh thread-local state for this thread so the assertion is clean.
    import strategies.dex_aggregator.parallel as par
    par._thread_local.__dict__.pop("w3_by_rpc", None)

    url = "http://localhost:8545"
    first = thread_web3(url)
    second = thread_web3(url)
    assert first is second
    # Lazy + cached: exactly one underlying Web3 built for that url.
    assert len(built) == 1


def test_thread_web3_distinct_instances_across_threads(monkeypatch):
    class FakeWeb3:
        @staticmethod
        def HTTPProvider(url):
            return ("provider", url)

        def __init__(self, provider):
            self.provider = provider

    import web3
    monkeypatch.setattr(web3, "Web3", FakeWeb3)

    url = "http://localhost:8545"
    results = {}
    started = threading.Barrier(2)

    def worker(name):
        # each thread has its OWN threading.local → its own Web3. Hold a real
        # reference (not id()) so the objects can't be GC'd and reuse an
        # address, which would spuriously collide.
        started.wait()
        results[name] = thread_web3(url)

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start(); t2.start(); t1.join(); t2.join()

    assert results["a"] is not results["b"]


def test_thread_web3_distinct_instances_per_rpc_url(monkeypatch):
    class FakeWeb3:
        @staticmethod
        def HTTPProvider(url):
            return ("provider", url)

        def __init__(self, provider):
            self.provider = provider

    import web3
    monkeypatch.setattr(web3, "Web3", FakeWeb3)

    import strategies.dex_aggregator.parallel as par
    par._thread_local.__dict__.pop("w3_by_rpc", None)

    a = thread_web3("http://a:8545")
    b = thread_web3("http://b:8545")
    assert a is not b
    assert thread_web3("http://a:8545") is a


# ── (c) parallel merge == serial reference ────────────────────────────────
#
# These need the ``minotaur_subnet`` SDK (BaselineSwapSolver imports it).
# Gate ONLY this group so the pure (a)/(b) tests above always run, even on a
# CI box without the SDK installed.

try:
    import minotaur_subnet  # noqa: F401

    from strategies.dex_aggregator.baseline_solver import BaselineSwapSolver
    from strategies.dex_aggregator import aerodrome as _aero

    _HAVE_SDK = True
except ImportError:
    _HAVE_SDK = False

_needs_sdk = pytest.mark.skipif(not _HAVE_SDK, reason="minotaur_subnet SDK not importable")

# A Base chain id so Aerodrome discovery is exercised too.
CHAIN = 8453
TOKEN_IN = "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb"   # DAI (base)
TOKEN_OUT = "0x0000000000000000000000000000000000000DEC"  # exotic out token
WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


def _addr(pair, dex):
    """Deterministic fake pool address from a normalized pair + dex tag."""
    a, b = sorted((pair[0].lower(), pair[1].lower()))
    h = abs(hash((a, b, dex))) % (16 ** 36)
    return "0x" + f"{h:040x}"[:40]


def _make_solver(monkeypatch):
    """A solver wired so _ensure_pools_for_route runs WITHOUT real RPC.

    The Uni + Aero discovery functions are replaced by deterministic fakes
    that record their call args and produce a pool per pair. The Web3 +
    Factory pre-warm hooks are stubbed so they don't touch the network.
    """
    solver = BaselineSwapSolver()
    solver._rpc_urls = {CHAIN: "http://fake-rpc:8545"}
    # Fixed intermediaries so the pair set is stable regardless of the SDK
    # token registry contents.
    monkeypatch.setattr(solver, "_intermediaries_for_chain", lambda cid: [WETH, USDC])
    # Pre-warm hooks must be inert (no real network).
    monkeypatch.setattr(solver, "_get_web3", lambda cid: object())
    monkeypatch.setattr(solver, "_get_factory", lambda cid: object())
    # thread_web3 is invoked inside the tasks; make it inert too. The solver
    # does a local `from ...parallel import thread_web3` each call, so patch
    # the name on the parallel module itself.
    import strategies.dex_aggregator.parallel as par
    monkeypatch.setattr(par, "thread_web3", lambda url: object())
    # Ensure Aerodrome is treated as supported on CHAIN.
    monkeypatch.setitem(_aero.AERODROME_SLIPSTREAM_FACTORY, CHAIN, "0xFACade")
    return solver


def _expected_pairs():
    pairs = [(TOKEN_IN, TOKEN_OUT)]
    for mid in (WETH, USDC):
        ml = mid.lower()
        if ml == TOKEN_IN.lower() or ml == TOKEN_OUT.lower():
            continue
        pairs.append((TOKEN_IN, mid))
        pairs.append((mid, TOKEN_OUT))
    return pairs


@_needs_sdk
def test_ensure_pools_for_route_parallel_matches_serial(monkeypatch):
    """The parallel merge yields the SAME pool set/states as a serial walk."""
    solver = _make_solver(monkeypatch)

    uni_calls = []
    aero_calls = []

    def fake_uni(chain_id, a, b, pool_states, w3=None):
        # Reads pool_states (dedup) and returns a LOCAL delta — matches the
        # real refactored contract. Records the call for the drop/dup check.
        uni_calls.append((chain_id, a.lower(), b.lower()))
        addr = _addr((a, b), "uniswap_v3")
        if addr in pool_states:
            return {}
        return {addr: {"token0": a, "token1": b, "dex": "uniswap_v3", "pair": (a, b)}}

    def fake_aero(w3, chain_id, a, b, pool_states, query, cache=None, cache_ttl=60.0):
        # Mirrors the real signature: MUTATES the dict passed in (the task
        # hands it a fresh local) and returns it.
        aero_calls.append((chain_id, a.lower(), b.lower()))
        addr = _addr((a, b), "aerodrome_slipstream")
        pool_states[addr] = {
            "token0": a, "token1": b, "dex": "aerodrome_slipstream", "pair": (a, b),
        }
        return pool_states

    monkeypatch.setattr(solver, "_discover_pools_for_pair", fake_uni)
    monkeypatch.setattr(_aero, "discover_pools_for_pair", fake_aero)

    # --- parallel (the code under test) ---
    parallel_states: dict = {}
    solver._ensure_pools_for_route(CHAIN, parallel_states, TOKEN_IN, TOKEN_OUT)

    # Snapshot the calls made by the PARALLEL run before the serial walk
    # reuses the same recorder lists.
    parallel_uni_calls = list(uni_calls)
    parallel_aero_calls = list(aero_calls)

    # --- serial reference: same fakes, walked one pair at a time ---
    serial_states: dict = {}
    for (a, b) in _expected_pairs():
        delta = fake_uni(CHAIN, a, b, serial_states)
        for addr, st in delta.items():
            serial_states.setdefault(addr, st)
    for (a, b) in _expected_pairs():
        local: dict = {}
        fake_aero(None, CHAIN, a, b, local, solver._query_pool_state)
        for addr, st in local.items():
            serial_states.setdefault(addr, st)

    # Same set of addresses, same states → parallelization changed nothing.
    assert set(parallel_states.keys()) == set(serial_states.keys())
    assert parallel_states == serial_states

    # The PARALLEL run discovered every expected pair on BOTH the Uni and
    # Aero paths exactly once (no pair dropped, none duplicated).
    expected = {(CHAIN, a.lower(), b.lower()) for (a, b) in _expected_pairs()}
    assert set(parallel_uni_calls) == expected
    assert len(parallel_uni_calls) == len(expected)
    assert set(parallel_aero_calls) == expected
    assert len(parallel_aero_calls) == len(expected)

    # Sanity: a multi-hop route produced more than just the direct pair.
    assert len(parallel_states) == 2 * len(_expected_pairs())


@_needs_sdk
def test_ensure_pools_for_route_no_rpc_is_noop(monkeypatch):
    """No RPC for the chain → returns the dict unchanged (preserved contract)."""
    solver = BaselineSwapSolver()
    solver._rpc_urls = {}
    states = {"0xexisting": {"dex": "uniswap_v3"}}
    out = solver._ensure_pools_for_route(CHAIN, states, TOKEN_IN, TOKEN_OUT)
    assert out is states
    assert states == {"0xexisting": {"dex": "uniswap_v3"}}


@_needs_sdk
def test_ensure_pools_for_route_skips_failed_task(monkeypatch):
    """An exception from one pair task is swallowed; others still merge."""
    solver = _make_solver(monkeypatch)

    direct = (TOKEN_IN, TOKEN_OUT)

    def fake_uni(chain_id, a, b, pool_states, w3=None):
        if (a, b) == direct:
            raise RuntimeError("rpc down for direct pair")
        addr = _addr((a, b), "uniswap_v3")
        return {addr: {"dex": "uniswap_v3"}}

    def fake_aero(w3, chain_id, a, b, pool_states, query, cache=None, cache_ttl=60.0):
        return pool_states  # no aero pools in this test

    monkeypatch.setattr(solver, "_discover_pools_for_pair", fake_uni)
    monkeypatch.setattr(_aero, "discover_pools_for_pair", fake_aero)

    states: dict = {}
    solver._ensure_pools_for_route(CHAIN, states, TOKEN_IN, TOKEN_OUT)

    # Direct pair raised → dropped; the other (intermediary) pairs merged.
    non_direct = [p for p in _expected_pairs() if p != direct]
    expected_addrs = {_addr(p, "uniswap_v3") for p in non_direct}
    assert set(states.keys()) == expected_addrs
