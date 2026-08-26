"""The validator's per-scenario RPC-READ budget, which this tree never modelled.

WHAT THE HARNESS ACTUALLY METERS
================================
Every budget commit in this lineage bounds WALL-CLOCK SECONDS -- the run pot,
the per-plan ceiling, the batch reserve, the run clock. The validator's own
source says wall-clock is not the cutoff:

  harness/orchestrator.py:1991
    "The run budget (TOTAL_BENCHMARK_TIMEOUT) is a shared wall-clock backstop
     checked per-worker; it RARELY TRIPS (the per-scenario RPC-read budget is
     the real cutoff)"

  harness/orchestrator.py:675
    "When the deterministic RPC-read budget is the cutoff, the wall-clock
     GENERATE_PLAN timeout is no longer the cutoff ... Loosen it to a runaway
     backstop."

The real cutoff is `harness/solver_read_proxy.py`:

  * DEFAULT_GENERATE_PLAN_BUDGET = 5000, described there as "a CONSENSUS-UNIFORM
    CODE CONSTANT ... so the whole fleet enforces the SAME cutoff", and
    "UNSET -> the uniform code constant (default-on, consensus-bound)". It is
    PER SCENARIO, and `budget_enforced()` opens the proxy session in `enforce`
    mode whenever it is positive.
  * The meter is an integer cost per JSON-RPC method from
    `rpc_budget_proxy/cost_table.py` (eth_call / eth_getStorageAt / eth_getCode
    / eth_getBalance / eth_getBlockByNumber = 1, eth_getLogs = 2, chainId /
    blockNumber / gasPrice = 0, anything unlisted = 1).
  * Calibration, quoted from solver_read_proxy.py:70 -- "the observed
    per-scenario max via the proxy is ~300 reads (cold DAI multi-hop), so 5000
    is ~16x headroom -- legit scenarios always pass; only a runaway loop is
    cut."

WHY IT IS INVISIBLE HERE, AND WHY THAT IS THE WHOLE PROBLEM
==========================================================
`rpc_budget_proxy/proxy.py` fails LOUD and STICKY: once a request would exceed
the budget it stops forwarding and returns a well-formed JSON-RPC error, code
-32099, message MINOTAUR_BUDGET_EXCEEDED, and its own docstring states the
rule -- "once over budget, stay over (deterministic)". Every remaining read in
that scenario gets the same error.

`venues.eth_call` catches `Exception` and returns None, and None is this tree's
universal "no liquidity / dead quote" answer. So an exhausted budget is read as
"every venue is empty": the ladder walks its whole candidate list getting None
from calls the proxy is no longer even forwarding, and the order ends with an
EMPTY plan. The validator scores an empty plan `chal: null` -- a dropped order
and a hard veto.

That is why no local gate has ever moved on it, and it is not a gap we can
close by adding another gate: `bin/perf-check` plans with `rpc_urls: {}`, and
`bin/exec-check` drives a local Anvil through `state/rpc-cache`. NEITHER RUNS
THE BUDGET PROXY, so neither can reproduce a budget-exceeded drop, and a
replayed order meets a fresh budget in any case. This is the missing half of
"all 7 drops replayed at js=1.0000, EXEC GATE: PASS" -- the replay is not
measuring the thing that dropped them.

WHAT THIS MODULE DOES, AND WHAT IT DELIBERATELY DOES NOT
========================================================
It latches the exhausted state and stops issuing reads the proxy has ALREADY
guaranteed will fail. That cannot change a plan's content: the proxy is sticky,
so a read issued after exhaustion returns the error either way, and refusing to
send it returns the same None the exception handler would have. The value is
that exhaustion becomes VISIBLE to the plan path, which can then fall back to a
rung that needs no reads at all instead of shipping the empty plan.

It does NOT impose a self-chosen read reserve -- a "stop covering at N reads"
threshold. Picking N without a measurement is exactly the kind of guess that
turns a served order into a drop. `spent()` is what makes that measurement
possible: since the meter moved to the provider hook it counts every forwarded
request at the proxy's own price, so a tick that wants to reason about a
reserve now has a real number against the 5000 cap instead of an estimate.
Note that `min_amt_alias` carries an unsourced "~573 priced reads" figure; it
predates any meter that could see the reads and should be re-derived from
`spent()`, not trusted.

A separate module rather than three statements in `consts.py` or `venues.py`:
the module top level is itself a region the validator measures as
`max_region_nodes`, `venues.py` is already the tree's largest, and
`consts._dz70` exists precisely to keep constants out of a module region.
"""
from __future__ import annotations
BUDGET_EXCEEDED_MESSAGE = 'MINOTAUR_BUDGET_EXCEEDED'
_M = {'reads': 0, 'exhausted': False}

