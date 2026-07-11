"""Strategy for app_da6c96b84c60 (DexAggregatorApp, Base chain 8453 only).

Execution model: the App pulls `amountIn` of `tokenIn` into a freshly
deployed EphemeralProxy, which then executes the plan's Interactions with
`msg.sender == proxy`. Approvals and swaps happen from the proxy's
balance/address.

CRITICAL: the App measures success by `balanceOf(App contract) - snapshot`.
The swap's output token MUST be delivered directly to the App contract
address (the `recipient` param in the router call), NOT to `receiver` and
NOT left at the proxy. Otherwise the plan scores 0.
"""
from __future__ import annotations
import time
from typing import Any
from eth_abi.abi import encode
from minotaur_subnet.shared.types import AppIntentDefinition, ExecutionPlan, Interaction, IntentState
from minotaur_subnet.sdk.intent_solver import MarketSnapshot
from minotaur_subnet.sdk.strategy import Strategy
from minotaur_subnet.sdk.selectors import APPROVE_SELECTOR, EXACT_INPUT_SINGLE_SELECTOR_V2, EXACT_INPUT_SELECTOR, SWAP_ROUTER_V2_CHAINS
APP_CONTRACT_ADDRESS = '0x0CDe9A7E60A0DF4B86c81490D0496ab3A8E104f1'
SWAP_ROUTER02_BASE = '0x2626664c2603336E57B271c5C0b26F421741e481'
UNISWAP_V3_FACTORY_BASE = '0x33128a8fC17869897dcE68Ed026d694621f6FDfD'
WETH = '0x4200000000000000000000000000000000000006'
USDC = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
DAI = '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb'
CBBTC = '0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf'
_FEE_TIERS = {frozenset({WETH.lower(), USDC.lower()}): 500, frozenset({USDC.lower(), DAI.lower()}): 100, frozenset({CBBTC.lower(), USDC.lower()}): 500, frozenset({CBBTC.lower(), WETH.lower()}): 500}
_DEFAULT_FEE = 500

