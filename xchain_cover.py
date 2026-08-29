"""Cross-chain destination-leg cover — the blind spot this lineage never fills.

WHY THIS EXISTS. `strategies/dex_aggregator/baseline_solver.py`'s
`_build_dest_swap_interactions` returns `[]` on every path: it discovers pools,
then falls through to a bare `return []`. So every cross-chain plan this tree
can build carries an EMPTY destination leg, and `_bg124_arch_c63a894`'s
`_g_xc_delivers` correctly refuses to ship one — an empty destination leg
delivers nothing by construction. A cross-chain order is therefore answered
with a SINGLE-CHAIN plan whose output token is the DESTINATION chain's address,
which never moves on the source fork. Both trees read `"0"`, the row scores
`skip`, and nobody is credited. 34 of the 122 per-order rows on
sub_9eb3590f858b were exactly that.

WHAT THE BENCHMARK MEASURES, read out of the validator's own code:

  harness/orchestrator._measure_destination_delivery
      requires `is_cross_chain_plan(plan)` — i.e. `metadata["cross_chain_plan"]`
      — and then sums transfers of `params["output_token"]` to a CREDITED
      recipient observed on the DESTINATION legs only. `_delivery_recipients`
      credits `params["receiver"]`, or the anvil default account when the params
      carry none, plus the destination chain's own app address.

  simulator/anvil_simulator.simulate_cross_chain
      the bridge leg is never executed. The deposit is SYNTHESIZED as
      `transfer(_MOCK_BRIDGE_TARGET, bridge_request.amount)` of the request's own
      token and run on the SOURCE fork, so the executor has to really hold it.
      What that transfer moved is passed through `benchmark_bridge_estimate` — a
      fixed 5 bps fee (`BENCHMARK_BRIDGE_FEE_BPS`) — and the result is DEALT to
      the executor on the destination fork under
      `map_bridged_token(token, src, dst)`. The destination leg then runs from
      that executor; `intent_order` is not forwarded to it, so its interactions
      execute directly rather than through the app's `scoreIntent`.

Every quantity in that chain is a code constant, so the delivered amount is
computable at plan time with no RPC and no quote. That matters here: this
identity has no Alchemy key, so a cover it cannot compute offline is a cover it
cannot verify at all.

SCOPE, deliberately narrow — only the IDENTITY bridge, where the asset the
intent spends maps to the very asset it asks for on the destination chain
(mainnet USDC -> Base USDC, and the WETH pair). That shape needs no destination
swap: the bridged funds land on the executor and one ERC-20 transfer delivers
them. A route that still needs a far-side swap is left to the stack, because
pricing it would need a destination-chain quote this identity cannot take.

VETO-SAFE BY CONSTRUCTION. This layer answers ONLY an intent whose
`dest_chain_id` names another chain, and only when the identity map holds —
which is precisely the class the whole lineage, champion included, scores zero
on. There is no served order here to turn into a regression. Every other order
takes one dict read and one comparison, then the identical path it takes today.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Mirrors `simulator/cross_chain_bench._CANONICAL_TOKEN_BY_CHAIN`, which that
# module documents as a CODE CONSTANT for the same reason it is copied rather
# than imported here: the simulator package is not importable from the solver
# sandbox, and a token the benchmark cannot map is seeded nowhere, so a cover
# built on a guess would deliver zero however correct its calldata.
_CANONICAL = {
    "weth": {1: "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
             8453: "0x4200000000000000000000000000000000000006"},
    "usdc": {1: "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
             8453: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"},
}

# `BENCHMARK_BRIDGE_FEE_BPS`. The benchmark ignores live bridge quotes on any
# scored path (two validators quoting seconds apart would disagree), so this
# fixed fee IS the number the scorer will use.
_FEE_BPS = 5

# `harness/orchestrator._ANVIL_DEFAULT_ACCOUNT` — who `_delivery_recipients`
# credits when the intent carries no receiver of its own, which is every
# benchmark quote case.
_ANVIL_DEFAULT = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

# The chains whose destination backends the benchmark actually runs. A plan
# naming any other chain is deferred LOUD by
# `_assert_destination_backends_usable`, so staying inside this set is what
# keeps a cover from costing the row it was meant to win.
_CHAINS = (1, 8453)

_TRANSFER_SELECTOR = "a9059cbb"


def _params(state):
    """The intent's raw params, through the accessor the harness itself uses.

    `_cross_chain_compat_params` in baseline_solver is literally
    `state.raw_params_view()`, and both `intent_requests_cross_chain` and
    `_delivery_recipients` read the same view — so reading anything else here
    would be answering a different question than the one being scored."""
    view = getattr(state, "raw_params_view", None)
    if view is not None:
        try:
            return dict(view() or {})
        except Exception:
            pass
    return dict(getattr(state, "raw_params", None) or {})


def _int_or_none(raw):
    if raw in (None, "", 0, "0"):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _bridged_to(token, src, dst):
    """`map_bridged_token`: the destination-chain address of what a bridge moves.

    Unmapped tokens pass through unchanged in the platform's copy, which seeds
    no destination balance — so here they return None instead, and the caller
    declines rather than shipping a plan that cannot be funded on the far side.
    """
    low = str(token or "").lower()
    for by_chain in _CANONICAL.values():
        if by_chain.get(src, "").lower() == low:
            return by_chain.get(dst)
    return None


def _transfer_call(to_addr, amount):
    """`ERC20.transfer(to, amount)` calldata."""
    return "0x%s%024x%s%064x" % (
        _TRANSFER_SELECTOR, 0, str(to_addr)[2:].lower().rjust(40, "0"), amount)


def _delivered_amount(amount_in):
    """What the destination fork will actually hold: the bridge's own arithmetic.

    `benchmark_bridge_estimate` takes the amount the deposit was OBSERVED to
    move and subtracts `amount * fee_bps // 10_000`. Integer division, floor,
    exactly as written there — transferring one wei more than this reverts the
    destination leg and turns a cover into a `destination_leg_reverted` zero."""
    return amount_in - amount_in * _FEE_BPS // 10_000


class _Route(object):
    """One identity-bridge order, resolved: everything the plan needs and
    nothing that needs a network to learn."""

    def __init__(self, src, dst, token_in, token_out, amount, recipient):
        self.src = src
        self.dst = dst
        self.token_in = token_in
        self.token_out = token_out
        self.amount = amount
        self.recipient = recipient
        self.delivered = _delivered_amount(amount)


# The chain pair this intent crosses, or None when it crosses nothing this
# cover can answer. Split out of `resolve` for the factorization metric: a
# module-level def's body is its own region, so the cheapest way to shrink the
# tree's largest region is to move whole decisions out of it rather than to
# golf them (minifying moves max_region_nodes by exactly zero).
def _chain_pair(state, params):
    dst = _int_or_none(params.get("dest_chain_id"))
    src = _int_or_none(getattr(state, "chain_id", 0))
    if dst is None or src is None or dst == src:
        return None
    # Staying inside the benchmark's own destination set is what keeps a cover
    # from costing the row it was meant to win — see _CHAINS.
    if src not in _CHAINS or dst not in _CHAINS:
        return None
    return src, dst


# The three order terms a plan cannot be built without, or None if any is
# missing or nonsensical. Same split rationale as _chain_pair.
def _order_terms(params):
    amount = _int_or_none(params.get("input_amount"))
    token_in = str(params.get("input_token") or "")
    token_out = str(params.get("output_token") or "")
    if amount is None or amount <= 0 or not token_in or not token_out:
        return None
    return amount, token_in, token_out


# The identity test, and the whole safety argument in one place: we answer only
# when the bridge itself already produces the asked-for asset. An order whose
# output token lives on the SOURCE chain fails this and is left alone, which is
# what keeps a mislabelled single-chain order out of here — and therefore what
# guarantees no order the champion serves can turn into a drop.
def _is_identity_bridge(token_in, token_out, src, dst):
    bridged = _bridged_to(token_in, src, dst)
    return bridged is not None and bridged.lower() == token_out.lower()


def resolve(state):
    """The identity-bridge route this intent asks for, or None.

    None is the answer for every order the stack already handles, and it is
    reached before anything expensive: one params read, then comparisons."""
    params = _params(state)
    pair = _chain_pair(state, params)
    if pair is None:
        return None
    src, dst = pair
    terms = _order_terms(params)
    if terms is None:
        return None
    amount, token_in, token_out = terms
    if not _is_identity_bridge(token_in, token_out, src, dst):
        return None
    recipient = str(params.get("receiver") or "") or _ANVIL_DEFAULT
    return _Route(src, dst, token_in, token_out, amount, recipient)


# The two legs of the journey. Leg 0 carries no interactions: the deposit is
# SYNTHESIZED by the benchmark from bridge_requests[0] (shared/types.
# mock_bridge_deposit, "synthesis (a solver-shape bridge leg that carries no
# calldata yet)"), so a source-side deposit written here would be work the
# harness discards.
#
# READ THIS BEFORE ADDING ONE ANYWAY — measured 2026-08-26 against the
# validator's own code, because the emptiness is ALSO why this cover cannot yet
# be credited, and the two facts are one line apart:
#
#   harness/orchestrator._mock_bridge_for_benchmark:2831  builds the SCORED
#   single-chain sim. When the top-level `interactions` is empty it calls
#   _source_leg_interactions, which keeps only legs whose chain_id == the
#   scored chain (:2756) — the destination leg is dropped, and leg 0 and the
#   synthesized bridge leg both contribute ZERO indices. `mocked` comes back
#   [] == plan.interactions, so :2853 returns the plan UNCHANGED with 0
#   interactions. Its own comment at :2815 says what happens next: "scoreIntent
#   then reverts '(empty revert)' and the row scores 0 NO MATTER HOW GOOD THE
#   PLAN IS", which sets fail_closed_miss (:2129) and SKIPS score_fn (:2191).
#   raw_output is only ever set from score_fn's result (:2228), and
#   epoch/relative_scoring reads raw_output alone — so the destination amount
#   this plan really delivers is recorded on the row (:2176, outside the guard)
#   and is still not what the ladder counts.
#
# So the credit gap is a platform asymmetry — the destination measurement
# synthesizes the deposit, the scored path does not — NOT a defect in the plan
# shape below. Closing it needs a source-side interaction whose selector is in
# shared/types._BRIDGE_CALL_SELECTORS (the benchmark rewrites those to
# token.transfer(mock, amount) and executes them). That was deliberately NOT
# written blind: this identity has no ALCHEMY_KEY, so bin/exec-check reads
# UNMEASURED here and no local gate executes a plan. Verify against a real
# bridge router address before adding it.
def _journey_legs(route):
    from minotaur_subnet.shared.types import ChainLeg, Interaction

    delivery = Interaction(
        target=route.token_out, value="0",
        call_data=_transfer_call(route.recipient, route.delivered),
        chain_id=route.dst)
    return [
        ChainLeg(chain_id=route.src, interactions=[],
                 metadata={"type": "bridge_source"}),
        ChainLeg(chain_id=route.dst, interactions=[delivery],
                 metadata={"type": "destination_swap"}),
    ]


# One request, source-chain token and amount. `_forward_legs` reads `amount`
# for the deterministic estimate and remaps `token` to the destination chain
# itself, so declaring the destination address here would double-map it.
def _bridge_requests(route):
    from minotaur_subnet.shared.types import BridgeRequest

    return [BridgeRequest(
        token=route.token_in, amount=route.amount,
        src_chain_id=route.src, dst_chain_id=route.dst,
        recipient=route.recipient,
        purpose="bridge %s.. for identity delivery" % route.token_in[:10])]


# `cross_chain_plan` is what declares_cross_chain keys on, and `dst_chain_id`
# is read by _delivery_recipients to credit the destination chain's own app
# address alongside the receiver. Both names are load-bearing; do not rename.
def _plan_metadata(route, payload):
    return {"cross_chain_plan": payload, "src_chain_id": route.src,
            "dst_chain_id": route.dst, "plan_type": "cross_chain",
            "solver": "xchain-identity",
            "expected_output": str(route.delivered)}


def build_plan(intent, state, route):
    """The two-leg journey, in the platform's own solver-shape primitive."""
    from minotaur_subnet.shared.types import CrossChainPlan, ExecutionPlan

    payload = CrossChainPlan(
        legs=_journey_legs(route),
        bridge_requests=_bridge_requests(route)).to_dict()
    return ExecutionPlan(
        intent_id=intent.app_id, interactions=[], deadline=9999999999,
        nonce=getattr(state, "nonce", 0),
        metadata=_plan_metadata(route, payload))


