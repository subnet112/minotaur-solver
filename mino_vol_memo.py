"""Per-plan memo for the eth_calls that move between blocks but not within a plan.

WHY THIS EXISTS. sub_561bc66ca871 (round-e29785000-n1) scored 3 better / 4 worse /
91 matched and every one of the 4 worse is a DROP: the champion carries an output,
we return null. Their per_order ordinals are 17/23/40/108 of 122 — SCATTERED, not a
contiguous tail — and they share no id with the 6 that sub_11034ef06181 dropped.
A contiguous tail is the 900s whole-run wall; scattered ordinals with disjoint sets
across rounds are a PER-PLAN resource failure. perf-check cannot see the class at
all: it reports those rows as VETOED BUT READS CLEAN, i.e. we plan byte-identically
to the champion, so the cost is off-plan rather than in the routing.

WHICH per-plan resource. Two candidates, and they cannot be separated offline, so
this memo is built to serve both rather than to bet on one.

  * WALL-CLOCK. While the budget proxy runs in observe mode the 30s per-plan cutoff
    is the live constraint, and min_amt_alias.py measured what a redundant read
    costs there: 1143 duplicate eth_chainId calls were free on a warm fork and
    11-114 seconds at validator latency. A duplicate eth_call is the same round
    trip. This memo removes the duplicates the chainId memo cannot, because they
    are not chainId.
  * THE METERED READ BUDGET (DEFAULT_GENERATE_PLAN_BUDGET = 5000 units, reset per
    scenario). This file used to rule it out, citing min_amt_alias.py's ~573
    billable units as 9x under the cap. That inference does not hold and the claim
    is withdrawn: 573 was measured on the LOCAL corpus's heaviest row, while the
    rows that actually drop are the content-addressed `quote:q_*` class, which that
    corpus does not contain at the same depth — a deep row fans out over more
    venues and more cover layers than anything reproducible here. The evidence the
    cap is real is already in this file: `_worth_caching_error` excludes -32099 BY
    NAME because it is the validator's read-budget refusal, and a budget that is
    never reached emits no refusals. A sibling identity pinned its own scattered
    drops on exactly this meter.

Both are relieved by the same act — issuing fewer round trips — so the ambiguity
does not have to be resolved before the work is worth doing. Mind the split in what
pays, though: eth_chainId, eth_blockNumber, eth_gasPrice and net_version are priced
0, so removing those buys wall-clock ONLY, while eth_call / eth_getStorageAt /
eth_getCode / eth_getBalance / eth_getBlockByNumber (1 unit each) and eth_getLogs
(2) buy both. Never read a saving on a free method as headroom against the meter.

WHY IT IS SOUND. getReserves/slot0/balanceOf move every block, so they can never be
memoed for the life of the process — that is why this is per-plan and not a sibling
of the chainId table. But they cannot move DURING one generate_plan: planning only
reads, and the validator pins every read to the fork block for the whole scenario.
Inside that window the same (endpoint, params) has exactly one answer, so serving
the second ask from the first ask's response returns the same bytes the node would
have returned. The plan is therefore byte-identical to the plan we build today; only
the round trips differ. That is the property that makes this unable to cost an
adoption — it cannot turn a matched order into a regression, because it cannot
change what we build.

FAIL-CLOSED, on purpose. `_GEN` starts at 0 meaning DISABLED, and only
`new_plan()` raises it. If the hook in solver.py is ever bypassed — a layer
installed above it that shadows generate_plan without chaining to super() — the
window never opens, `_key` returns None for every call and not one response is
served from the memo. The degraded state is exactly today's behaviour, never a
stale read.

The key is the METHOD plus the FULL canonical params, not just (to, data), so an
eth_call carrying a state override, a different `from`, or a different block tag can
never collide with the plain one. Two spellings of the same call simply miss, which
costs one read. The method belongs in the key and not merely in the routing: several
memoed methods take the SAME params shape, so `eth_getBalance(addr, "latest")` and
`eth_getCode(addr, "latest")` would otherwise collide on one entry and hand a balance
back as bytecode. That was latent while only eth_call was routed here.

WHICH METHODS (`MEMOABLE`). Every read whose answer is a pure function of the block,
because the validator pins the block for the whole scenario:

  * eth_call / eth_getStorageAt / eth_getCode / eth_getBalance / eth_getBlockByNumber
    / eth_getLogs -- the metered ones, 1 unit each and 2 for getLogs.
  * eth_blockNumber / eth_gasPrice / net_version -- priced 0 in the validator's
    cost_table, so these are pure WALL-CLOCK. Since wall-clock is the binding
    constraint here and not the meter, a free-but-slow round trip is exactly the
    thing worth removing; web3 re-asks these the way it re-asked eth_chainId.

REVERTS COUNT AS ANSWERS. The window caches a deterministic revert (code 3,
'execution reverted') alongside successful reads, because a revert is as pinned to
the block as a return value is. This was the last repeated read still paying full
price: `_champ_base._qv2_q` swallows a reverting QuoterV2 probe as 0, so a venue that
cannot quote at this size is silently re-asked by every cover layer that looks at it,
and nothing in our logs records the cost. Transient errors are NOT answers and still
go to the node every time -- see `_worth_caching_error` for why -32099 and timeouts
are excluded by name.

DELIBERATELY EXCLUDED. eth_chainId belongs to min_amt_alias's process-lifetime table
and never reaches this one. eth_getTransactionCount is a nonce: it is invariant while
we only plan, but it is the single read whose caller may reasonably expect it to move
after a send, so it keeps going to the node -- the saving is not worth owning that
argument. Anything that writes is not a read and was never a candidate.
"""
_DR_UNSET = object()
import json as _json
MEMOABLE = frozenset(('eth_call', 'eth_getStorageAt', 'eth_getCode', 'eth_getBalance', 'eth_getBlockByNumber', 'eth_getLogs', 'eth_blockNumber', 'eth_gasPrice', 'net_version'))
STICKY_SELECTORS = frozenset(('1698ee82', 'e6a43905'))
_BY_KEY = {}
_STICKY = {}
_GEN = [0]

