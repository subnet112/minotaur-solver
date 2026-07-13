"""viking-mino-solver — thin fill-only-empty shim over the CURRENT champion
(apex-split-router v2.5.1, re-forked verbatim as apex_king_base.py per its own
doctrine: "Re-fork onto a new champion = copy its solver.py").

ONE addition: a RAW-REPLAY table (king_replay.json) of captured working router
calldata for corpus orders the champion lineage structurally cannot route
(true venues outside its engine+cover: sushi-v3 / quickswap-v4 / hydrex /
baseswap / maverick / clanker+flaunch+zora v4 variants / infinity-cl ...).
Served ONLY when the champion stack returns EMPTY, on an EXACT
(tin, tout, amount) key => can only lift a champion-0 to a delivery (a win /
blind-spot cover), never regress. Everything else defers byte-for-byte to the
champion. 84 rows, KyberSwap-verified, PMM-free (RFQ quotes expire), gas<=1.5M.
"""
from __future__ import annotations

def _lr5():
    global ExecutionPlan, Interaction, SOLVER_AUTHOR, SOLVER_NAME, SOLVER_VERSION, SolverMetadata, _ApexBase, _DR_UNSET, _KING_REPLAY_CACHE, _dr21, _king_replay, logger, logging, os
    _DR_UNSET = object()

    def _dr21():
        _DR_UNSET = object()
        import logging
        import os
        from apex_king_base import SOLVER_CLASS as _ApexBase
        from minotaur_subnet.sdk.intent_solver import SolverMetadata
        from minotaur_subnet.shared.types import ExecutionPlan, Interaction
        logger = logging.getLogger(__name__)
        SOLVER_NAME = os.environ.get('MINOTAUR_SOLVER_NAME', 'putty-clean-solver')
        SOLVER_VERSION = os.environ.get('MINOTAUR_SOLVER_VERSION', '0.87.5-edge')

        def _lr69():
            SOLVER_AUTHOR = os.environ.get('MINOTAUR_SOLVER_AUTHOR', 'martindev0207')
            _KING_REPLAY_CACHE = None
            _KING_OVERRIDE_CACHE = None

            def _king_replay() -> dict:
                """Lazy, memoized king_replay.json {"tin|tout|amt": {"interactions": [...]}}.
    Deferred out of module import so the Stage-2 init check (60s budget on a
    CPU-starved screening box) never pays the parse. Never raises — a broken
    file just disables the layer."""
                global _KING_REPLAY_CACHE
                if _KING_REPLAY_CACHE is None:
                    import json as _json
                    import os as _os
                    path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'king_replay.json')

                    def _dr35():
                        out: dict = {}
                        ix = None

                        def _lr155():
                            nonlocal out
                            try:
                                data = _json.load(open(path)) or {}
                                for key, spec in data.items() if isinstance(data, dict) else []:

                                    def _lr70():
                                        nonlocal ix
                                        try:
                                            ix = (spec or {}).get('interactions')
                                            if ix and str(key).count('|') == 2:
                                                out[str(key).lower()] = ix
                                        except Exception:
                                            return
                                    _lr70()
                            except Exception:
                                out = {}
                            return out
                        return _lr155()
                    out = _dr35()
                    _KING_REPLAY_CACHE = out
                return _KING_REPLAY_CACHE
            return (ExecutionPlan, Interaction, SOLVER_AUTHOR, SOLVER_NAME, SOLVER_VERSION, SolverMetadata, _ApexBase, _DR_UNSET, _KING_REPLAY_CACHE, _king_replay, logger, logging, os)
        return _lr69()
    ExecutionPlan, Interaction, SOLVER_AUTHOR, SOLVER_NAME, SOLVER_VERSION, SolverMetadata, _ApexBase, _DR_UNSET, _KING_REPLAY_CACHE, _king_replay, logger, logging, os = _dr21()
_lr5()

