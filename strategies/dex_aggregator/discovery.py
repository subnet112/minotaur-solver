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
_DR_UNSET = object()
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

        def _dz2771():
            CBETH, V2_FORKS_BASE, VIRTUAL, ZORA = _dz2770()
            V2_FORKS_MAINNET = (('uniswap_v2', '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D', 'uniswap_v2'), ('sushi_v2', '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F', None))
            AERO_V2_ROUTER = '0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43'
            return (AERO_V2_ROUTER, CBETH, V2_FORKS_BASE, V2_FORKS_MAINNET, VIRTUAL, ZORA)

        def _dz2770():
            CBETH = '0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22'
            ZORA = '0x1111111111166b7fe7bd91427724b487980afc69'
            VIRTUAL = '0x0b3e328455c4059eeb9e3f84b5543f74e24e7e1b'
            V2_FORKS_BASE = (('uniswap_v2', '0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24', 'uniswap_v2'), ('pancake_v2', '0x8cFe327CEc66d1C090Dd72bd0FF11d690C33a2Eb', 'pancake_v2'), ('sushi_v2', '0x6BDED42c6DA8FBf0d2bA55B2fa120C5e0c8D7891', None), ('baseswap', '0x327Df1E6de05895d2ab08513aaDD9313Fe505d86', None))
            return (CBETH, V2_FORKS_BASE, VIRTUAL, ZORA)

        def _dz2769():
            AERO_V2_FACTORY = '0x420DD381b31aEf6683db6B902084cB0FFECe40Da'
            V4_STATE_VIEW = '0xA3c0c9b65baD0b08107Aa264b0f3dB444b867A71'
            V4_QUOTER = '0x0d5e0F971ED27FBfF6c2837bf31316121532048D'
            return (((AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger),),)
            return _DR_UNSET
        AERO_V2_ROUTER, CBETH, V2_FORKS_BASE, V2_FORKS_MAINNET, VIRTUAL, ZORA = _dz2771()
        _r_dz2769 = _dz2769()
        if _r_dz2769 is not _DR_UNSET:
            return _r_dz2769[0]
    _fwr4 = _fw4()
    if _fwr4 is not None:
        return _fwr4[0]

def _fz4():

    def _dz2785():
        V4_DYN_FEE = 8388608
        CLANKER_HOOK = '0xb429d62f8f3bffb98cdb9569533ea23bf0ba28cc'
        return ((AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, CLANKER_HOOK, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_DYN_FEE, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger),)
        return _DR_UNSET
    AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger = _dr9()
    _r_dz2785 = _dz2785()
    if _r_dz2785 is not _DR_UNSET:
        return _r_dz2785[0]

def _fz5():

    def _dz2783():
        return ((AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, CLANKER_HOOK, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_DYN_FEE, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger),)
        return _DR_UNSET
    AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, CLANKER_HOOK, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_DYN_FEE, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger = _fz4()
    _r_dz2783 = _dz2783()
    if _r_dz2783 is not _DR_UNSET:
        return _r_dz2783[0]

def _fz6():

    def _dz2781():
        return ((AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, CLANKER_HOOK, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_DYN_FEE, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger),)
        return _DR_UNSET
    AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, CLANKER_HOOK, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_DYN_FEE, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger = _fz5()
    _r_dz2781 = _dz2781()
    if _r_dz2781 is not _DR_UNSET:
        return _r_dz2781[0]

def _fz7():

    def _dz2779():
        return ((AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, CLANKER_HOOK, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_DYN_FEE, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger),)
        return _DR_UNSET
    AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, CLANKER_HOOK, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_DYN_FEE, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger = _fz6()
    _r_dz2779 = _dz2779()
    if _r_dz2779 is not _DR_UNSET:
        return _r_dz2779[0]

def _fz8():

    def _dz2777():
        return ((AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, CLANKER_HOOK, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_DYN_FEE, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger),)
        return _DR_UNSET
    AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, CLANKER_HOOK, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_DYN_FEE, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger = _fz7()
    _r_dz2777 = _dz2777()
    if _r_dz2777 is not _DR_UNSET:
        return _r_dz2777[0]

