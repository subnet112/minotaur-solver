"""Baseline Yield Optimizer — the solver miners must beat.

Queries Aave V3 and Compound V3 lending rates via RPC, picks the
highest-yielding protocol, and generates a supply plan. This is the
simplest possible yield strategy: 100% allocation to the best rate.

Miners should surpass this with:
- Split allocations for risk diversification
- Rate trend analysis (predicting rate changes)
- Gas-cost-aware rebalancing (skip if improvement < gas cost)
- Multi-protocol yield farming (stacking rewards)
- Withdrawal queue awareness
"""
from __future__ import annotations

def _lr22():
    global Any, _DR_UNSET, _encode_aave_supply, _encode_compound_supply, _lr4, _query_aave_rate, _query_compound_rate, logging, time
    _DR_UNSET = object()
    import logging
    import time
    from typing import Any

    def _lr4():
        global AAVE_V3_POOL, AppIntentDefinition, COMPOUND_V3_CUSDC, ExecutionPlan, IntentState, Interaction, MarketSnapshot, Strategy, USDC, _encode_address, _encode_approve, _encode_uint256, logger
        from minotaur_subnet.shared.types import AppIntentDefinition, ExecutionPlan, Interaction, IntentState
        from minotaur_subnet.sdk.intent_solver import MarketSnapshot
        from minotaur_subnet.sdk.strategy import Strategy
        logger = logging.getLogger(__name__)
        AAVE_V3_POOL = '0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2'
        COMPOUND_V3_CUSDC = '0xc3d688B66703497DAA19211EEdff47f25384cdc3'
        USDC = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'

        def _encode_address(addr: str) -> str:
            return addr.replace('0x', '').lower().zfill(64)

        def _encode_uint256(value: int) -> str:
            return hex(value)[2:].zfill(64)

        def _encode_approve(spender: str, amount: int) -> str:
            """ERC-20 approve(address,uint256)"""
            selector = '095ea7b3'
            return '0x' + selector + _encode_address(spender) + _encode_uint256(amount)
    _lr4()

    def _encode_aave_supply(asset: str, amount: int, on_behalf_of: str) -> str:
        """Aave V3 supply(address,uint256,address,uint16)"""
        selector = '617ba037'
        return '0x' + selector + _encode_address(asset) + _encode_uint256(amount) + _encode_address(on_behalf_of) + _encode_uint256(0)

    def _encode_compound_supply(asset: str, amount: int) -> str:
        """Compound V3 supply(address,uint256)"""
        selector = 'f2b9fdb8'
        return '0x' + selector + _encode_address(asset) + _encode_uint256(amount)

    def _query_aave_rate(rpc_url: str) -> float:
        """Query Aave V3 USDC supply rate via RPC."""
        try:

            def _dr6():
                import urllib.request
                import json
                data = '0x35ea6a75' + _encode_address(USDC)
                _lr2 = rate_hex = None

                def _lr15():
                    nonlocal _lr2, rate_hex
                    payload = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'eth_call', 'params': [{'to': AAVE_V3_POOL, 'data': data}, 'latest']}).encode()
                    req = urllib.request.Request(rpc_url, data=payload, headers={'Content-Type': 'application/json'})
                    rate_hex = None

                    def _lr2():
                        nonlocal rate_hex
                        resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
                        result = resp.get('result', '0x')
                        rate_hex = result[2 + 2 * 64:2 + 3 * 64]
                _lr15()
                _lr2()
                return rate_hex
            rate_hex = _dr6()
            rate_ray = int(rate_hex, 16) if rate_hex else 0
            return rate_ray / 1e+27 * 100
        except Exception as exc:
            logger.debug('Failed to query Aave rate: %s', exc)
            return 0.0

    def _query_compound_rate(rpc_url: str) -> float:
        """Query Compound V3 USDC supply rate via RPC."""
        rate_per_second = req = resp = None
        payload = None
        try:

            def _lr21():
                nonlocal payload
                import urllib.request
                import json
                payload = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'eth_call', 'params': [{'to': COMPOUND_V3_CUSDC, 'data': '0x7eb71131'}, 'latest']}).encode()

                def _lr6():
                    nonlocal rate_per_second, req, resp

                    def _dr2():
                        nonlocal payload, resp
                        req = urllib.request.Request(rpc_url, data=payload, headers={'Content-Type': 'application/json'})
                        _lr1 = None

                        def _lr14():
                            nonlocal _lr1, resp
                            resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
                            util_hex = resp.get('result', '0x0')
                            utilization = int(util_hex, 16)
                            data = '0xd955759d' + _encode_uint256(utilization)

                            def _lr1():
                                nonlocal payload, req
                                payload = json.dumps({'jsonrpc': '2.0', 'id': 2, 'method': 'eth_call', 'params': [{'to': COMPOUND_V3_CUSDC, 'data': data}, 'latest']}).encode()
                                req = urllib.request.Request(rpc_url, data=payload, headers={'Content-Type': 'application/json'})
                                return req
                        _lr14()
                        return _lr1()
                    req = _dr2()
                    resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
                    rate_hex = resp.get('result', '0x0')
                    rate_per_second = int(rate_hex, 16)
                _lr6()
            _lr21()
            return rate_per_second * 31536000 / 1e+18 * 100
        except Exception as exc:
            logger.debug('Failed to query Compound rate: %s', exc)
            return 0.0
