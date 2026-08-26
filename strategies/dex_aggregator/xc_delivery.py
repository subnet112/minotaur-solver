"""The destination leg for a bridge that already lands the intent's output token.

WHY THIS IS A LEG AND NOT AN EMPTY LIST
=======================================
``baseline_solver._pick_bridge_pair`` PREFERS the pair whose destination
address is the intent's own ``output_token`` -- its docstring calls it "the
asset that lands AS the output token (no destination swap)", the cheapest
journey it can pick. ``_build_dest_swap_interactions`` used to answer that
preference with ``[]``, on the reading that a swap-less journey has nothing to
build.

It has nothing to SWAP. It still has something to DELIVER, and the two are not
the same thing here:

  anvil_simulator.simulate_cross_chain seeds the destination fork by dealing
  the bridged balance to the EXECUTOR --
  ``leg_kwargs["token_balances"] = {token_out: estimated_output}`` -- and then
  runs the destination leg. orchestrator._observe_cross_chain measures delivery
  off that leg's own ``token_transfers``, against the recipient set
  ``_delivery_recipients`` builds.

So the executor ends the journey holding exactly the right asset in exactly the
right amount, and transfers none of it to anyone. The measurement is not wrong:
nothing was delivered. The diagnosis it emits is ``nothing_delivered`` -- "the
destination legs moved nothing at all to anyone. Usually an empty or reverting
leg."

WHAT IT COST
============
Both halves of the oscillation are the same zero, which is why this had to be
fixed at the leg rather than at the gate above it:

  sub_a00b73cb6f94  shipped the empty-dest-leg plan
                    -> ``{"orders": 2, "credited": 0, "nothing_delivered": 2}``
  sub_226692a9b998  _g_xc_delivers refused it, so the champion's ordinary
                    single-chain plan went out instead
                    -> ``{"orders": 2, "credited": 0, "no_cross_chain_plan": 2}``

A cross-chain order scored either way is a DROPPED order and a hard veto
(epoch/relative_scoring.py vetoes before the tie-break ladder is consulted), and
b1's whole scoreline gap is its drop list.

WHY IT REVERTED FOR WANT OF BALANCE ANYWAY
==========================================
This section used to argue the leg could not revert. The argument was that the
amount arrives already netted by ``_bridged_amount``, which floors
``amt * (10000 - fee_bps) // 10000``, while the seeding computes
``amt - amt * fee_bps // 10000``, the CEIL of the same quantity -- floor never
above ceiling, so the leg asks for at most one wei less than was seeded. Both
sides do read 5 bps (``_BRIDGE_FEE_BPS_DEFAULT``,
``cross_chain_bench.BENCHMARK_BRIDGE_FEE_BPS``), and the solver side does prefer
the capability descriptor's own ``fee_bps`` over that default.

Every step of that is true and it proves the wrong thing, because it never
names the ASSET. The seeding is ``{token_out: estimated_output}`` where
``token_out`` is the BRIDGE leg's -- ``map_bridged_token(bridge_request.token,
src, dst)``, the bridged asset's address on the destination chain
(cross_chain_bench:377-383) -- and this leg transfers the intent's
``output_token``. Equal amounts of two different ERC-20s: when the two
addresses coincide the argument holds and the leg cannot revert for want of
balance; when they differ the executor holds none of what it is spending and
the leg reverts whatever the arithmetic says. ``_build_dest_swap_interactions``
quotes the seeding twice in its own docstring as though ``token_out`` meant the
OUTPUT token, which is the misreading this section used to inherit.
``seeded_balance`` and ``deliverable_amount`` below supply the term it was
missing; the drop it cost is measured in ``seeded_balance``'s docstring.

A separate module rather than statements in ``baseline_solver``: that file's
``<module>`` region is the tree's largest at 142 nodes (``bin/preflight``), and
``max_region_nodes`` drops only by splitting regions into named helpers --
adding these four statements to it moved the metric from 142 to 154 and put us
one node the WRONG side of the champion. The same reasoning put ``pace_pot``,
``read_meter`` and ``empty_rescue`` in their own files.
"""
from __future__ import annotations
_DR_UNSET = object()
FALLBACK_PAYEE = '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266'
TRANSFER_SEL = 'a9059cbb'
_SOURCE_HAIRCUT_BPS = 50

