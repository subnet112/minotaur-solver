"""Venue sweep — build the quote job list and fan it out concurrently.

Split from quotes.py purely for the AST-region budget: the metric counts a
module body as one region, and one file holding every def header exceeded it.
"""
from __future__ import annotations

import concurrent.futures
import time

import consts
from quotes import _multihop, _single, _v2


def _single_jobs(w3, tin: str, tout: str, amount: int, chain_id: int) -> list:
    """Direct-pair quotes: Uniswap fee tiers (+ Aerodrome tick spacings on Base)
    plus a Uniswap-V2 direct quote (where exotic long-tail liquidity often sits).

    ``aero_ticks`` is empty on Ethereum, so that family drops out here.
    """
    tier = consts.tiers(chain_id)
    jobs = [lambda f=f: _single(w3, "uni", tin, tout, amount, f, chain_id)
            for f in tier["uni_fees"]]
    jobs += [lambda t=t: _single(w3, "aero", tin, tout, amount, t, chain_id)
             for t in tier["aero_ticks"]]
    jobs.append(lambda: _v2(w3, tin, tout, amount, chain_id))
    return jobs


def _mid_jobs(w3, tin: str, mid: str, tout: str, amount: int, chain_id: int) -> list:
    """2-hop quotes through one intermediate token, per-chain venue families
    (Uniswap/Aerodrome v3 packed-path plus a Uniswap-V2 [tin,mid,tout] hop)."""
    tier, route = consts.tiers(chain_id), (tin, mid, tout)
    jobs = [
        lambda f=f: _multihop(w3, "uni", route, f, amount, chain_id)
        for f in tier["uni_kg_twohop_fees"]
    ]
    jobs += [
        lambda t=t: _multihop(w3, "aero", route, t, amount, chain_id)
        for t in tier["aero_twohop_ticks"]
    ]
    jobs.append(lambda: _v2(w3, tin, tout, amount, chain_id, mid))
    return jobs


def _harvest(futures: list, deadline: float) -> list:
    """Collect whatever finishes before the wall-clock deadline; drop the rest.

    Harvest in COMPLETION order, never submission order. Waiting on futures in
    the order they were submitted head-of-line blocks: one cold pool can take
    ~19s to quote (an uncached WBTC/USDC 0.01% tier, measured), and if that
    future is first, it eats the entire budget and every fast quote behind it
    gets cancelled — the sweep returns nothing and the order scores as a DROP.
    With as_completed the slow venue costs only itself.
    """
    out = []
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return out
    try:
        for fut in concurrent.futures.as_completed(futures, timeout=remaining):
            try:
                got = fut.result()
            except Exception:
                got = None
            if got:
                out.append(got)
    except Exception:
        pass  # global timeout — keep whatever already landed
    for fut in futures:
        fut.cancel()
    return out


def _run(jobs: list, deadline: float) -> list:
    """Fire a job wave concurrently and harvest it before the deadline."""
    if not jobs:
        return []
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs))
    try:
        return _harvest([pool.submit(j) for j in jobs], deadline)
    finally:
        # Don't join: a straggler quote must not hold the plan past its budget.
        pool.shutdown(wait=False, cancel_futures=True)


def _all_jobs(w3, tin: str, tout: str, amount: int, chain_id: int) -> list:
    """Every quote for this pair — direct venues plus each 2-hop mid."""
    jobs = _single_jobs(w3, tin, tout, amount, chain_id)
    for mid in consts.twohop_mids(chain_id):
        if mid in (tin.lower(), tout.lower()):
            continue
        jobs += _mid_jobs(w3, tin, mid, tout, amount, chain_id)
    return jobs


def enumerate_quotes(w3, tin: str, tout: str, amount: int, chain_id: int = 8453) -> list:
    """Fire every venue quote in ONE concurrent wave. Never raises.

    One wave, not two: splitting direct-then-2-hop makes the first wave wait on
    its own slowest future (a cold WBTC/USDC 0.01% tier measured at ~19s), which
    burns the whole 12s budget and leaves the 2-hop expansion unexplored — the
    order then fills from a thin direct pool and REGRESSES against the champion.
    Harvesting by completion (_harvest) already isolates slow venues, so there
    is nothing to protect the direct quotes from.
    """
    if w3 is None or int(amount) <= 0:
        return []
    deadline = time.monotonic() + consts.budgets()["select"]
    return _run(_all_jobs(w3, tin, tout, amount, chain_id), deadline)
