"""supported_tokens() must surface tokens for EVERY venue the solver routes.

Regression guard for the completeness gap: discovery used to query only the
Uniswap V3 factory among seed pairs, so an Aerodrome-only token (routable by
the solver) never appeared in the public token list until it had been routed
at least once. supported_tokens now runs Aerodrome Slipstream seed-pair
discovery too.
"""

import pytest

pytest.importorskip("minotaur_subnet")

from strategies.dex_aggregator.baseline_solver import (  # noqa: E402
    BaselineSwapSolver,
    _DISCOVERY_SEED_TOKENS,
)
from strategies.dex_aggregator import aerodrome as _aero  # noqa: E402

_CHAIN = 8453  # Base — Aerodrome Slipstream is deployed here
_AERO_ONLY = "0xAe00000000000000000000000000000000000001"


def _make_solver(monkeypatch):
    s = BaselineSwapSolver()
    s._rpc_urls = {}          # enrichment builds no Web3 → no real RPC
    s._pool_cache = {}        # no live-routed pools
    s._token_cache = {}       # bypass the result TTL cache
    # No known Uni V3 pools and no Uni V3 factory pools for this test.
    monkeypatch.setattr(s, "_get_pool_states", lambda cid, snapshot=None: {})
    monkeypatch.setattr(s, "_discover_pools_for_pair", lambda *a, **k: None)
    # Truthy web3 so the Aerodrome discovery branch runs.
    monkeypatch.setattr(s, "_get_web3", lambda cid: object())
    return s


def test_supported_tokens_includes_aerodrome_only_token(monkeypatch):
    seed = _DISCOVERY_SEED_TOKENS.get(_CHAIN) or []
    assert seed, "expected Base seed tokens"
    assert _CHAIN in _aero.AERODROME_SLIPSTREAM_FACTORY

    s = _make_solver(monkeypatch)
    seed0 = seed[0]

    def _fake_aero(w3, cid, a, b, pool_states, query, cache, cache_ttl=60.0):
        # An Aero-only token paired with the first seed token (no Uni V3 pool).
        if a == seed0:
            pool_states["0xPOOLAERO"] = {
                "token0": seed0,
                "token1": _AERO_ONLY,
                "dex": "aerodrome_slipstream",
            }
        return pool_states

    monkeypatch.setattr(_aero, "discover_pools_for_pair", _fake_aero)

    tokens = s.supported_tokens(_CHAIN)
    addrs = {t["address"].lower() for t in tokens}
    assert _AERO_ONLY.lower() in addrs, "Aerodrome-only token missing from supported_tokens"


def test_without_aero_contribution_token_absent(monkeypatch):
    # Control: if Aero discovery contributes nothing, the token isn't there —
    # proves the inclusion above comes from the Aero path, not elsewhere.
    s = _make_solver(monkeypatch)
    monkeypatch.setattr(_aero, "discover_pools_for_pair", lambda *a, **k: a[4])  # no-op
    tokens = s.supported_tokens(_CHAIN)
    addrs = {t["address"].lower() for t in tokens}
    assert _AERO_ONLY.lower() not in addrs