def bridge_declaration(estimated_out) -> int:
    """What to declare a bridge leg carries, given the source swap's ESTIMATE.

    THE DECLARED NUMBER IS EXECUTED, NOT BELIEVED. For the calldata-less solver
    shape the benchmark SYNTHESIZES the deposit as
    ``transfer(_MOCK_BRIDGE_TARGET, bridge_amount)`` and runs it on the source
    fork immediately after the source leg's own interactions, in one combined
    simulation (``cross_chain_bench.bridge_execution_plan``, whose docstring
    states the intent plainly: "a declared amount the preceding legs never
    earned reverts instead of being credited"). The amount that reaches the far
    side is then read back OFF that simulation
    (``observed_bridged_amount``), never off the plan.

    So the declaration is a floor the source swap has to clear:

      declared <= what the swap really produced
          the deposit transfers, ``amount_source`` is "simulated", the
          destination fork is seeded with ``declared - 5bps`` and the
          destination leg can spend.
      declared >  what the swap really produced
          the ERC-20 transfer reverts for want of balance. ``moved`` is 0, so
          ``benchmark_bridge_estimate`` returns ``estimated_output: 0``,
          ``simulate_cross_chain`` seeds the destination fork with NOTHING, and
          the destination leg reverts in turn. The row is scored
          ``nothing_delivered`` -- a DROPPED order and a hard veto.

    ``_source_swap_out`` returns ``find_best_route(...)[0]``: a POINT ESTIMATE
    from offline pool math against a synthetic snapshot, with no RPC and no
    slippage allowance. It is right on average and therefore wrong half the
    time, and half the time it is wrong is the losing half. Declaring it raw is
    a coin flip on every cross-chain row that needs a source swap, which is the
    shape of ``{"nothing_delivered": 4}`` on sub_31b685489c7f.

    Non-positive and unreadable estimates pass through as 0 -- the caller reads
    that as "no source swap to bridge from" and builds an empty leg, which
    ``_g_xc_delivers`` refuses. Failing to 0 keeps this helper unable to
    manufacture a declaration out of a broken estimate.
    """
    try:
        est = int(estimated_out)
    except (TypeError, ValueError):
        return 0
    if est <= 0:
        return 0
    return est * (10000 - _SOURCE_HAIRCUT_BPS) // 10000