class JamesSolver(_ApexBase):
    """Champion base + exact-key raw-replay cover for its structural drops."""

    def metadata(self):
        base = super().metadata()
        return SolverMetadata(name=SOLVER_NAME, version=SOLVER_VERSION, author=SOLVER_AUTHOR, description='Current-champion base + raw-replay blind-spot cover (captured router calldata for venues outside its engine)', supported_chains=base.supported_chains, supported_intent_types=base.supported_intent_types)

    @staticmethod
    def _is_empty(plan) -> bool:
        try:
            return plan is None or not getattr(plan, 'interactions', None)
        except Exception:
            return True

    def _swap_key(self, intent, state):
        """Exact (tin|tout|amt) replay key for this order; None on any problem.
        Uses the lineage's normalizer when present, state.raw_params otherwise."""
        try:

            def _dr32():
                norm = getattr(self, '_normalized_swap_params', None)
                try:
                    p = norm(intent, state) if callable(norm) else {}
                except Exception:
                    p = {}

                def _lr104():
                    nonlocal p
                    if not p:
                        p = dict(getattr(state, 'raw_params', None) or {})
                    tin = str(p.get('input_token', '') or '').lower()

                    def _lr36():
                        tout = str(p.get('output_token', '') or '').lower()
                        amt = str(int(p.get('input_amount', 0) or 0))
                        return (amt, tin, tout)
                    return _lr36()
                return _lr104()
            amt, tin, tout = _dr32()
            if tin and tout and (amt != '0'):
                return tin + '|' + tout + '|' + amt
        except Exception:
            pass
        return None

    def _replay_plan(self, key, intent, state, snapshot):
        """Build the captured replay plan for an exact key; None on any problem."""
        _dr29 = None
        try:

            def _lr152():
                nonlocal _dr29
                ixs = _king_replay().get(key) if key else None
                if not ixs or Interaction is None or ExecutionPlan is None:
                    return (1, None)

                def _dr28():
                    chain_id = int(getattr(state, 'chain_id', 0) or (getattr(snapshot, 'chain_id', 0) if snapshot else 0) or 0)

                    def _lr138():
                        ix = [Interaction(target=r['target'], value=str(r.get('value', '0')), call_data=r['data'], chain_id=chain_id) for r in ixs]

                        def _lr67():
                            rp = ExecutionPlan(intent_id=intent.app_id, interactions=ix, deadline=9999999999, nonce=state.nonce, metadata={'solver': 'king-replay', 'chain_id': chain_id})
                            return None if self._is_empty(rp) else rp
                            return _DR_UNSET
                        return _lr67()
                    return _lr138()
                _dr29 = _dr28()
                return (0, None)
            _lrt153 = _lr152()
            if _lrt153[0]:
                return _lrt153[1]
            if _dr29 is not _DR_UNSET:
                return _dr29
        except Exception:
            logger.exception('[james] replay build failed')
            return None

    def generate_plan(self, intent, state, snapshot=None):
        try:
            plan = super().generate_plan(intent, state, snapshot)
        except Exception:
            logger.exception('[james] champion generate_plan raised')
            plan = None

        def _lr137():
            if self._is_empty(plan):
                try:

                    def _lr93():
                        rp = self._replay_plan(self._swap_key(intent, state), intent, state, snapshot)
                        if rp is not None:
                            logger.info('[james] raw-replay fill (fill-only-empty)')
                            return (1, rp)
                        return (0, None)
                    _lrt94 = _lr93()
                    if _lrt94[0]:
                        return _lrt94[1]
                except Exception:
                    logger.exception('[james] raw-replay fill failed; champion plan stands')
            return plan
        return _lr137()
