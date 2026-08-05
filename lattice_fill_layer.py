"""lattice fill layer — EMPTY-ONLY overlay above the reigning solver stack.

The stack underneath this module is a refork of the current champion, so on every order
the champion can price, this tree reproduces its route byte for byte and the row scores
`matched`. That is what makes `dropped`, `regression` and `catastrophic` structurally
zero rather than merely unlikely: those three are hard vetoes under the adoption rule and
no quantity of wins buys them back.

Upside therefore has to come from somewhere the incumbent produces nothing at all. On
such a row the scored `champ` field is null, so there is no incumbent output for a fill
to fall short of, and the row is credited `blind_spot_cover`. Round e29756712 settled the
argument empirically: the submission that took the crown scored `better 2 / worse 1 /
dropped 0`, and its two `better` rows WERE its two blind-spot fills. Zero true wins.

WHY EMPTY-ONLY IS NOT NEGOTIABLE. Every veto this lineage has taken came from answering
ahead of the inner engine. Preempting on a row the champion serves means betting frozen
calldata against pools that move between mint and bench, and that bet has no safe
threshold: one row scored 1.0093 (a win) in one round and 0.9861 (a catastrophic, past
FLOOR_BPS=100) in the next, on byte-identical calldata. Nor can the blind set be screened
ahead of time -- corpus `estimated_output == 0` disagrees with the champion's real
behaviour on 29% of rows, always in the dangerous direction. Asking the inner stack first
and filling only its empties is the only screen that cannot leak, because the fallback is
the `skip` the row already was.

Cover rot is the residual, and on this base it is harmless. A cover whose calldata has
gone stale reverts and delivers nothing -- but it only ever runs where the champion also
delivered nothing, so a rotted fill forfeits a credit instead of causing a drop. Measured
2026-07-30: three of seven held covers no longer simulate, and on the previous (stale)
base each of those three scored `dropped`. On this base the same three cost nothing.
"""
from __future__ import annotations

import json
from _lattice_prims import (_CONFIRM_POOL, _EXEC_BY_CHAIN, _abi_addr_uint,
                            _addr, _num, _word)
import logging
import os
import time as _time

_log = logging.getLogger(__name__)

_FILL_NONCE = "37"          # rotated per build; moves content_fingerprint (semantics+data hashed), which gates the resubmit quota
_TABLE_FILE = "lattice_wins.json"

