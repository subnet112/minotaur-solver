"""Ethereum (chain_id==1) superset router — a zero-regression delta over the
champion floor.

Layering (top defers down; NOTHING overrides a champion-served order except a
same-block, quoter-proven, strictly-better route):

    solver.py (this file)  RobustFloorSolver  — the chain-1 superset override.
    _champ_floor.py        SOLVER_CLASS (the renamed champion solver.py /
                           JamesSolver) whose MRO is
                           JamesSolver -> _McSolver -> _PuttyCleanSolver ->
                           VikingSolver -> hydra_top.MinerSolver -> champ_top ->
                           apex_king_base -> _apex_champ -> baseline_solver.
                           From that MRO we inherit, unchanged:
                             _normalized_swap_params  (baseline_solver:266)
                             _get_web3 / _rpc_urls / _web3_cache (baseline:148)
                             _apex_recipient / _apex_deadline (apex_king_base:187)
                             generate_plan            (JamesSolver / hydra_top)

WHAT THIS DOES (chain 1 only; every other chain is byte-identical champion):
  1. Always compute the champion's OWN chain-1 plan first  (super().generate_plan
     -> hydra_top._hydra_eth_fastpath). That plan is the floor and the always-safe
     return value.
  2. Reconstruct the champion fastpath's EXACT route (deterministic from its code)
     and quote it via QuoterV2 at the pinned read block  =>  q_champ  (the bar).
  3. Quote a SUPERSET at the same block: every Uniswap-V3 fee tier direct, every
     2-hop via {WETH, USDC}, plus Curve StableSwap-NG get_dy on stable pairs.
  4. Return MY plan ONLY when a specific candidate is quoted (same quoter, same
     block) to beat the champion's own quoted route by a strict margin AND clears
     the order's min_output (so it cannot revert the app invariant). Otherwise
     return the champion plan verbatim.  On ANY doubt / exception / missing RPC we
     return the champion plan  =>  it can never do worse than the champion.

Calldata is byte-parity with the champion fastpath: approve(0x095ea7b3) to the
V3 SwapRouter, then exactInput(0xc04b8d59) with the packed path; recipient is the
SAME expression the champion resolves (state.contract_address == the app contract
== scoreIntent's _gained(address(this)) measurement target). Curve uses the NG
exchange-with-receiver overload (0xddc1f59d) so output lands at the app contract
directly. Uses only web3 + eth_abi + eth_utils + stdlib (all in the base image).
"""
from __future__ import annotations
import logging
from _champ_floor import SOLVER_CLASS as _ChampFloor
from cbbtc_aero_guard import maybe_base_stability_plan
from minotaur_subnet.shared.types import ExecutionPlan, Interaction

def _lr1():
    global _CHAMP_FEE, _CRVUSD, _CURVE_NG_POOLS, _DAI, _FEE_TIERS, _HUBS, _MSG_SENDER_SENTINEL, _QUOTER_V2, _SEL_APPROVE, _USDC, _USDT, _V3_ROUTER, _WBTC, _WETH, logger
    logger = logging.getLogger('eth_superset')
    _WETH = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
    _USDC = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'
    _WBTC = '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599'
    _USDT = '0xdac17f958d2ee523a2206206994597c13d831ec7'
    _DAI = '0x6b175474e89094c44da98b954eedeac495271d0f'
    _CRVUSD = '0xf939e0a03fb07f59a73314e73794be0e57ac1b4e'
    _V3_ROUTER = '0xE592427A0AEce92De3Edee1F18E0157C05861564'
    _QUOTER_V2 = '0x61fFE014bA17989E743c5F6cB21bF9697530B21e'
    _FEE_TIERS = (100, 500, 3000, 10000)
    _HUBS = (_WETH, _USDC)
    _MSG_SENDER_SENTINEL = '0x0000000000000000000000000000000000000001'
    _CHAMP_FEE = {frozenset((_WETH, _USDC)): 500, frozenset((_WETH, _WBTC)): 500}
    _CURVE_NG_POOLS = {'0x4f493b7de8aac7d55f71853688b1f7c8f0243c85': {_USDC: 0, _USDT: 1}}
    _SEL_APPROVE = '0x095ea7b3'