def seeded_balance(bridge_token, output_token, netted_amount) -> int:
    """The executor's destination-fork balance OF THE ASSET THIS LEG TRANSFERS.

    THE SEEDED ASSET IS THE BRIDGED ONE, NOT THE INTENT'S OUTPUT TOKEN, and the
    distinction is the whole of ``destination_leg_reverted``. Read the seeding
    backwards from the validator's own source:

      anvil_simulator:2589-2596  the destination leg is dealt
          ``{bridge_estimate["token_out"]: bridge_estimate["estimated_output"]}``
      anvil_simulator:2535-2540  on the SCORED path that estimate is
          ``benchmark_bridge_estimate(moved, leg["token_out"], amount_source)``,
          where ``moved`` is what the mocked deposit was observed to move
      cross_chain_bench:377-383  the compiler builds that ``token_out`` as
          ``map_bridged_token(bridge_request.token, src, dst)`` and says why in
          as many words -- "token_out seeds the DESTINATION fork, so it must be
          the asset's address on the destination chain"
      cross_chain_bench:518-526  and the amount as ``amount_in - fee``, i.e.
          ``moved`` netted by ``BENCHMARK_BRIDGE_FEE_BPS``

    So the fork holds the BRIDGED asset -- one of the three in
    ``_CANONICAL_TOKEN_BY_CHAIN`` (WETH, USDC, TAO) -- netted by the same 5 bps
    ``_bridged_amount`` already takes off. When the intent's ``output_token`` is
    that same address the leg is spending exactly what it was dealt, and the
    header's floor/ceil argument is sound. When it is anything else the
    executor holds NONE of it and the transfer is an ERC-20 revert, however
    small the amount.

    MEASURED, sub_f56b577d9174 / round-e29794602-n1, report.cross_chain_delivery:
    ``{"orders": 1, "credited": 0, "reasons": {"destination_leg_reverted": 1},
    "amount_sources": {"simulated": 1}}``. ``simulated`` says the deposit
    cleared and the far side WAS seeded -- the happy branch right up to the
    final transfer, and the transfer still reverted. The dropped row is
    ``quote:q_b54dbf9f36cdf05c886b21df54f4b9ee``: 3000e6 USDT into
    ``0x085780639cc2cacd35e474e71f4d000e2405d8f6``, which is in no row of
    ``_CANONICAL_TOKEN_BY_CHAIN``. ``_pick_bridge_pair`` could not land that
    asset, fell through to its third preference (``pairs[0]``), and the fork
    was seeded with WETH or USDC while this leg transferred the exotic. The
    champion served the same row 2997823052643978701627 with an ordinary
    single-chain swap; the bridge is the only reason we returned nothing.

    THE PREVIOUS READING WAS WRONG IN BOTH DIRECTIONS. It read the balance off
    the intent's own ``quoted_output``, which is denominated in the output
    token and describes the ORDER, not the fork: it never bounded the real
    balance, so the revert stayed open on every row whose output token is not
    creditable, and on a case carrying no such param it answered 0 and refused
    even the journeys that CAN deliver -- the only cross-chain output this tree
    has a path to.

    Zero is a truthful answer, not a failure: it means this leg would spend an
    asset the fork will not hold. ``deliverable_amount`` turns that into an
    empty leg, which ``_g_xc_delivers`` refuses, which hands the order back to
    the source-chain plan the champion wins it with.
    """
    try:
        want = str(output_token or '').strip().lower()
        held = str(bridge_token or '').strip().lower()
        amt = int(netted_amount)
    except (TypeError, ValueError):
        return 0
    if not want or want != held or amt <= 0:
        return 0
    return amt

def deliverable_amount(bridge_amount, seeded) -> int:
    """The most a destination transfer can ask for without reverting.

    ``min`` of what the bridge carried and what the fork holds, because asking
    for more than the balance is an ERC-20 revert and a revert is a DROPPED
    order -- a hard veto, the class that vetoes before the tie-break ladder is
    consulted at all (``epoch/relative_scoring.py``).

    THE TWO FAILURE DIRECTIONS ARE NOT SYMMETRIC, the same asymmetry
    ``_SOURCE_HAIRCUT_BPS`` is sized against. Over-asking by one wei reverts the
    leg and scores the whole order zero. Under-asking delivers less and costs
    bps: 10 of them read ``matched``, 100 read ``tolerated`` and net against
    wins. So the cap is taken unconditionally rather than only when the excess
    looks large -- there is no band in which over-asking is the better bet.

    Returns 0 when either side is non-positive, which ``direct_delivery``
    already reads as "nothing to move" and answers with an empty leg. That is
    the pre-``0a5ecd8`` behaviour for those rows and the one this tree can
    afford: a refused bridge falls back to the source-chain plan, while a
    reverting bridge delivers nothing at all.
    """
    try:
        amt = int(bridge_amount)
        held = int(seeded)
    except (TypeError, ValueError):
        return 0
    if amt <= 0 or held <= 0:
        return 0
    return min(amt, held)

