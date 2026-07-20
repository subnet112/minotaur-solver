"""Split-routing optimizer for SN112 (Minotaur) miner solver.

Implements the parallel-pool splitting the DEX-aggregator routing literature
calls for: given several venues that trade the same pair (Uniswap V3 fee tiers,
Aerodrome Slipstream, etc.), allocate the input amount across them to MAXIMIZE
total output net of gas, instead of dumping the whole trade into one pool.

Why this is an edge on Minotaur
-------------------------------
The V3 output math (``pool_math.compute_v3_output``) caps a single pool at ~1%
price impact and returns 0 beyond it. So on a LARGE order the champion's
single-hop selection either saturates one pool (poor rate) or drops the order
(returns 0). Spreading the input across parallel pools keeps each leg in its
low-impact region and captures materially more output — a strict WIN, and on
orders the champion drops, a blind-spot cover.

Design
------
Pure, deterministic, dependency-free (stdlib only) so it is unit-testable
without the SDK or RPC. Each venue is described by a *concave* output function
``output(amount_in:int) -> output_wei:int`` (0 when infeasible) plus a one-time
gas cost expressed in OUTPUT-token wei. The optimizer never assumes a specific
curve, so V3, Aerodrome, and stable-swap venues compose uniformly.

Algorithm: marginal-output water-filling — the discrete form of the marginal-
price equalization 1inch/Uniswap use. For a concave output function, greedily
handing each input chunk to the venue with the highest *marginal* output is
optimal in the continuous limit; discretization error shrinks with ``chunks``.
Ties break on venue index so the result is deterministic (the subnet replays
plans and any nondeterminism reads as a regression).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Venue:
    """One place to route (part of) the trade.

    output_fn: amount_in (wei) -> delivered output (wei). MUST be concave and
               non-decreasing, and return 0 when the amount is infeasible
               (e.g. beyond the pool's price-impact cap).
    gas_out:   gas cost of *including* this venue, expressed in OUTPUT-token wei.
               Deducted once if the venue receives any allocation. 0 to ignore gas.
    """
    key: str
    output_fn: Callable[[int], int]
    gas_out: int = 0


@dataclass
class SplitResult:
    allocations: dict[str, int]      # venue key -> input wei assigned (only used venues)
    gross_output: int                # sum of leg outputs, before gas
    net_output: int                  # gross minus gas of used venues
    is_split: bool                   # True if >1 venue used
    legs: int = field(default=0)

    def __post_init__(self):
        self.legs = len([a for a in self.allocations.values() if a > 0])


def _gross_and_net(venues: dict[str, Venue], alloc: dict[str, int]) -> tuple[int, int]:
    gross = 0
    gas = 0
    for k, amt in alloc.items():
        if amt <= 0:
            continue
        gross += venues[k].output_fn(amt)
        gas += venues[k].gas_out
    return gross, gross - gas


def best_single(venues: list[Venue], amount_in: int) -> SplitResult:
    """The champion's behavior: put everything in the single best venue."""
    best_key, best_net, best_gross = None, None, 0
    for v in venues:
        out = v.output_fn(amount_in)
        if out <= 0:
            continue
        net = out - v.gas_out
        if best_net is None or net > best_net or (net == best_net and best_key is None):
            best_key, best_net, best_gross = v.key, net, out
    if best_key is None:
        return SplitResult({}, 0, 0, False)
    return SplitResult({best_key: amount_in}, best_gross, best_net, False)


def optimal_split(
    venues: list[Venue],
    amount_in: int,
    *,
    chunks: int = 256,
    min_leg_bps: int = 50,
) -> SplitResult:
    """Allocate ``amount_in`` across ``venues`` to maximize net output.

    chunks:      granularity of the water-fill (higher = finer, slower).
    min_leg_bps: legs smaller than this fraction of the total are pruned and
                 their amount re-filled among the survivors (a dust leg pays a
                 full gas cost for little output).
    """
    venues = [v for v in venues if v is not None]
    if not venues or amount_in <= 0:
        return SplitResult({}, 0, 0, False)
    if len(venues) == 1:
        return best_single(venues, amount_in)

    by_key = {v.key: v for v in venues}
    alloc = _waterfill(venues, amount_in, chunks)

    # Prune dust legs (min_leg_bps of total) and re-fill among survivors, once.
    floor = amount_in * min_leg_bps // 10_000
    survivors = [by_key[k] for k, amt in alloc.items() if amt >= floor and amt > 0]
    if survivors and len(survivors) < len([a for a in alloc.values() if a > 0]):
        alloc = _waterfill(survivors, amount_in, chunks)
        by_key = {v.key: v for v in survivors}

    gross, net = _gross_and_net(by_key, alloc)
    used = {k: a for k, a in alloc.items() if a > 0}
    return SplitResult(used, gross, net, is_split=len(used) > 1)


def _waterfill(venues: list[Venue], amount_in: int, chunks: int) -> dict[str, int]:
    """Marginal-output greedy allocation. Deterministic (index tie-break)."""
    n = max(1, min(chunks, amount_in))
    base = amount_in // n
    rem = amount_in - base * n
    # chunk sizes: distribute the remainder into the first `rem` chunks
    chunk_sizes = [base + (1 if i < rem else 0) for i in range(n)]

    alloc = {v.key: 0 for v in venues}
    out_at = {v.key: 0 for v in venues}   # cached output at current allocation

    for size in chunk_sizes:
        if size <= 0:
            continue
        best_i, best_marginal = -1, 0
        for i, v in enumerate(venues):
            cur = alloc[v.key]
            new_out = v.output_fn(cur + size)
            marginal = new_out - out_at[v.key]
            # strict '>' with index tie-break keeps it deterministic
            if best_i == -1 or marginal > best_marginal:
                best_i, best_marginal, best_new_out = i, marginal, new_out
        if best_i == -1 or best_marginal <= 0:
            # no venue can absorb more profitably; stop (leftover stays unrouted)
            break
        vk = venues[best_i].key
        alloc[vk] += size
        out_at[vk] = best_new_out
    return alloc


def choose(
    venues: list[Venue],
    amount_in: int,
    *,
    improve_bps: int = 10,
    chunks: int = 256,
    min_leg_bps: int = 50,
) -> tuple[SplitResult, bool]:
    """Compare the optimal split against the best single venue.

    Returns (result, use_split). ``use_split`` is True only when the split beats
    the single-venue net output by at least ``improve_bps`` (0.1% default, the
    subnet's noise band) — so we never trade a proven single-hop plan for a
    marginal, within-noise split. This is the gate that keeps the enhancement
    strictly non-regressing versus the champion's own selection.
    """
    single = best_single(venues, amount_in)
    split = optimal_split(venues, amount_in, chunks=chunks, min_leg_bps=min_leg_bps)
    if not split.is_split:
        return single, False
    # require a strict, above-noise improvement on NET output
    threshold = single.net_output + (single.net_output * improve_bps // 10_000)
    if single.net_output > 0 and split.net_output > threshold:
        return split, True
    if single.net_output <= 0 and split.net_output > 0:
        # champion delivers nothing here; the split is a blind-spot cover
        return split, True
    return single, False