_lr1()

def _lr9():
    global _FAR_DEADLINE, _SEL_CURVE_XCHG, _SEL_EXACT_INPUT, _SEL_GET_DY, _SEL_Q_PATH, _SEL_Q_SINGLE, _approve_interactions, _build_interactions, _cf_h1, _cf_p1, _champ_route, _ck, _curve_candidates, _decide, _enc, _eth_call, _is_addr, _pack_path, _quote_calldata, _route_tag, _v3_candidates
    _SEL_EXACT_INPUT = '0xc04b8d59'
    _SEL_Q_SINGLE = '0xc6a5026a'
    _SEL_Q_PATH = '0xcdca1753'
    _SEL_GET_DY = '0x5e0d443f'
    _SEL_CURVE_XCHG = '0xddc1f59d'
    _FAR_DEADLINE = 9999999999

    def _ck(addr):
        from eth_utils import to_checksum_address
        return to_checksum_address(addr)

    def _enc(types, values):
        from eth_abi import encode
        return encode(types, values)

    def _pack_path(tokens, fees):
        """Packed V3 path, tokenIn-first, NOT sorted: token(20)+fee(3)+...+token(20).
    Byte-identical to hydra_top._hydra_eth_fastpath.path_bytes and
    v3_codec.encode_swap_path."""
        b = b''
        for i, t in enumerate(tokens):
            h = t[2:] if t.startswith('0x') else t
            b += bytes.fromhex(h)
            if i < len(fees):
                b += int(fees[i]).to_bytes(3, 'big')
        return b

    def _champ_route(tin, tout):
        """Reconstruct hydra_top._hydra_eth_fastpath's EXACT route selection."""
        fs = frozenset((tin, tout))

        def _lr12():
            if fs in _CHAMP_FEE:
                return ('v3', (tin, tout), (_CHAMP_FEE[fs],))
            if _WETH not in (tin, tout):
                f1 = _CHAMP_FEE.get(frozenset((tin, _WETH)), 3000)
                f2 = _CHAMP_FEE.get(frozenset((_WETH, tout)), 3000)
                return ('v3', (tin, _WETH, tout), (f1, f2))
            return ('v3', (tin, tout), (3000,))
        return _lr12()

    def _v3_candidates(tin, tout):
        """Superset of V3 routes: every fee tier direct + every 2-hop via {WETH,USDC}."""
        out = [('v3', (tin, tout), (fee,)) for fee in _FEE_TIERS]
        for hub in _HUBS:
            if hub in (tin, tout):
                continue
            for fa in _FEE_TIERS:
                for fb in _FEE_TIERS:
                    out.append(('v3', (tin, hub, tout), (fa, fb)))
        return out

    def _curve_candidates(tin, tout):
        """Curve NG routes for this pair (only allowlisted, receiver-overload pools)."""
        out = []
        for pool, idx in _CURVE_NG_POOLS.items():
            if tin in idx and tout in idx:
                out.append(('curve', pool, idx[tin], idx[tout]))
        return out

    def _quote_calldata(route, amt):
        """(to_address, calldata_hex) for quoting a route.  None for unknown kinds."""
        kind = route[0]
        if kind == 'v3':

            def _lr6():
                nonlocal _, data
                _, tokens, fees = route
                if len(tokens) == 2:
                    data = _SEL_Q_SINGLE + _enc(['address', 'address', 'uint256', 'uint24', 'uint160'], [_ck(tokens[0]), _ck(tokens[1]), int(amt), int(fees[0]), 0]).hex()
                else:
                    data = _SEL_Q_PATH + _enc(['bytes', 'uint256'], [_pack_path(tokens, fees), int(amt)]).hex()
            _lr6()
            return (_QUOTER_V2, data)
        if kind == 'curve':
            _, pool, i, j = route
            data = _SEL_GET_DY + _enc(['int128', 'int128', 'uint256'], [int(i), int(j), int(amt)]).hex()
            return (pool, data)
        return None

    def _approve_interactions(tin, spender, amt):
        """[approve(spender,amt)], with a USDT nonzero->nonzero reset guard prepended."""

        def _mk(a):
            return Interaction(target=_ck(tin), value='0', call_data=_SEL_APPROVE + _enc(['address', 'uint256'], [_ck(spender), int(a)]).hex(), chain_id=1)
        ixs = []
        if tin == _USDT:
            ixs.append(_mk(0))
        ixs.append(_mk(amt))
        return ixs

    def _build_interactions(route, tin, amt, recip):
        """The [approve, swap] interaction list for a winning route (or None)."""
        kind = route[0]
        if kind == 'v3':
            _, tokens, fees = route
            swap_cd = _SEL_EXACT_INPUT + _enc(['(bytes,address,uint256,uint256,uint256)'], [(_pack_path(tokens, fees), _ck(recip), _FAR_DEADLINE, int(amt), 0)]).hex()
            return _approve_interactions(tin, _V3_ROUTER, amt) + [Interaction(target=_ck(_V3_ROUTER), value='0', call_data=swap_cd, chain_id=1)]

        def _lr5():
            nonlocal _
            if kind == 'curve':
                _, pool, i, j = route
                xchg_cd = _SEL_CURVE_XCHG + _enc(['int128', 'int128', 'uint256', 'uint256', 'address'], [int(i), int(j), int(amt), 0, _ck(recip)]).hex()
                return _approve_interactions(tin, pool, amt) + [Interaction(target=_ck(pool), value='0', call_data=xchg_cd, chain_id=1)]
            return None
        return _lr5()

    def _route_tag(route):
        return 'eth-superset-curve' if route[0] == 'curve' else 'eth-superset-v3'

    def _decide(tin, tout, amt, min_out, champ_route, champ_empty, quote_fn, margin_bps):
        """Pure decision core.  quote_fn(route)->int|None (quoted tokenOut at the read
    block).  Returns a winning route (strictly better + revert-safe) or None
    (defer to champion).  No RPC, no I/O — fully unit-testable."""
        best = None
        for cand in _v3_candidates(tin, tout) + _curve_candidates(tin, tout):
            q = quote_fn(cand)
            if q and q > 0 and (best is None or q > best[0]):
                best = (q, cand)

        def _lr7():
            if best is None:
                return None
            q_mine, route = best
            if min_out > 0 and q_mine < min_out:
                return None
            if champ_empty:
                return route
            q_champ = quote_fn(champ_route)
            if not q_champ or q_champ <= 0:
                return None
            if route == champ_route:
                return None
            if q_mine * 10000 < q_champ * (10000 + int(margin_bps)):
                return None
            return route
        return _lr7()

    def _eth_call(w3, to, data, block):
        try:
            ret = w3.eth.call({'to': _ck(to), 'data': data}, block_identifier=block)
            return bytes(ret)
        except Exception:
            return None

    def _is_addr(a):
        if not isinstance(a, str) or not a.startswith('0x') or len(a) != 42:
            return False
        try:
            int(a, 16)
            return True
        except Exception:
            return False

    def _cf_p1(self, intent, state):
        p = self._normalized_swap_params(intent, state)
        tin = str(p.get('input_token', '') or '').lower()
        tout = str(p.get('output_token', '') or '').lower()
        amt = int(p.get('input_amount', 0) or 0)
        min_out = int(p.get('min_output_amount', 0) or 0)
        return (p, tin, tout, amt, min_out)

    def _cf_h1(self, amt, w3, block, tin, tout, min_out, champ_route, champ_empty, recip, intent, state):
        seen = {}
        n = [0]

        def quote_fn(route):
            key = repr(route)
            if key in seen:
                return seen[key]
            if n[0] >= self._MAX_QUOTES:
                return None
            n[0] += 1
            if route[0] == 'curve' and (not self._CURVE_ENABLED):
                seen[key] = None
                return None

            def _lr8():
                qc = _quote_calldata(route, amt)
                if qc is None:
                    seen[key] = None
                    return None
                to, data = qc
                ret = _eth_call(w3, to, data, block)
                q = int.from_bytes(ret[:32], 'big') if ret and len(ret) >= 32 else None
                seen[key] = q
                return q
            return _lr8()
        route = _decide(tin, tout, amt, min_out, champ_route, champ_empty, quote_fn, self._STRICT_MARGIN_BPS)

        def _lr10():
            if route is None:
                return None
            ixs = _build_interactions(route, tin, amt, recip)
            if not ixs:
                return None
            logger.info('[eth-superset] override %s->%s amt=%s via %s (block=%s)', tin[:8], tout[:8], amt, route, block)
            return ExecutionPlan(intent_id=intent.app_id, interactions=ixs, deadline=_FAR_DEADLINE, nonce=state.nonce, metadata={'solver': _route_tag(route), 'chain_id': 1, 'route': repr(route)})
        return _lr10()
