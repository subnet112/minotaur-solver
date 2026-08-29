"""Reading the ORDER out of an IntentState, for the on-fork cover router.

WHY THESE FOUR LEFT `bg124_onfork`
==================================
That module's own header already states the rule this file follows:

    REGION DISCIPLINE: the calldata/ABI layer lives in bg124_onfork_abi.py and
    the tables in onfork_tables.json (JSON = zero AST nodes), because a single
    module holding every def pushed its top-level region past the champion's
    own maximum -- winning orders is worthless if the tie-break then hands over
    the crown.

`bg124_onfork.<module>` was the tree's MAXIMUM region at 140 nodes
(`lib/budget_audit.py`, sha 9a995df), and `max_region_nodes` drops only by
splitting regions into named helpers -- minifying or one-lining moves it by
exactly zero. Four `def` HEADERS moved out of that region is a real reduction;
the `from ... import` that replaces them is one statement.

The same reasoning already put `_install_fallback_venues`' nested defs behind an
installer in that file, and `pace_pot`, `read_meter`, `empty_rescue`,
`xc_delivery` and `xc_order` in files of their own.

WHY THIS GROUP AND NOT ANOTHER
==============================
These four are the whole of the module's INTENT-READING layer and they are the
only top-level group in it that touches no routing state: they take a state and
a params dict and return plain data. Nothing here calls `_types()`, so this
module holds no import of the validator's shared types and cannot participate in
an import cycle with `bg124_onfork` -- which is why `_plan` STAYED behind. It
reads `ExecutionPlan` off `_types()` and moving it here would have created one.

`bg124_onfork_abi as A` is imported for `_valid` alone, which tests the chain
against the quoter table. That is the same module `bg124_onfork` already imports
and it imports nothing back, so the edge is safe.

IMPORTED UNDER THEIR OWN NAMES, deliberately. The call sites in `_route` and
`_cover` are untouched -- `_parse(state)`, `_recipient(state, p)`, exactly as
before. Rebinding them as `I.parse(...)` would have added an attribute load to
each call site, and `_cover` is itself a 138-node region one node under the two
that hold the tree's maximum: paying for this reduction out of that region would
have moved the metric by nothing at all.
"""
from __future__ import annotations

import bg124_onfork_abi as A


def _num(p, key):
    """`p[key]` as a non-negative int, or -1 when it will not parse.

    -1 rather than 0 because `_valid` tests `amt > 0` and `min_out >= 0`: a
    zero would read as a legitimate `min_output_amount` and admit an order
    whose amount field was unreadable.
    """
    try:
        return int(p.get(key, 0) or 0)
    except (TypeError, ValueError):
        return -1


def _valid(tin, tout, amt, min_out, chain):
    """Is this an order this router can quote at all?

    The chain test is the load-bearing one: every candidate builder reads
    `A.T["quoter"][str(chain)]`, so a chain absent from that table raises
    KeyError inside `try_cover`'s except and reads exactly like "no route
    found". Refusing it here keeps that failure a decision rather than an
    exception.
    """
    return (amt > 0 and min_out >= 0 and tin.startswith("0x")
            and tout.startswith("0x") and str(chain) in A.T.get("quoter", {}))


def _parse(state):
    """(p, tin, tout, amt, min_out, chain) or None."""
    p = dict(getattr(state, "raw_params", {}) or {})
    tin = str(p.get("input_token", "") or "").lower()
    tout = str(p.get("output_token", "") or "").lower()
    amt, min_out = _num(p, "input_amount"), _num(p, "min_output_amount")
    chain = int(getattr(state, "chain_id", 0) or 0)
    if not _valid(tin, tout, amt, min_out, chain):
        return None
    return p, tin, tout, amt, min_out, chain


def _recipient(state, p):
    """Who the swap leg pays.

    Order preserved byte-for-byte from `bg124_onfork`. This is a SOURCE-chain
    swap on the chain that is executing, so the cross-chain credited-recipient
    ladder in `strategies/dex_aggregator/xc_delivery.credited_recipient` does
    not apply here and must not be welded in: that ladder exists to reach the
    Anvil fallback on orders naming no receiver, and it is scored off
    `_delivery_recipients` on the DESTINATION fork.
    """
    return str(getattr(state, "contract_address", "") or p.get("receiver", "")
               or getattr(state, "owner", "")
               or "0x0000000000000000000000000000000000000001")
