"""Decode the CHAMPION'S OWN swap route out of its plan, into the descriptor our
own quote batch already speaks.

WHY THIS EXISTS: `blind_spot_repeat`, THE ROW THE VALIDATOR CALLS MOST ACTIONABLE
=================================================================================
The adoption ladder has three outcomes on an order the champion delivers 0 on:

    blind_spot_cover   we delivered AND beat its adoption-time value    -> +1
    blind_spot_repeat  we delivered but did not beat it -- NEUTRAL, 0
    dropped            no plan on a champion-SERVED order               -> -1

Measured 2026-08-27 on HEAD 9641fcb, `state/last-perf-ab.json`: 22 of 220
scenarios carry `live_champ_zero: true`, and on EVERY ONE of them our
`our_legs_detail` is BYTE-IDENTICAL to `champ_legs_detail`. Four are live
`quote:q_*` rows rather than replayed history:

    q_f46626a0c7ff256a86be1d3ed0abf50c   8453  MORPHO -> WETH
    q_4c7f3ebd7620032f22470c645f013c71   8453  WELL   -> USDC
    q_fff02cb4b2a34d746699ffe4752a6ca3   8453  weETH  -> USDT
    q_ef2534ad611df357cb13f562113ba6d7      1  (Balancer-style router leg)

Byte-identical plans cannot deliver different amounts, so all four are repeats:
we are in reach on every one of them and score zero on every one of them. That
is the whole of the gap between the tree's current `122 rows better=0 worse=0
dropped=0 net=+0` and the `net >= +1` rung 1 needs.

WHY THE COVER LADDER NEVER SEES THEM
====================================
`solver.Bg124Solver.generate_plan` runs the ladder on `_empty(self, plan)` --
the champion returned NO interactions. On these rows it returns two: an approve
and a `exactInputSingle`. So the plan is not empty, `bar = _expected(plan)` is
taken, and both branches below it hand the champion plan straight back. The
ladder is gated on the champion being SILENT, and this champion is not silent --
it is WRONG. It emits a default-fee single hop into a pool that does not hold
the pair, quotes itself a number, and delivers nothing.

WHY DECODING IT IS THE SAFE WAY IN, AND METADATA IS NOT
=======================================================
The blind branch that used to override on `bar <= 0` was closed for cause and
must not be reopened: `solver.py:388` records the price -- the A/B found all 50
override-on-served rows carrying `live_champ_zero: false`, and sub_e171b56c05b5
paid 7 better against 14 DROPPED. That branch judged the champion on METADATA,
which is its own claim about itself, and a claim is not a measurement.

This module makes the measurement instead. It returns the champion's route as a
descriptor in the exact `("single", fee, None)` / `("path", fees, mid)` /
`("v2", router, path)` vocabulary `bg124_onfork._v3_cands` and `._v2_cands`
already emit -- so the champion's own route is ALREADY A CANDIDATE IN OUR BATCH,
at a known index, quoted on the same fork block that will execute it, for no
extra eth_call at all. `dead_cover` reads that one slot. A route the fork quotes
at zero delivers zero; there is no third possibility, and no metadata is
consulted anywhere in the chain.

FAILING CLOSED IS THE WHOLE CONTRACT. Every unreadable shape returns None, and
None leaves the caller on the champion plan it has today. A false None costs the
cover we might have won; a false decode would aim the override at a live order,
which is the 14-drop shape above. So the shapes admitted are only the ones whose
layout is pinned by the router ABI, and each is checked field by field.

NO `eth_abi` HERE, deliberately. Every argument in the admitted shapes is a
fixed 32-byte word, so a hex slice reads them exactly; pulling in the decoder
would add an import whose failure mode is an exception on the plan path in
exchange for nothing. `bg124_onfork_intent._valid` states the same preference
for the same reason.
"""
from __future__ import annotations

_APPROVE = '095ea7b3'
_SINGLE = '04e45aaf'


def _words(cd, want):
    """`cd`'s argument words as lowercase hex, or None unless there are `want`.

    Exactly `want` -- not "at least". A trailing word this module does not know
    about means the selector is not the ABI it was matched against, and a
    misread route is the one failure this file may not have.
    """
    try:
        body = str(cd or '')[10:]
        if len(body) != want * 64:
            return None
        return [body[i * 64:(i + 1) * 64].lower() for i in range(want)]
    except (TypeError, ValueError, AttributeError):
        return None


