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

def _lr27():
    global Any, Callable, MAX_CALLS, _ck, _dec, _dr9, _enc, _kk, _lr7, _sorted_pair, logging, v4_pool_id
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

        def _lr18():
            CBETH = '0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22'
            ZORA = '0x1111111111166b7fe7bd91427724b487980afc69'
            VIRTUAL = '0x0b3e328455c4059eeb9e3f84b5543f74e24e7e1b'
            V2_FORKS_BASE = (('uniswap_v2', '0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24', 'uniswap_v2'), ('pancake_v2', '0x8cFe327CEc66d1C090Dd72bd0FF11d690C33a2Eb', 'pancake_v2'), ('sushi_v2', '0x6BDED42c6DA8FBf0d2bA55B2fa120C5e0c8D7891', None), ('baseswap', '0x327Df1E6de05895d2ab08513aaDD9313Fe505d86', None))
            V2_FORKS_MAINNET = (('uniswap_v2', '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D', 'uniswap_v2'), ('sushi_v2', '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F', None))

            def _lr5():
                AERO_V2_ROUTER = '0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43'
                AERO_V2_FACTORY = '0x420DD381b31aEf6683db6B902084cB0FFECe40Da'
                V4_STATE_VIEW = '0xA3c0c9b65baD0b08107Aa264b0f3dB444b867A71'
                V4_QUOTER = '0x0d5e0F971ED27FBfF6c2837bf31316121532048D'
                return (AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger)
            return _lr5()
        return _lr18()

    def _lr7():
        global AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, CLANKER_HOOK, HOOK_BDF9, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_BASES, V4_DYN_FEE, V4_KEY_GRID, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, ZORA_CREATOR_HOOK, ZORA_HOOK, _ZERO, _dr3, logger
        AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger = _dr9()
        V4_DYN_FEE = 8388608
        CLANKER_HOOK = '0xb429d62f8f3bffb98cdb9569533ea23bf0ba28cc'

        def _dr3():
            HOOK_BDF9 = '0xbdf938149ac6a781f94faa0ed45e6a0e984c6544'
            ZORA_HOOK = '0xc8d077444625eb300a427a6dfb2b1dbf9b159040'
            ZORA_CREATOR_HOOK = '0xd61a675f8a0c67a73dc3b54fb7318b4d91409040'

            def _lr15():
                return ((V4_DYN_FEE, 200, CLANKER_HOOK), (V4_DYN_FEE, 200, '0xd60d6b218116cfd801e28f78d011a203d2b068cc'), (V4_DYN_FEE, 200, '0xbdf938149ac6a781f94faa0ed45e6a0e984c6544'), (V4_DYN_FEE, 200, HOOK_BDF9), (30000, 200, ZORA_CREATOR_HOOK), (10000, 200, ZORA_HOOK), (10000, 200, _ZERO))

            def _lr16():
                return ((3000, 60, _ZERO), (100000, 2000, _ZERO), (500, 10, _ZERO), (100, 1, _ZERO), (20000, 200, _ZERO), (800000, 100, CLANKER_HOOK))
            V4_KEY_GRID = (*_lr15(), *_lr16())

            def _lr4():
                V4_BASES = (_ZERO, WETH, USDC, ZORA, VIRTUAL)
                return (HOOK_BDF9, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK)
            return _lr4()
        HOOK_BDF9, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK = _dr3()
    _lr7()
    MAX_CALLS = 90

    def _sorted_pair(a: str, b: str) -> tuple[str, str]:
        return (a, b) if int(a, 16) < int(b, 16) else (b, a)

    def v4_pool_id(c0: str, c1: str, fee: int, tick: int, hooks: str) -> bytes:
        """keccak(abi.encode(PoolKey)) — computed offline, no RPC."""
        return _kk(_enc(['address', 'address', 'uint24', 'int24', 'address'], [_ck(c0), _ck(c1), int(fee), int(tick), _ck(hooks)]))
_lr27()

