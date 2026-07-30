_FR_UNSET = object()
__all__ = ['_fx_5', '_fx_23', '_fx_25', '__fx_tbl29__C1B', '__fx_tbl29__C1D', '__fx_tbl29__C1T', '__fx_tbl29__C1U', '__fx_tbl29__C1W', '_fx_tbl29']

def _fx_5(_B1Ix, _B1Plan, _b1_approve, _fx_2, amount_in, best, cfg, cid, intent, state, tin):
    chain_id, deadline, swap_cd = _fx_2()
    return _B1Plan(intent_id=intent.app_id, interactions=[_B1Ix(target=tin, value='0', call_data=_b1_approve(cfg['rsingle'], amount_in), chain_id=chain_id), _B1Ix(target=cfg['rsingle'] if best[0] == 'single' else cfg['rmulti'], value='0', call_data=swap_cd, chain_id=chain_id)], deadline=deadline, nonce=getattr(state, 'nonce', 0), metadata={'solver': 'b1-generic', 'route': f'cid{cid} {best[0]}'})

def _fx_23(_dec, _enc, amt, di, pool, rpc):
    dy = i = j = None

    def _fr_10():
        nonlocal dy, i, j
        try:
            i, j, is_under = _dec(['int128', 'int128', 'bool'], di)
        except Exception:
            return None
        if is_under:
            return None
        dy = eth_call(rpc, pool, '0x' + S_CURVE_GETDY + _enc(['int128', 'int128', 'uint256'], [int(i), int(j), int(amt)]).hex())
        return _FR_UNSET
    _rv_10 = _fr_10()
    if _rv_10 is not _FR_UNSET:
        return _rv_10
    if not dy or len(dy) < 32:
        return None
    try:
        out = int(_dec(['uint256'], dy[:32])[0])
    except Exception:
        return None
    return {'pool': pool, 'i': int(i), 'j': int(j), 'dy': out} if out > 0 else None

def _fx_25(_B1Ix, _B1Plan, _B1_AERO_V2_FACTORY, _B1_AERO_V2_ROUTER, _B1_ROUTER_8453, _B1_SPLIT_LEG_SLACK, _B1_SPLIT_MARGIN, _b1_approve, _b1_quote_aero_v2, _b1_quote_single, _b1_v3single, _b1time, amount_in, amount_out_min_floor, chain_id, champ_out, intent, state, tin, tout, w3):
    if champ_out <= 0:
        return None
    best_a1 = best_q2 = best_stable = min1 = None

    def _fr_11():
        nonlocal best_a1, best_q2, best_stable, min1
        best_total, best_a1, best_q1, best_q2, best_stable = (0, 0, 0, 0, True)

        def _fx_3():
            nonlocal a2, best_a1, best_q1, best_q2, best_stable, best_total
            for pct in (50, 60, 65, 70, 75, 80):
                a1 = amount_in * pct // 100
                a2 = amount_in - a1
                q1 = _b1_quote_single(w3, tin, tout, a1, 100)
                if q1 <= 0:
                    continue
                for stable in (True, False):
                    q2 = _b1_quote_aero_v2(w3, tin, tout, a2, stable)
                    if q2 > 0 and q1 + q2 > best_total:
                        best_total, best_a1 = (q1 + q2, a1)
                        best_q1, best_q2, best_stable = (q1, q2, stable)
        _fx_3()
        if best_total <= 0:
            return None
        floor = max(int(amount_out_min_floor), int(champ_out * _B1_SPLIT_MARGIN))
        if best_total <= floor:
            return None
        min1 = int(best_q1 * (1.0 - _B1_SPLIT_LEG_SLACK))
        return _FR_UNSET
    _rv_11 = _fr_11()
    if _rv_11 is not _FR_UNSET:
        return _rv_11
    min2 = int(best_q2 * (1.0 - _B1_SPLIT_LEG_SLACK))
    if min1 + min2 <= champ_out:
        return None
    a2 = amount_in - best_a1
    recipient = getattr(state, 'contract_address', '') or getattr(state, 'owner', '')

    def _fx_12():
        deadline = int(_b1time.time()) + 300
        try:

            def _fx_7():
                from web3 import Web3 as _W3
                from eth_abi import encode as _enc
                from eth_utils import keccak as _kk
                ck = _W3.to_checksum_address
                v3_cd = _b1_v3single(token_in=tin, token_out=tout, fee=100, recipient=recipient, deadline=deadline, amount_in=best_a1, amount_out_minimum=min1, chain_id=chain_id)
                aero_sel = _kk(text='swapExactTokensForTokens(uint256,uint256,(address,address,bool,address)[],address,uint256)')[:4]
                aero_cd = '0x' + (aero_sel + _enc(['uint256', 'uint256', '(address,address,bool,address)[]', 'address', 'uint256'], [int(a2), int(min2), [(ck(tin), ck(tout), bool(best_stable), ck(_B1_AERO_V2_FACTORY))], ck(recipient), int(deadline)])).hex()
                return (aero_cd, v3_cd)
            aero_cd, v3_cd = _fx_7()
        except Exception:
            return None
        return _B1Plan(intent_id=intent.app_id, interactions=[_B1Ix(target=tin, value='0', call_data=_b1_approve(_B1_ROUTER_8453, best_a1), chain_id=chain_id), _B1Ix(target=_B1_ROUTER_8453, value='0', call_data=v3_cd, chain_id=chain_id), _B1Ix(target=tin, value='0', call_data=_b1_approve(_B1_AERO_V2_ROUTER, a2), chain_id=chain_id), _B1Ix(target=_B1_AERO_V2_ROUTER, value='0', call_data=aero_cd, chain_id=chain_id)], deadline=deadline, nonce=getattr(state, 'nonce', 0), metadata={'solver': 'b1-split', 'route': '%s->%s split v3_100 + aero(stable=%s)' % (tin[:6], tout[:6], best_stable)})
    return _fx_12()
__fx_tbl29__C1B = '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599'
__fx_tbl29__C1D = '0x6b175474e89094c44da98b954eedeac495271d0f'
__fx_tbl29__C1T = '0xdac17f958d2ee523a2206206994597c13d831ec7'
__fx_tbl29__C1U = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'
__fx_tbl29__C1W = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'

def _fr_9():
    global _fx_tbl29
    _fx_tbl29 = {frozenset((__fx_tbl29__C1W, __fx_tbl29__C1U)): 500, frozenset((__fx_tbl29__C1W, __fx_tbl29__C1T)): 500, frozenset((__fx_tbl29__C1W, __fx_tbl29__C1B)): 500, frozenset((__fx_tbl29__C1W, __fx_tbl29__C1D)): 3000, frozenset((__fx_tbl29__C1U, __fx_tbl29__C1T)): 100, frozenset((__fx_tbl29__C1U, __fx_tbl29__C1D)): 100, frozenset((__fx_tbl29__C1T, __fx_tbl29__C1D)): 100, frozenset((__fx_tbl29__C1B, __fx_tbl29__C1U)): 3000}
_fr_9()