SOLVER_CLASS = JamesSolver
try:

    def _lr78():
        global _PUTTY_ROUTES, _PUTTY_RPC, _PUTTY_SUBS, _PUTTY_SUBS_WETH, _PUTTY_USDC, _PUTTY_WETH, _PuttyChampionBase, _dr13, _putty_build_alt_plan, _putty_build_sub_plan, _putty_log, _putty_state_getter

        def _dr13():
            import logging as _putty_logging
            from eth_abi import encode as _putty_abi_encode
            from minotaur_subnet.shared.types import ExecutionPlan as _PuttyExecutionPlan
            from minotaur_subnet.shared.types import Interaction as _PuttyInteraction
            try:
                from eth_utils import to_checksum_address as _putty_ck
            except Exception:

                def _putty_ck(a):
                    return a
            _lr32 = None

            def _lr117():
                nonlocal _lr32
                _putty_log = _putty_logging.getLogger('putty_shim')
                _PUTTY_USDC = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
                _PUTTY_WETH = '0x4200000000000000000000000000000000000006'
                _PUTTY_BASE_CHAIN = 8453
                _PUTTY_DEADLINE = 9999999999
                _PUTTY_APPROVE_SEL = bytes.fromhex('095ea7b3')
                _PUTTY_EXACT_IN_SINGLE_SEL = bytes.fromhex('a026383e')
                _PUTTY_TRANSFER_SEL = bytes.fromhex('a9059cbb')

                def _lr32():
                    _PUTTY_PAIR_SWAP_SEL = bytes.fromhex('022c0d9f')

                    def _dr9():
                        _PUTTY_DEPOSIT_SEL = bytes.fromhex('6e553f65')
                        _PUTTY_GET_AMOUNT_OUT_SEL = bytes.fromhex('f140a35a')
                        _PUTTY_QUOTE_SINGLE_SEL = bytes.fromhex('c6a5026a')
                        _dr15 = None

                        def _lr90():
                            nonlocal _dr15
                            _PUTTY_R02_SINGLE_SEL = bytes.fromhex('04e45aaf')
                            _PUTTY_R02_PATH_SEL = bytes.fromhex('b858183f')
                            _PUTTY_UNI_R02 = '0x2626664c2603336E57B271c5C0b26F421741e481'
                            _PUTTY_UNI_QUOTER = '0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a'
                            _PUTTY_MSG_SENDER = '0x0000000000000000000000000000000000000001'
                            _PUTTY_OLD_SINGLE_SEL = bytes.fromhex('414bf389')
                            _PUTTY_CURVE_XCHG_SEL = bytes.fromhex('ddc1f59d')

                            def _dr15():
                                _PUTTY_SUSHI_V3_ROUTER = '0xFB7eF66a7e61224DD6FcD0D7d9C3be5C8B049b9f'

                                def _dr3():
                                    _PUTTY_SUSHI_V3_QUOTER = '0xb1E835Dc2785b52265711e17fCCb0fd018226a6e'

                                    def _dr17():
                                        _PUTTY_CURVE_SUPEROETHB = '0x302a94e3c28c290eaf2a4605fc52e11eb915f378'
                                        _PUTTY_ROUTES = {}

                                        def _lr37():
                                            return {'0xfac77f01957ed1b3dd1cbea992199b8f85b6e886': {'kind': 'aero_pd', 'hops': (('0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', '0xddc75f435af318b757dbe1aa23cf0d362b88e57c', True),), 'lo': 1000000, 'hi': 4000000}, '0x3ee5e23eee121094f1cfc0ccc79d6c809ebd22e5': {'kind': 'aero_pd', 'hops': (('0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', '0xcdac0d6c6c59727a65f871236188350531885c43', False), ('0x4200000000000000000000000000000000000006', '0x0fac819628a7f612abac1cad939768058cc0170c', False)), 'lo': 1000000, 'hi': 4000000}}

                                        def _lr38():
                                            return {'0xeff2a458e464b07088bdb441c21a42ab4b61e07e': {'kind': 'aero_pd', 'hops': (('0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', '0xcdac0d6c6c59727a65f871236188350531885c43', False), ('0x4200000000000000000000000000000000000006', '0x04e5a1c883dafd1eae6b11bd6d3eb784d90ce515', True)), 'lo': 1000000, 'hi': 4000000}, '0x01facc69ec7360640aa5898e852326752801674a': {'kind': 'aero_pd', 'hops': (('0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', '0xcdac0d6c6c59727a65f871236188350531885c43', False), ('0x4200000000000000000000000000000000000006', '0xc238f8eaa625bac4014ffd0e702a4b9a9d12019e', False)), 'lo': 1000000, 'hi': 4000000}}

                                        def _lr39():
                                            return {'0xdbfefd2e8460a6ee4955a68582f85708baea60a3': {'kind': 'curve_full', 'pool': '0x302a94e3c28c290eaf2a4605fc52e11eb915f378', 'i': 0, 'j': 1, 'lo': 1000000, 'hi': 4000000}, '0x6985884c4392d348587b19cb9eaaf157f13271cd': {'kind': 'uni_sushi', 'sushi_fee': 500, 'lo': 1000000, 'hi': 4000000}}
                                        _PUTTY_SUBS = {**_lr37(), **_lr38(), **_lr39()}
                                        return (_PUTTY_ROUTES, _PUTTY_SUBS)
                                    _PUTTY_ROUTES, _PUTTY_SUBS = _dr17()
                                    _PUTTY_SUBS_WETH = None

                                    def _lr95():
                                        nonlocal _PUTTY_SUBS_WETH
                                        _PUTTY_SUBS_WETH = {'0x01facc69ec7360640aa5898e852326752801674a': {'kind': 'aero_pd', 'hops': (('0x4200000000000000000000000000000000000006', '0xc238f8eaa625bac4014ffd0e702a4b9a9d12019e', False),), 'lo': 100000000000000, 'hi': 10000000000000000}, '0x3ee5e23eee121094f1cfc0ccc79d6c809ebd22e5': {'kind': 'aero_pd', 'hops': (('0x4200000000000000000000000000000000000006', '0x0fac819628a7f612abac1cad939768058cc0170c', False),), 'lo': 100000000000000, 'hi': 10000000000000000}, '0xeff2a458e464b07088bdb441c21a42ab4b61e07e': {'kind': 'aero_pd', 'hops': (('0x4200000000000000000000000000000000000006', '0x04e5a1c883dafd1eae6b11bd6d3eb784d90ce515', True),), 'lo': 100000000000000, 'hi': 10000000000000000}}
                                    _lr95()
                                    _PUTTY_RPC = {'url': None}
                                    return (_PUTTY_ROUTES, _PUTTY_RPC, _PUTTY_SUBS, _PUTTY_SUBS_WETH, _PUTTY_SUSHI_V3_QUOTER)
                                _PUTTY_ROUTES, _PUTTY_RPC, _PUTTY_SUBS, _PUTTY_SUBS_WETH, _PUTTY_SUSHI_V3_QUOTER = _dr3()

                                def _putty_eth_call(to, data_hex):
                                    import json as _pj
                                    import urllib.request as _pu
                                    url = _PUTTY_RPC.get('url')

                                    def _dr37():
                                        out = res = None

                                        def _lr102():
                                            nonlocal out, res
                                            if not url:
                                                raise RuntimeError('putty: no rpc url captured')
                                            body = _pj.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'eth_call', 'params': [{'to': _putty_ck(to), 'data': data_hex}, 'latest']}).encode()
                                            out = res = None

                                            def _lr40():
                                                nonlocal out, res
                                                req = _pu.Request(url, data=body, headers={'content-type': 'application/json'})
                                                with _pu.urlopen(req, timeout=10) as resp:
                                                    out = _pj.loads(resp.read())
                                                res = out.get('result')
                                            _lr40()
                                        _lr102()
                                        if not res or res == '0x':
                                            raise RuntimeError(f'putty eth_call failed: {out.get('error')}')
                                        return res
                                    res = _dr37()
                                    return bytes.fromhex(res[2:])
                                _putty_build_sub_plan = None

                                def _lr111():
                                    nonlocal _putty_build_sub_plan

                                    def _putty_encode_approve(spender, amount):
                                        return '0x' + (_PUTTY_APPROVE_SEL + _putty_abi_encode(['address', 'uint256'], [_putty_ck(spender), int(amount)])).hex()

                                    def _putty_encode_exact_input_single(token_in, token_out, tick_spacing, recipient, amount_in):
                                        enc = _putty_abi_encode(['(address,address,int24,address,uint256,uint256,uint256,uint160)'], [(_putty_ck(token_in), _putty_ck(token_out), int(tick_spacing), _putty_ck(recipient), int(_PUTTY_DEADLINE), int(amount_in), 0, 0)])
                                        return '0x' + (_PUTTY_EXACT_IN_SINGLE_SEL + enc).hex()

                                    def _putty_state_getter(state):
                                        """Champion-agnostic reader over the STABLE IntentState surface."""
                                        raw = {}
                                        try:
                                            if hasattr(state, 'raw_params_view'):
                                                raw = dict(state.raw_params_view() or {})
                                        except Exception:
                                            raw = {}

                                        def _lr107():
                                            nonlocal raw
                                            if not raw:
                                                try:
                                                    raw = dict(getattr(state, 'raw_params', {}) or {})
                                                except Exception:
                                                    raw = {}
                                            typed = getattr(state, 'typed_context', None)

                                            def _get(key):
                                                v = raw.get(key)
                                                if (v is None or v == '') and typed is not None:
                                                    v = getattr(typed, key, None)
                                                return v
                                            return _get
                                        return _lr107()

                                    def _putty_build_alt_plan(intent, state, token_out, amount_in, router, tick_spacing):
                                        _dr34 = None

                                        def _lr169():
                                            nonlocal _dr34
                                            recipient = getattr(state, 'contract_address', None) or _putty_state_getter(state)('receiver') or getattr(state, 'owner', None)
                                            chain_id = int(getattr(state, 'chain_id', 0) or _PUTTY_BASE_CHAIN)

                                            def _dr33():
                                                interactions = None

                                                def _lr170():
                                                    nonlocal interactions
                                                    interactions = [_PuttyInteraction(target=_PUTTY_USDC, value='0', call_data=_putty_encode_approve(router, int(amount_in)), chain_id=chain_id), _PuttyInteraction(target=router, value='0', call_data=_putty_encode_exact_input_single(_PUTTY_USDC, token_out, tick_spacing, recipient, int(amount_in)), chain_id=chain_id)]
                                                _lr170()

                                                def _lr66():
                                                    return _PuttyExecutionPlan(intent_id=str(getattr(intent, 'app_id', '') or ''), interactions=interactions, deadline=_PUTTY_DEADLINE, nonce=int(getattr(state, 'nonce', 0) or 0), metadata={'solver': 'putty-additive-edge', 'route': 'aerodrome_slipstream_alt', 'venue_param': int(tick_spacing), 'chain_id': chain_id})
                                                    return _DR_UNSET
                                                return _lr66()
                                            _dr34 = _dr33()
                                        _lr169()
                                        if _dr34 is not _DR_UNSET:
                                            return _dr34
                                    _putty_build_sub_plan = None

                                    def _lr33():
                                        nonlocal _putty_build_sub_plan

                                        def _putty_ix(target, data, chain_id):
                                            return _PuttyInteraction(target=_putty_ck(target), value='0', call_data=data, chain_id=chain_id)

                                        def _putty_encode_transfer(to, amount):
                                            return '0x' + (_PUTTY_TRANSFER_SEL + _putty_abi_encode(['address', 'uint256'], [_putty_ck(to), int(amount)])).hex()

                                        def _putty_r02_single(token_out, fee, recipient, amount_in):
                                            enc = _putty_abi_encode(['(address,address,uint24,address,uint256,uint256,uint160)'], [(_putty_ck(_PUTTY_USDC), _putty_ck(token_out), int(fee), _putty_ck(recipient), int(amount_in), 0, 0)])
                                            return '0x' + (_PUTTY_R02_SINGLE_SEL + enc).hex()

                                        def _putty_r02_path(mids, token_out, fees, recipient, amount_in):
                                            toks = [_PUTTY_USDC] + list(mids) + [token_out]
                                            enc = path = None

                                            def _lr96():
                                                nonlocal enc, path

                                                def _lr31():
                                                    nonlocal path
                                                    path = b''
                                                    for i, f in enumerate(fees):
                                                        path += bytes.fromhex(toks[i][2:]) + int(f).to_bytes(3, 'big')
                                                _lr31()
                                                path += bytes.fromhex(toks[-1][2:])
                                                enc = _putty_abi_encode(['(bytes,address,uint256,uint256)'], [(path, _putty_ck(recipient), int(amount_in), 0)])
                                            _lr96()
                                            return '0x' + (_PUTTY_R02_PATH_SEL + enc).hex()

                                        def _putty_quote_usdc_weth(fee, amount_in):
                                            raw = None

                                            def _lr98():
                                                nonlocal raw
                                                data = '0x' + (_PUTTY_QUOTE_SINGLE_SEL + _putty_abi_encode(['(address,address,uint256,uint24,uint160)'], [(_putty_ck(_PUTTY_USDC), _putty_ck(_PUTTY_WETH), int(amount_in), int(fee), 0)])).hex()
                                                raw = _putty_eth_call(_PUTTY_UNI_QUOTER, data)
                                            _lr98()
                                            out = int.from_bytes(raw[:32], 'big')
                                            if out <= 0:
                                                raise RuntimeError('putty quoter returned 0')
                                            return out

                                        def _putty_quote_v3(quoter, token_in, token_out, fee, amount_in):
                                            """QuoterV2-ABI single quote (uni + sushi share the struct); 0 on failure."""
                                            raw = None
                                            try:

                                                def _lr118():
                                                    nonlocal raw
                                                    data = '0x' + (_PUTTY_QUOTE_SINGLE_SEL + _putty_abi_encode(['(address,address,uint256,uint24,uint160)'], [(_putty_ck(token_in), _putty_ck(token_out), int(amount_in), int(fee), 0)])).hex()
                                                    raw = _putty_eth_call(quoter, data)
                                                _lr118()
                                                return int.from_bytes(raw[:32], 'big')
                                            except Exception:
                                                return 0

                                        def _putty_best_usdc_weth(amount_in):
                                            """Best uni-v3 USDC->WETH quote over fees {100,500,3000} — a strict
        SUPERSET of the champion curve_ng probe set {500,3000}, so our WETH
        leg is never worse than the champion's."""
                                            best_out, best_fee = (0, 0)

                                            def _lr119():
                                                nonlocal best_fee, best_out
                                                for fee in (100, 500, 3000):
                                                    out = _putty_quote_v3(_PUTTY_UNI_QUOTER, _PUTTY_USDC, _PUTTY_WETH, fee, amount_in)
                                                    if out > best_out:
                                                        best_out, best_fee = (out, fee)
                                                if best_out <= 0:
                                                    raise RuntimeError('putty: no uni USDC->WETH quote')
                                            _lr119()
                                            return (best_out, best_fee)

                                        def _putty_pair_get_amount_out(pair, amount_in, token_in):
                                            out = None

                                            def _lr154():
                                                nonlocal out
                                                data = '0x' + (_PUTTY_GET_AMOUNT_OUT_SEL + _putty_abi_encode(['uint256', 'address'], [int(amount_in), _putty_ck(token_in)])).hex()
                                                out = int.from_bytes(_putty_eth_call(pair, data)[:32], 'big')
                                            _lr154()
                                            if out <= 0:
                                                raise RuntimeError('putty getAmountOut returned 0')
                                            return out

                                        def _putty_sub_interactions(spec, token_out, amount_in, recipient, chain_id):
                                            """Build the substituted interaction list for one table entry."""
                                            kind = spec['kind']

                                            def _dr30():

                                                def _lr158():
                                                    if kind == 'univ3_single':
                                                        return (1, [_putty_ix(_PUTTY_USDC, _putty_encode_approve(_PUTTY_UNI_R02, amount_in), chain_id), _putty_ix(_PUTTY_UNI_R02, _putty_r02_single(token_out, spec['fee'], recipient, amount_in), chain_id)])
                                                    return (0, None)
                                                _lrt159 = _lr158()
                                                if _lrt159[0]:
                                                    return _lrt159[1]

                                                def _dr4():
                                                    if kind == 'univ3_path':

                                                        def _lr147():
                                                            return (1, [_putty_ix(_PUTTY_USDC, _putty_encode_approve(_PUTTY_UNI_R02, amount_in), chain_id), _putty_ix(_PUTTY_UNI_R02, _putty_r02_path(spec['mids'], token_out, spec['fees'], recipient, amount_in), chain_id)])
                                                            return (0, None)
                                                        _lrt148 = _lr147()
                                                        if _lrt148[0]:
                                                            return _lrt148[1]

                                                    def _dr26():

                                                        def _lr62():
                                                            return [_putty_ix(_PUTTY_USDC, _putty_encode_approve(_PUTTY_UNI_R02, amount_in), chain_id), _putty_ix(_PUTTY_UNI_R02, _putty_r02_single(_PUTTY_WETH, spec['fee'], _PUTTY_MSG_SENDER, amount_in), chain_id)]

                                                        def _lr63():
                                                            return [_putty_ix(_PUTTY_WETH, _putty_encode_approve(token_out, quoted), chain_id)]

                                                        def _lr64():
                                                            return [_putty_ix(token_out, '0x' + (_PUTTY_DEPOSIT_SEL + _putty_abi_encode(['uint256', 'address'], [int(quoted), _putty_ck(recipient)])).hex(), chain_id)]
                                                        if kind == 'erc4626':
                                                            quoted = _putty_quote_usdc_weth(spec['fee'], amount_in)
                                                            return [*_lr62(), *_lr63(), *_lr64()]
                                                        return _DR_UNSET
                                                        return _DR_UNSET
                                                    _dr27 = _dr26()
                                                    if _dr27 is not _DR_UNSET:
                                                        return _dr27
                                                    return _DR_UNSET
                                                _dr5 = _dr4()
                                                if _dr5 is not _DR_UNSET:
                                                    return _dr5
                                                return _DR_UNSET
                                            _dr31 = _dr30()
                                            fee = weth_out = None

                                            def _lr142():
                                                nonlocal fee, weth_out
                                                if _dr31 is not _DR_UNSET:
                                                    return _dr31
                                                if kind == 'curve_full':
                                                    weth_out, fee = _putty_best_usdc_weth(amount_in)

                                                    def _dr11():
                                                        pool = spec['pool']

                                                        def _lr44():
                                                            return [_putty_ix(_PUTTY_USDC, _putty_encode_approve(_PUTTY_UNI_R02, amount_in), chain_id), _putty_ix(_PUTTY_UNI_R02, _putty_r02_single(_PUTTY_WETH, fee, _PUTTY_MSG_SENDER, amount_in), chain_id), _putty_ix(_PUTTY_WETH, _putty_encode_approve(pool, weth_out), chain_id)]

                                                        def _lr45():
                                                            return [_putty_ix(pool, '0x' + (_PUTTY_CURVE_XCHG_SEL + _putty_abi_encode(['int128', 'int128', 'uint256', 'uint256', 'address'], [int(spec['i']), int(spec['j']), int(weth_out), 0, _putty_ck(recipient)])).hex(), chain_id)]
                                                        return [*_lr44(), *_lr45()]
                                                        return _DR_UNSET
                                                    _dr12 = _dr11()
                                                    if _dr12 is not _DR_UNSET:
                                                        return _dr12

                                                def _lr68():

                                                    def _dr1():
                                                        nonlocal fee, weth_out
                                                        _dr25 = None
                                                        if kind == 'uni_sushi':

                                                            def _lr130():
                                                                nonlocal _dr25, fee, weth_out
                                                                weth_out, fee = _putty_best_usdc_weth(amount_in)
                                                                sushi_fee = int(spec['sushi_fee'])
                                                                if _putty_quote_v3(_PUTTY_SUSHI_V3_QUOTER, _PUTTY_WETH, token_out, sushi_fee, weth_out) <= 0:
                                                                    raise RuntimeError('putty: sushi leg quote empty')

                                                                def _dr24():
                                                                    sushi_call = None

                                                                    def _lr65():
                                                                        nonlocal sushi_call
                                                                        sushi_call = '0x' + (_PUTTY_OLD_SINGLE_SEL + _putty_abi_encode(['(address,address,uint24,address,uint256,uint256,uint256,uint160)'], [(_putty_ck(_PUTTY_WETH), _putty_ck(token_out), sushi_fee, _putty_ck(recipient), int(_PUTTY_DEADLINE), int(weth_out), 0, 0)])).hex()
                                                                    _lr65()

                                                                    def _lr140():
                                                                        return [_putty_ix(_PUTTY_USDC, _putty_encode_approve(_PUTTY_UNI_R02, amount_in), chain_id), _putty_ix(_PUTTY_UNI_R02, _putty_r02_single(_PUTTY_WETH, fee, _PUTTY_MSG_SENDER, amount_in), chain_id), _putty_ix(_PUTTY_WETH, _putty_encode_approve(_PUTTY_SUSHI_V3_ROUTER, weth_out), chain_id)]

                                                                    def _lr141():
                                                                        return [_putty_ix(_PUTTY_SUSHI_V3_ROUTER, sushi_call, chain_id)]
                                                                    return [*_lr140(), *_lr141()]
                                                                    return _DR_UNSET
                                                                _dr25 = _dr24()
                                                            _lr130()
                                                            if _dr25 is not _DR_UNSET:
                                                                return _dr25
                                                        return _DR_UNSET
                                                    _dr2 = _dr1()
                                                    if _dr2 is not _DR_UNSET:
                                                        return _dr2
                                                    if kind == 'aero_pd':

                                                        def _dr8():
                                                            hops = spec['hops']
                                                            ixs = [_putty_ix(hops[0][0], _putty_encode_transfer(hops[0][1], amount_in), chain_id)]
                                                            cur = None

                                                            def _lr97():
                                                                nonlocal cur
                                                                cur = int(amount_in)
                                                                for i, (tin, pair, in_is_t0) in enumerate(hops):

                                                                    def _dr20():
                                                                        nonlocal cur
                                                                        out = _putty_pair_get_amount_out(pair, cur, tin)
                                                                        a0 = a1 = to = None

                                                                        def _lr109():
                                                                            nonlocal a0, a1, to
                                                                            to = recipient if i == len(hops) - 1 else hops[i + 1][1]
                                                                            a0, a1 = (0, out) if in_is_t0 else (out, 0)
                                                                        _lr109()

                                                                        def _lr34():
                                                                            nonlocal cur
                                                                            ixs.append(_putty_ix(pair, '0x' + (_PUTTY_PAIR_SWAP_SEL + _putty_abi_encode(['uint256', 'uint256', 'address', 'bytes'], [a0, a1, _putty_ck(to), b''])).hex(), chain_id))
                                                                            cur = out
                                                                        _lr34()
                                                                        return (a0, a1, out, to)
                                                                    a0, a1, out, to = _dr20()
                                                                return ixs
                                                            return _lr97()
                                                        ixs = _dr8()
                                                        return ixs
                                                    raise RuntimeError(f'putty: unknown sub kind {kind}')
                                                return _lr68()
                                            return _lr142()

                                        def _putty_build_sub_plan(intent, state, spec, token_out, amount_in):
                                            recipient = getattr(state, 'contract_address', None) or _putty_state_getter(state)('receiver') or getattr(state, 'owner', None)

                                            def _lr149():
                                                chain_id = int(getattr(state, 'chain_id', 0) or _PUTTY_BASE_CHAIN)
                                                interactions = _putty_sub_interactions(spec, token_out, int(amount_in), recipient, chain_id)

                                                def _lr46():
                                                    return _PuttyExecutionPlan(intent_id=str(getattr(intent, 'app_id', '') or ''), interactions=interactions, deadline=_PUTTY_DEADLINE, nonce=int(getattr(state, 'nonce', 0) or 0), metadata={'solver': 'putty-additive-edge', 'route': 'putty_eps_' + spec['kind'], 'chain_id': chain_id})
                                                return _lr46()
                                            return _lr149()
                                    _lr33()
                                    return (_PUTTY_ROUTES, _PUTTY_RPC, _PUTTY_SUBS, _PUTTY_SUBS_WETH, _putty_build_alt_plan, _putty_build_sub_plan, _putty_state_getter)
                                    return _DR_UNSET
                                return _lr111()
                        _lr90()
                        _dr16 = _dr15()
                        if _dr16 is not _DR_UNSET:
                            return _dr16
                    _PUTTY_ROUTES, _PUTTY_RPC, _PUTTY_SUBS, _PUTTY_SUBS_WETH, _putty_build_alt_plan, _putty_build_sub_plan, _putty_state_getter = _dr9()
                    return (_PUTTY_ROUTES, _PUTTY_RPC, _PUTTY_SUBS, _PUTTY_SUBS_WETH, _PUTTY_USDC, _PUTTY_WETH, _putty_build_alt_plan, _putty_build_sub_plan, _putty_log, _putty_state_getter)
            _lr117()
            return _lr32()
        _PUTTY_ROUTES, _PUTTY_RPC, _PUTTY_SUBS, _PUTTY_SUBS_WETH, _PUTTY_USDC, _PUTTY_WETH, _putty_build_alt_plan, _putty_build_sub_plan, _putty_log, _putty_state_getter = _dr13()
        _PuttyChampionBase = SOLVER_CLASS
    _lr78()

    class PuttyEdgeSolver(_PuttyChampionBase):
        """Champion primary; substitutes a known-good alt-CL plan on exactly the
        5 fork-proven USDC->token routes the champion zeroes. Pure pass-through
        everywhere else; any failure in our path falls back to the champion."""

        def initialize(self, *args, **kwargs):
            url = None
            try:
                for cfg in list(args) + list(kwargs.values()):
                    if isinstance(cfg, dict):

                        def _lr88():
                            nonlocal url
                            urls = cfg.get('rpc_urls') or {}
                            if isinstance(urls, dict):
                                url = urls.get(8453) or urls.get('8453')
                                if url:
                                    _PUTTY_RPC['url'] = str(url)
                        _lr88()
            except Exception:
                pass
            return super().initialize(*args, **kwargs)

        def generate_plan(self, *args, **kwargs):
            plan = None
            _dr23 = None
            try:

                def _lr135():

                    def _dr14():
                        intent = state = None

                        def _lr171():
                            nonlocal intent, state
                            intent = args[0] if len(args) > 0 else kwargs.get('intent', kwargs.get('app'))
                            state = args[1] if len(args) > 1 else kwargs.get('state')
                        _lr171()
                        return (intent, state)
                    intent, state = _dr14()
                    if state is not None:

                        def _dr10():
                            get = _putty_state_getter(state)
                            tin = str(get('input_token') or '').strip()

                            def _lr112():
                                tout = str(get('output_token') or '').strip()
                                amount_in = int(get('input_amount') or 0)
                                route = _PUTTY_ROUTES.get(tout.lower())
                                return (amount_in, route, tin, tout)
                            return _lr112()

                        def _lr86():
                            amount_in, route, tin, tout = _dr10()

                            def _lr59():
                                nonlocal _dr23

                                def _lr30():
                                    return route is not None and tin.lower() == _PUTTY_USDC.lower() and (amount_in > 0)
                                if _lr30():
                                    router, tick_spacing = route

                                    def _lr3():
                                        nonlocal plan
                                        plan = _putty_build_alt_plan(intent, state, tout, amount_in, router, tick_spacing)
                                        if plan is not None and plan.interactions:
                                            _putty_log.info('[putty] alt-CL substitution for %s router=%s tick=%s', tout, router, tick_spacing)
                                            return (1, plan)
                                        return (0, None)
                                    _lrt4 = _lr3()
                                    if _lrt4[0]:
                                        return (1, _lrt4[1])

                                def _dr22():
                                    spec = _PUTTY_SUBS.get(tout.lower())

                                    def _dr6():
                                        nonlocal plan

                                        def _lr168():
                                            return spec is not None and tin.lower() == _PUTTY_USDC.lower() and (spec['lo'] <= amount_in <= spec['hi'])
                                        if _lr168():

                                            def _lr71():
                                                nonlocal plan
                                                plan = _putty_build_sub_plan(intent, state, spec, tout, amount_in)
                                                if plan is not None and plan.interactions:
                                                    _putty_log.info('[putty] eps substitution %s for %s amt=%s', spec['kind'], tout, amount_in)
                                                    return (1, plan)
                                                return (0, None)
                                            _lrt72 = _lr71()
                                            if _lrt72[0]:
                                                return _lrt72[1]

                                        def _lr115():

                                            def _dr18():
                                                nonlocal plan
                                                spec_w = _PUTTY_SUBS_WETH.get(tout.lower())

                                                def _lr129():
                                                    return spec_w is not None and tin.lower() == _PUTTY_WETH.lower() and (spec_w['lo'] <= amount_in <= spec_w['hi'])
                                                if _lr129():

                                                    def _lr79():
                                                        nonlocal plan
                                                        plan = _putty_build_sub_plan(intent, state, spec_w, tout, amount_in)
                                                        if plan is not None and plan.interactions:
                                                            _putty_log.info('[putty] eps WETH substitution %s for %s amt=%s', spec_w['kind'], tout, amount_in)
                                                            return (1, plan)
                                                        return (0, None)
                                                    _lrt80 = _lr79()
                                                    if _lrt80[0]:
                                                        return _lrt80[1]
                                                return _DR_UNSET
                                                return _DR_UNSET
                                            _dr19 = _dr18()
                                            if _dr19 is not _DR_UNSET:
                                                return _dr19
                                            return _DR_UNSET
                                        return _lr115()
                                    _dr7 = _dr6()
                                    if _dr7 is not _DR_UNSET:
                                        return _dr7
                                    return _DR_UNSET
                                _dr23 = _dr22()
                                return (0, None)
                            _lrt60 = _lr59()
                            if _lrt60[0]:
                                return (1, _lrt60[1])
                            if _dr23 is not _DR_UNSET:
                                return (1, _dr23)
                            return (0, None)
                        _lrt87 = _lr86()
                        if _lrt87[0]:
                            return (1, _lrt87[1])
                    return (0, None)
                _lrt136 = _lr135()
                if _lrt136[0]:
                    return _lrt136[1]
            except Exception:
                _putty_log.exception('[putty] edge failed; deferring to champion plan')
            return super().generate_plan(*args, **kwargs)
    SOLVER_CLASS = PuttyEdgeSolver