class _DiscoveryEngineDR12:

    def v2_candidates(self, chain_id: int, tin: str, tout: str, amount_in: int) -> list[dict]:
        forks = V2_FORKS_BASE if chain_id == 8453 else V2_FORKS_MAINNET if chain_id == 1 else ()
        hubs = [WETH, USDC] if chain_id == 8453 else ['0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48']
        _dr6 = out = None

        def _lr13():
            nonlocal _dr6, out
            out = []
            paths = [[tin, tout]] + [[tin, h, tout] for h in hubs if h.lower() not in (tin.lower(), tout.lower())]

            def _dr6():
                base = None
                q = None
                for label, router, native in forks:
                    for path in paths:

                        def _lr23():
                            nonlocal q
                            q = self._v2_quote(router, path, amount_in)

                            def _lr10():
                                nonlocal base
                                if q <= 0:
                                    return True
                                n_hops = len(path) - 1
                                base = {'out': q, 'tokens': tuple(path), 'gas_est': 150000 * n_hops, 'gas_model': 350000 + 150000 * n_hops, 'discovered': label}
                            if _lr10():
                                return True
                            if native:
                                out.append({**base, 'venue': native, 'param': tuple(path)})
                            else:
                                out.append({**base, 'venue': 'v2_fork', 'router': router, 'param': router})
                        if _lr23():
                            continue
                        break
        _lr13()
        _dr6()
        return out

    def aero_v2_candidates(self, chain_id: int, tin: str, tout: str, amount_in: int) -> list[dict]:
        if chain_id != 8453:
            return []

        def _dr2():
            out = route_sets = None

            def _lr28():
                nonlocal out, route_sets
                out = []
                route_sets = []
                for stable in (False, True):
                    route_sets.append(((tin, tout, stable, AERO_V2_FACTORY),))

                def _lr11():
                    for hub in (WETH, USDC):
                        if hub.lower() in (tin.lower(), tout.lower()):
                            continue
                        route_sets.append(((tin, hub, False, AERO_V2_FACTORY), (hub, tout, False, AERO_V2_FACTORY)))
                _lr11()
            _lr28()
            return (out, route_sets)
        out, route_sets = _dr2()
        q = None

        def _lr21():
            nonlocal q
            q = None
            for routes in route_sets:

                def _lr8():
                    nonlocal q

                    def _dr8():
                        data = None

                        def _lr24():
                            nonlocal data
                            data = _kk(text='getAmountsOut(uint256,(address,address,bool,address)[])')[:4] + _enc(['uint256', '(address,address,bool,address)[]'], [amount_in, [(_ck(a), _ck(b), s, _ck(f)) for a, b, s, f in routes]])
                        _lr24()
                        r = self._c(AERO_V2_ROUTER, data)
                        return (data, r)
                    data, r = _dr8()
                    if not r:
                        return True
                    try:
                        q = int(_dec(['uint256[]'], r)[0][-1])
                    except Exception:
                        return True
                    if q <= 0:
                        return True
                if _lr8():
                    continue
                out.append({'venue': 'aerodrome_v2', 'routes': routes, 'out': q, 'param': AERO_V2_FACTORY, 'gas_est': 170000 * len(routes), 'gas_model': 350000 + 170000 * len(routes), 'discovered': 'aero_v2'})
            return out
        return _lr21()

class _DiscoveryEngineLR9(_DiscoveryEngineDR12):

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
        r = None

        def _lr22():
            nonlocal r
            data = _kk(text='getAmountsOut(uint256,address[])')[:4] + _enc(['uint256', 'address[]'], [amount_in, [_ck(p) for p in path]])
            r = self._c(router, data)
        _lr22()
        if not r:
            return 0
        try:
            return int(_dec(['uint256[]'], r)[0][-1])
        except Exception:
            return 0

    def _v4_liquidity(self, pool_id: bytes) -> int:
        data = _kk(text='getLiquidity(bytes32)')[:4] + pool_id
        r = self._c(V4_STATE_VIEW, data)
        if not r:
            return 0
        try:
            return int.from_bytes(r[-16:], 'big')
        except Exception:
            return 0

    def _v4_quote(self, key: tuple, zero_for_one: bool, amount_in: int) -> int:
        c0, c1, fee, tick, hooks = key

        def _lr20():
            return _kk(text='quoteExactInputSingle(((address,address,uint24,int24,address),bool,uint128,bytes))')[:4] + _enc(['((address,address,uint24,int24,address),bool,uint128,bytes)'], [((_ck(c0), _ck(c1), int(fee), int(tick), _ck(hooks)), bool(zero_for_one), int(amount_in), b'')])
        data = _lr20()

        def _lr3():
            r = self._c(V4_QUOTER, data)
            if not r or len(r) < 32:
                return 0
            try:
                return int(_dec(['uint256', 'uint256'], r)[0])
            except Exception:
                return 0
        return _lr3()

class _DiscoveryEngineLR29(_DiscoveryEngineLR9):

    def __init__(self, call: Callable[[str, str], Any]):
        self._call = call
        self._used = 0

