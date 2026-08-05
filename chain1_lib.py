# chain-1 dynamic tier: quoting + v3 building helpers
from chain1_c import _WETH, _USDT, _QUOTER, _ROUTER, _FEES, _HUBS, _CHAMP_FEE

def _pack(tokens, fees):
    b = b''
    for i, t in enumerate(tokens):
        b += bytes.fromhex(t[2:])
        if i < len(fees):
            b += int(fees[i]).to_bytes(3, 'big')
    return b

def _champ_route(tin, tout):
    fs = frozenset((tin, tout))
    if fs in _CHAMP_FEE:
        return ((tin, tout), (_CHAMP_FEE[fs],))
    if _WETH not in (tin, tout):
        f1 = _CHAMP_FEE.get(frozenset((tin, _WETH)), 3000)
        f2 = _CHAMP_FEE.get(frozenset((_WETH, tout)), 3000)
        return ((tin, _WETH, tout), (f1, f2))
    return ((tin, tout), (3000,))

def _direct_legs(tin, tout):
    """Every (route, fees) pair for the single-hop tin -> tout, one per fee tier.

    Sibling of `_hub_legs`, named for the same reason: the two differ in ARITY -- a direct
    route carries ONE fee, a two-hop an ordered pair -- and `_pack` walks fees alongside
    tokens, so a one-element tuple written `(f)` instead of `(f,)` is not a tuple at all and
    packs a truncated path that quotes some other pool rather than raising.

    ORDER IS LOAD-BEARING and belongs to the caller: these are emitted BEFORE any hub leg so
    the sweep's strict `>` leaves a direct route in place when a two-hop merely ties it.
    """
    return [((tin, tout), (f,)) for f in _FEES]


# The two-hop half of the candidate list: every (route, fees) pair that reaches `tout` from
# `tin` THROUGH one hub token, one per ordered fee pair. `_direct_legs` above already names
# this function as its sibling -- they are separate because they differ in ARITY, and `_pack`
# walks fees alongside tokens, so arity decides which pool actually gets quoted.
#
# `hub in (tin, tout)` drops the degenerate legs whose hub IS an endpoint. Those spell a
# single-hop route with a repeated token, and the path they pack names a pool that does not
# exist -- the quote returns None and the candidate is spent for nothing.
#
# Loop order is load-bearing for the same reason the direct legs go first. The sweep replaces
# its best only on a STRICT improvement, so among equal quotes the earliest emitted wins, and
# it stops once its quote budget is spent -- which makes this list a PREFIX, not a set.
# Reordering the loops changes nothing about which routes exist and everything about which
# one is served.
# The hubs that can actually sit in the middle of THIS pair. A hub equal to either endpoint
# spells a route with a repeated token, whose packed path names a pool that does not exist —
# the quote comes back None and the candidate is spent for nothing.
#
# Order is preserved from `_HUBS` deliberately: the sweep improves only on a STRICT `>` and
# stops when its quote budget runs out, so this sequence is a PREFIX of what gets tried, not a
# set. Filtering must not reorder.
def _usable_hubs(tin, tout):
    return [hub for hub in _HUBS if hub not in (tin, tout)]


def _hub_legs(tin, tout):
    out = []
    for hub in _usable_hubs(tin, tout):
        for fa in _FEES:
            for fb in _FEES:
                out.append(((tin, hub, tout), (fa, fb)))
    return out


def _candidates(tin, tout):
    return _direct_legs(tin, tout) + _hub_legs(tin, tout)

# A 4-byte function selector, derived rather than pasted. Both call sites below need one and
# both were spelling out `keccak(text=...)[:4]` in full.
#
# Derived on purpose: a hardcoded selector is a magic constant that cannot be checked by eye,
# and getting one wrong does not fail loudly -- the call reverts as though the pool were dry,
# which reads exactly like a legitimately missing route. Keeping the signature TEXT in the
# source means the thing a reader verifies is the ABI signature itself.
def _selector(sig):
    from eth_utils import keccak as _keccak
    return _keccak(text=sig)[:4]