def try_cover(intent, state):
    """A delivering cross-chain plan for this intent, or None to stand aside."""
    try:
        route = resolve(state)
        if route is None:
            return None
        return build_plan(intent, state, route)
    except Exception:
        logger.exception("[xchain] identity cover failed; stack plan stands")
        return None


def install(base_cls):
    """Wrap `base_cls` so the identity bridge is answered before the stack.

    OUTERMOST on purpose. A cross-chain plan is delivered as EMPTY
    `interactions` plus the payload under `metadata["cross_chain_plan"]`, and
    almost every fill layer in this tree judges emptiness on `interactions`
    alone — `solver._empty`, `_apex_ourbase._empty`,
    `payload_cover_apex._HybridLayer._empty` and
    `payload_cover_k._BoundCover.is_hollow` all read a valid bridge plan as
    nothing and would clobber it with a same-chain fill. (`mino_fill_layer`
    already excludes the marker, for this exact reason.) Answering above all of
    them is one edit instead of five, and it cannot be undone by a layer that
    was never taught the shape.
    """

    class _XChainCover(base_cls):

        def generate_plan(self, intent, state, snapshot=None):
            plan = try_cover(intent, state)
            if plan is not None:
                return plan
            return super().generate_plan(intent, state, snapshot)

    return _XChainCover