class DiscoveryEngine(_DiscoveryEngineLR29):
    """Stateless per-call sweep; ``call`` is an eth_call thunk with the
    solver's socket timeout already applied: call(to, data) -> bytes|None."""

    def v4_candidates(self, chain_id: int, tin: str, tout: str, amount_in: int) -> list[dict]:
        """Find a V4 pool holding ``tout`` against a known base currency.

        Emits ``uniswap_v4_ur`` specs matching the solver's existing builder:
        base == tin -> single v4 leg; base != tin -> UR v3 leg (tin->WETH/USDC)
        chained into the v4 leg via CONTRACT_BALANCE.
        """
        if chain_id != 8453:
            return []
        out: list[dict] = []
        _dr1 = leg_in = q = spec = zero_for_one = None
        _dr11 = _dr4 = _lr2 = c0 = c1 = fee = hooks = pid = tick = None

        def _lr17():
            nonlocal _dr11, _dr4, _lr2, c0, c1, fee, hooks, pid, tick
            _dr11 = _dr4 = _lr2 = c0 = c1 = fee = hooks = pid = tick = None
            for base in V4_BASES:
                if base.lower() == tout.lower():
                    continue

                def _lr12():
                    nonlocal _dr11, _dr4, _lr2, c0, c1, fee, hooks, pid, tick
                    for fee, tick, hooks in V4_KEY_GRID:

                        def _dr11():
                            c0, c1 = _sorted_pair(base, tout)
                            pid = v4_pool_id(c0, c1, fee, tick, hooks)
                            return (c0, c1, pid)
                        c0, c1, pid = _dr11()
                        if self._v4_liquidity(pid) <= 0:
                            continue

                        def _lr2():
                            nonlocal _dr1, leg_in, q, spec, zero_for_one
                            zero_for_one = c0.lower() == base.lower()
                            leg_in = amount_in

                            def _dr5():
                                spec: dict[str, Any] = {'pool': (c0, c1, fee, tick, hooks), 'settle': base if base != _ZERO else WETH, 'zero_for_one': zero_for_one}
                                return spec
                            spec = _dr5()
                            if base.lower() != tin.lower():

                                def _dr1():
                                    nonlocal leg_in
                                    settle = WETH if base == _ZERO else base

                                    def _lr25():
                                        nonlocal leg_in
                                        spec['v3_tokens'] = (tin, settle)
                                        spec['v3_fees'] = (500,) if settle.lower() == WETH.lower() else (3000,)
                                        if base == _ZERO:
                                            spec['native_eth'] = True
                                        leg_in = 0
                                        return settle
                                    return _lr25()
                                settle = _dr1()

                            def _dr7():
                                q = self._v4_quote((c0, c1, fee, tick, hooks), zero_for_one, leg_in) if leg_in else 1
                                return q
                            q = _dr7()
                        _lr2()
                        if q <= 0:
                            continue

                        def _dr4():
                            out.append({'venue': 'uniswap_v4_ur', 'spec': spec, 'param': 'v4-disc', 'out': q, 'gas_est': 650000, 'gas_model': 350000 + 650000, 'discovered': f'v4:{fee}/{tick}/{hooks[:8]}'})
                        _dr4()
                        break
                _lr12()
                if out:
                    break
            return out
        return _lr17()

    def discover(self, chain_id: int, tin: str, tout: str, amount_in: int, min_out: int) -> list[dict]:
        """All venue families, cheapest/most-likely first. Returns candidates
        sorted by quoted output desc; quoted candidates beat probed ones."""

        def _dr10():
            nonlocal tin, tout
            tin, tout = (tin.lower(), tout.lower())
            cands = None

            def _lr26():
                nonlocal cands
                cands = []
                try:
                    cands += self.v2_candidates(chain_id, tin, tout, amount_in)

                    def _lr6():
                        nonlocal cands
                        if not (min_out <= 1 and cands):
                            cands += self.aero_v2_candidates(chain_id, tin, tout, amount_in)
                        if not (min_out <= 1 and cands):
                            cands += self.v4_candidates(chain_id, tin, tout, amount_in)
                    _lr6()
                except Exception:
                    logger.exception('[discovery] sweep failed (%s->%s)', tin, tout)
                return cands
            return _lr26()
        cands = _dr10()
        cands.sort(key=lambda c: c.get('out', 0), reverse=True)
        logger.info('[discovery] %s->%s chain=%s: %d candidate(s), %d rpc calls', tin[:8], tout[:8], chain_id, len(cands), self._used)
        return cands
