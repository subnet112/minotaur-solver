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

def _dr9():
    logger = logging.getLogger('solver.discovery')
    _ZERO = '0x0000000000000000000000000000000000000000'
    WETH = '0x4200000000000000000000000000000000000006'
    USDC = '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'
    USDBC = '0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca'
    def _fw4():
        CBETH = '0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22'
        ZORA = '0x1111111111166b7fe7bd91427724b487980afc69'
        VIRTUAL = '0x0b3e328455c4059eeb9e3f84b5543f74e24e7e1b'
        V2_FORKS_BASE = (('uniswap_v2', '0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24', 'uniswap_v2'), ('pancake_v2', '0x8cFe327CEc66d1C090Dd72bd0FF11d690C33a2Eb', 'pancake_v2'), ('sushi_v2', '0x6BDED42c6DA8FBf0d2bA55B2fa120C5e0c8D7891', None), ('baseswap', '0x327Df1E6de05895d2ab08513aaDD9313Fe505d86', None))
        V2_FORKS_MAINNET = (('uniswap_v2', '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D', 'uniswap_v2'), ('sushi_v2', '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F', None))
        AERO_V2_ROUTER = '0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43'
        AERO_V2_FACTORY = '0x420DD381b31aEf6683db6B902084cB0FFECe40Da'
        V4_STATE_VIEW = '0xA3c0c9b65baD0b08107Aa264b0f3dB444b867A71'
        V4_QUOTER = '0x0d5e0F971ED27FBfF6c2837bf31316121532048D'
        return ((AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger),)
    _fwr4 = _fw4()
    if _fwr4 is not None:
        return _fwr4[0]
AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger = _dr9()
V4_DYN_FEE = 8388608
CLANKER_HOOK = '0xb429d62f8f3bffb98cdb9569533ea23bf0ba28cc'

def _dr3():
    HOOK_BDF9 = '0xbdf938149ac6a781f94faa0ed45e6a0e984c6544'
    ZORA_HOOK = '0xc8d077444625eb300a427a6dfb2b1dbf9b159040'
    ZORA_CREATOR_HOOK = '0xd61a675f8a0c67a73dc3b54fb7318b4d91409040'
    def _fw3():
        V4_KEY_GRID = ((V4_DYN_FEE, 200, CLANKER_HOOK), (V4_DYN_FEE, 200, '0xd60d6b218116cfd801e28f78d011a203d2b068cc'), (V4_DYN_FEE, 200, '0xbdf938149ac6a781f94faa0ed45e6a0e984c6544'), (V4_DYN_FEE, 200, HOOK_BDF9), (30000, 200, ZORA_CREATOR_HOOK), (10000, 200, ZORA_HOOK), (10000, 200, _ZERO), (3000, 60, _ZERO), (100000, 2000, _ZERO), (500, 10, _ZERO), (100, 1, _ZERO), (20000, 200, _ZERO), (800000, 100, CLANKER_HOOK))
        V4_BASES = (_ZERO, WETH, USDC, ZORA, VIRTUAL)
        return (V4_KEY_GRID, V4_BASES)
    V4_KEY_GRID, V4_BASES = _fw3()
    return (HOOK_BDF9, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK)
HOOK_BDF9, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK = _dr3()
# Ethereum (chain 1) Uniswap V4 venue config. No StateView wired for this chain
# -> the quoter is the liquidity gate (reverts / returns 0 on an empty pool), so
# _v4_liquidity is skipped on ETH.
ETH_WETH = '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'
ETH_USDC = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'
ETH_DAI = '0x6B175474E89094C44Da98b954EedeAC495271d0F'
ETH_USDT = '0xdAC17F958D2ee523a2206206994597C13D831ec7'
ETH_WBTC = '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599'
ETH_V4_QUOTER = '0x52f0e24d1c21c8a0cb1e5a5dd6198556bd9e1203'
ETH_V4_BASES = (_ZERO, ETH_WETH, ETH_USDC, ETH_DAI, ETH_USDT, ETH_WBTC)
# hookless fee/tickSpacing grid + the ultra-low-fee stable pools (fee 7/10/100,
# tick 1) that mainnet uses for stable<->stable; ordered most-liquid first.
ETH_V4_KEY_GRID = ((3000, 60, _ZERO), (500, 10, _ZERO), (10000, 200, _ZERO), (100, 1, _ZERO), (10, 1, _ZERO), (7, 1, _ZERO))
MAX_CALLS = 90


def _v4_cfg(chain_id):
    """(bases, grid, weth, quoter, stateview_or_None) for the chain's V4 venue."""
    if chain_id == 8453:
        return (V4_BASES, V4_KEY_GRID, WETH, V4_QUOTER, V4_STATE_VIEW)
    return (ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_WETH, ETH_V4_QUOTER, None)

