"""viking_sim — execution-sim floor for UNDECODABLE base plans.

The engine routes ~20% of orders through the Uniswap Universal Router with a V4
leg (execute() cmds 0x00+0x10). viking can't re-quote V4, so _base_out returns
None and viking DEFERS — which serves the base plan even when its thin-V4 pool
delivers 0 (a silent drop) while viking has a real exec-accurate route. This runs
the base plan under eth_simulateV1 (executor funded with tin via the detected
balance slot) and returns the TRUE delivered tout, so viking overrides ONLY when
its candidate strictly beats the real base delivery. Delivered is summed over the
app + executor tout balances so the router's recipient choice can't fool it. If
the balance slot can't be found (unfamiliar token layout) sim_floor returns None
and viking keeps deferring — the prior safe behavior, never a blind override."""
_EXEC = '0x1111111111111111111111111111111111111111'
_SLOTS = (0, 1, 2, 3, 9, 4, 5, 6, 7, 8, 51, 101)

def _bkey(holder, slot):
    from eth_utils import keccak
    return '0x' + keccak(bytes.fromhex(holder[2:].rjust(64, '0')) + int(slot).to_bytes(32, 'big')).hex()

def _bal(holder):
    return '0x70a08231' + holder[2:].rjust(64, '0')

def _w(n):
    return '0x' + hex(int(n))[2:].rjust(64, '0')

def _probe_bsc(token, slot, big):
    return {'stateOverrides': {token: {'stateDiff': {_bkey(_EXEC, slot): _w(big)}}}, 'calls': [{'from': _EXEC, 'to': token, 'data': _bal(_EXEC)}]}

def _detect_slot(w3, token, amt):
    """The ERC20 balanceOf storage slot for `token` (probed in ONE simulateV1
    with a blockStateCall per candidate), or None if none of the tries reflect."""
    big = amt * 1000
    bsc = [_probe_bsc(token, s, big) for s in _SLOTS]
    try:
        r = w3.provider.make_request('eth_simulateV1', [{'blockStateCalls': bsc, 'validation': False}, 'latest'])
    except Exception:
        return None
    for s, res in zip(_SLOTS, r['result']):
        rd = res['calls'][0].get('returnData') or '0x'
        if int(rd, 16) == big:
            return s
    return None

def _plan_calls(ixs, tout, app):
    """balanceOf(app),balanceOf(exec) BEFORE + the plan + the same two AFTER, so
    delivered is measured as a DELTA (the app is a live contract that already
    holds token balances — absolute reads would count those as delivery)."""
    bals = [{'from': _EXEC, 'to': tout, 'data': _bal(app)}, {'from': _EXEC, 'to': tout, 'data': _bal(_EXEC)}]
    mid = [{'from': _EXEC, 'to': x.target, 'data': x.call_data, 'gas': hex(8000000)} for x in ixs]
    return bals + mid + bals

def _fund_ovr(tin, slot, amt):
    return {tin: {'stateDiff': {_bkey(_EXEC, slot): _w(amt * 100)}}, _EXEC: {'balance': _w(10 ** 18)}}

def _rd(c):
    return int(c.get('returnData') or '0x0', 16)

def _delta(cs):
    """delivered = (app after-before) + (exec after-before), floored at 0."""
    return max(0, _rd(cs[-2]) - _rd(cs[0])) + max(0, _rd(cs[-1]) - _rd(cs[1]))

def _delivered(w3, ixs, tin, amt, tout, slot, app):
    """Run the base plan funded; delivered tout measured as an app+exec delta."""
    bsc = [{'stateOverrides': _fund_ovr(tin, slot, amt), 'calls': _plan_calls(ixs, tout, app)}]
    try:
        r = w3.provider.make_request('eth_simulateV1', [{'blockStateCalls': bsc, 'validation': False}, 'latest'])
        return _delta(r['result'][0]['calls'])
    except Exception:
        return None

def sim_floor(w3, plan, tin, tout, amt, app):
    """True delivered tout of an undecodable base plan, or None if unfundable
    (-> viking keeps deferring). 0 means the base plan is a drop."""
    ixs = getattr(plan, 'interactions', None)
    if not ixs or not app:
        return None
    from eth_utils import to_checksum_address as _ck
    tin, tout, app = (_ck(tin), _ck(tout), _ck(app))
    slot = _detect_slot(w3, tin, amt)
    if slot is None:
        return None
    return _delivered(w3, ixs, tin, amt, tout, slot, app)