def _fz9():

    def _dz2775():
        return ((AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, CLANKER_HOOK, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_DYN_FEE, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger),)
        return _DR_UNSET
    AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, CLANKER_HOOK, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_DYN_FEE, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger = _fz8()
    _r_dz2775 = _dz2775()
    if _r_dz2775 is not _DR_UNSET:
        return _r_dz2775[0]

def _fz10():

    def _dz2773():
        return ((AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, CLANKER_HOOK, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_DYN_FEE, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger),)
        return _DR_UNSET
    AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, CLANKER_HOOK, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_DYN_FEE, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger = _fz9()
    _r_dz2773 = _dz2773()
    if _r_dz2773 is not _DR_UNSET:
        return _r_dz2773[0]
AERO_V2_FACTORY, AERO_V2_ROUTER, CBETH, CLANKER_HOOK, USDBC, USDC, V2_FORKS_BASE, V2_FORKS_MAINNET, V4_DYN_FEE, V4_QUOTER, V4_STATE_VIEW, VIRTUAL, WETH, ZORA, _ZERO, logger = _fz10()

def _dr3():
    HOOK_BDF9 = '0xbdf938149ac6a781f94faa0ed45e6a0e984c6544'
    ZORA_HOOK = '0xc8d077444625eb300a427a6dfb2b1dbf9b159040'
    ZORA_CREATOR_HOOK = '0xd61a675f8a0c67a73dc3b54fb7318b4d91409040'

    def _fw3():

        def _dz2767():
            V4_BASES = (_ZERO, WETH, USDC, ZORA, VIRTUAL)
            return ((V4_KEY_GRID, V4_BASES),)
            return _DR_UNSET
        V4_KEY_GRID = ((V4_DYN_FEE, 200, CLANKER_HOOK), (V4_DYN_FEE, 200, '0xd60d6b218116cfd801e28f78d011a203d2b068cc'), (V4_DYN_FEE, 200, '0xbdf938149ac6a781f94faa0ed45e6a0e984c6544'), (V4_DYN_FEE, 200, HOOK_BDF9), (30000, 200, ZORA_CREATOR_HOOK), (10000, 200, ZORA_HOOK), (10000, 200, _ZERO), (3000, 60, _ZERO), (100000, 2000, _ZERO), (500, 10, _ZERO), (100, 1, _ZERO), (20000, 200, _ZERO), (800000, 100, CLANKER_HOOK))
        _r_dz2767 = _dz2767()
        if _r_dz2767 is not _DR_UNSET:
            return _r_dz2767[0]
    V4_KEY_GRID, V4_BASES = _fw3()
    return (HOOK_BDF9, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK)

