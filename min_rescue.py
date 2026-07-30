"""Rescue a champion plan whose own swap provably quotes nothing.

Fail-CLOSED: returns None unless the quoter positively says the plan's tier yields 0 and a
different tier yields more. Only the fee word of the exactInputSingle calldata is rewritten;
recipient, deadline, amounts and the approve interaction stay exactly as the champion built
them, so a rescue can only convert a revert into a delivery.
"""
_DR_UNSET = object()
_SEL_EIS = '414bf389'
_TIERS = (100, 500, 3000, 10000)
_QUOTER = {1: '0x61fFE014bA17989E743c5F6cB21bF9697530B21e', 8453: '0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a'}

def _words(cd):
    body = cd[10:]
    return [body[i:i + 64] for i in range(0, len(body), 64)]

def _quote(w3, quoter, ti, to, amt, fee):
    data = 'c6a5026a' + ti.rjust(64, '0') + to.rjust(64, '0') + format(int(amt), '064x') + format(int(fee), '064x') + '0' * 64
    try:
        ret = bytes(w3.eth.call({'to': quoter, 'data': '0x' + data}))
        return int.from_bytes(ret[:32], 'big') if len(ret) >= 32 else 0
    except Exception:
        return 0

def _swap_ix(plan):
    """Index of the plan's exactInputSingle interaction, else None."""
    try:
        for i, ix in enumerate(plan.interactions):
            if str(getattr(ix, 'call_data', '') or '').lower().startswith('0x' + _SEL_EIS):
                return i
    except Exception:
        pass
    return None

def _better_fee(self, w3, cid, w, cur_fee):

    def _dz242():
        if _quote(w3, quoter, ti, to, amt, cur_fee) > 0:
            return (None,)
        best, bf = (0, None)
        for f in _TIERS:
            if int(f) == int(cur_fee):
                continue
            o = _quote(w3, quoter, ti, to, amt, f)
            if o > best:
                best, bf = (o, f)
        return (bf if best > 0 else None,)
        return _DR_UNSET
    ti, to = (w[0][-40:], w[1][-40:])
    amt = int(w[5], 16)
    quoter = _QUOTER[cid]
    _r_dz242 = _dz242()
    if _r_dz242 is not _DR_UNSET:
        return _r_dz242[0]

def _w3_of(self, cid):
    try:
        gw = getattr(self, '_get_web3', None)
        return gw(cid) if callable(gw) else None
    except Exception:
        return None

def _rescue_dead(self, plan, intent, state, snapshot):

    def _dz240(i, plan):
        cd = str(plan.interactions[i].call_data)
        _r_dz239 = _dz239()
        return (_r_dz239, cd)

    def _dz239():
        _r_dz238 = _dz238()
        if _r_dz238 is not _DR_UNSET:
            return (_r_dz238[0],)
        return (plan,)
        return _DR_UNSET

    def _dz238():
        w = _words(cd)
        if len(w) < 8:
            return (None,)
        nf = _better_fee(self, w3, cid, w, int(w[2], 16))
        if nf is None:
            return (None,)
        w[2] = format(int(nf), '064x')
        try:
            plan.interactions[i].call_data = cd[:10] + ''.join(w)
        except Exception:
            return (None,)
        return _DR_UNSET
    try:
        if plan is None or not getattr(plan, 'interactions', None):
            return None
        cid = int(getattr(state, 'chain_id', 0) or 0)
        if cid not in _QUOTER:
            return None
        i = _swap_ix(plan)
        if i is None:
            return None
        w3 = _w3_of(self, cid)
        if w3 is None:
            return None
        _r_dz239, cd = _dz240(i, plan)
        if _r_dz239 is not _DR_UNSET:
            return _r_dz239[0]
    except Exception:
        return None