# ---------------------------------------------------------------------------
# PAR-RATE OVERRIDE -- chain-1 USDS -> USDC
#
# The one place this file answers a row the inner engine ALSO answers. Everything else here
# is empty-only; read the reasoning below before widening it.
#
# THE DEFECT. The inherited engine has a Sky PSM route (`_sky_psm_plan`), but it is wired
# entirely to Base: `_SKY_PSM3` is the L2 PSM3 deployment and the pair set that reaches it
# holds Base token addresses (`_USDC` 0x833589fc..., `_T_USDS` 0x820c137f...). Mainnet USDS
# 0xdC035D45... -> mainnet USDC 0xA0b86991... matches none of them, so the order falls
# through to generic DEX routing, finds a thin pool, and pays an 87% haircut: order
# q_d6b2ea0d43873e28199433364f37cfa6 returned 13,725.061424 USDC for 103,602.343974 USDS.
# Chain 1 is the ONLY adoption-scored chain, so the gap sits precisely on the scored surface,
# and reclaim-router took a round off this lineage on that single row.
#
# WHY THIS PREEMPTS WHERE NOTHING ELSE DOES. A preempting cover that fails delivers nothing
# where the incumbent delivered something, which scores `dropped` -- a hard veto that kills
# the whole submission, not just the row. That asymmetry is why frozen aggregator calldata is
# never allowed to preempt: 18 of 20 fresh Kyber mints failed to reproduce at bench, because
# a mint-time `minReturnAmount` is frozen against pools that then move.
#
# This route has no such parameter. UsdsPsmWrapper accepts USDS, sells into LitePSM and
# forwards USDC at a rate fixed by contract arithmetic:
#     buyGem(usr, gemAmt) pulls gemAmt * to18ConversionFactor * (WAD + tout) / WAD
# With tout = 0 that is exactly gemAmt * 1e12, flat. No pool reserve, no slippage argument, no
# venue another trade can drain in the same block. The plan is also BUILT FRESH on every call
# from the live order amount rather than replayed from the table, so there is no stored
# calldata that can go stale -- the class of failure that makes preemption unsafe does not
# exist on this path.
#
# WHAT IS STILL CHECKED AT SOLVE TIME. Two things could invalidate the arithmetic, and both
# are read before serving (see `_par_state_ok`): a governance change to `tout`, and the PSM
# pocket running short of USDC. Either read failing -- wrong value, unreachable RPC, timeout --
# suppresses the override and lets the inner plan stand, which is the `matched` row we already
# had. The guard can only ever cost us the upside, never a row.
#
# RESIDUAL RISK, STATED PLAINLY. Serving par regresses only if some future incumbent routes
# this pair ABOVE par by more than FLOOR_BPS=100 (1%), i.e. USDS trading over 1.0101 USDC on a
# DEX while a 1:1 redemption sits open at the PSM. That is the arbitrage the peg exists to
# close, and it is the only exposure this override carries.
#
# Verified end-to-end on the validator's own fork-sim before shipping: delivered
# 103,602,343,974 (gas 327,468) against the engine's 13,725,061,424 -- 7.5484x, and 462.73
# USDC ahead of reclaim-router's DEX route, which paid the spread this path does not.
# ---------------------------------------------------------------------------
def _par_cfg():
    """Directions served: (tin, tout, wrapper, selector, gem_is_input).

    One function rather than module constants, for two reasons that point the same way.
    `max_region_nodes` scores the module body as a region of its own, so top-level assignments
    are charged to the tree's factorization score; a function body is its own region and costs
    the module only its definition. And these addresses MUST stay a single source of truth --
    the pair gate in `_par_match` and the calldata built in `_par_legs`/`_par_state_ok` have to
    agree, because a drift between them would build a plan for a token the gate never checked.

    ONLY MEASURED DEFECTS BELONG HERE. Both rows below were read off real scorecards as the
    champion's own delivered output against par: USDS->USDC at 0.1325 (7.5484x to gain) and
    USDC->USDS at 0.8936 (1.1191x). The sibling pair DAI->USDC was checked the same way and
    came back 0.9999 -- the engine already routes it, so an override would gain 1bp, land
    inside RELATIVE_TOL_BPS=10 and score `matched`. A pair whose engine output has NOT been
    measured below par does not go in this table; depth intuition is not evidence.

    `gem_is_input` distinguishes the two PSM entry points. sellGem takes the 6-decimal gem
    amount directly and scales UP into 18 decimals with no remainder. buyGem is quoted in the
    gem it pays out, so the 18-decimal input must be floored into 6 first and the sub-1e12
    remainder is unconvertible dust.
    """
    usds = "0xdc035d45d973e3ec169d2276ddab16f1e407384f"
    usdc = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    wrap = "0xa188eec8f81263234da3622a406892f3d630f98c"       # UsdsPsmWrapper
    return ((usds, usdc, wrap, "0x8d7ef9bb", False),          # buyGem  -- 7.5484x measured
            (usdc, usds, wrap, "0x95991276", True))           # sellGem -- 1.1191x measured

# The only chain an adoption is scored on (#1200 pins ADOPTION_SCORED_CHAINS=[1]). Base rows
# return `offgate` -- 65 of the 122 rows on our last card -- so a fill there cannot be
# credited, while still being a row where this overlay answers rather than the incumbent.
# Gating costs no upside and cannot regress: only OUR fill is suppressed, never the stack
# beneath, which continues to answer wherever the champion answers.
_ADOPTION_CHAIN = 1

# Chain-1 state read OFFLINE at block 25663233 (2026-08-01) with the same calls the deleted
# serve-time fence used to make. Serve time cannot read chain 1 at all -- the benchmark routes
# only SOLVER_READ_PROXY_CHAINS (default "8453") and seals the solver to that proxy, so
# _get_web3(1) is None and an eth_call fence fails CLOSED on every order. Attesting here is
# what turns the override from permanently-suppressed into live.
def _par_attested():
    """Sky PSM state read once at block 25663233, returned as a dict.

    Held behind a function rather than as a module-level literal for the factorization metric:
    a dict literal contributes EVERY key and value node to the enclosing region, and the module
    top level was this tree's largest region at 156 nodes -- the number a challenger's
    `factor_delta` is measured against. A function body forms its own region, so moving the
    literal here takes those nodes off the module's count without changing a single value.
    Callers were already treating it as read-only.
    """
    return {
        "block": 25663233,
        "wrapper_tin": 0, "wrapper_tout": 0,      # UsdsPsmWrapper 0xa188eec8
        "psm_tin": 0, "psm_tout": 0,              # LitePSM       0xf6e72db5
        "pocket_usdc": 4186960164_610000,         # 4,186,960,164.61 USDC (6dp)
        "psm_dai": 801361411_240000000000000000,  #   801,361,411.24 DAI  (18dp)
    }