def _field(ix, name):
    """`ix.name`, falling back to `ix[name]`, as a string -- '' when neither.

    Both shapes are read because `Interaction` is a dataclass on the plan path
    and a plain dict everywhere a plan has been round-tripped through JSON. A
    reader that knew only one of them would return None on the other, which
    fails closed but silently stops covering an entire class of order.
    """
    got = getattr(ix, name, None)
    if got is None and isinstance(ix, dict):
        got = ix.get(name)
    return str(got or '')


def _sel(ix):
    """`(selector, target)` of one interaction, both lowercase, else `('', '')`."""
    try:
        return _field(ix, 'call_data')[2:10].lower(), _field(ix, 'target').lower()
    except (TypeError, ValueError, AttributeError):
        return '', ''


def _addr(word):
    """The 20-byte address in a 32-byte word, or '' if the padding is not zero."""
    return '0x' + word[24:] if word[:24] == '0' * 24 else ''


def _int(word):
    try:
        return int(word, 16)
    except (TypeError, ValueError):
        return -1


def _single(words):
    """`exactInputSingle` -> `(("single", fee, None), tin, tout, amt, min_out)`.

    SwapRouter02's struct is the 7-word
    `(tokenIn, tokenOut, fee, recipient, amountIn, amountOutMinimum,
    sqrtPriceLimitX96)` -- no `deadline`, which is what distinguishes it from the
    original SwapRouter and why the word count is checked rather than assumed.
    """
    tin, tout = _addr(words[0]), _addr(words[1])
    fee, amt, min_out = _int(words[2]), _int(words[4]), _int(words[5])
    if not tin or not tout or fee <= 0 or amt <= 0 or min_out < 0:
        return None
    return ('single', fee, None), tin, tout, amt, min_out


def _shape(plan):
    """`(approve_leg, swap_leg, token, router)` for the one admitted shape, else None.

    That shape is `[approve(spender, amt), exactInputSingle(...)]` on that same
    spender -- what all four live blind spots in the header carry, and what the
    champion emits for a pair it has no route for.

    REGION DISCIPLINE, and it is the reason this is not one function with
    `_bind`. `route_of` measured 185 nodes as a single body against a tree whose
    maximum was 139; `lib/budget_audit.py` scored it the largest region in the
    repo on the first audit after it was written. Splitting into named helpers is
    the ONLY move that lowers `max_region_nodes` -- minifying or one-lining moves
    it by exactly zero -- and the module docstrings of `bg124_onfork` and
    `bg124_onfork_intent` record this tree paying for the same lesson twice.
    """
    try:
        ix = list(getattr(plan, 'interactions', None) or [])
    except (TypeError, ValueError):
        return None
    if len(ix) != 2:
        return None
    a_sel, token = _sel(ix[0])
    s_sel, router = _sel(ix[1])
    if a_sel != _APPROVE or s_sel != _SINGLE or not router:
        return None
    return ix[0], ix[1], token, router


def _bind(approve, swap, token, router):
    """The decoded route, once the two legs are known to agree with each other.

    The approve leg is not decoration: it pins the swap target as the contract
    the tokens were actually approved to, so a two-interaction plan whose second
    leg merely shares a selector cannot be read as a route to somewhere else.
    """
    a_words = _words(_field(approve, 'call_data'), 2)
    s_words = _words(_field(swap, 'call_data'), 7)
    if a_words is None or s_words is None:
        return None
    if _addr(a_words[0]) != router:
        return None
    got = _single(s_words)
    return got if got is not None and got[1] == token else None


def route_of(plan):
    """The champion plan's route as `(desc, tin, tout, amt, min_out)`, else None.

    `exactInput` (`0xb858183f`) and V2 `swapExactTokensForTokens` (`0x38ed1739`)
    are deliberately NOT decoded. Their argument words are dynamic offsets rather
    than values, so reading them needs the real decoder, and no measured blind
    spot wears either shape today. Adding one is a change to `_shape` and
    `_bind`; nothing downstream knows the difference.
    """
    got = _shape(plan)
    return None if got is None else _bind(*got)
