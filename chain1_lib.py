# chain-1 dynamic tier: quoting + v3 building helpers
from chain1_c import _WETH, _USDT, _QUOTER, _ROUTER, _FEES, _HUBS, _CHAMP_FEE
from chain1_appr_ext import _needs_reset_approve  # relocated leaf; see that module for why
from chain1_dleg_ext import _direct_legs  # relocated leaf; see that module for why
from chain1_appr2_ext import _approves  # relocated leaf; see that module for why
from chain1_abytes_ext import _addr_bytes  # relocated leaf; see that module for why

# One address as the 20 RAW bytes a V3 path is built from -- not hex text, and not ABI-encoded.
#
# `t[2:]` strips the '0x' and nothing else, so the caller's addresses must already be the plain
# 42-char form `_token` produces. That coupling is the reason this is named: an address that is
# checksummed still packs (hex digits are case-insensitive), but one that is padded, prefixed
# twice, or empty packs a path of the WRONG LENGTH -- and a mis-sized path does not raise. It
# names some other pool, or none, and the quote comes back as an ordinary None while the real
# fault sits two functions upstream.


def _pack(tokens, fees):
    b = b''
    for i, t in enumerate(tokens):
        b += _addr_bytes(t)
        if i < len(fees):
            b += int(fees[i]).to_bytes(3, 'big')
    return b

# The fee tier the champion's own router would pick for one leg, defaulting to 3000.
#
# `frozenset` and not a tuple: `_CHAMP_FEE` is keyed by UNORDERED pair, because a pool is the
# same pool traded either way. Keying it by an ordered tuple would miss on exactly half the
# lookups -- and miss SILENTLY, since a miss is indistinguishable from an unmapped pair and both
# land on the default.
#
# 3000 is the router's own fallback tier, not a guess of ours. It is load-bearing that it is the
# SAME constant on both legs and the same one the direct branch below uses: the whole point of
# `_champ_route` is to reconstruct what the incumbent would have quoted, and a "better" default
# here would make us beat a champion that never existed -- the comparison in `_clears_margin`
# would clear on a fictional number and we would spend a route to win nothing.
def _champ_fee(a, b):
    return _CHAMP_FEE.get(frozenset((a, b)), 3000)


def _champ_route(tin, tout):
    fs = frozenset((tin, tout))
    if fs in _CHAMP_FEE:
        return ((tin, tout), (_CHAMP_FEE[fs],))
    if _WETH not in (tin, tout):
        return ((tin, _WETH, tout), (_champ_fee(tin, _WETH), _champ_fee(_WETH, tout)))
    return ((tin, tout), (3000,))



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

# The output amount out of a quoteExactInput return blob.
#
# The quoter returns FOUR values -- (amountOut, sqrtPriceX96After[], initializedTicksCrossed[],
# gasEstimate) -- and only the first is a price. The other three must still be named in the decode
# or the ABI reader mis-frames the whole payload: the arrays are dynamic, so dropping them does
# not yield a short read, it yields a WRONG first word. That failure is silent, and a plausible
# wrong quote is worse here than no quote at all, because the sweep picks its route on it.
#
# `or None` collapses a zero to the same "did not price" signal every other quoter here returns,
# so no caller has to distinguish a legitimate 0 from a failure.
def _quoted_amount(blob):
    from eth_abi import decode as _dec
    return _dec(['uint256', 'uint160[]', 'uint32[]', 'uint256'], blob)[0] or None


def _qroute(w3, route, amt, block):
    try:
        from eth_utils import to_checksum_address as _ck
        r = w3.eth.call({'to': _ck(_QUOTER), 'data': _qdata(route, amt)}, block_identifier=block)
        return _quoted_amount(r)
    except Exception:
        return None

def _swap_leg(route, amt, rcpt):
    from eth_abi import encode as _enc
    from eth_utils import to_checksum_address as _ck
    tokens, fees = route
    sel = _selector('exactInput((bytes,address,uint256,uint256,uint256))')
    return '0x' + (sel + _enc(['(bytes,address,uint256,uint256,uint256)'], [(_pack(tokens, fees), _ck(rcpt), 9999999999, int(amt), 0)])).hex()




def _build(route, tin, amt, rcpt, chain_id):
    from minotaur_subnet.shared.types import Interaction as _IX
    leg = _swap_leg(route, amt, rcpt)
    return _approves(tin, amt, chain_id) + [_IX(target=_ROUTER, value='0', call_data=leg, chain_id=chain_id)]

# One wei-denominated field off the normalized params, coerced the way every caller assumes.
#
# `or 0` is doing the load-bearing work and it is NOT the same as the get default: the default
# only fires on a MISSING key, while an explicitly null field survives it and reaches `int()`,
# which raises. That raise happens inside `superset`'s blanket try, so it would be swallowed and
# read downstream as "declined this order" -- the failure mode that looks identical to having
# nothing to serve and reports nothing anywhere.
#
# `int()` around a value that is usually already an int is for the string form: these arrive off
# the wire as decimal strings on some intents, and a string amount would compare and arithmetic
# in ways that silently misprice rather than fail.
def _wei(p, field):
    return int(p.get(field, 0) or 0)


def _amounts(p):
    return _wei(p, 'input_amount'), _wei(p, 'min_output_amount')

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


# One token address off the normalized params, in the exact form the rest of this module
# assumes. Every term does work that `_valid_pair` downstream depends on:
#
#   .get(field, '')   a missing key becomes '', which is length 0 -- so the length test reads it
#                     as absent rather than raising on None.
#   `or ''`           an explicit null in the params is ALSO '' . Without it `str(None)` is the
#                     four-character 'None', which is neither 42 long nor a valid address, and
#                     would travel as if it were a token.
#   .lower()          the table is keyed lower-case and so is every comparison here; a
#                     checksummed address from the wire misses every lookup silently.
#
# Written once because it was written twice, and because the two copies are the only reason
# `len(...) == 42` is a sound emptiness test at all -- a future edit to one copy alone would
# quietly break the guard without touching it.
def _token(p, field):
    return str(p.get(field, '') or '').lower()


def _params(s, intent, state):
    p = s._normalized_swap_params(intent, state)
    tin = _token(p, 'input_token')
    tout = _token(p, 'output_token')
    amt, mo = _amounts(p)
    if not _valid_pair(tin, tout, amt):
        return None
    return (tin, tout, amt, mo)