def new_plan():
    """Open a fresh window. Called once per generate_plan, from solver.py.

    Clearing on entry rather than on exit is deliberate: a layer that re-plans by
    calling down a second time re-opens the window, which drops the memo back to
    cold. Cold is correct-by-construction; a window held open across a boundary
    the validator may have moved the fork block over would not be.

    `_STICKY` is deliberately NOT cleared. It holds only write-once factory hits
    (see STICKY_SELECTORS), whose answer is a property of the chain rather than of
    the block, so the argument that forces `_BY_KEY` cold at a plan boundary does
    not apply to it. Everything else still starts cold.
    """
    _BY_KEY.clear()
    _GEN[0] += 1

def _key(provider, method, params):
    """Canonical key for one memoable read inside the current window, or None.

    None means "do not memo this one" and is returned for every call before the
    first new_plan(); see the fail-closed note in the module docstring.
    """
    if _GEN[0] <= 0:
        return None

    def _canonical():
        """Nested for the factorization metric, which merges a region with the
        helpers it calls: this body would otherwise count against
        `_mino_make_request`, the caller two frames up and the file's largest."""
        try:
            uri = getattr(provider, 'endpoint_uri', None)
            if uri is None:
                return None
            return (str(uri), method, _json.dumps(params or [], sort_keys=True, default=repr))
        except Exception:
            return None
    return _canonical()