def _fz3():

    def _dz2772():
        return ((ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK),)
        return _DR_UNSET

    def _fz16():

        def _dz2766():
            return ((ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK),)
            return _DR_UNSET

        def _fz17():

            def _dz2751():
                return ((ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK),)
                return _DR_UNSET

            def _fz18():

                def _dz2739():
                    return ((ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK),)
                    return _DR_UNSET

                def _fz19():

                    def _dz2733():
                        return ((ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK),)
                        return _DR_UNSET

                    def _fz20():

                        def _dz2731():
                            return ((ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK),)
                            return _DR_UNSET

                        def _fz21():

                            def _dz2730():
                                return ((ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK),)
                                return _DR_UNSET

                            def _fz22():

                                def _dz2729():
                                    return ((ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK),)
                                    return _DR_UNSET

                                def _fz23():

                                    def _dz2728():
                                        return ((ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK),)
                                        return _DR_UNSET

                                    def _fz24():

                                        def _dz2727():
                                            return ((ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK),)
                                            return _DR_UNSET

                                        def _fz25():

                                            def _dz2726():
                                                return ((ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK),)
                                                return _DR_UNSET

                                            def _fz26():

                                                def _dz2725():
                                                    return ((ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK),)
                                                    return _DR_UNSET

                                                def _fz27():

                                                    def _dz2723():
                                                        HOOK_BDF9, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK = _dr3()
                                                        ETH_WETH = '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'
                                                        ETH_USDC = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'
                                                        ETH_DAI = '0x6B175474E89094C44Da98b954EedeAC495271d0F'
                                                        return (ETH_DAI, ETH_USDC, ETH_WETH, HOOK_BDF9, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK)

                                                    def _dz2722():
                                                        MAX_CALLS = 90
                                                        return ((ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK),)
                                                        return _DR_UNSET
                                                    ETH_DAI, ETH_USDC, ETH_WETH, HOOK_BDF9, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK = _dz2723()
                                                    ETH_USDT = '0xdAC17F958D2ee523a2206206994597C13D831ec7'
                                                    ETH_WBTC = '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599'
                                                    ETH_V4_QUOTER = '0x52f0e24d1c21c8a0cb1e5a5dd6198556bd9e1203'

                                                    def _grid():

                                                        def _dz2721():
                                                            ETH_V4_BASES = (_ZERO, ETH_WETH, ETH_USDC, ETH_DAI, ETH_USDT, ETH_WBTC)
                                                            return ETH_V4_BASES
                                                        ETH_V4_BASES = _dz2721()
                                                        ETH_V4_KEY_GRID = ((3000, 60, _ZERO), (500, 10, _ZERO), (10000, 200, _ZERO), (100, 1, _ZERO), (10, 1, _ZERO), (7, 1, _ZERO))
                                                        return (ETH_V4_BASES, ETH_V4_KEY_GRID)
                                                    ETH_V4_BASES, ETH_V4_KEY_GRID = _grid()
                                                    _r_dz2722 = _dz2722()
                                                    if _r_dz2722 is not _DR_UNSET:
                                                        return _r_dz2722[0]
                                                ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK = _fz27()
                                                _r_dz2725 = _dz2725()
                                                if _r_dz2725 is not _DR_UNSET:
                                                    return _r_dz2725[0]
                                            ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK = _fz26()
                                            _r_dz2726 = _dz2726()
                                            if _r_dz2726 is not _DR_UNSET:
                                                return _r_dz2726[0]
                                        ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK = _fz25()
                                        _r_dz2727 = _dz2727()
                                        if _r_dz2727 is not _DR_UNSET:
                                            return _r_dz2727[0]
                                    ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK = _fz24()
                                    _r_dz2728 = _dz2728()
                                    if _r_dz2728 is not _DR_UNSET:
                                        return _r_dz2728[0]
                                ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK = _fz23()
                                _r_dz2729 = _dz2729()
                                if _r_dz2729 is not _DR_UNSET:
                                    return _r_dz2729[0]
                            ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK = _fz22()
                            _r_dz2730 = _dz2730()
                            if _r_dz2730 is not _DR_UNSET:
                                return _r_dz2730[0]
                        ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK = _fz21()
                        _r_dz2731 = _dz2731()
                        if _r_dz2731 is not _DR_UNSET:
                            return _r_dz2731[0]
                    ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK = _fz20()
                    _r_dz2733 = _dz2733()
                    if _r_dz2733 is not _DR_UNSET:
                        return _r_dz2733[0]
                ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK = _fz19()
                _r_dz2739 = _dz2739()
                if _r_dz2739 is not _DR_UNSET:
                    return _r_dz2739[0]
            ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK = _fz18()
            _r_dz2751 = _dz2751()
            if _r_dz2751 is not _DR_UNSET:
                return _r_dz2751[0]
        ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK = _fz17()
        _r_dz2766 = _dz2766()
        if _r_dz2766 is not _DR_UNSET:
            return _r_dz2766[0]
    ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK = _fz16()
    _r_dz2772 = _dz2772()
    if _r_dz2772 is not _DR_UNSET:
        return _r_dz2772[0]
ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_V4_QUOTER, ETH_WETH, HOOK_BDF9, MAX_CALLS, V4_BASES, V4_KEY_GRID, ZORA_CREATOR_HOOK, ZORA_HOOK = _fz3()

def _v4_cfg(chain_id):
    """(bases, grid, weth, quoter, stateview_or_None) for the chain's V4 venue."""
    if chain_id == 8453:
        return (V4_BASES, V4_KEY_GRID, WETH, V4_QUOTER, V4_STATE_VIEW)
    return (ETH_V4_BASES, ETH_V4_KEY_GRID, ETH_WETH, ETH_V4_QUOTER, None)

def _sorted_pair(a, b):
    return (a, b) if int(a, 16) < int(b, 16) else (b, a)

