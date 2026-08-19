"""Rescue the amount_in/amountIn param alias the SDK normalizer misses.

Also installs the eth_chainId memo (2026-08-08). Measured: eth_chainId was 1143 of 1716
RPC calls on a single row — 67% of the budget spent asking the node what chain it is on,
because web3.py re-validates a CONSTANT on every contract call. Free on a warm fork,
11-114 seconds at validator latency, which is why every local gate passed while rounds
scored dropped=43. Cached per provider instance; first call wins; fail-open throughout.
"""
try:
    from web3.providers.rpc import HTTPProvider as _MinoHP
    if not getattr(_MinoHP, '_mino_chainid_memo', False):
        _mino_orig_make_request = _MinoHP.make_request

        def _mino_make_request(self, method, params):
            if method == 'eth_chainId':
                _c = getattr(self, '_mino_cid_cache', None)
                if _c is not None:
                    return _c
                _r = _mino_orig_make_request(self, method, params)
                try:
                    self._mino_cid_cache = _r
                except Exception:
                    pass
                return _r
            return _mino_orig_make_request(self, method, params)
        _MinoHP.make_request = _mino_make_request
        _MinoHP._mino_chainid_memo = True
except Exception:
    pass

def _raw_params(state):
    typed = getattr(state, 'typed_context', None)
    if typed is not None:
        raw = getattr(typed, 'raw_params', None)
        if isinstance(raw, dict):
            return raw
    try:
        view = getattr(state, 'raw_params_view', None)
        if callable(view):
            raw = view()
            if isinstance(raw, dict):
                return raw
    except Exception:
        pass
    raw = getattr(state, 'raw_params', None)
    return raw if isinstance(raw, dict) else {}

def install(cls):

    class _AmtAlias(cls):

        def _normalized_swap_params(self, intent, state):
            p = super()._normalized_swap_params(intent, state)
            try:
                if not int(p.get('input_amount') or 0):
                    raw = _raw_params(state)
                    alt = raw.get('amount_in') or raw.get('amountIn') or 0
                    alt = int(str(alt)) if alt else 0
                    if alt > 0:
                        p = dict(p)
                        p['input_amount'] = alt
            except Exception:
                pass
            return p
    return _AmtAlias