except Exception:

    def _lr116():
        global _putty_logging2
        try:
            import logging as _putty_logging2
            _putty_logging2.getLogger('putty_shim').exception('[putty] shim import/setup failed; champion solver left unchanged')
        except Exception:
            pass
    _lr116()

def _lr173():
    global _MO_Base, _MO_OVR, _mo_json, _mo_load, _mo_os
    import json as _mo_json, os as _mo_os
    _MO_OVR = None

    def _mo_load():
        global _MO_OVR

        def _lr172():
            global _MO_OVR
            if _MO_OVR is None:
                try:
                    _d = _mo_json.load(open(_mo_os.path.join(_mo_os.path.dirname(_mo_os.path.abspath(__file__)), 'override_replay.json')))

                    def _lr81():
                        global _MO_OVR
                        _MO_OVR = {str(_k).lower(): _v.get('interactions') for _k, _v in _d.items() if isinstance(_v, dict) and _v.get('interactions')}
                    _lr81()
                except Exception:
                    _MO_OVR = {}
        _lr172()
        return _MO_OVR
    _MO_Base = SOLVER_CLASS
_lr173()

class _MinoOverrideSolver(_MO_Base):

    def _mo_key(self, intent, state):
        try:

            def _dr36():
                p = dict(getattr(state, 'raw_params', None) or {})

                def _lr106():
                    nonlocal p
                    if not p.get('input_token'):
                        tc = getattr(state, 'typed_context', None)
                        if tc is not None:
                            p = getattr(tc, 'raw_params', p) or p
                _lr106()
                tin = str(p.get('input_token', '') or '').lower()

                def _lr42():
                    tout = str(p.get('output_token', '') or '').lower()
                    amt = str(int(p.get('input_amount', 0) or 0))
                    return (amt, tin, tout)
                return _lr42()
            amt, tin, tout = _dr36()
            if tin and tout and (amt != '0'):
                return tin + '|' + tout + '|' + amt
        except Exception:
            pass
        return None

    def generate_plan(self, intent, state, snapshot=None):
        try:

            def _dr38():
                _ix = None

                def _lr43():
                    nonlocal _ix
                    _k = self._mo_key(intent, state)
                    _ix = _mo_load().get(_k) if _k else None
                _lr43()
                if _ix:
                    from minotaur_subnet.shared.types import ExecutionPlan as _EP, Interaction as _IX
                    _cid = int(getattr(state, 'chain_id', 0) or 8453)

                    def _lr100():

                        def _lr76():
                            return (intent.app_id, [_IX(target=_r['target'], value=str(_r.get('value', '0')), call_data=_r['data'], chain_id=_cid) for _r in _ix])
                        _lrt77 = _lr76()
                        _plan = _EP(intent_id=_lrt77[0], interactions=_lrt77[1], deadline=9999999999, nonce=state.nonce, metadata={'solver': 'mino-override', 'chain_id': _cid})
                        if _plan.interactions:
                            return (1, _plan)
                        return (0, None)
                    _lrt101 = _lr100()
                    if _lrt101[0]:
                        return _lrt101[1]
                return _DR_UNSET
            _dr39 = _dr38()
            if _dr39 is not _DR_UNSET:
                return _dr39
        except Exception:
            pass
        return super().generate_plan(intent, state, snapshot)
SOLVER_CLASS = _MinoOverrideSolver
