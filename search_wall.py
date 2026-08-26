"""The plan window, enforced at the provider instead of at one call site.

WHAT WAS MEASURED, 2026-08-22
=============================
`bin/certify` replayed the full 111-row corpus at d6219cd in ten chunks. Eight
measured. Chunks 002 and 006 died the same way:

    EXEC GATE: UNMEASURED — SolverTimeoutError:
        Command Command.GENERATE_PLAN timed out after 30.0s

The genesis (champion) tree completed all twelve rows of both chunks, including
the row ours died on. Counting the `[SIM] scoreIntent path: ... preview=<input
token>` lines against each chunk's scenario list pins the two exactly:

    chunk-002  index 10  veto:q_5565fcefa372   USDC -> 0x056Fd409 (SAI)
    chunk-006  index 5   veto:q_9de56d30c548   MKR  -> 0x6c3ea903 (PYUSD)

Both are thin, exotic pairs -- the champion returns on q_9de56d30c548 too, it
just returns a REVERT (`CallFailed(index=1)`) in a couple of seconds instead of
grinding. A `GENERATE_PLAN` that never returns is scored `chal: null`, which is
a dropped order and a HARD VETO, and it also costs every row behind it in the
same container.

That 30.0s is the real wall for these runs, not the 300s backstop
`pace_pot.ceiling` widens to. `harness/solver_read_proxy.generate_plan_recv_timeout`
only returns the backstop when `budget_enforced()`, which is
`read_proxy_config() is not None and cfg.budget > 0`, and `read_proxy_config()`
returns None unless `SOLVER_READ_PROXY` is set. Neither `bin/exec-check` nor
`bin/certify` sets it (`grep -rn SOLVER_READ_PROXY /root/bitworld-pipeline`
finds nothing), so those runs get `TIMEOUTS[GENERATE_PLAN]` = 30.0 unchanged.
`pace_pot._proxied` reads that same condition off our own `rpc_urls` and so
already returns the narrow 20.0 ceiling here -- nothing in this file argues
with the pot arithmetic, and this is not a revert of 323691f.

WHY A 20s WINDOW STILL OVERRAN A 30s WALL
=========================================
Because almost nothing was inside the window. `pacing_bridge._pb_arm_window`
sets `consts._SEARCH_DEADLINE` for the plan as a whole, but that cell has
exactly one enforcement point in this tree -- `venues.eth_call`, via
`venues._effective_timeout` -- and `venues.eth_call` is not where the reads
happen. `venues.eth_call`'s own docstring says so, in the correction it earned
the hard way:

    "an earlier revision of this docstring claiming it was the tree's 'single
     funnel to the chain' was simply wrong: `venue_batch.mc_quote` does come
     through here, but king_base, apex_king_base, hydra_top, _champ_base,
     shape_lib, aero_legs and viking_sim each build their own `Web3` and read
     directly, which is dozens of call sites against this one."

So the deadline governed a small minority of the search's reads and the rest
ran untimed. On a pair where the ladder walks a long candidate list against a
cold RPC, the untimed majority is the whole cost, and the armed window bounds
nothing that matters.

THE READ METER ALREADY SOLVED THIS EXACT PROBLEM, AND THIS RIDES ITS FIX
========================================================================
The same "dozens of call sites" sentence is why `read_meter` stopped metering
at `venues.eth_call` and moved to the patched `HTTPProvider.make_request` in
`min_amt_alias`, "which every one of those sites reaches whatever `Web3` object
it built". The deadline needed the same migration and never got it. This module
is that migration: the predicate lives here, `_mino_orig_make_request` calls it,
and every direct-Web3 site inherits the plan window without one call site
changing.

WHY THE METER'S REASON FOR *NOT* REFUSING DOWN THERE DOES NOT APPLY
===================================================================
`_mino_orig_make_request` deliberately meters without refusing, and its
docstring gives the reason:

    "a latch enforced down here would outlive any scenario whose boundary was
     missed and would suppress reads the proxy would have answered."

That is a true statement about the BUDGET LATCH, which is sticky by design --
"once over budget, stay over" -- and therefore depends on a per-scenario reset
to ever clear. It is not true of the deadline. `_SEARCH_DEADLINE` holds an
absolute `time.monotonic()` instant, not a latched flag:

  * it is armed per plan by `_pb_arm_window` and restored in that method's
    `finally`, so a missed boundary cannot leave it armed;
  * unarmed it reads `0.0`, which this module treats as "no wall", so every
    path that is not inside a plan -- `quote` included, which
    `pacing_bridge.quote` pointedly does not wrap, protecting the 14s quote
    budget behind our blind_spot_cover wins -- is untouched;
  * and it self-expires: even a hypothetical leak stops mattering the moment
    the instant passes, because a stale deadline in the past refuses only
    reads that were already out of time.

The failure mode the meter is guarding against needs a flag that never clears.
This has no flag.

BLAST RADIUS
============
`eth_call` only. The dispatcher in `min_amt_alias` also forwards
`eth_getCode`, `eth_blockNumber`, `eth_chainId` and the `eth_simulateV1` /
`eth_getLogs` traffic on the default branch; those are cheap, rare, memoised,
or structural (a `Web3` doing chain detection), and refusing one could break a
construction path rather than shorten a search. The search's cost is quotes,
and quotes are `eth_call`.

WHAT IT CAN AND CANNOT CHANGE
=============================
It cannot change a plan that finished inside its window: before the instant
passes this returns False and the request forwards untouched, byte for byte.
Past the instant the search is out of time by the tree's own accounting, and
`venues.eth_call` -- the one site that already saw the deadline -- has been
returning None there all along. This makes the other sites agree with it
instead of reading on. Every one of them wraps its call in a bare
`except Exception: return None` (the same survey quoted above), so a refusal
arrives as the None they already handle.

Fail-open in both directions on purpose: an unreadable or missing `consts`
means no wall, never a refusal.
"""
from __future__ import annotations
import time
_REFUSAL = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32001, 'message': 'minotaur: plan search deadline exceeded'}}
_WALLED = ('eth_call',)

def expired(method) -> bool:
    """True when `method` is walled and the armed plan window has already passed.

    False whenever there is no wall to apply: no armed deadline (the cell reads
    `0.0` outside `pacing_bridge._pb_arm_window`), a method the wall does not
    cover, or a `consts` that cannot be read. Never raises -- every failure is
    an answer of False, which forwards the request exactly as before.
    """
    if method not in _WALLED:
        return False
    try:
        from consts import _SEARCH_DEADLINE
        dl = _SEARCH_DEADLINE[0]
        return bool(dl) and dl - time.monotonic() <= 0.0
    except Exception:
        return False

def refusal():
    """A fresh copy of the JSON-RPC refusal, so no caller can mutate the template."""
    return dict(_REFUSAL)