def v4_pool_id(c0, c1, fee, tick, hooks):
    """keccak(abi.encode(PoolKey)) — computed offline, no RPC."""
    return _kk(_enc(['address', 'address', 'uint24', 'int24', 'address'], [_ck(c0), _ck(c1), int(fee), int(tick), _ck(hooks)]))

class _DiscoveryEngineDR12:

    def v2_candidates(self, chain_id, tin, tout, amount_in):

        def _dz2764(chain_id):
            forks = V2_FORKS_BASE if chain_id == 8453 else V2_FORKS_MAINNET if chain_id == 1 else ()
            hubs = [WETH, USDC] if chain_id == 8453 else ['0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48']
            return (forks, hubs)
        forks, hubs = _dz2764(chain_id)
        out = []
        paths = [[tin, tout]] + [[tin, h, tout] for h in hubs if h.lower() not in (tin.lower(), tout.lower())]

        def _dr6():

            def _dz392():

                def _dz2737(path, q):
                    n_hops = len(path) - 1
                    base = {'out': q, 'tokens': tuple(path), 'gas_est': 150000 * n_hops, 'gas_model': 350000 + 150000 * n_hops, 'discovered': label}
                    return (base, n_hops)

                def _dz2736():
                    if native:
                        out.append({**base, 'venue': native, 'param': tuple(path)})
                    else:
                        out.append({**base, 'venue': 'v2_fork', 'router': router, 'param': router})
                for path in paths:
                    q = self._v2_quote(router, path, amount_in)
                    if q <= 0:
                        continue
                    base, n_hops = _dz2737(path, q)
                    _dz2736()
                    break
            for label, router, native in forks:
                _dz392()
        _dr6()
        return out

    def aero_v2_candidates(self, chain_id, tin, tout, amount_in):

        def _dz394():

            def _dz2750(r):
                q = int(_dec(['uint256[]'], r)[0][-1])
                return q

            def _dz2749():
                out.append({'venue': 'aerodrome_v2', 'routes': routes, 'out': q, 'param': AERO_V2_FACTORY, 'gas_est': 170000 * len(routes), 'gas_model': 350000 + 170000 * len(routes), 'discovered': 'aero_v2'})
            for routes in route_sets:

                def _dr8():
                    data = _kk(text='getAmountsOut(uint256,(address,address,bool,address)[])')[:4] + _enc(['uint256', '(address,address,bool,address)[]'], [amount_in, [(_ck(a), _ck(b), s, _ck(f)) for a, b, s, f in routes]])
                    r = self._c(AERO_V2_ROUTER, data)
                    return (data, r)
                data, r = _dr8()
                if not r:
                    continue
                try:
                    q = _dz2750(r)
                except Exception:
                    continue
                if q <= 0:
                    continue
                _dz2749()
        if chain_id != 8453:
            return []

        def _dr2():

            def _dz2748():
                out = []
                route_sets = []
                _dz2747()
                return (out, route_sets)

            def _dz2747():
                for stable in (False, True):
                    route_sets.append(((tin, tout, stable, AERO_V2_FACTORY),))

            def _dz2746():
                route_sets.append(((tin, hub, False, AERO_V2_FACTORY), (hub, tout, False, AERO_V2_FACTORY)))
            out, route_sets = _dz2748()
            for hub in (WETH, USDC):
                if hub.lower() in (tin.lower(), tout.lower()):
                    continue
                _dz2746()
            return (out, route_sets)
        out, route_sets = _dr2()
        _dz394()
        return out