def _qdata(route, amt):
    from eth_abi import encode as _enc
    tokens, fees = route
    sel = _selector('quoteExactInput(bytes,uint256)')
    return '0x' + (sel + _enc(['bytes', 'uint256'], [_pack(tokens, fees), int(amt)])).hex()

def _qroute(w3, route, amt, block):
    try:
        from eth_abi import decode as _dec
        from eth_utils import to_checksum_address as _ck
        r = w3.eth.call({'to': _ck(_QUOTER), 'data': _qdata(route, amt)}, block_identifier=block)
        return _dec(['uint256', 'uint160[]', 'uint32[]', 'uint256'], r)[0] or None
    except Exception:
        return None

def _swap_leg(route, amt, rcpt):
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    tokens, fees = route
    sel = _selector('exactInput((bytes,address,uint256,uint256,uint256))')
    return '0x' + (sel + _enc(['(bytes,address,uint256,uint256,uint256)'], [(_pack(tokens, fees), _ck(rcpt), 9999999999, int(amt), 0)])).hex()

def _needs_reset_approve(tin):
    """Whether `tin` must be approved to 0 before being approved to the real amount.

    USDT's approve() reverts outright when it would move a NON-ZERO allowance to another
    non-zero value -- it is not ERC-20 compliant on that path. Every other token in the
    corpus overwrites its allowance happily, so the extra interaction is spent only where it
    is load-bearing.

    The failure mode this guards is quiet and expensive: the approve reverts, the whole plan
    reverts with it, and the row scores as a delivery failure rather than as anything that
    points at an allowance. Naming the condition keeps the reason attached to the test, which
    a bare `tin == _USDT` beside a zero-amount approve does not.
    """
    return tin == _USDT


def _approves(tin, amt, chain_id):
    from eth_utils import to_checksum_address as _ck
    from common.abi_utils import encode_approve
    from minotaur_subnet.shared.types import Interaction as _IX
    ixs = []
    if _needs_reset_approve(tin):
        ixs.append(_IX(target=tin, value='0', call_data=encode_approve(_ck(_ROUTER), 0), chain_id=chain_id))
    ixs.append(_IX(target=tin, value='0', call_data=encode_approve(_ck(_ROUTER), int(amt)), chain_id=chain_id))
    return ixs

def _build(route, tin, amt, rcpt, chain_id):
    from minotaur_subnet.shared.types import Interaction as _IX
    leg = _swap_leg(route, amt, rcpt)
    return _approves(tin, amt, chain_id) + [_IX(target=_ROUTER, value='0', call_data=leg, chain_id=chain_id)]

def _amounts(p):
    amt = int(p.get('input_amount', 0) or 0)
    mo = int(p.get('min_output_amount', 0) or 0)
    return amt, mo

# Is this a swap we can even attempt? Four independent reasons it might not be, and each one
# is a real intent seen on the wire rather than a defensive flourish:
#
#   len != 42     the token field was empty or malformed; `str(... or '').lower()` upstream
#                 turns a missing key into '', which is length 0, not a short address.
#   amt <= 0      a zero-amount intent quotes to zero everywhere and would bake a useless route.
#   tin == tout   a self-swap has no pool and every quoter reverts on it.
#
# Expressed as a POSITIVE predicate because the caller wants "may I proceed", while the inline
# form stated the negation of a four-term disjunction -- the shape most likely to be misread
# when a fifth condition is eventually added.
def _valid_pair(tin, tout, amt):
    return len(tin) == 42 and len(tout) == 42 and amt > 0 and tin != tout


def _params(s, intent, state):
    p = s._normalized_swap_params(intent, state)
    tin = str(p.get('input_token', '') or '').lower()
    tout = str(p.get('output_token', '') or '').lower()
    amt, mo = _amounts(p)
    if not _valid_pair(tin, tout, amt):
        return None
    return (tin, tout, amt, mo)