def _dr3():

    def _bh2():
        _FEE_TIER_PROBE_ORDER = (500, 3000, 10000, 100)
        _GET_POOL_SELECTOR = bytes.fromhex('1698ee82')
        _LIQUIDITY_SELECTOR = bytes.fromhex('1a686502')
        return (_FEE_TIER_PROBE_ORDER, _GET_POOL_SELECTOR, _LIQUIDITY_SELECTOR)
    _FEE_TIER_PROBE_ORDER, _GET_POOL_SELECTOR, _LIQUIDITY_SELECTOR = _bh2()

    def _fee_for_pair(token_a, token_b):
        key = frozenset({token_a.lower(), token_b.lower()})
        return _FEE_TIERS.get(key, _DEFAULT_FEE)

    def _encode_approve(spender, amount):
        encoded_params = encode(['address', 'uint256'], [spender, amount])
        return '0x' + (APPROVE_SELECTOR + encoded_params).hex()

    def _encode_exact_input_single_v2(token_in, token_out, fee, recipient, amount_in, amount_out_minimum, sqrt_price_limit_x96=0):
        """SwapRouter02 (V2) exactInputSingle — no deadline param."""
        encoded_params = encode(['(address,address,uint24,address,uint256,uint256,uint160)'], [(token_in, token_out, fee, recipient, amount_in, amount_out_minimum, sqrt_price_limit_x96)])
        return '0x' + (EXACT_INPUT_SINGLE_SELECTOR_V2 + encoded_params).hex()

    def _encode_path(token_in, fee1, token_mid, fee2, token_out):
        """Uniswap V3 multi-hop path encoding: tokenIn + fee(3B) + tokenMid + fee(3B) + tokenOut."""

        def _addr_bytes(addr):
            return bytes.fromhex(addr[2:].rjust(40, '0'))
        return _addr_bytes(token_in) + fee1.to_bytes(3, 'big') + _addr_bytes(token_mid) + fee2.to_bytes(3, 'big') + _addr_bytes(token_out)

    def _encode_exact_input_v1(path, recipient, deadline, amount_in, amount_out_minimum):
        encoded_params = encode(['(bytes,address,uint256,uint256,uint256)'], [(path, recipient, deadline, amount_in, amount_out_minimum)])
        return '0x' + (EXACT_INPUT_SELECTOR + encoded_params).hex()

    def _eth_call(w3, target, data):

        def _bh1():
            return bytes(w3.eth.call({'to': target, 'data': data}))
        try:
            return _bh1()
        except Exception:
            return None

    def _get_pool(w3, factory, token_a, token_b, fee):
        data = _GET_POOL_SELECTOR + encode(['address', 'address', 'uint24'], [token_a, token_b, fee])
        result = _eth_call(w3, factory, data)
        if not result or len(result) < 32:
            return None
        addr_int = int.from_bytes(result[-20:], 'big')
        if addr_int == 0:
            return None
        return '0x' + result[-20:].hex()

    def _get_liquidity(w3, pool):
        result = _eth_call(w3, pool, _LIQUIDITY_SELECTOR)
        if not result:
            return 0
        return int.from_bytes(result[-32:], 'big')

    def _find_best_fee_tier(w3, factory, token_a, token_b):
        """Probe fee tiers in priority order; among tiers with a real pool, pick
    the highest-liquidity one. Returns None if no pool exists at any tier."""
        best_fee = None
        best_liquidity = -1
        for fee in _FEE_TIER_PROBE_ORDER:
            pool = _get_pool(w3, factory, token_a, token_b, fee)
            if pool is None:
                continue
            liquidity = _get_liquidity(w3, pool)
            if liquidity > best_liquidity:
                best_liquidity = liquidity
                best_fee = fee
        return best_fee
    return (_FEE_TIER_PROBE_ORDER, _encode_approve, _encode_exact_input_single_v2, _encode_exact_input_v1, _encode_path, _fee_for_pair, _find_best_fee_tier, _get_pool)
_FEE_TIER_PROBE_ORDER, _encode_approve, _encode_exact_input_single_v2, _encode_exact_input_v1, _encode_path, _fee_for_pair, _find_best_fee_tier, _get_pool = _dr3()