class DiscoveryEngine(_DiscoveryEngineDR12):
    """Stateless per-call sweep; ``call`` is an eth_call thunk with the
    solver's socket timeout already applied: call(to, data) -> bytes|None."""

    def __init__(self, call):
        self._call = call
        self._used = 0

    def _c(self, to, data):

        def _dz2763():
            try:
                r = self._call(_ck(to), '0x' + data.hex())
                if r is None:
                    return (None,)
                return (bytes(r),)
            except Exception:
                return (None,)
            return _DR_UNSET
        if self._used >= MAX_CALLS:
            return None
        self._used += 1
        _r_dz2763 = _dz2763()
        if _r_dz2763 is not _DR_UNSET:
            return _r_dz2763[0]

    def _v2_quote(self, router, path, amount_in):

        def _dz2762():
            if not r:
                return (0,)
            try:
                return (int(_dec(['uint256[]'], r)[0][-1]),)
            except Exception:
                return (0,)
            return _DR_UNSET

        def _dz2761(amount_in, path):
            data = _kk(text='getAmountsOut(uint256,address[])')[:4] + _enc(['uint256', 'address[]'], [amount_in, [_ck(p) for p in path]])
            return data
        data = _dz2761(amount_in, path)
        r = self._c(router, data)
        _r_dz2762 = _dz2762()
        if _r_dz2762 is not _DR_UNSET:
            return _r_dz2762[0]

    def _v4_liquidity(self, pool_id, state_view=None):

        def _dz2759(pool_id):
            data = _kk(text='getLiquidity(bytes32)')[:4] + pool_id
            _r_dz2758 = _dz2758()
            return (_r_dz2758, data)

        def _dz2758():
            r = self._c(sv, data)
            if not r:
                return (0,)
            try:
                return (int.from_bytes(r[-16:], 'big'),)
            except Exception:
                return (0,)
            return _DR_UNSET
        sv = state_view or V4_STATE_VIEW
        if state_view is None and sv is None:
            return 1
        _r_dz2758, data = _dz2759(pool_id)
        if _r_dz2758 is not _DR_UNSET:
            return _r_dz2758[0]

    def _v4_quote(self, key, zero_for_one, amount_in, quoter=None):

        def _fz15():
            c0, c1, fee, tick, hooks = key
            data = _kk(text='quoteExactInputSingle(((address,address,uint24,int24,address),bool,uint128,bytes))')[:4] + _enc(['((address,address,uint24,int24,address),bool,uint128,bytes)'], [((_ck(c0), _ck(c1), int(fee), int(tick), _ck(hooks)), bool(zero_for_one), int(amount_in), b'')])
            r = self._c(quoter or V4_QUOTER, data)
            return r
        r = _fz15()
        if not r or len(r) < 32:
            return 0
        try:
            return int(_dec(['uint256', 'uint256'], r)[0])
        except Exception:
            return 0

    def _v4_spec(self, base, tin, tout, amount_in, weth, state_view, skip_liq, fee, tick, hooks):
        """Pool id + liquidity gate + spec build for one (base, fee/tick/hooks).
        Returns ``(spec, key, zero_for_one, leg_in)`` or ``None`` (liquidity-gated)."""

        def _dz2756():
            pid = v4_pool_id(c0, c1, fee, tick, hooks)
            if not skip_liq and self._v4_liquidity(pid, state_view) <= 0:
                return (None,)
            return _DR_UNSET
        c0, c1 = _sorted_pair(base, tout)
        _r_dz2756 = _dz2756()
        if _r_dz2756 is not _DR_UNSET:
            return _r_dz2756[0]

        def _fz14():

            def _dz2744():
                spec = {'pool': (c0, c1, fee, tick, hooks), 'settle': base if base != _ZERO else weth, 'zero_for_one': zero_for_one}
                return ((leg_in, spec, zero_for_one),)
                return _DR_UNSET
            zero_for_one = c0.lower() == base.lower()
            leg_in = amount_in
            _r_dz2744 = _dz2744()
            if _r_dz2744 is not _DR_UNSET:
                return _r_dz2744[0]
        leg_in, spec, zero_for_one = _fz14()

        def _fz13():

            def _dz2743():
                settle = weth if base == _ZERO else base
                spec['v3_tokens'] = (tin, settle)
                _dz2742()
                leg_in = 0
                return (leg_in, settle)

            def _dz2742():
                spec['v3_fees'] = (500,) if settle.lower() == weth.lower() else (3000,)
                if base == _ZERO:
                    spec['native_eth'] = True
            if base.lower() != tin.lower():
                leg_in, settle = _dz2743()
            key = (c0, c1, fee, tick, hooks)
            return (key, leg_in)
        key, leg_in = _fz13()
        return (spec, key, zero_for_one, leg_in)

    def _v4_probe(self, base, tin, tout, amount_in, weth, quoter, state_view, skip_liq, fee, tick, hooks):
        """Quote one candidate; returns the venue spec dict or ``None`` (no fill)."""

        def _dz2754():
            if q <= 0:
                return (None,)
            _r_dz2753 = _dz2753()
            if _r_dz2753 is not _DR_UNSET:
                return (_r_dz2753[0],)
            return _DR_UNSET

        def _dz2753():
            return ({'venue': 'uniswap_v4_ur', 'spec': spec, 'param': 'v4-disc', 'out': q, 'gas_est': 650000, 'gas_model': 350000 + 650000, 'discovered': f'v4:{fee}/{tick}/{hooks[:8]}'},)
            return _DR_UNSET
        built = self._v4_spec(base, tin, tout, amount_in, weth, state_view, skip_liq, fee, tick, hooks)
        if built is None:
            return None

        def _fz12():

            def _dz2741():
                nonlocal q
                if skip_liq:
                    q = 1 if self._v4_quote(key, zero_for_one, 10 ** 6, quoter) > 0 else 0
                else:
                    q = 1
            spec, key, zero_for_one, leg_in = built
            if leg_in:
                q = self._v4_quote(key, zero_for_one, leg_in, quoter)
            else:
                _dz2741()
            return (q, spec)
        q, spec = _fz12()
        _r_dz2754 = _dz2754()
        if _r_dz2754 is not _DR_UNSET:
            return _r_dz2754[0]

    def v4_candidates(self, chain_id, tin, tout, amount_in):
        """Find a V4 pool holding ``tout`` against a known base currency.

        Emits ``uniswap_v4_ur`` specs matching the solver's existing builder:
        base == tin -> single v4 leg; base != tin -> UR v3 leg (tin->WETH/USDC)
        chained into the v4 leg via CONTRACT_BALANCE. Base + Ethereum (chain 1)
        via chain-selected quoter/bases/grid (see ``_v4_cfg``).
        """

        def _dz393():

            def _dz2740(base, fee, hooks, tick):
                cand = self._v4_probe(base, tin, tout, amount_in, weth, quoter, state_view, skip_liq, fee, tick, hooks)
                return cand
            for base in bases:
                if base.lower() == tout.lower():
                    continue
                for fee, tick, hooks in grid:
                    cand = _dz2740(base, fee, hooks, tick)
                    if cand is None:
                        continue
                    out.append(cand)
                    break
                if out:
                    break
        if chain_id not in (8453, 1):
            return []

        def _fz11():
            bases, grid, weth, quoter, state_view = _v4_cfg(chain_id)
            skip_liq = state_view is None
            out = []
            return (bases, grid, out, quoter, skip_liq, state_view, weth)
        bases, grid, out, quoter, skip_liq, state_view, weth = _fz11()
        _dz393()
        return out

    def discover(self, chain_id, tin, tout, amount_in, min_out):
        """All venue families, cheapest/most-likely first. Returns candidates
        sorted by quoted output desc; quoted candidates beat probed ones."""

        def _dz2752():
            cands.sort(key=lambda c: c.get('out', 0), reverse=True)
            logger.info('[discovery] %s->%s chain=%s: %d candidate(s), %d rpc calls', tin[:8], tout[:8], chain_id, len(cands), self._used)

        def _dr10():

            def _dz391():

                def _dz2735():
                    nonlocal cands
                    try:
                        _dz2734()
                        if not (min_out <= 1 and cands):
                            cands += self.v4_candidates(chain_id, tin, tout, amount_in)
                    except Exception:
                        logger.exception('[discovery] sweep failed (%s->%s)', tin, tout)

                def _dz2734():
                    nonlocal cands
                    cands += self.v2_candidates(chain_id, tin, tout, amount_in)
                    if not (min_out <= 1 and cands):
                        cands += self.aero_v2_candidates(chain_id, tin, tout, amount_in)
                cands = []
                _dz2735()
                return (cands,)
                return _DR_UNSET
            nonlocal tin, tout
            tin, tout = (tin.lower(), tout.lower())
            _r_dz391 = _dz391()
            if _r_dz391 is not _DR_UNSET:
                return _r_dz391[0]
        cands = _dr10()
        _dz2752()
        return cands