def _sorted_pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if int(a, 16) < int(b, 16) else (b, a)

def v4_pool_id(c0: str, c1: str, fee: int, tick: int, hooks: str) -> bytes:
    """keccak(abi.encode(PoolKey)) — computed offline, no RPC."""
    return _kk(_enc(['address', 'address', 'uint24', 'int24', 'address'], [_ck(c0), _ck(c1), int(fee), int(tick), _ck(hooks)]))

class _DiscoveryEngineDR12:

    def v2_candidates(self, chain_id: int, tin: str, tout: str, amount_in: int) -> list[dict]:
        forks = V2_FORKS_BASE if chain_id == 8453 else V2_FORKS_MAINNET if chain_id == 1 else ()
        hubs = [WETH, USDC] if chain_id == 8453 else ['0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48']
        out: list[dict] = []
        paths = [[tin, tout]] + [[tin, h, tout] for h in hubs if h.lower() not in (tin.lower(), tout.lower())]

        def _dr6():
            for label, router, native in forks:
                for path in paths:
                    q = self._v2_quote(router, path, amount_in)
                    if q <= 0:
                        continue
                    n_hops = len(path) - 1
                    base = {'out': q, 'tokens': tuple(path), 'gas_est': 150000 * n_hops, 'gas_model': 350000 + 150000 * n_hops, 'discovered': label}
                    if native:
                        out.append({**base, 'venue': native, 'param': tuple(path)})
                    else:
                        out.append({**base, 'venue': 'v2_fork', 'router': router, 'param': router})
                    break
        _dr6()
        return out

    def aero_v2_candidates(self, chain_id: int, tin: str, tout: str, amount_in: int) -> list[dict]:
        if chain_id != 8453:
            return []

        def _dr2():
            out: list[dict] = []
            route_sets: list[tuple[tuple, ...]] = []
            for stable in (False, True):
                route_sets.append(((tin, tout, stable, AERO_V2_FACTORY),))
            for hub in (WETH, USDC):
                if hub.lower() in (tin.lower(), tout.lower()):
                    continue
                route_sets.append(((tin, hub, False, AERO_V2_FACTORY), (hub, tout, False, AERO_V2_FACTORY)))
            return (out, route_sets)
        out, route_sets = _dr2()
        for routes in route_sets:

            def _dr8():
                data = _kk(text='getAmountsOut(uint256,(address,address,bool,address)[])')[:4] + _enc(['uint256', '(address,address,bool,address)[]'], [amount_in, [(_ck(a), _ck(b), s, _ck(f)) for a, b, s, f in routes]])
                r = self._c(AERO_V2_ROUTER, data)
                return (data, r)
            data, r = _dr8()
            if not r:
                continue
            try:
                q = int(_dec(['uint256[]'], r)[0][-1])
            except Exception:
                continue
            if q <= 0:
                continue
            out.append({'venue': 'aerodrome_v2', 'routes': routes, 'out': q, 'param': AERO_V2_FACTORY, 'gas_est': 170000 * len(routes), 'gas_model': 350000 + 170000 * len(routes), 'discovered': 'aero_v2'})
        return out

