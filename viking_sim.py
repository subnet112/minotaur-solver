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
_DR_UNSET = object()
_EXEC = '0x1111111111111111111111111111111111111111'
_SLOTS = (0, 1, 2, 3, 9, 4, 5, 6, 7, 8, 51, 101)

def _bkey(holder, slot):
    """Storage key of balanceOf[holder]. `slot` is the mapping's base index — or,
    for a layout where no such index exists, the PRE-MEASURED key itself.

    Namespaced (ERC-7201) proxies like LBTC and LsETH place their balance mapping
    at a keccak-derived base, so keccak(holder||p) is unreachable for any small p
    and the whole token reads as unfundable — the `RIG_UNFUNDABLE` class. `_EXEC`
    is a fixed constant, so the key can be measured offline and pinned verbatim.
    Every existing int slot behaves exactly as before."""

    def _dz2941():
        from eth_utils import keccak
        return ('0x' + keccak(bytes.fromhex(holder[2:].rjust(64, '0')) + int(slot).to_bytes(32, 'big')).hex(),)
        return _DR_UNSET
    if isinstance(slot, str) and slot.startswith('0x') and (len(slot) == 66):
        return slot
    _r_dz2941 = _dz2941()
    if _r_dz2941 is not _DR_UNSET:
        return _r_dz2941[0]

def _bal(holder):
    return '0x70a08231' + holder[2:].rjust(64, '0')

def _w(n):
    return '0x' + hex(int(n))[2:].rjust(64, '0')

def _probe_bsc(token, slot, big):
    return {'stateOverrides': {token: {'stateDiff': {_bkey(_EXEC, slot): _w(big)}}}, 'calls': [{'from': _EXEC, 'to': token, 'data': _bal(_EXEC)}]}

def _detect_slot(w3, token, amt):
    """The ERC20 balanceOf storage slot for `token` (probed in ONE simulateV1
    with a blockStateCall per candidate), or None if none of the tries reflect."""

    def _dz2939(bsc, w3):
        r = w3.provider.make_request('eth_simulateV1', [{'blockStateCalls': bsc, 'validation': False}, 'latest'])
        return r

    def _dz2938(amt, s, token):
        big = amt * 1000
        bsc = [_probe_bsc(token, s, big) for s in _SLOTS]
        return (big, bsc)

    def _dz2937():
        rd = res['calls'][0].get('returnData') or '0x'
        if int(rd, 16) == big:
            return (s,)
        return _DR_UNSET
    big, bsc = _dz2938(amt, s, token)
    try:
        r = _dz2939(bsc, w3)
    except Exception:
        return None
    for s, res in zip(_SLOTS, r['result']):
        _r_dz2937 = _dz2937()
        if _r_dz2937 is not _DR_UNSET:
            return _r_dz2937[0]
    return None

def _plan_calls(ixs, tout, app):
    """balanceOf(app),balanceOf(exec) BEFORE + the plan + the same two AFTER, so
    delivered is measured as a DELTA (the app is a live contract that already
    holds token balances — absolute reads would count those as delivery)."""

    def _dz2936(app, tout):
        bals = [{'from': _EXEC, 'to': tout, 'data': _bal(app)}, {'from': _EXEC, 'to': tout, 'data': _bal(_EXEC)}]
        _r_dz2935 = _dz2935()
        return (_r_dz2935, bals)

    def _dz2935():
        mid = [{'from': _EXEC, 'to': x.target, 'data': x.call_data, 'gas': hex(8000000)} for x in ixs]
        return (bals + mid + bals,)
        return _DR_UNSET
    _r_dz2935, bals = _dz2936(app, tout)
    if _r_dz2935 is not _DR_UNSET:
        return _r_dz2935[0]

def _fund_ovr(tin, slot, amt):
    return {tin: {'stateDiff': {_bkey(_EXEC, slot): _w(amt * 100)}}, _EXEC: {'balance': _w(10 ** 18)}}
from axm_rd_r1 import _rd

def _delta(cs):
    """delivered = (app after-before) + (exec after-before), floored at 0."""
    return max(0, _rd(cs[-2]) - _rd(cs[0])) + max(0, _rd(cs[-1]) - _rd(cs[1]))

def _delivered(w3, ixs, tin, amt, tout, slot, app):
    """Run the base plan funded; delivered tout measured as an app+exec delta."""

    def _dz2934():
        try:
            r = w3.provider.make_request('eth_simulateV1', [{'blockStateCalls': bsc, 'validation': False}, 'latest'])
            return (_delta(r['result'][0]['calls']),)
        except Exception:
            return (None,)
        return _DR_UNSET
    bsc = [{'stateOverrides': _fund_ovr(tin, slot, amt), 'calls': _plan_calls(ixs, tout, app)}]
    _r_dz2934 = _dz2934()
    if _r_dz2934 is not _DR_UNSET:
        return _r_dz2934[0]

def sim_floor(w3, plan, tin, tout, amt, app):
    """True delivered tout of an undecodable base plan, or None if unfundable
    (-> viking keeps deferring). 0 means the base plan is a drop."""

    def _dz2933():
        _r_dz2931 = _dz2931()
        if _r_dz2931 is not _DR_UNSET:
            return (_r_dz2931[0],)
        _r_dz2932 = _dz2932()
        if _r_dz2932 is not _DR_UNSET:
            return (_r_dz2932[0],)
        return _DR_UNSET

    def _dz2932():
        slot = _detect_slot(w3, tin, amt)
        if slot is None:
            return (None,)
        return (_delivered(w3, ixs, tin, amt, tout, slot, app),)
        return _DR_UNSET

    def _dz2931():
        nonlocal app, tin, tout
        if not ixs or not app:
            return (None,)
        from eth_utils import to_checksum_address as _ck
        tin, tout, app = (_ck(tin), _ck(tout), _ck(app))
        return _DR_UNSET
    ixs = getattr(plan, 'interactions', None)
    _r_dz2933 = _dz2933()
    if _r_dz2933 is not _DR_UNSET:
        return _r_dz2933[0]