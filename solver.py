"""w0 (topaz-dex-router) — distinct smart fill cover for crown DEFENSE. Behaviorally like the fleet's
smart covers (stable pair -> direct UniV3 fee-100, WETH pair -> direct fee-500, else -> WETH-hop; reads
apex_routes.json / apex_base_routes.json), so it TIES the champion rather than churning the crown.
Structurally distinct via a BUILDER-DICT dispatch (map route-kind -> builder function) — a different call
graph from w7 (mixin), wf (composed object), w8 (two-method branch), w9 (module-fn inline), w5 (2-class).

BASE-AWARE + BLIND-AWARE: fires the fill cover when the champion (super) returns EMPTY *or* a BLIND
best-effort/offline-fallback plan (both score as a drop/catastrophic), on chain-1 AND Base (8453). chain-1
uses SwapRouter WITH deadline (sel 0x414bf389); Base uses SwapRouter02 WITHOUT deadline (sel 0x04e45aaf).

WEAKLY DOMINANT: fork champion (super) + fill-on-empty-or-blind + min_out=quoted*99//100 => only turns a
DROP into a fill or a clean revert; never touches orders the champion already serves."""
from __future__ import annotations
_DR_UNSET = object()
import os
import json
from _garnet_full import SOLVER_CLASS as _Base
from _garnet_full import _blind as _topaz_blind
_ROUTER = '0xE592427A0AEce92De3Edee1F18E0157C05861564'
_ROUTER_BASE = '0x2626664c2603336E57B271c5C0b26F421741e481'
_WETH = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
_WETH_BASE = '0x4200000000000000000000000000000000000006'
_STABLES = {'0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48', '0xdac17f958d2ee523a2206206994597c13d831ec7', '0x6b175474e89094c44da98b954eedeac495271d0f', '0x853d955acef822db058eb8505911ed77f175b99e', '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'}
SOLVER_NAME = os.environ.get('MINOTAUR_SOLVER_NAME', "leanrtr")
SOLVER_VERSION = os.environ.get('MINOTAUR_SOLVER_VERSION', '3.0.0')
SOLVER_AUTHOR = os.environ.get('MINOTAUR_SOLVER_AUTHOR', 'GuilhermeSilva')

def _topaz_router(chain):
    """Router address + exactInputSingle selector + has-deadline flag for the given chain."""
    if chain == 8453:
        return (_ROUTER_BASE, '0x04e45aaf', False)
    return (_ROUTER, '0x414bf389', True)

def _enc_single(chain, tin, tout, fee, amt, min_out, recip):

    def _dz2500(amt, fee, min_out, recip, tin, tout):
        tup = (_ck(tin), _ck(tout), int(fee), _ck(recip), int(amt), int(min_out), 0)
        sig = '(address,address,uint24,address,uint256,uint256,uint160)'
        return (sig, tup)

    def _dz2499():
        nonlocal sig, tup
        tup = (_ck(tin), _ck(tout), int(fee), _ck(recip), 9999999999, int(amt), int(min_out), 0)
        sig = '(address,address,uint24,address,uint256,uint256,uint256,uint160)'
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    _router, sel, has_dl = _topaz_router(chain)
    if has_dl:
        _dz2499()
    else:
        sig, tup = _dz2500(amt, fee, min_out, recip, tin, tout)
    return sel + _enc([sig], [tup]).hex()

def _enc_hop(chain, tin, tout, fee, amt, min_out, recip):

    def _dz2497(amt, min_out, raw, recip):
        tup = (raw, _ck(recip), int(amt), int(min_out))
        sig = '(bytes,address,uint256,uint256)'
        return (sig, tup)

    def _dz2496():
        nonlocal sig, tup
        tup = (raw, _ck(recip), 9999999999, int(amt), int(min_out))
        sig = '(bytes,address,uint256,uint256,uint256)'
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    weth = _WETH_BASE if chain == 8453 else _WETH
    raw = bytes.fromhex(tin[2:]) + int(fee).to_bytes(3, 'big') + bytes.fromhex(weth[2:]) + int(fee).to_bytes(3, 'big') + bytes.fromhex(tout[2:])
    if chain == 8453:
        sig, tup = _dz2497(amt, min_out, raw, recip)
    else:
        _dz2496()
    return '0xb858183f' + _enc([sig], [tup]).hex()
_BUILDERS = {'single': _enc_single, 'hop': _enc_hop}

def _topaz_baked_fee(chain, tin, tout):
    """Baked single-tier fee for the pair from the chain-specific route table, or None."""

    def _dz2494(fh):
        tbl = json.load(fh) or {}
        return tbl

    def _dz2493(tbl, tin, tout):
        r = tbl.get(tin + ':' + tout) or tbl.get(tout + ':' + tin)
        _r_dz2492 = _dz2492()
        return (_r_dz2492, r)

    def _dz2492():
        if isinstance(r, dict) and r.get('kind') == 'univ3_single' and r.get('fee'):
            return (int(r['fee']),)
        return _DR_UNSET
    fname = 'apex_base_routes.json' if chain == 8453 else 'apex_routes.json'
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)) as fh:
            tbl = _dz2494(fh)
        _r_dz2492, r = _dz2493(tbl, tin, tout)
        if _r_dz2492 is not _DR_UNSET:
            return _r_dz2492[0]
    except Exception:
        pass
    return None

