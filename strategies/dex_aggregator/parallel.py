"""Bounded thread-pool parallelism for the solver's RPC fan-outs.

The baseline solver issues every on-chain read one-at-a-time, so a cold
multi-hop route makes ~100+ serial ``eth_call``s and can exceed the validator's
30s GENERATE_PLAN timeout. web3's ``HTTPProvider`` releases the GIL during the
blocking socket recv, so running independent ``.call()``s on a small thread pool
overlaps their RPC latency — collapsing a long serial chain into a few waves.

Determinism (the load-bearing property for a champion-eligible solver: every
validator must compute the IDENTICAL route + quoted output): this module only
parallelizes work whose RESULT is order-independent — discovering the SET of
pools for a route. Route SELECTION stays single-threaded over a deterministically
sorted candidate list, so concurrency never changes which route or score wins.

Thread-safety: a single ``Web3``/``requests.Session`` is NOT safe for concurrent
requests, so each worker thread gets its OWN ``Web3`` (``thread_web3``), keyed by
rpc_url in ``threading.local`` and reused across tasks on that thread.
"""
from __future__ import annotations

import concurrent.futures
import threading
from typing import Any, Callable

# Cap concurrent in-flight eth_calls. Bounded so fanning out against a throttled
# live upstream can't trip rate limits / exhaust the connection pool (the serial
# path never hit those); against a warm Anvil fork this is plenty.
MAX_WORKERS = 8

_thread_local = threading.local()


def thread_web3(rpc_url: str) -> Any:
    """Return a per-THREAD Web3 for ``rpc_url`` (own requests.Session).

    Never share one Web3 across worker threads — its session is not concurrency
    safe. Cached per thread + rpc_url so repeated tasks on the same pool thread
    reuse the connection instead of rebuilding it.
    """
    cache = getattr(_thread_local, "w3_by_rpc", None)
    if cache is None:
        cache = _thread_local.w3_by_rpc = {}
    w3 = cache.get(rpc_url)
    if w3 is None:
        from web3 import Web3
        w3 = cache[rpc_url] = Web3(Web3.HTTPProvider(rpc_url))
    return w3


def parallel_map(tasks: list[Callable[[], Any]], max_workers: int = MAX_WORKERS) -> list[Any]:
    """Run zero-arg callables concurrently, returning results in INPUT ORDER.

    Order-preserving (index-keyed, not as-completed) so any selection-sensitive
    caller stays deterministic. A task that raises is captured and returned IN
    PLACE (the exception object) rather than aborting the batch, so each call
    site keeps its own error semantics. 0/1 tasks run inline (no pool overhead).
    """
    n = len(tasks)
    if n == 0:
        return []
    if n == 1:
        try:
            return [tasks[0]()]
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller
            return [exc]

    results: list[Any] = [None] * n
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, n)) as pool:
        fut_to_idx = {pool.submit(task): i for i, task in enumerate(tasks)}
        for fut in concurrent.futures.as_completed(fut_to_idx):
            idx = fut_to_idx[fut]
            try:
                results[idx] = fut.result()
            except Exception as exc:  # noqa: BLE001 - surfaced to the caller
                results[idx] = exc
    return results