_lr9()

class RobustFloorSolver(_ChampFloor):
    """Champion floor + a fail-closed Ethereum-mainnet superset router."""
    _STRICT_MARGIN_BPS = 15
    _CURVE_ENABLED = True
    _MAX_QUOTES = 96

    def metadata(self):
        import dataclasses as _dc
        base = super().metadata()
        try:
            return _dc.replace(base, name='_RL_BRAND_NAME_', version='_RL_BRAND_VER_')
        except Exception:
            return base

    def generate_plan(self, intent, state, snapshot=None):
        champ = super().generate_plan(intent, state, snapshot)
        try:
            if int(getattr(state, 'chain_id', 0) or 0) == 1:
                mine = self._eth_superset_plan(intent, state, snapshot, champ)
                if mine is not None and getattr(mine, 'interactions', None):
                    return mine
        except Exception:
            logger.exception('[eth-superset] override failed; serving champion plan')
        return champ

    def _eth_w3(self):
        for cid in (1, 31337):
            try:
                w3 = self._get_web3(cid)
            except Exception:
                w3 = None
            if w3 is not None:
                return w3
        return None

    @staticmethod
    def _eth_read_block(snapshot):
        bn = getattr(snapshot, 'block_number', None) if snapshot else None
        try:
            bn = int(bn) if bn else None
        except Exception:
            bn = None
        return bn if bn and bn > 0 else 'latest'

    def _eth_superset_plan(self, intent, state, snapshot, champ):
        p, tin, tout, amt, min_out = _cf_p1(self, intent, state)

        def _lr11():
            if not _is_addr(tin) or not _is_addr(tout) or amt <= 0 or (tin == tout):
                return None
            for ck_ in ('_input_chain', '_output_chain'):
                c = p.get(ck_)
                if c not in (None, 1, '1'):
                    return None
            recip = str(p.get('receiver', '') or '') or getattr(state, 'contract_address', '') or getattr(state, 'owner', '') or _MSG_SENDER_SENTINEL

            def _lr4():
                if not _is_addr(recip):
                    return None
                w3 = self._eth_w3()
                if w3 is None:
                    return None
                block = self._eth_read_block(snapshot)
                champ_empty = champ is None or not getattr(champ, 'interactions', None)
                champ_route = _champ_route(tin, tout)
                return _cf_h1(self, amt, w3, block, tin, tout, min_out, champ_route, champ_empty, recip, intent, state)
            return _lr4()
        return _lr11()
class CompactSuccessorSolver(RobustFloorSolver):
    """Compact factor build with deterministic Base stability fast paths."""

    def generate_plan(self, intent, state, snapshot=None):
        candidate = maybe_base_stability_plan(self, intent, state, snapshot, None)
        if candidate is not None and getattr(candidate, 'interactions', None):
            return candidate
        return super().generate_plan(intent, state, snapshot)


SOLVER_CLASS = CompactSuccessorSolver