def reset() -> None:
    """Start a new scenario's meter.

    Called from the OUTERMOST `generate_plan` and `quote` (pacing_bridge), which
    are the same per-scenario boundary the proxy opens its session on. Resetting
    on both matters: the latch must never survive into a scenario that was given
    a fresh budget, or we would refuse reads that the proxy would have answered.
    The quote path is where this tree's blind_spot_cover wins come from, and
    `king_base.quote` reaches the baseline solver's own RPC work WITHOUT going
    through `generate_plan`, so the `generate_plan` reset alone would not cover
    it.
    """
    _M['reads'] = 0
    _M['exhausted'] = False

def spent() -> int:
    """This scenario's spend IN THE PROXY'S OWN UNITS, not a raw call count.

    Charged by `note_method` at the price the proxy's `cost_table.py` uses, and
    charged only for requests that were actually FORWARDED -- a Multicall3
    aggregate3 sweep is one eth_call however many subcalls it carries, and a
    request served out of `min_amt_alias`'s memo tables never reaches the proxy
    and so costs nothing. That makes this directly comparable to the 5000 cap.
    """
    return int(_M['reads'])

def exhausted() -> bool:
    """True once the proxy has refused a read for this scenario."""
    return bool(_M['exhausted'])
_COST = {'eth_chainId': 0, 'eth_blockNumber': 0, 'eth_gasPrice': 0, 'eth_getLogs': 2}

def _cost(method) -> int:
    """The proxy's price for one JSON-RPC method."""
    try:
        return int(_COST.get(str(method), 1))
    except Exception:
        return 1

def note_method(method) -> None:
    """Charge one request that is about to be forwarded to the node.

    Called from the provider-level hook in `min_amt_alias`, which is the only
    point in this tree that sees EVERY read. The per-venue helpers cannot serve
    that role: `venues.eth_call` documents itself as the tree's single funnel to
    the chain, but the reads are overwhelmingly issued elsewhere -- king_base,
    apex_king_base, hydra_top, _champ_base, shape_lib, aero_legs and viking_sim
    all build their own `Web3` and call `w3.eth.call` / `make_request` directly,
    which is dozens of sites against that one. Metering there measured a small
    fraction of the spend and, worse, left the budget refusal invisible at every
    site that was not it.
    """
    _M['reads'] = int(_M['reads']) + _cost(method)

def note_response(resp) -> bool:
    """Latch if `resp` is the proxy's budget refusal reply. True when it was.

    The proxy answers over budget with a well-formed JSON-RPC error rather than
    a transport failure, so at the provider hook the refusal arrives as a plain
    dict and is read here directly. That is strictly more reliable than waiting
    for `note_error`: web3 turns an error reply into a ValueError, a
    Web3RPCError or a bare RPCResponse depending on version and call path, and
    the sites that swallow it never re-raise at all.
    """
    try:
        err = resp.get('error') if isinstance(resp, dict) else None
        msg = err.get('message') if isinstance(err, dict) else None
        if msg is not None and BUDGET_EXCEEDED_MESSAGE in str(msg):
            _M['exhausted'] = True
            return True
    except Exception:
        pass
    return False

def note_error(exc) -> bool:
    """Latch if `exc` is the proxy's budget refusal. True when it was.

    Every other exception -- a revert, a socket hiccup, a decode failure -- is
    left alone and stays the ordinary "dead quote" None it has always been.
    Narrow by construction: only the exact consensus message latches, so a
    misread cannot suppress reads that would have been answered.
    """
    try:
        if BUDGET_EXCEEDED_MESSAGE in str(exc):
            _M['exhausted'] = True
            return True
    except Exception:
        pass
    return False