_lr22()

class BaselineYieldStrategy(Strategy):
    """Baseline: deposit 100% to the highest-rate protocol."""
    APP_ID = ''
    INTENT_FUNCTIONS = ['rebalance']

    def generate_plan(self, intent: AppIntentDefinition, state: IntentState, snapshot: MarketSnapshot | None=None) -> ExecutionPlan | None:
        _lr7 = rpc_url = None

        def _lr23():
            nonlocal _lr7, rpc_url
            params = state.raw_params_view() if hasattr(state, 'raw_params_view') else getattr(state, 'raw_params', {}) or {}
            asset = params.get('asset', USDC)
            amount = int(params.get('amount', 0))
            rpc_url = None

            def _lr7():
                nonlocal rpc_url
                chain_id = state.chain_id or 31337
                contract_address = state.contract_address or ''
                if amount <= 0:
                    return None
                rpc_url = ''

                def _dr3():
                    nonlocal rpc_url
                    _lrt13 = _lrt32 = _lrt38 = aave_rate = compound_rate = interactions = route = target_protocol = None

                    def _lr39():
                        nonlocal _lrt13, _lrt32, _lrt38, aave_rate, compound_rate, interactions, route, target_protocol
                        _lrt13 = _lrt32 = aave_rate = compound_rate = interactions = route = target_protocol = None

                        def _lr33():
                            nonlocal _lrt13, _lrt32, aave_rate, compound_rate, interactions, route, target_protocol
                            aave_rate = compound_rate = interactions = route = target_protocol = None

                            def _lr5():
                                nonlocal aave_rate, compound_rate, interactions, route, rpc_url, target_protocol
                                if snapshot and hasattr(snapshot, 'rpc_urls') and snapshot.rpc_urls:
                                    rpc_url = snapshot.rpc_urls.get(chain_id, '')

                                def _dr1():
                                    nonlocal rpc_url
                                    if not rpc_url:
                                        import os
                                        rpc_url = os.environ.get('ANVIL_RPC_URL', '')

                                    def _dr5():
                                        aave_rate = _query_aave_rate(rpc_url) if rpc_url else 0
                                        compound_rate = _query_compound_rate(rpc_url) if rpc_url else 0
                                        route = supply_calldata = target_protocol = None

                                        def _lr16():
                                            nonlocal route, supply_calldata, target_protocol
                                            if compound_rate > aave_rate and compound_rate > 0:
                                                target_protocol = COMPOUND_V3_CUSDC
                                                supply_calldata = _encode_compound_supply(asset, amount)
                                                route = 'compound_v3'
                                            else:

                                                def _lr3():
                                                    nonlocal route, supply_calldata, target_protocol
                                                    if aave_rate > 0:
                                                        target_protocol = AAVE_V3_POOL
                                                        supply_calldata = _encode_aave_supply(asset, amount, contract_address)
                                                        route = 'aave_v3'
                                                    else:
                                                        target_protocol = AAVE_V3_POOL
                                                        supply_calldata = _encode_aave_supply(asset, amount, contract_address)
                                                        route = 'aave_v3_default'
                                                _lr3()
                                            return (aave_rate, compound_rate, route, supply_calldata, target_protocol)
                                        return _lr16()
                                    aave_rate, compound_rate, route, supply_calldata, target_protocol = _dr5()

                                    def _lr8():
                                        interactions = [Interaction(target=asset, value='0', call_data=_encode_approve(target_protocol, amount), chain_id=chain_id), Interaction(target=target_protocol, value='0', call_data=supply_calldata, chain_id=chain_id)]
                                        return (aave_rate, compound_rate, interactions, route, target_protocol)
                                    return _lr8()
                                aave_rate, compound_rate, interactions, route, target_protocol = _dr1()
                            _lr5()

                            def _lr12():
                                return (intent.app_id, interactions, int(time.time()) + 300)
                            _lrt13 = _lr12()

                            def _lr31():
                                return (_lrt13[0],)
                            _lrt32 = _lr31()
                        _lr33()

                        def _lr37():
                            return (_lrt32[0],)
                        _lrt38 = _lr37()
                    _lr39()

                    def _lr43():
                        return (_lrt38[0],)

                    def _lr9():
                        _lrt44 = _lr43()
                        return ExecutionPlan(intent_id=_lrt44[0], interactions=_lrt13[1], deadline=_lrt13[2], nonce=state.nonce, metadata={'strategy': 'baseline_yield', 'route': route, 'aave_rate': round(aave_rate, 4), 'compound_rate': round(compound_rate, 4), 'target_protocol': target_protocol, 'asset': asset, 'amount': str(amount)})
                        return _DR_UNSET
                    return _lr9()
                _dr4 = _dr3()
                if _dr4 is not _DR_UNSET:
                    return _dr4
        _lr23()
        return _lr7()
STRATEGY_CLASS = BaselineYieldStrategy