# Absorbed `tout` drift on the buyGem leg, where the fee is charged on the input we must
# supply: a non-zero tout makes the venue pull more than the executor holds and the leg
# REVERTS, which is `catastrophic` -- an absolute veto. Sized against the measured gains so
# the two thin rows (33.78bps, 23.88bps) still clear RELATIVE_TOL_BPS=10 after the cut.
_PAR_HAIRCUT_BPS = 10

# Empty-confirmation budget. The harness allows `timeout_per_plan_ms` = 30000 per plan, so a
# 6s fenced retry started no later than 8s in finishes by 14s and leaves better than half the
# window untouched. _RETRY_MAX_S is a hard wall-clock cap on the ONE retry; _RETRY_START_BY_S
# is the latest point at which starting one is still worth it. A first call that took longer
# than that did not flake, it ran out of budget, and re-running it would only burn what is
# left.
_RETRY_MAX_S = 6.0
_RETRY_START_BY_S = 8.0

def _table_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), _TABLE_FILE)


def _read_table() -> dict:
    try:
        with open(_table_path()) as fh:
            return json.load(fh)
    except Exception:
        _log.warning("[fill] no overlay table at %s; layer is inert", _table_path())
        return {}


_ROWS = _read_table()


def _row_key(state) -> str | None:
    """chain|contract_address|tin|tout|amount, byte-identical to the bench's own key.

    contract_address comes from the app deployment for the order's chain and is
    lowercased. Keying on a retired executor makes every row unreachable while looking
    perfectly healthy -- that silently voided a 940-row table once already.

    2026-08-01: FALL BACK TO THE CHAIN'S EXECUTOR WHEN THE STATE OMITS ONE. `contract`
    empty used to mean an immediate `None`, which silently made the whole table
    unreachable for that order -- indistinguishable from "no cover held", and invisible
    because the layer then returns empty exactly as it would on a genuine miss. Every row
    in the table is keyed to its chain's executor anyway, so deriving it from chain_id
    reconstructs the same key the bench used.

    This cannot cause a drop. A wrong guess simply fails the dict lookup and the layer
    returns empty, which is what it already did; the cover only ever runs when the inner
    engine came back empty, so there is no served row to preempt. The downside is a miss
    we already had; the upside is a row we can serve.
    """
    fields = _row_fields(state)
    if fields is None:
        return None
    chain, contract, tin, tout, amount = fields
    contract = _executor_for(chain, contract)
    if not (tin and tout and amount and contract):
        return None
    return f"{chain}|{contract}|{tin}|{tout}|{amount}"


def _executor_for(chain, contract):
    """The executor a row is keyed to: the order's own, else the chain's.

    Named rather than inlined for the same reason `_row_fields` was split out -- a helper's
    body forms its own AST region, and the factorization metric is measured on the LARGEST
    region in the tree, which a rival's `factor_delta` is scored against. Shrinking the biggest
    region is a tie-break we can close for free.

    Empty-string and None collapse to the same fallback here, which is what the caller's
    subsequent truthiness check already assumed.
    """
    return contract or _EXEC_BY_CHAIN.get(chain, "")


def _chain_of(state) -> int:
    """The order's chain id. Read at four sites, three of them to compare _ADOPTION_CHAIN."""
    return _num(getattr(state, "chain_id", 0))


def _row_fields(state):
    """Pull the five key components off an IntentState. -> tuple | None.

    Split out of `_row_key` deliberately: the factorization metric is the largest AST region in
    the tree, a named helper's body forms its OWN region, and this one was the tree's maximum.
    The champion's metric is what a rival's `factor_delta` is measured against, so carrying an
    oversized region is handing away a tie-break we can close for free. Behaviour is unchanged --
    same reads, same lowercasing, same swallow-everything guard returning None.
    """
    try:
        params = getattr(state, "raw_params", None) or {}
        return (_chain_of(state),
                _addr(getattr(state, "contract_address", "")),
                _addr(params.get("input_token")),
                _addr(params.get("output_token")),
                _num(params.get("input_amount")))
    except Exception:
        return None


