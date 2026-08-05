# chain-1 dynamic tier: decision + entry
from chain1_lib import _qroute, _build, _params, _champ_route
from chain1_v2 import _v2_build, _sweep, _v2_best

_BPS = 10000
# 12bps, not 10. RELATIVE_TOL_BPS is 10, so a route winning by exactly the tolerance scores
# `matched` anyway; the extra 2bps is the cushion that stops us spending a live-quoted route
# to buy a verdict we already had. As the bare pair 10000/10012 this was two magic numbers
# whose relationship -- and whose units -- appeared nowhere.
_BEAT_MARGIN_BPS = 12


def _clears_margin(q_mine, q_champ):
    """Whether q_mine beats q_champ by at least the margin. Integer math end to end.

    Cross-multiplied rather than divided: `q_mine / q_champ > 1.0012` puts a float on values
    that run past 2**53 on 18-decimal tokens, i.e. the comparison stops being exact at
    precisely the sizes worth routing. A falsy q_champ (no pool, or priced 0) is NOT a win by
    default -- it means the comparison could not be made, and the caller must decline.
    """
    if not q_champ:
        return False
    return q_mine * _BPS >= q_champ * (_BPS + _BEAT_MARGIN_BPS)


def _beats_champ(w3, tin, tout, amt, block, q_mine, route):
    croute = _champ_route(tin, tout)
    if route == croute:
        return False
    return _clears_margin(q_mine, _qroute(w3, croute, amt, block))

def _meets_min_out(q, mo):
    """Whether quote `q` clears the order's declared minimum output.

    `mo > 0` is what separates "no minimum declared" from a floor: _amounts coerces a missing
    or null min_output_amount to 0, and 0 has to mean unset. The clause is redundant as pure
    arithmetic -- a quote is never negative, so `q < 0` could not fire anyway -- but writing
    the intent down is the point. Read without it, the test looks like it enforces a
    zero floor, and the next edit to _amounts (a sentinel, a signed value) would silently
    turn every unset order into a rejection with nothing here to contradict it.
    """
    return not (mo > 0 and q < mo)


def _decide(w3, tin, tout, amt, mo, block, base_empty):
    best = _v2_best(w3, tin, tout, amt, block, _sweep(w3, tin, tout, amt, block))
    if best is None:
        return None
    q_mine, route = best
    if not _meets_min_out(q_mine, mo):
        return None
    if not base_empty and not _beats_champ(w3, tin, tout, amt, block, q_mine, route):
        return None
    return route

def _mk_plan(route, tin, amt, rcpt, intent, state):
    from minotaur_subnet.shared.types import ExecutionPlan as _EP
    if isinstance(route, tuple) and route and route[0] == 'v2':
        ixs = _v2_build(route[1], route[2], tin, amt, route[3], rcpt, 1)
    else:
        ixs = _build(route, tin, amt, rcpt, 1)
    return _EP(intent_id=intent.app_id, interactions=ixs, deadline=9999999999, nonce=state.nonce, metadata={'solver': 'viking-eth-dyn', 'chain_id': 1})

# The block every quote in one solve is priced at. Two separate collapses to `'latest'` hide
# in the two lines this replaces, and they mean different things:
#
#   no snapshot at all   -- nothing pinned the chain, so the newest block is the only answer.
#   snapshot, no block   -- `block_number` absent, None, or 0. A pinned 0 is not a block we
#                           can quote; treating it as `'latest'` is the same fallback, reached
#                           for a different reason.
#
# Both land on the string `'latest'` rather than a number because that is what web3 wants in
# `block_identifier`, and the ONLY other caller-visible value is an int. Returning a mixed
# str/int is deliberate and belongs here, where it can be named, instead of at the call site
# where the two `if`s read as one accidental chain.
#
# `int(block)` still raises on a non-numeric block_number, exactly as before. Swallowing that
# would silently price the whole solve at the wrong block, which is a routing change wearing
# the costume of a defensive guard.
def _block_of(snapshot):
    block = getattr(snapshot, 'block_number', None) if snapshot else None
    return int(block) if block else 'latest'


def _rdctx(s, snapshot):
    w3 = s._get_web3(1) or s._get_web3(31337)
    if w3 is None:
        return None
    return w3, _block_of(snapshot)

# Who the swap pays out to. The contract address is preferred and the owner is the fallback,
# and the ORDER is the whole content of this function: paying the owner when a contract address
# exists sends the proceeds somewhere the settlement layer is not watching, so the two are not
# interchangeable defaults.
#
# Both are read with getattr rather than attribute access because `state` arrives from the
# harness and an absent field is a normal state, not an error -- and `or` (not a None check)
# because the empty string is as unusable a recipient as None is.
def _receiver(state):
    return getattr(state, 'contract_address', None) or getattr(state, 'owner', None)


def _guards(s, intent, state, snapshot):
    if int(getattr(state, 'chain_id', 0) or 0) != 1:
        return None
    pr = _params(s, intent, state)
    if pr is None:
        return None
    rcpt = _receiver(state)
    if not rcpt:
        return None
    rd = _rdctx(s, snapshot)
    if rd is None:
        return None
    return pr, rcpt, rd[0], rd[1]

def superset(s, intent, state, snapshot, base_plan):
    """Chain-1 candidate sweep; a plan only when strictly better than the
    engine's own quoted route by the margin (or the base plan is empty)."""
    try:
        g = _guards(s, intent, state, snapshot)
        if g is None:
            return None
        (tin, tout, amt, mo), rcpt, w3, block = g
        base_empty = base_plan is None or not getattr(base_plan, 'interactions', None)
        route = _decide(w3, tin, tout, amt, mo, block, base_empty)
        if route is None:
            return None
        return _mk_plan(route, tin, amt, rcpt, intent, state)
    except Exception:
        return None