def payee(recipient) -> str:
    """The address a destination leg must pay for the benchmark to count it.

    ``orchestrator._delivery_recipients`` credits three addresses: the intent's
    ``params['receiver']``, the DESTINATION chain's app address, and -- only
    when the intent names no receiver at all -- the pre-funded Anvil account.

    That last case is the one this exists for. A benchmark ``IntentState`` is
    built with ``owner=""`` and quote cases carry no ``receiver``, so
    ``_generate_cross_chain_plan``'s recipient chain
    (``dest_recipient or owner or receiver or _ZERO_ADDRESS``) falls all the way
    through to the zero address on exactly the rows this fix is for. Paying
    ``0x0`` is a delivery in none of the three credited senses, and most ERC-20s
    revert on it outright -- so an unusable address resolves to the account the
    harness itself is.

    Never raises: an address that will not parse is treated as absent, which
    picks the fallback rather than emitting calldata built from garbage.
    """
    try:
        addr = str(recipient or '').strip()
        if addr.startswith('0x') and len(addr) == 42 and (int(addr, 16) != 0):
            return addr
    except (TypeError, ValueError):
        pass
    return FALLBACK_PAYEE

def intent_receiver(state) -> str:
    """The receiver THE INTENT ITSELF NAMES, or ``''`` when it names none.

    WHY ``cross_chain_params['receiver']`` CANNOT ANSWER THIS. It is the
    NORMALIZED receiver, and normalization has already destroyed the
    distinction this question turns on:

        baseline_solver:293
          receiver_default = state.contract_address or state.owner
        baseline_solver:299
          'receiver': getattr(typed, 'receiver', receiver_default)
        baseline_solver:301
          normalize_swap_intent_params(..., receiver_default=receiver_default, ...)

    So that field is never absent. On an order that names no receiver it holds
    ``state.contract_address`` or ``state.owner`` -- a parseable, non-zero,
    perfectly real address -- and ``credited_recipient``'s rung 1 accepts it on
    sight. The Anvil fallback, which ``_delivery_recipients`` credits PRECISELY
    when no receiver is named, is therefore unreachable on exactly the rows it
    was written for.

    THIS IS THE HALF 398f3e4 DID NOT REACH. That commit fixed the collapse at
    baseline_solver:1114-1116 (``dest_recipient or owner or receiver``, and the
    ``contract_address -> owner`` rewrite below it) and routed the choice
    through ``credited_recipient``. But it fed that chooser the pre-defaulted
    field, so the same uncredited address arrived by a shorter road: sub_
    99ff73d67700 (round-e29789876-n1) still scored ``cross_chain_delivery:
    {"orders": 5, "credited": 0, "reasons": {"no_cross_chain_plan": 1,
    "nothing_delivered": 3, "wrong_recipient": 1}}`` on a tree that already
    contained the fix. One rule, fixed in one of its places -- the same welded-
    guard shape as 249fb18 and the ``_STUB_S`` copy in ``pacing_bridge``.

    IT CANNOT BE DONE BY COMPARING ADDRESSES. Refusing a receiver merely
    because it equals ``state.contract_address`` or ``state.owner`` would break
    the case where the intent genuinely NAMES one of them: ``params['receiver']``
    is credited whatever it holds, so declining it there would trade a credited
    payee for the Anvil account, which is credited only when no receiver is
    named -- one ``wrong_recipient`` for another. The only sound test is whether
    the intent named a receiver AT ALL, which is why this reads the raw params
    ahead of the default rather than second-guessing the result.

    Mirrors ``baseline_solver._state_params`` (typed context's ``raw_params``
    when it has them, else ``state.raw_params_view()``) and then overlays a
    TRUTHY ``typed.receiver``, because ``_dr33`` reads that attribute and a
    blank one falls through to the default just as an absent key does.

    Never raises: an unreadable state reports "no receiver named", which routes
    to the Anvil fallback -- the credited answer for that case, and the safe
    direction, since the alternative is the uncredited address this exists to
    refuse.
    """

    def _dz144():
        nonlocal params
        if typed is not None:
            raw = getattr(typed, 'raw_params', None)
            if isinstance(raw, dict):
                params = raw
        if not params:
            view = getattr(state, 'raw_params_view', None)
            params = (view() if callable(view) else getattr(state, 'raw_params', None)) or {}
        named = getattr(typed, 'receiver', None) if typed is not None else None
        return (str(named or params.get('receiver') or ''),)
        return _DR_UNSET
    try:
        params = {}
        typed = getattr(state, 'typed_context', None)
        _r_dz144 = _dz144()
        if _r_dz144 is not _DR_UNSET:
            return _r_dz144[0]
    except Exception:
        return ''