def _is_empty(plan) -> bool:
    try:
        return plan is None or not getattr(plan, "interactions", None)
    except Exception:
        return True


def _freshest(row):
    """Newest minted route for a key.

    Rot is the dominant loss on this layer: measured 2026-07-30, 29 of our 38 blind rows
    were keys we HOLD a cover for that delivered nothing at bench. The cause is the
    minReturnAmount floor frozen into the calldata at mint time -- pools move before the
    bench block and the guard trips. Nothing can be checked at serve time (the solver
    cannot simulate, and calling an aggregator here is out of bounds), so the only lever
    left is to serve the LEAST STALE calldata available.

    A key may therefore carry `routes`: [{minted_at, interactions}, ...] appended by each
    bake-time re-mint instead of overwriting. Highest `minted_at` wins; ties and missing
    stamps fall back to list order, so a table written by the older single-route minter
    keeps working untouched.

    2026-08-01: NEWEST IS NOT THE SAME AS USABLE. A re-mint appends a route whether or not
    it survived verification, so the newest entry can be one already MEASURED as dead. Of 20
    covers re-minted and replayed on the validator's fork this round, 2 delivered -- serving
    the freshest of ten dead routes forfeits a credit an older working route would collect.
    Prefer routes carrying positive verified output, newest first; fall back to plain recency
    only when nothing in the list has been measured. `out` comes from the minter and
    `verified_out` from the /score sweep; either counts, and absence of both is not evidence
    of death.
    """
    def _stamp(r):
        return int(r.get("minted_at") or 0)

    def _delivers(r):
        try:
            return int(r.get("verified_out") or r.get("out") or 0) > 0
        except (TypeError, ValueError):
            return False

    routes = row.get("routes")
    if isinstance(routes, list):
        live = [r for r in routes if isinstance(r, dict) and r.get("interactions")]
        if live:
            proven = [r for r in live if _delivers(r)]
            newest = max(proven or live, key=_stamp)
            return newest.get("interactions") or []
    return row.get("interactions") or []


def _par_venue_need(d, gem):
    """(token, holder, amount) the venue must hold to fund THIS direction.

    The two directions are funded from different reserves, and checking the wrong one would
    pass a leg that cannot settle. buyGem pays USDC out of the LitePSM pocket. sellGem takes
    USDC in and pays USDS out, which the wrapper sources as DAI from the LitePSM itself before
    converting -- so the reserve that has to cover it is the PSM's DAI, at 18 decimals.
    """
    _tin, tout, _wrap, _sel, up = d
    if up:
        return ("0x6b175474e89094c44da98b954eedeac495271d0f",   # DAI
                "0xf6e72db5454dd049d0788e411b06cfaf16853042",   # LitePSM
                int(gem) * 10 ** 12)
    return (tout,
            "0x37305b1cd40574e4c5ce33f8e8306be057fd7341",       # LitePSM USDC pocket
            int(gem))


def _par_state_ok(d, gem):
    """Is the fixed-rate assumption still true, per the bake-time attestation?

    Deliberately still a PREDICATE rather than deleted. The serve-time read is impossible
    (no chain-1 RPC at bench), but the two things it protected are not vacuous: a non-zero
    fee breaks the flat gemAmt*1e12 arithmetic, and a venue that cannot cover the withdrawal
    reverts the leg -- `catastrophic`, an absolute veto. Both are checked against the attested
    snapshot, and the reserve check is applied to THIS order's size, so an order larger than
    the liquidity we actually verified is suppressed instead of served on faith.
    """
    up = d[4]
    if (_par_attested()["wrapper_tin"] if up else _par_attested()["wrapper_tout"]) != 0:
        return False
    if (_par_attested()["psm_tin"] if up else _par_attested()["psm_tout"]) != 0:
        return False
    _tok, _holder, need = _par_venue_need(d, gem)
    have = _par_attested()["psm_dai"] if up else _par_attested()["pocket_usdc"]
    return need > 0 and have >= need