class DiscoveryEngine(_DiscoveryEngineDR12):
    """Stateless per-call sweep; ``call`` is an eth_call thunk with the
    solver's socket timeout already applied: call(to, data) -> bytes|None."""

    def __init__(self, call: Callable[[str, str], Any]):
        self._call = call
        self._used = 0

    def _c(self, to: str, data: bytes) -> bytes | None:
        if self._used >= MAX_CALLS:
            return None
        self._used += 1
        try:
            r = self._call(_ck(to), '0x' + data.hex())
            if r is None:
                return None
            return bytes(r)
        except Exception:
            return None

    def _v2_quote(self, router: str, path: list[str], amount_in: int) -> int:
        data = _kk(text='getAmountsOut(uint256,address[])')[:4] + _enc(['uint256', 'address[]'], [amount_in, [_ck(p) for p in path]])
        r = self._c(router, data)
        if not r:
            return 0
        try:
            return int(_dec(['uint256[]'], r)[0][-1])
        except Exception:
            return 0

    def _v4_liquidity(self, pool_id: bytes, state_view=None) -> int:
        # state_view None (mainnet — no public StateView wired) -> skip the
        # liquidity gate; the quoter reverts/returns 0 on an empty pool anyway.
        sv = state_view or V4_STATE_VIEW
        if state_view is None and sv is None:
            return 1
        data = _kk(text='getLiquidity(bytes32)')[:4] + pool_id
        r = self._c(sv, data)
        if not r:
            return 0
        try:
            return int.from_bytes(r[-16:], 'big')
        except Exception:
            return 0

    def _v4_quote(self, key: tuple, zero_for_one: bool, amount_in: int, quoter=None) -> int:
        c0, c1, fee, tick, hooks = key
        data = _kk(text='quoteExactInputSingle(((address,address,uint24,int24,address),bool,uint128,bytes))')[:4] + _enc(['((address,address,uint24,int24,address),bool,uint128,bytes)'], [((_ck(c0), _ck(c1), int(fee), int(tick), _ck(hooks)), bool(zero_for_one), int(amount_in), b'')])
        r = self._c(quoter or V4_QUOTER, data)
        if not r or len(r) < 32:
            return 0
        try:
            return int(_dec(['uint256', 'uint256'], r)[0])
        except Exception:
            return 0

    def v4_candidates(self, chain_id: int, tin: str, tout: str, amount_in: int) -> list[dict]:
        """Find a V4 pool holding ``tout`` against a known base currency.

        Emits ``uniswap_v4_ur`` specs matching the solver's existing builder:
        base == tin -> single v4 leg; base != tin -> UR v3 leg (tin->WETH/USDC)
        chained into the v4 leg via CONTRACT_BALANCE. Base + Ethereum (chain 1)
        via chain-selected quoter/bases/grid (see ``_v4_cfg``).
        """
        if chain_id not in (8453, 1):
            return []
        bases, grid, weth, quoter, state_view = _v4_cfg(chain_id)
        # ETH (state_view None): skip the on-chain liquidity gate, let the quoter
        # decide; Base keeps its StateView getLiquidity() pre-filter.
        skip_liq = state_view is None
        out: list[dict] = []
        for base in bases:
            if base.lower() == tout.lower():
                continue
            for fee, tick, hooks in grid:
                c0, c1 = _sorted_pair(base, tout)
                pid = v4_pool_id(c0, c1, fee, tick, hooks)
                if not skip_liq and self._v4_liquidity(pid, state_view) <= 0:
                    continue
                zero_for_one = c0.lower() == base.lower()
                leg_in = amount_in
                spec: dict[str, Any] = {'pool': (c0, c1, fee, tick, hooks), 'settle': base if base != _ZERO else weth, 'zero_for_one': zero_for_one}
                if base.lower() != tin.lower():
                    settle = weth if base == _ZERO else base
                    spec['v3_tokens'] = (tin, settle)
                    spec['v3_fees'] = (500,) if settle.lower() == weth.lower() else (3000,)
                    if base == _ZERO:
                        spec['native_eth'] = True
                    leg_in = 0
                key = (c0, c1, fee, tick, hooks)
                if leg_in:
                    q = self._v4_quote(key, zero_for_one, leg_in, quoter)
                elif skip_liq:
                    # ETH has no StateView gate above -> confirm the pool exists
                    # with a nominal probe quote (an empty pool reverts -> 0).
                    q = 1 if self._v4_quote(key, zero_for_one, 10 ** 6, quoter) > 0 else 0
                else:
                    q = 1  # Base: liquidity already gated by _v4_liquidity
                if q <= 0:
                    continue
                out.append({'venue': 'uniswap_v4_ur', 'spec': spec, 'param': 'v4-disc', 'out': q, 'gas_est': 650000, 'gas_model': 350000 + 650000, 'discovered': f'v4:{fee}/{tick}/{hooks[:8]}'})
                break
            if out:
                break
        return out

    def discover(self, chain_id: int, tin: str, tout: str, amount_in: int, min_out: int) -> list[dict]:
        """All venue families, cheapest/most-likely first. Returns candidates
        sorted by quoted output desc; quoted candidates beat probed ones."""

        def _dr10():
            nonlocal tin, tout
            tin, tout = (tin.lower(), tout.lower())
            cands = []
            try:
                cands += self.v2_candidates(chain_id, tin, tout, amount_in)
                if not (min_out <= 1 and cands):
                    cands += self.aero_v2_candidates(chain_id, tin, tout, amount_in)
                if not (min_out <= 1 and cands):
                    cands += self.v4_candidates(chain_id, tin, tout, amount_in)
            except Exception:
                logger.exception('[discovery] sweep failed (%s->%s)', tin, tout)
            return cands
        cands = _dr10()
        cands.sort(key=lambda c: c.get('out', 0), reverse=True)
        logger.info('[discovery] %s->%s chain=%s: %d candidate(s), %d rpc calls', tin[:8], tout[:8], chain_id, len(cands), self._used)
        return cands
