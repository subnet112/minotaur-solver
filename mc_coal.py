"""mc_coal — transparent Multicall3 coalescer for the engine's concurrent quotes.

The engine fans its venue quotes out on ThreadPoolExecutors (8+ workers) as
individual eth_calls — ~50-90 per order. Under the benchmark's full-corpus load
that storms the sandbox archive RPC into rate-limit flakes, and a single flaked
probe can null a route enumeration (silent drop). This shim sits on
HTTPProvider.make_request (the same proven surface as the chainId cache) and
coalesces plain quote calls ({'to','data'} at 'latest') that arrive within a
12ms window into ONE aggregate3 round-trip, handing each thread back its own
sub-result. Selection logic is untouched: the same calls get the same answers
(aggregate3 returns each sub-call's exact returnData; a reverting sub-call is
surfaced as a standard execution-reverted error, which every quote site already
catches as 0/None). Lone calls in a window pass through unchanged, as do calls
with gas/from/block overrides and calls targeting Multicall3 itself (viking /
chain1 manage their own batches). If the batch call itself fails, every waiter
falls back to its original individual call — worst case is exactly the old
behavior. Disable with MINOTAUR_NO_COAL=1."""
import os
import threading
import time

_MC3 = '0xcA11bde05977b3631167028862bE2a173976CA11'   # Multicall3 (all chains)
_SEL = '0x82ad56cb'                                    # aggregate3((address,bool,bytes)[])
_WIN_S = 0.012
_CHUNK = 16
_ON = os.environ.get('MINOTAUR_NO_COAL', '') != '1'


def _plain_call(c):
    """A bare {'to','data'} read — no gas/from/value keys — and never Multicall3
    itself (self-managed batches pass through)."""
    if not isinstance(c, dict) or set(c) - {'to', 'data'}:
        return False
    to, da = c.get('to'), c.get('data')
    return bool(to) and isinstance(da, str) and da.startswith('0x') and to.lower() != _MC3.lower()


def _eligible(method, params):
    """Only plain latest-block eth_calls coalesce; everything else passes through."""
    if method != 'eth_call' or not isinstance(params, (list, tuple)) or len(params) != 2:
        return False
    return params[1] == 'latest' and _plain_call(params[0])


def _state(prov):
    st = getattr(prov, '_coal_st', None)
    if st is None:
        st = {'lock': threading.Lock(), 'wait': []}
        try:
            prov._coal_st = st
        except Exception:
            return None
    return st


def _pack(chunk):
    from eth_abi import encode as _enc
    arr = [(w['c']['to'], True, bytes.fromhex(w['c']['data'][2:])) for w in chunk]
    return _SEL + _enc(['(address,bool,bytes)[]'], [arr]).hex()


def _ok_resp(rb):
    return {'jsonrpc': '2.0', 'id': 1, 'result': '0x' + bytes(rb).hex()}


def _rev_resp(rb):
    return {'jsonrpc': '2.0', 'id': 1,
            'error': {'code': 3, 'message': 'execution reverted',
                      'data': '0x' + bytes(rb).hex()}}


def _fill(chunk, rows):
    for w, (ok, rb) in zip(chunk, rows):
        w['r'] = _ok_resp(rb) if ok else _rev_resp(rb)


def _exec_chunk(orig, prov, chunk):
    """One aggregate3 for a chunk; each waiter gets a synthesized response, or
    None (= fall back to its own individual call) if the batch itself fails."""
    from eth_abi import decode as _dec
    try:
        resp = orig(prov, 'eth_call', [{'to': _MC3, 'data': _pack(chunk)}, 'latest'])
        rows = _dec(['(bool,bytes)[]'], bytes.fromhex(resp['result'][2:]))[0]
        if len(rows) != len(chunk):
            raise ValueError('row count mismatch')
        _fill(chunk, rows)
    except Exception:
        for w in chunk:
            w['r'] = None


def _flush(orig, prov, batch):
    if len(batch) == 1:
        batch[0]['r'] = None          # lone call: no batching benefit — direct
    else:
        for i in range(0, len(batch), _CHUNK):
            _exec_chunk(orig, prov, batch[i:i + _CHUNK])
    for w in batch:
        w['e'].set()


def _resolve(orig, prov, w, method, params):
    """One waiter's answer: the synthesized batch response, else the original call."""
    if not w['e'].wait(20) or w['r'] is None:
        return orig(prov, method, params)
    return w['r']


def _enqueue(st, w):
    """Append a waiter; True if it is the window leader (first in)."""
    with st['lock']:
        st['wait'].append(w)
        return len(st['wait']) == 1


def _lead_flush(orig, prov, st):
    """Leader: hold the window open briefly, then take and flush the batch."""
    time.sleep(_WIN_S)
    with st['lock']:
        batch, st['wait'] = st['wait'], []
    _flush(orig, prov, batch)


def install():
    """Wrap HTTPProvider.make_request once (composes over the chainId cache)."""
    import web3
    hp = web3.HTTPProvider
    if getattr(hp, '_coal_wrapped', False) or not _ON:
        return
    orig = hp.make_request

    def _mr(self, method, params):
        if not _eligible(method, params):
            return orig(self, method, params)
        st = _state(self)
        if st is None:
            return orig(self, method, params)
        w = {'c': params[0], 'e': threading.Event(), 'r': None}
        if _enqueue(st, w):
            _lead_flush(orig, self, st)
        return _resolve(orig, self, w, method, params)

    hp.make_request = _mr
    hp._coal_wrapped = True