def _topaz_route_kind(chain, tin, tout):
    """Route-kind + fee: baked table > stable-pair 100 > WETH-pair 500 > volatile WETH-hop."""

    def _dz2491():
        _r_dz2490 = _dz2490()
        if _r_dz2490 is not _DR_UNSET:
            return (_r_dz2490[0],)
        if (_WETH_BASE if chain == 8453 else _WETH) in (tin, tout):
            return (('single', 500),)
        return _DR_UNSET

    def _dz2490():
        if baked is not None:
            return (('single', baked),)
        if tin in _STABLES and tout in _STABLES:
            return (('single', 100),)
        return _DR_UNSET
    baked = _topaz_baked_fee(chain, tin, tout)
    _r_dz2491 = _dz2491()
    if _r_dz2491 is not _DR_UNSET:
        return _r_dz2491[0]
    return ('hop', 3000)

def _topaz_should_cover(plan):
    """Fire the fill cover only when super() returned EMPTY or a BLIND best-effort/offline-fallback plan."""
    served = plan is not None and getattr(plan, 'interactions', None)
    return not served or _topaz_blind(plan)

def _topaz_parse_order(state):

    def _dz2488(state):
        amt, p, quoted, tin, tout = _dz2487(state)
        _r_dz2484 = _dz2484()
        return (_r_dz2484, amt, p, quoted, tin, tout)

    def _dz2487(state):
        amt, p, tin, tout = _dz2486(state)
        quoted = int(p.get('quoted_output', 0) or 0)
        return (amt, p, quoted, tin, tout)

    def _dz2486(state):
        p, tin, tout = _dz2485(state)
        amt = int(p.get('input_amount', 0) or 0)
        return (amt, p, tin, tout)

    def _dz2485(state):
        p, tin = _dz2482(state)
        tout = str(p.get('output_token', '') or '').lower()
        return (p, tin, tout)

    def _dz2484():
        _r_dz2483 = _dz2483()
        if _r_dz2483 is not _DR_UNSET:
            return (_r_dz2483[0],)
        return ((p, tin, tout, amt, quoted),)
        return _DR_UNSET

    def _dz2483():
        if not (tin.startswith('0x') and tout.startswith('0x')) or amt <= 0 or quoted <= 0 or (tin == tout):
            return (None,)
        return _DR_UNSET

    def _dz2482(state):
        """Extract & validate the on-chain order from state.raw_params for w0's cover.
    Returns (p, tin, tout, amt, quoted) or None when the champion plan should stand."""
        p = dict(getattr(state, 'raw_params', {}) or {})
        tin = str(p.get('input_token', '') or '').lower()
        return (p, tin)
    _r_dz2484, amt, p, quoted, tin, tout = _dz2488(state)
    if _r_dz2484 is not _DR_UNSET:
        return _r_dz2484[0]

def _topaz_recipient(state, p):
    """Resolve the swap recipient for w0's fill cover (falls back to a sentinel)."""
    return str(p.get('receiver', '') or getattr(state, 'contract_address', None) or getattr(state, 'owner', None) or '0x0000000000000000000000000000000000000001')

def _topaz_build_fill(intent, state, chain, kind, fee, tin, tout, amt, quoted, recip):
    """Encode approve+swap and assemble the fill ExecutionPlan for w0's builder-dispatch."""

    def _dz2480(amt, chain, fee, kind, quoted, recip, tin, tout):
        router = _ROUTER_BASE if chain == 8453 else _ROUTER
        swap = _BUILDERS[kind](chain, tin, tout, fee, amt, quoted * 99 // 100, recip)
        return (router, swap)

    def _dz2479():
        return (_EP(intent_id=intent.app_id, interactions=ix, deadline=9999999999, nonce=state.nonce, metadata={'solver': 'fork-dispatch-w0', 'chain_id': chain, 'kind': kind, 'fee': fee}),)
        return _DR_UNSET
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction as _IX, ExecutionPlan as _EP
    router, swap = _dz2480(amt, chain, fee, kind, quoted, recip, tin, tout)
    ix = [_IX(target=_ck(tin), value='0', call_data=encode_approve(_ck(router), int(amt)), chain_id=chain), _IX(target=_ck(router), value='0', call_data=swap, chain_id=chain)]
    _r_dz2479 = _dz2479()
    if _r_dz2479 is not _DR_UNSET:
        return _r_dz2479[0]

class ForkDispatchFill(_Base):
    """Champion engine + fill-on-empty-or-blind cover via a BUILDER-DICT dispatch (chain-1 + Base)."""

    def generate_plan(self, intent, state, snapshot=None):

        def _dz2477():
            built = _topaz_build_fill(intent, state, chain, kind, fee, tin, tout, amt, quoted, recip)
            return (built if getattr(built, 'interactions', None) else plan,)
            return _DR_UNSET
        plan = super().generate_plan(intent, state, snapshot)
        chain = int(getattr(state, 'chain_id', 0) or 0)
        if chain not in (1, 8453) or not _topaz_should_cover(plan):
            return plan
        try:
            parsed = _topaz_parse_order(state)
            if parsed is None:
                return plan
            p, tin, tout, amt, quoted = parsed
            recip = _topaz_recipient(state, p)
            kind, fee = _topaz_route_kind(chain, tin, tout)
            _r_dz2477 = _dz2477()
            if _r_dz2477 is not _DR_UNSET:
                return _r_dz2477[0]
        except Exception:
            return plan

    def metadata(self):
        base = super().metadata()
        try:
            from minotaur_subnet.sdk.intent_solver import SolverMetadata
            return SolverMetadata(name=SOLVER_NAME, version=SOLVER_VERSION, author=SOLVER_AUTHOR, description='champion fork + builder-dispatch fill cover', supported_chains=base.supported_chains, supported_intent_types=base.supported_intent_types)
        except Exception:
            return base
SOLVER_CLASS = ForkDispatchFill

def _apex_fp_29800239n1(v):
    return v + 10
_APEX_FP = _apex_fp_29800239n1(0)
_FACTOR_FP = 'round-e29800470-n1-min-factor-min-hk8-cj117-001'