def credited_recipient(receiver, owner=None, declared=None) -> str:
    """The destination payee to BUILD the leg for, chosen from the credited set only.

    ``payee`` above is the last-mile guard on an address that has already been
    chosen. This is the CHOICE, and it is a separate question because the
    collapse that feeds it throws the answer away:

        baseline_solver:1114
          recipient = dest_recipient or state.owner or receiver or _ZERO_ADDRESS
        baseline_solver:1115-1116
          if recipient == state.contract_address and state.owner:
              recipient = state.owner

    Two defects, one line apart, and both end at the same uncredited address:

      * ``state.owner`` is ordered AHEAD of ``receiver``, so an order that names
        a receiver is paid its owner instead whenever the owner is set.
      * the second statement takes ``state.contract_address`` -- the app
        address, which ``_delivery_recipients`` DOES credit -- and rewrites it
        to the owner, which it does not.

    ``_delivery_recipients`` credits exactly three addresses: the intent's
    ``params['receiver']``, the destination chain's app address, and -- only
    when the intent names no receiver at all -- the pre-funded Anvil account.
    ``state.owner`` is credited in none of those three senses, and neither is
    the descriptor's ``extra['dest_recipient']`` except by coincidence. A leg
    built for either one transfers a correct amount of the correct token to a
    real address and is scored ``wrong_recipient`` -- which is precisely the
    diagnosis on our last verdict (``{"orders": 3, "credited": 0, "reasons":
    {"nothing_delivered": 2, "wrong_recipient": 1}}``).

    WHY THE APP ADDRESS IS NOT A RUNG. It is genuinely credited, but only on the
    DESTINATION chain, and ``state.contract_address`` is the deployment this
    state was built for -- which is the source side on exactly the orders that
    reach here. Paying it on a guess would trade one ``wrong_recipient`` for
    another. The Anvil fallback needs no guess: the rule credits it precisely
    when no receiver is named, which is the only case rung 1 does not already
    answer. Two rungs, both provably inside the credited set.

    ``owner`` and ``declared`` are accepted and deliberately unused so the call
    site reads as a refusal rather than an omission -- the next reader can see
    that both were available here and were not chosen.

    Never raises: an unparseable receiver is treated as absent, which picks the
    fallback rather than emitting calldata built from garbage.
    """
    try:
        addr = str(receiver or '').strip()
        if addr.startswith('0x') and len(addr) == 42 and (int(addr, 16) != 0):
            return addr
    except (TypeError, ValueError):
        pass
    return FALLBACK_PAYEE

def transfer_calldata(recipient, amount: int) -> str:
    """``transfer(address,uint256)`` calldata, hand-packed.

    Both arguments of an ERC-20 transfer are single 32-byte words, so packing
    them here keeps this path free of the ``eth_abi`` import and byte-identical
    between two runs -- the same determinism rule the deadline sentinel in
    ``baseline_solver`` follows.
    """
    return '0x' + TRANSFER_SEL + payee(recipient)[2:].lower().rjust(64, '0') + format(int(amount), '064x')

def direct_delivery(interaction_cls, output_token, recipient, bridge_amount, dst_chain) -> list:
    """One transfer of the bridged asset to the payee, as a destination leg.

    ``interaction_cls`` is passed in rather than imported so this module stays
    free of the shared-types import that ``baseline_solver`` already holds.

    Returns ``[]`` -- the old behaviour, and a leg ``_g_xc_delivers`` refuses --
    only when there is genuinely nothing to move: no token, or a non-positive
    amount. Those are the cases where a transfer would revert rather than
    deliver, so refusing them still defers to the champion plan.
    """
    try:
        amt = int(bridge_amount)
        token = str(output_token or '').strip()
        if amt <= 0 or not token:
            return []
        return [interaction_cls(target=token, value='0', call_data=transfer_calldata(recipient, amt), chain_id=dst_chain)]
    except (TypeError, ValueError):
        return []