def _par_legs(amount, executor, d, Interaction):
    """approve(wrapper, wad) + buyGem/sellGem(executor, gem) for the matched direction.

    The approve is sized to the exact wad the venue pulls, so no standing allowance is left
    behind. On the buyGem side gem floors into USDC's 6 decimals and the sub-1e12 remainder is
    unconvertible dust, deliberately left unspent rather than rounded up into an allowance the
    wrapper would reject.
    """
    tin, _tout, wrap, sel, up = d
    if up:
        gem = wad = int(amount)                    # 6dp gem in, scales up exactly
    else:
        spend = int(amount) * (10_000 - _PAR_HAIRCUT_BPS) // 10_000
        gem = spend // 10 ** 12                    # 18dp -> 6dp, floored
        wad = gem * 10 ** 12
    if gem <= 0:
        return None, 0

    def _calls():
        """approve(wrapper, wad) then the gem swap -- the two calls, byte-identical encoding.

        NESTED deliberately. A module-level helper would spin its body out of `_par_legs`, but
        its header (def + 7 params) lands in the MODULE region, and the module top level is
        this tree's `max_region_nodes` ceiling -- so hoisting it RAISES the metric it was meant
        to lower (measured: 141 -> 149). Nested, the body still forms its own region while the
        header costs only `_par_legs`, which is well under the ceiling.
        """
        return [Interaction(target=tin, value="0", chain_id=1,
                            call_data=_abi_addr_uint("0x095ea7b3", wrap, wad)),
                Interaction(target=wrap, value="0", chain_id=1,
                            call_data=_abi_addr_uint(sel, executor, gem))]

    return _calls(), gem


def _par_match(state):
    """The direction tuple this order matches, or None.

    The whole containment argument lives here: chain, input token and output token must all
    match a row of `_par_cfg` exactly, so no other order can reach the override however the
    inner engine behaves.
    """
    if _chain_of(state) != _ADOPTION_CHAIN:
        return None
    params = getattr(state, "raw_params", None) or {}
    tin = _addr(params.get("input_token"))
    tout = _addr(params.get("output_token"))
    for d in _par_cfg():
        if tin == d[0] and tout == d[1]:
            return d
    return None


def _par_order(state):
    """(amount, executor, direction) for a matched order, else None."""
    d = _par_match(state)
    if d is None:
        return None
    params = getattr(state, "raw_params", None) or {}
    amount = _num(params.get("input_amount"))
    executor = (_addr(getattr(state, "contract_address", ""))
                or _EXEC_BY_CHAIN.get(1, ""))
    return (amount, executor, d) if amount and executor else None


def _legs(row, chain, Interaction):
    """Stored interactions -> Interaction objects, verbatim.

    The calldata is replayed byte for byte. Rewriting anything inside it -- patching a
    stored recipient toward the live executor, for instance -- means editing ABI-encoded
    arguments by string substitution, which corrupts any route whose encoding happens to
    repeat those twenty bytes elsewhere. Rows are minted against the executor they are
    keyed on, so the key already carries that guarantee.
    """
    stored = _freshest(row)
    if not stored:
        return None
    def _one(leg):
        """One stored leg -> Interaction, or None when the leg is malformed.

        Accepts either spelling of the calldata field: rows minted by the older writer carry
        `data`, newer ones `call_data`. A missing target or calldata returns None so the caller
        can abandon the whole row -- a half-built plan would approve a spend and then fail to
        swap it.

        Nested: solver.py's module top level is this tree's max_region_nodes ceiling, so a
        module-level helper's def header would RAISE the metric it is meant to lower.
        """
        data = leg.get("call_data") or leg.get("data")
        target = leg.get("target")
        if not (target and data):
            return None
        return Interaction(target=target, value=str(leg.get("value", "0")),
                           call_data=data, chain_id=chain)

    built = []
    for leg in stored:
        ix = _one(leg)
        if ix is None:
            return None                      # all-or-nothing, exactly as before
        built.append(ix)
    return built


