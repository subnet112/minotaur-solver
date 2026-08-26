"""Is THIS ORDER a cross-chain delivery? Asked of the state, before any plan exists.

WHY IT IS A SEPARATE QUESTION FROM `empty_rescue.is_cross_chain`
================================================================
That predicate answers "does this PLAN carry a bridge payload?" and is the one
owner for the four layers that had to stop overwriting a bridge plan they had
mis-read as empty (1fc59e2, 85adae2, eca60e8, 2ff4a9b, 6e91880, 586051a). It
can only be asked once a plan has been built.

Two paths in this tree return a plan WITHOUT ever building one, and neither can
use that predicate:

  pacing_bridge._pb_prepare      the outermost generate_plan; on `pace <
                                 _FAST_BELOW_S` it returns `_fast_plan(...)` and
                                 never calls super().
  _apex_champ.JamesSolver._dr20  the same fast path at the governor's own depth,
                                 taken on `_behind_pace()`.

Both hand back `king_base._last_resort_plan`, which is an offline snapshot or a
default-fee Uniswap V3 single hop -- a SOURCE-CHAIN swap in every case. Its own
`eip155:`-prefix refusal (`king_base.py:3451`, `:3998`) does not stop it here,
for the reason `empty_rescue`'s header already records: cross-chain-ness is not
carried on the token. `baseline_solver.py:440` reads it off `dest_chain_id` in
the STATE, and such an order's tokens are ordinary `0x...` addresses.

WHAT THE FAST PATH COSTS ON THOSE ORDERS
========================================
A source-chain plan answering a cross-chain intent is scored
`{"orders": N, "credited": 0, "reasons": {"no_cross_chain_plan": N}}` -- exactly
the block on sub_226692a9b998's verdict. Credited 0 is a DROPPED order and a
hard veto (`epoch/relative_scoring.py` vetoes before the tie-break ladder is
consulted at all), so taking the fast path on such an order is not a cheaper
answer, it is a GUARANTEED ZERO.

Worse, it is a zero that skips the only code that could have served the order.
`_PacingBridge` is installed at `solver.py:544`, above `_GarnetXChain`
(`_bg124_arch_c63a894.py:483`), whose `_g_try_xchain` runs the cross-chain
solver AHEAD of super(). Returning early from `_pb_prepare` means the bridge is
never attempted -- the five commits above stopped later layers from throwing a
bridge plan away; this stops the stack from declining to build one.

WHY IT CANNOT COST A MATCHED ORDER
==================================
The guard only ever DECLINES a fast plan, and only on orders whose fast plan is
credited zero by construction. An order the fast path currently serves for real
is single-chain, so `dest_chain` returns 0 for it and nothing changes. The worst
case is a cross-chain order that spends its own share of the pot and still comes
back with nothing -- scored the same drop it was already getting. The best case
is a bridge plan.

The run pot is not at risk either: the corpus carries 2 such orders
(`cross_chain_delivery.orders` on the last three verdicts) and `_g_xc_call`
bounds each of them at `min(_G_XC_BUDGET_S, _dyn_order_budget)`.

A module rather than a method: both call sites live on different classes in
different files and a copied predicate is the e57efe3 -> dcc15d2 drift this tree
keeps paying for -- the same reasoning that put `pace_pot`, `read_meter`,
`empty_rescue` and `xc_delivery` in their own files, and that keeps
`max_region_nodes` off the two regions that hold the tree's maximum.
"""
from __future__ import annotations
_DR_UNSET = object()
_PREFIX = 'eip155:'

def _token_chain(value, default: int) -> int:
    """The chain an `eip155:<chain>:<addr>` token names, else `default`.

    Mirrors `baseline_solver._normalized_swap_params._dr80`, which parses the
    same prefix through `InteropAddress` and falls back to `state.chain_id` for
    a bare address. Parsed here by hand so this module holds no import of the
    validator's shared types: it is consulted on the fast path, which exists to
    be cheap, and a failed import must not decide routing.
    """
    try:
        text = str(value or '')
        if not text.startswith(_PREFIX):
            return default if text else 0
        return int(text[len(_PREFIX):].split(':', 1)[0])
    except (TypeError, ValueError):
        return default

def _params(state) -> dict:
    """The order's raw parameters, preferring the typed context's token names.

    `_normalized_swap_params._dr33` overlays `typed_context` over the raw params
    before the chain prefixes are read, so a typed order carries its tokens
    there and the raw copy can be stale. Never raises: an unreadable state
    yields `{}`, which reports the order single-chain and leaves every caller on
    the behaviour it had before this module existed.
    """
    out = {}
    try:
        view = getattr(state, 'raw_params_view', None)
        out = dict((view() if callable(view) else getattr(state, 'raw_params', None)) or {})
        typed = getattr(state, 'typed_context', None)
        for key in ('input_token', 'output_token'):
            val = getattr(typed, key, None) if typed is not None else None
            if val:
                out[key] = val
    except Exception:
        return out if isinstance(out, dict) else {}
    return out

def dest_chain(state) -> int:
    """The chain this order must DELIVER on when that is not the source chain, else 0.

    The two signals are the two `baseline_solver` reads before it dispatches to
    `_generate_cross_chain_plan` (`:440`-`:450`), in the same order and with the
    same precedence:

      1. `raw_params['dest_chain_id']`, the explicit declaration;
      2. an `eip155:` chain prefix on the output token that differs from the
         one on the input token -- the `_output_chain != _input_chain` branch,
         which fires only when (1) is absent.

    Returns 0 -- "ordinary single-chain order" -- for anything it cannot read.
    Failing that way keeps this guard inert on every order it does not
    understand, which is the safe direction: the cost of a false 0 is the
    behaviour we already have, while a false non-zero would decline a fast plan
    that was serving an order for real.
    """

    def _dz150():
        src = int(getattr(state, 'chain_id', 0) or 0)
        declared = params.get('dest_chain_id')
        if declared not in (None, '', 0, '0'):
            return (int(declared) if int(declared) != src else 0,)
        source = _token_chain(params.get('input_token'), src)
        dest = _token_chain(params.get('output_token'), 0)
        return (dest if dest and dest != (source or src) else 0,)
        return _DR_UNSET
    try:
        params = _params(state)
        _r_dz150 = _dz150()
        if _r_dz150 is not _DR_UNSET:
            return _r_dz150[0]
    except (TypeError, ValueError, AttributeError):
        return 0