class DexAggregatorStrategy(Strategy):
    APP_ID = 'app_da6c96b84c60'
    INTENT_FUNCTIONS = ['swap']

    def generate_plan(self, intent, state, snapshot=None):

        def _dr4():

            def _bh3():
                typed = getattr(state, 'typed_context', None)
                raw = getattr(state, 'raw_params', {}) or {}
                input_token = getattr(typed, 'input_token', '') or raw.get('input_token', '')
                output_token = getattr(typed, 'output_token', '') or raw.get('output_token', '')
                input_amount = int(getattr(typed, 'input_amount', 0) or raw.get('input_amount', '0') or 0)
                return (input_amount, input_token, output_token, raw, typed)
            input_amount, input_token, output_token, raw, typed = _bh3()

            def _bh4():
                min_output_amount = int(getattr(typed, 'min_output_amount', 0) or getattr(typed, 'suggested_min_output', 0) or raw.get('min_output_amount', '0') or raw.get('suggested_min_output', '0') or 0)
                chain_id = state.chain_id or 8453
                amount_out_minimum = min_output_amount if min_output_amount > 0 else 1
                return (amount_out_minimum, chain_id)
            amount_out_minimum, chain_id = _bh4()

            def _dr2():
                nonlocal Web3, fee, w3
                fee = None
                multihop_path = None
                rpc_url = self.rpc_for(chain_id)
                if rpc_url:
                    try:
                        from web3 import Web3
                        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 3}))
                        fee = _find_best_fee_tier(w3, UNISWAP_V3_FACTORY_BASE, input_token, output_token)
                        if fee is None:
                            for bridge in (WETH, USDC):
                                if input_token.lower() == bridge.lower() or output_token.lower() == bridge.lower():
                                    continue
                                fee_in = _find_best_fee_tier(w3, UNISWAP_V3_FACTORY_BASE, input_token, bridge)
                                fee_out = _find_best_fee_tier(w3, UNISWAP_V3_FACTORY_BASE, bridge, output_token)
                                if fee_in is not None and fee_out is not None:
                                    multihop_path = _encode_path(input_token, fee_in, bridge, fee_out, output_token)
                                    break
                    except Exception:
                        fee = None
                        multihop_path = None
                return (multihop_path, rpc_url)

            def _bh5():
                multihop_path, rpc_url = _dr2()
                return (1, (amount_out_minimum, chain_id, input_amount, input_token, multihop_path, output_token, rpc_url))
                return (0, None)
            _t5 = _bh5()
            if _t5[0]:
                return _t5[1]
        amount_out_minimum, chain_id, input_amount, input_token, multihop_path, output_token, rpc_url = _dr4()
        if fee is None and multihop_path is None:
            if rpc_url:
                try:
                    from web3 import Web3
                    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 3}))
                    for candidate_fee in _FEE_TIER_PROBE_ORDER:
                        pool = _get_pool(w3, UNISWAP_V3_FACTORY_BASE, input_token, output_token, candidate_fee)
                        if pool is not None:
                            fee = candidate_fee
                            break
                except Exception:
                    pass
            if fee is None:
                fee = _fee_for_pair(input_token, output_token)

        def _dr1():
            approve_calldata = _encode_approve(SWAP_ROUTER02_BASE, input_amount)

            def _bh7():
                deadline_param = int(time.time()) + 300
                swap_calldata = _encode_exact_input_v1(path=multihop_path, recipient=APP_CONTRACT_ADDRESS, deadline=deadline_param, amount_in=input_amount, amount_out_minimum=amount_out_minimum)
                return swap_calldata
            if multihop_path is not None:
                swap_calldata = _bh7()
            else:

                def _bh6():
                    swap_calldata = _encode_exact_input_single_v2(token_in=input_token, token_out=output_token, fee=fee, recipient=APP_CONTRACT_ADDRESS, amount_in=input_amount, amount_out_minimum=amount_out_minimum, sqrt_price_limit_x96=0)
                    return swap_calldata
                if chain_id in SWAP_ROUTER_V2_CHAINS:
                    swap_calldata = _bh6()
                else:
                    from minotaur_subnet.sdk.selectors import EXACT_INPUT_SINGLE_SELECTOR_V1
                    deadline_param = int(time.time()) + 300
                    encoded_params = encode(['(address,address,uint24,address,uint256,uint256,uint256,uint160)'], [(input_token, output_token, fee, APP_CONTRACT_ADDRESS, deadline_param, input_amount, amount_out_minimum, 0)])
                    swap_calldata = '0x' + (EXACT_INPUT_SINGLE_SELECTOR_V1 + encoded_params).hex()

            def _bh8():
                interactions = [Interaction(target=input_token, value='0', call_data=approve_calldata, chain_id=chain_id), Interaction(target=SWAP_ROUTER02_BASE, value='0', call_data=swap_calldata, chain_id=chain_id)]
                return (1, interactions)
                return (0, None)
            _t8 = _bh8()
            if _t8[0]:
                return _t8[1]

        def _bh10():
            interactions = _dr1()
            deadline = int(time.time()) + 300
            return (deadline, interactions)
        deadline, interactions = _bh10()

        def _bh9():
            deadline = int(snapshot.timestamp) + 300
            return deadline

        def _bh11(deadline):
            if snapshot is not None and getattr(snapshot, 'timestamp', None):
                deadline = _bh9()
            return (1, ExecutionPlan(intent_id=intent.app_id, interactions=interactions, deadline=deadline, nonce=state.nonce))
            return (0, None)
        _t11 = _bh11(deadline)
        if _t11[0]:
            return _t11[1]
STRATEGY_CLASS = DexAggregatorStrategy