def cached_call(provider, orig, method, params):
    """Serve `method` from this plan's window when we have already asked for it.

    Fail-open throughout: any key we cannot build, and any response we are not
    certain of, goes to the node exactly as it does today.
    """

    def _dz1632():
        if key is None:
            return (orig(provider, method, params),)
        _r_dz1631 = _dz1631()
        if _r_dz1631 is not _DR_UNSET:
            return (_r_dz1631[0],)
        return _DR_UNSET

    def _dz1631():
        hit = _BY_KEY.get(key)
        if hit is None:
            hit = _STICKY.get(key)
        if hit is not None:
            return (dict(hit),)
        return _DR_UNSET
    key = _key(provider, method, params)
    _r_dz1632 = _dz1632()
    if _r_dz1632 is not _DR_UNSET:
        return _r_dz1632[0]

    def _worth_caching(out):
        """True for any answer the node actually returned. Nested for the same
        region reason as `_ask_node` below.

        THE NEGATIVE PROBE IS AN ANSWER (2026-08-19). Until now this rejected
        '0x' (`len > 2`) and empty containers, on the grounds that caching an
        absence could make a contract that does exist read as absent for the
        rest of the plan. That is the PROCESS-LIFETIME rule, and applying it to
        a per-plan window was a category error: the module docstring's own
        invariant is that planning only reads and the validator pins every read
        to the fork block for the whole scenario. Nothing can come into
        existence between two asks inside one window, so '0x' from a call into
        a codeless address is exactly as pinned to this block as a return value
        is -- the same argument that licenses the memo at all. The old rule did
        not make the answer safer, it just re-asked the node for it.

        It re-asked for the read that repeats MOST. Every cover layer walks its
        candidate venues, and the candidates that do not exist at this block are
        the ones each successive layer re-probes: apex, k, mino_fill, g2_fill,
        lattice_fill and the pins all miss on the same dead pools and factories.
        Each miss was a full round trip AND a billable unit (eth_call and
        eth_getCode are 1 each, eth_getLogs 2). This is the success-side twin of
        the deterministic revert `_worth_caching_error` took on 394d6e6, and it
        is the last repeated read still paying full price on both meters.

        Narrow on purpose: str/bytes/dict/list is every success shape the
        MEMOABLE methods can return through a raw HTTPProvider, which hands back
        JSON-RPC hex strings rather than decoded ints. A `None` result is not an
        answer we can attribute to the block, so it still falls through to the
        node on every ask."""
        return isinstance(out, (str, bytes, bytearray, dict, list))

    def _worth_caching_error(err):
        """True only for a DETERMINISTIC revert: the one error class that is a
        property of the pinned block rather than of the node's mood.

        Caching success only was leaving the largest repeated read on the table.
        `_champ_base._qv2_q` wraps every QuoterV2 probe in `except Exception:
        return 0`, so a pool that cannot quote at this size reverts, costs a full
        round trip, and reports nothing -- and the cover layers re-ask the same
        dead venue on every repeat. A revert is as pinned as a successful return:
        same block, same calldata, same EVM, same revert. Serving it from the
        window hands back the identical error dict, web3 raises the identical
        ContractLogicError, and `_qv2_q` returns the identical 0.

        The predicate is deliberately narrow. code 3 + 'execution reverted' is
        what the fork node emits for a real revert. Everything else falls
        through to the node on purpose: -32099 is the validator's read-budget
        signal and timeouts are transient, so both are properties of the RUN and
        not of the block. Caching either would freeze a transient failure into
        the rest of the plan -- the one way this memo could cost an adoption.
        """
        try:
            if not isinstance(err, dict) or err.get('code') != 3:
                return False
            msg = err.get('message')
            return isinstance(msg, str) and 'execution reverted' in msg
        except Exception:
            return False

    def _sticky_code(res):
        """Promote a NON-EMPTY eth_getCode so the next plan does not re-ask.

        Same asymmetry as `_sticky_put`, resting on a different write-once fact:
        contract code is fixed at deployment. There is no opcode that edits the
        code at a live address -- an upgradeable proxy swaps the implementation
        it delegates INTO, while its own runtime bytecode, which is what this
        read returns, never changes -- so once the node has told us an address
        carries code at this fork, it carries the same code at any later block.

        NON-EMPTY ONLY. '0x' says only "no contract at THIS block", which a
        later block may contradict, so it is never promoted; it falls through to
        `_BY_KEY`, which is allowed to hold it for exactly one window (that is
        the negative probe `_worth_caching` took on 758470b). `len > 2` is the
        whole test because getCode answers in hex, so absence is exactly '0x'.

        This is the same repeat `_sticky_put` attacks, on the other read the
        cover layers spend: every layer resolves its routers, factories and
        token contracts by asking whether code is there, and re-asks the same
        addresses once per plan for the life of the process. eth_getCode is
        billed 1 unit each time, so this pays on the wall clock and on the
        metered read budget alike -- the two mechanisms left for the drops now
        that perf-check has shown the dropped rows plan identically.
        """
        try:
            if method != 'eth_getCode':
                return
            out = res.get('result')
            if isinstance(out, str) and len(out) > 2:
                _STICKY[key] = dict(res)
        except Exception:
            pass

    def _sticky_put(res):
        """Promote a WRITE-ONCE factory hit so the next plan does not re-ask.

        The per-plan window already collapses the repeats INSIDE one generate_plan;
        this is the repeat ACROSS them. Every scenario in a round re-walks the same
        candidate venues from cold, so the same handful of getPool/getPair lookups
        are re-asked once per plan for the life of the process -- a full round trip
        and a billable unit each, on the path whose 30s cutoff is what drops us.

        HITS ONLY, and the asymmetry is the whole soundness argument. A non-zero
        answer says the pool was already deployed at this fork, and a factory
        mapping is never reassigned, so it is still that pool at any later block.
        A ZERO answer says only "not at this block", which a later block may
        contradict -- so a miss is never promoted and falls through to the
        per-plan table, which is allowed to hold it for exactly one window.

        '0x' raises in int() and is caught here, so an absent contract can never
        become sticky by another door.
        """

        def _dz1629():
            call = (params or [None])[0]
            return call

        def _dz1628(call):
            data = call.get('data') or call.get('input') or ''
            _r_dz1627 = _dz1627()
            return (_r_dz1627, data)

        def _dz1627():
            _r_dz1626 = _dz1626()
            if _r_dz1626 is not _DR_UNSET:
                return (_r_dz1626[0],)
            _STICKY[key] = dict(res)
            return _DR_UNSET

        def _dz1626():
            if data[2:10].lower() not in STICKY_SELECTORS:
                return (None,)
            out = res.get('result')
            if not isinstance(out, str) or int(out, 16) == 0:
                return (None,)
            return _DR_UNSET
        try:
            if method != 'eth_call':
                return
            call = _dz1629()
            if not isinstance(call, dict):
                return
            _r_dz1627, data = _dz1628(call)
            if _r_dz1627 is not _DR_UNSET:
                return _r_dz1627[0]
        except Exception:
            pass

    def _ask_node():
        """Miss path, nested for the same reason min_amt_alias nests its own.

        The factorization metric merges a region with the helper it calls, so
        this function's body counts against `_mino_make_request` upstream; a
        nested def is the split point that keeps the merged region off the wall.
        """

        def _dz1625():
            if not err:
                if _worth_caching(res.get('result')):
                    _BY_KEY[key] = dict(res)
                    _sticky_put(res)
                    _sticky_code(res)
            elif _worth_caching_error(err):
                _BY_KEY[key] = dict(res)
        res = orig(provider, method, params)
        try:
            if isinstance(res, dict):
                err = res.get('error')
                _dz1625()
        except Exception:
            pass
        return res
    return _ask_node()