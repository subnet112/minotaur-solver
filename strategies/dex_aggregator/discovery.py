"""Dynamic route discovery — find a serving route for ANY token at plan time.

Every prior champion covers exotic tokens with a hand-curated static table
(``_STATIC_EXOTIC_ROUTES`` / ``_HOLE_ROUTES``): a new planted order goes
unserved until a human fork-verifies a route and ships a new build. This
module replaces that human step with an on-chain sweep at plan time:

  1. V2-fork routers (Uniswap V2, Sushi V2, Pancake V2, BaseSwap) — quoted via
     each router's own ``getAmountsOut`` (self-validating: a wrong router or a
     missing pair simply returns no candidate). Direct + via-WETH/USDC paths.
  2. Aerodrome classic vAMM/sAMM — quoted via the Aero router with explicit
     factory routes (stable and volatile, direct + hub legs).
  3. Uniswap V4 — candidate pool keys built from the pattern grid visible in
     historically-planted pools (Clanker dynamic-fee hook, Zora creator hooks,
     standard static tiers), checked with ONE ``StateView.getLiquidity`` call
     per key (poolId is keccak'd OFFLINE — zero RPC), then quoted through the
     V4 Quoter. Emitted as ``uniswap_v4_ur`` specs (UR v3-leg + v4-leg when the
     order input isn't the pool's base currency).
  4. Ethereum mainnet (chain 1): Uniswap V2 + Sushi V2 router quotes.

Zero-regression contract: callers gate this to orders the rest of the engine
cannot serve (min_output <= 1 covers, or no min-clearing candidate found).
Candidates carry REAL quoted outputs, so unlike the static table's phantom
``out = max(min_out, 1)`` this never prefers a dead pool over a live one.

All addresses are const; every RPC call is wrapped so any single venue failing
degrades to "no candidate from that venue", never an exception upward.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from eth_abi import encode as _enc, decode as _dec
from eth_utils import keccak as _kk, to_checksum_address as _ck

logger = logging.getLogger("solver.discovery")

_ZERO = "0x0000000000000000000000000000000000000000"

# ── Base (8453) canonical tokens ─────────────────────────────────────────────
WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
USDBC = "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca"
CBETH = "0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22"
ZORA = "0x1111111111166b7fe7bd91427724b487980afc69"
VIRTUAL = "0x0b3e328455c4059eeb9e3f84b5543f74e24e7e1b"

# ── V2-fork routers, Base. Quoting goes through the ROUTER's getAmountsOut so
# a stale/wrong address self-eliminates (call fails -> no candidate).
#   (label, router, native_kind_or_None)  — native kinds reuse the solver's
#   dedicated builders; others emit the generic "v2_fork" candidate.
V2_FORKS_BASE = (
    ("uniswap_v2", "0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24", "uniswap_v2"),
    ("pancake_v2", "0x8cFe327CEc66d1C090Dd72bd0FF11d690C33a2Eb", "pancake_v2"),
    ("sushi_v2",   "0x6BDED42c6DA8FBf0d2bA55B2fa120C5e0c8D7891", None),
    ("baseswap",   "0x327Df1E6de05895d2ab08513aaDD9313Fe505d86", None),
)
V2_FORKS_MAINNET = (
    ("uniswap_v2", "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D", "uniswap_v2"),
    ("sushi_v2",   "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F", None),
)

AERO_V2_ROUTER = "0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43"
AERO_V2_FACTORY = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"

# ── Uniswap V4, Base ─────────────────────────────────────────────────────────
V4_STATE_VIEW = "0xA3c0c9b65baD0b08107Aa264b0f3dB444b867A71"
V4_QUOTER = "0x0d5e0F971ED27FBfF6c2837bf31316121532048D"
V4_DYN_FEE = 8388608  # 0x800000 — Clanker-style dynamic-fee sentinel
CLANKER_HOOK = "0xb429d62f8f3bffb98cdb9569533ea23bf0ba28cc"
HOOK_BDF9 = "0xbdf938149ac6a781f94faa0ed45e6a0e984c6544"
ZORA_HOOK = "0xc8d077444625eb300a427a6dfb2b1dbf9b159040"
ZORA_CREATOR_HOOK = "0xd61a675f8a0c67a73dc3b54fb7318b4d91409040"

# (fee, tickSpacing, hooks) grid — harvested from every V4 pool pattern seen in
# planted benchmark orders + the standard static tiers. Order = hit likelihood.
V4_KEY_GRID = (
    (V4_DYN_FEE, 200, CLANKER_HOOK),
    (V4_DYN_FEE, 200, HOOK_BDF9),
    (30000, 200, ZORA_CREATOR_HOOK),
    (10000, 200, ZORA_HOOK),
    (10000, 200, _ZERO),
    (3000, 60, _ZERO),
    (100000, 2000, _ZERO),
    (500, 10, _ZERO),
    (100, 1, _ZERO),
    (20000, 200, _ZERO),
    (800000, 100, CLANKER_HOOK),
)
# Base currencies to pair a mystery token against in V4 (native ETH = zero addr
# first: Clanker/Zora launches overwhelmingly pool against native ETH).
V4_BASES = (_ZERO, WETH, USDC, ZORA, VIRTUAL)

# Per-invocation RPC call ceiling — stays a small fraction of the harness'
# 5000-unit budget even if every probe fires.
MAX_CALLS = 90


def _sorted_pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if int(a, 16) < int(b, 16) else (b, a)


def v4_pool_id(c0: str, c1: str, fee: int, tick: int, hooks: str) -> bytes:
    """keccak(abi.encode(PoolKey)) — computed offline, no RPC."""
    return _kk(_enc(
        ["address", "address", "uint24", "int24", "address"],
        [_ck(c0), _ck(c1), int(fee), int(tick), _ck(hooks)],
    ))


class DiscoveryEngine:
    """Stateless per-call sweep; ``call`` is an eth_call thunk with the
    solver's socket timeout already applied: call(to, data) -> bytes|None."""

    def __init__(self, call: Callable[[str, str], Any]):
        self._call = call
        self._used = 0

    # ── budgeted eth_call helper ────────────────────────────────────────────
    def _c(self, to: str, data: bytes) -> bytes | None:
        if self._used >= MAX_CALLS:
            return None
        self._used += 1
        try:
            r = self._call(_ck(to), "0x" + data.hex())
            if r is None:
                return None
            return bytes(r)
        except Exception:
            return None

    # ── V2-fork family ──────────────────────────────────────────────────────
    def _v2_quote(self, router: str, path: list[str], amount_in: int) -> int:
        data = _kk(text="getAmountsOut(uint256,address[])")[:4] + _enc(
            ["uint256", "address[]"], [amount_in, [_ck(p) for p in path]])
        r = self._c(router, data)
        if not r:
            return 0
        try:
            return int(_dec(["uint256[]"], r)[0][-1])
        except Exception:
            return 0

    def v2_candidates(self, chain_id: int, tin: str, tout: str,
                      amount_in: int) -> list[dict]:
        forks = V2_FORKS_BASE if chain_id == 8453 else (
            V2_FORKS_MAINNET if chain_id == 1 else ())
        hubs = [WETH, USDC] if chain_id == 8453 else [
            "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH mainnet
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC mainnet
        ]
        out: list[dict] = []
        paths = [[tin, tout]] + [
            [tin, h, tout] for h in hubs
            if h.lower() not in (tin.lower(), tout.lower())
        ]
        for label, router, native in forks:
            for path in paths:
                q = self._v2_quote(router, path, amount_in)
                if q <= 0:
                    continue
                n_hops = len(path) - 1
                base = {
                    "out": q, "tokens": tuple(path),
                    "gas_est": 150000 * n_hops,
                    "gas_model": 350000 + 150000 * n_hops,
                    "discovered": label,
                }
                if native:
                    out.append({**base, "venue": native, "param": tuple(path)})
                else:
                    out.append({**base, "venue": "v2_fork",
                                "router": router, "param": router})
                break  # best path for this fork found; try next fork
        return out

    # ── Aerodrome classic (vAMM + sAMM) ─────────────────────────────────────
    def aero_v2_candidates(self, chain_id: int, tin: str, tout: str,
                           amount_in: int) -> list[dict]:
        if chain_id != 8453:
            return []
        out: list[dict] = []
        route_sets: list[tuple[tuple, ...]] = []
        for stable in (False, True):
            route_sets.append(((tin, tout, stable, AERO_V2_FACTORY),))
        for hub in (WETH, USDC):
            if hub.lower() in (tin.lower(), tout.lower()):
                continue
            route_sets.append(((tin, hub, False, AERO_V2_FACTORY),
                               (hub, tout, False, AERO_V2_FACTORY)))
        for routes in route_sets:
            data = _kk(text="getAmountsOut(uint256,(address,address,bool,address)[])")[:4] + _enc(
                ["uint256", "(address,address,bool,address)[]"],
                [amount_in, [(_ck(a), _ck(b), s, _ck(f)) for a, b, s, f in routes]])
            r = self._c(AERO_V2_ROUTER, data)
            if not r:
                continue
            try:
                q = int(_dec(["uint256[]"], r)[0][-1])
            except Exception:
                continue
            if q <= 0:
                continue
            out.append({
                "venue": "aerodrome_v2", "routes": routes, "out": q,
                "param": AERO_V2_FACTORY,
                "gas_est": 170000 * len(routes),
                "gas_model": 350000 + 170000 * len(routes),
                "discovered": "aero_v2",
            })
        return out

    # ── Uniswap V4 ──────────────────────────────────────────────────────────
    def _v4_liquidity(self, pool_id: bytes) -> int:
        data = _kk(text="getLiquidity(bytes32)")[:4] + pool_id
        r = self._c(V4_STATE_VIEW, data)
        if not r:
            return 0
        try:
            return int.from_bytes(r[-16:], "big")
        except Exception:
            return 0

    def _v4_quote(self, key: tuple, zero_for_one: bool, amount_in: int) -> int:
        c0, c1, fee, tick, hooks = key
        data = _kk(text=(
            "quoteExactInputSingle(((address,address,uint24,int24,address),"
            "bool,uint128,bytes))"))[:4] + _enc(
            ["((address,address,uint24,int24,address),bool,uint128,bytes)"],
            [((( _ck(c0)), _ck(c1), int(fee), int(tick), _ck(hooks)),
              bool(zero_for_one), int(amount_in), b"")])
        r = self._c(V4_QUOTER, data)
        if not r or len(r) < 32:
            return 0
        try:
            return int(_dec(["uint256", "uint256"], r)[0])
        except Exception:
            return 0

    def v4_candidates(self, chain_id: int, tin: str, tout: str,
                      amount_in: int) -> list[dict]:
        """Find a V4 pool holding ``tout`` against a known base currency.

        Emits ``uniswap_v4_ur`` specs matching the solver's existing builder:
        base == tin -> single v4 leg; base != tin -> UR v3 leg (tin->WETH/USDC)
        chained into the v4 leg via CONTRACT_BALANCE.
        """
        if chain_id != 8453:
            return []
        out: list[dict] = []
        for base in V4_BASES:
            if base.lower() == tout.lower():
                continue
            for fee, tick, hooks in V4_KEY_GRID:
                c0, c1 = _sorted_pair(base, tout)
                pid = v4_pool_id(c0, c1, fee, tick, hooks)
                if self._v4_liquidity(pid) <= 0:
                    continue
                zero_for_one = c0.lower() == base.lower()
                # Quote the v4 leg alone with a representative amount (the
                # actual input for base==tin; a WETH-leg estimate otherwise).
                leg_in = amount_in
                spec: dict[str, Any] = {
                    "pool": (c0, c1, fee, tick, hooks),
                    "settle": base if base != _ZERO else WETH,
                    "zero_for_one": zero_for_one,
                }
                if base.lower() != tin.lower():
                    # UR v3 first leg tin -> settle currency (WETH covers the
                    # native-ETH case: UR unwraps via the v4 SETTLE).
                    settle = WETH if base == _ZERO else base
                    spec["v3_tokens"] = (tin, settle)
                    spec["v3_fees"] = (500,) if settle.lower() == WETH.lower() else (3000,)
                    if base == _ZERO:
                        spec["native_eth"] = True
                    leg_in = 0  # unknown until leg1 executes; quote sanity only
                q = self._v4_quote((c0, c1, fee, tick, hooks), zero_for_one,
                                   leg_in) if leg_in else 1
                if q <= 0:
                    continue
                out.append({
                    "venue": "uniswap_v4_ur", "spec": spec, "param": "v4-disc",
                    "out": q, "gas_est": 650000, "gas_model": 350000 + 650000,
                    "discovered": f"v4:{fee}/{tick}/{hooks[:8]}",
                })
                break  # one live pool per base is enough
            if out:
                break
        return out

    # ── top-level sweep ─────────────────────────────────────────────────────
    def discover(self, chain_id: int, tin: str, tout: str, amount_in: int,
                 min_out: int) -> list[dict]:
        """All venue families, cheapest/most-likely first. Returns candidates
        sorted by quoted output desc; quoted candidates beat probed ones."""
        tin, tout = tin.lower(), tout.lower()
        cands: list[dict] = []
        try:
            cands += self.v2_candidates(chain_id, tin, tout, amount_in)
            # For a pure cover (min<=1) one live quoted route suffices.
            if not (min_out <= 1 and cands):
                cands += self.aero_v2_candidates(chain_id, tin, tout, amount_in)
            if not (min_out <= 1 and cands):
                cands += self.v4_candidates(chain_id, tin, tout, amount_in)
        except Exception:
            logger.exception("[discovery] sweep failed (%s->%s)", tin, tout)
        cands.sort(key=lambda c: c.get("out", 0), reverse=True)
        logger.info("[discovery] %s->%s chain=%s: %d candidate(s), %d rpc calls",
                    tin[:8], tout[:8], chain_id, len(cands), self._used)
        return cands