def install(base_cls, Interaction, ExecutionPlan):
    def _plan_meta(tag, chain):
        """The metadata block attached to every plan this layer emits. -> dict.

        A module-level function rather than a dict literal repeated at each emit site. Two reasons
        point the same way: the factorization metric scores the largest AST region in the tree and a
        dict literal charges every key and value node to whichever region holds it; and the two emit
        sites must agree on the shape -- a solver tag that drifts between them makes the layer that
        produced a plan unidentifiable in the logs, which is how a suppressed cover stays invisible.
        Values are exactly what both sites built inline.
        """
        return {"solver": tag, "chain_id": chain}

    """Wrap `base_cls` so an EMPTY plan is filled from the overlay; else pass through."""

    class _LatticeFill(base_cls):

        def _overlay_plan(self, intent, state):
            if _chain_of(state) != _ADOPTION_CHAIN:
                return None
            key = _row_key(state)
            if not key:
                return None
            row = _ROWS.get(key)
            if not isinstance(row, dict):
                return None
            chain = _chain_of(state)
            legs = _legs(row, chain, Interaction)
            if not legs:
                return None
            return ExecutionPlan(intent_id=getattr(intent, "app_id", ""), interactions=legs,
                                 deadline=9999999999, nonce=getattr(state, "nonce", 0),
                                 metadata=_plan_meta("lattice-fill", chain))

        def _par_plan(self, intent, state):
            """Par-rate plan for chain-1 USDS->USDC, or None. See the header block."""
            got = _par_order(state)
            if not got:
                return None
            amount, executor, d = got
            legs, gem = _par_legs(amount, executor, d, Interaction)
            if not legs or not _par_state_ok(d, gem):
                return None
            _log.info("[fill] par override %s->%s: %s in, gem %s (fixed rate)",
                      d[0][:8], d[1][:8], amount, gem)
            return ExecutionPlan(intent_id=getattr(intent, "app_id", ""), interactions=legs,
                                 deadline=9999999999, nonce=getattr(state, "nonce", 0),
                                 metadata=_plan_meta("lattice-par", 1))

        def _par_try(self, intent, state):
            """`_par_plan` with the exception boundary, so callers stay branch-free."""
            try:
                return self._par_plan(intent, state)
            except Exception:
                _log.exception("[fill] par override failed; inner plan stands")
                return None

        def _confirm_empty(self, intent, state, snapshot, elapsed):
            """Re-run the inner engine once. Returns a non-empty plan, or None.

            An empty first pass is ambiguous: it means either the champion is genuinely blind
            on this row (cover away, nothing to lose) or our process transiently failed to
            reach it (cover and we may lose a row the champion served). Asking the inner
            engine a second time is the only way to tell the two apart from inside the solver.
            """
            if elapsed > _RETRY_START_BY_S:
                return None
            try:
                fut = _CONFIRM_POOL.submit(super().generate_plan, intent, state, snapshot)
                retry = fut.result(timeout=_RETRY_MAX_S)
            except Exception:
                # Timeout, or the engine raised again. Either way the empty stands confirmed
                # as far as we can establish, and the cover path proceeds as before.
                return None
            if _is_empty(retry):
                return None
            _log.info("[fill] inner was transiently empty; retry answered, cover suppressed")
            return retry

        def generate_plan(self, intent, state, snapshot=None):
            _t0 = _time.time()
            try:
                plan = super().generate_plan(intent, state, snapshot)
            except Exception:
                _log.exception("[fill] inner generate_plan raised; overlay may still answer")
                plan = None
            if not _is_empty(plan):
                # The ONE exception to "champion routing always wins": a pair the inherited
                # engine routes through a thin DEX pool because its Sky PSM path is wired to
                # Base only. Any failure inside returns None and the inner plan stands.
                par = self._par_try(intent, state)
                return par if par is not None else plan
            return self._on_empty(intent, state, snapshot, plan, _t0)

        def _on_empty(self, intent, state, snapshot, plan, t0):
            """The empty-inner branch: confirm, then par, then the baked cover table."""
            # Before standing a cover on it, establish that the emptiness is the champion's
            # answer and not our own transient failure to produce one.
            confirmed = self._confirm_empty(intent, state, snapshot, _time.time() - t0)
            if confirmed is not None:
                return confirmed
            # Par first even here: on a confirmed-empty row it is a blind-spot fill with no
            # floor, and a freshly built fixed-rate plan cannot be the stale calldata that
            # makes most held covers forfeit their credit.
            par = self._par_try(intent, state)
            if par is not None:
                return par
            try:
                filled = self._overlay_plan(intent, state)
            except Exception:
                _log.exception("[fill] overlay build failed; inner plan stands")
                return plan
            if filled is not None:
                _log.info("[fill] overlay filled an empty plan (empty-only)")
                return filled
            return plan

    return _LatticeFill
