"""Graph max-flow-style multi-path swap router for SN112 (Minotaur).

Models the routing problem as a FLOW on a token graph, per the DEX-aggregator /
network-flow framing:

    nodes = tokens
    edges = pools (a pool between A and B is two directed converting edges)

The objective is to move `amount_in` of `token_in` to `token_out` maximizing the
delivered output. This is NOT plain max-flow (Dinic's): a swap edge CONVERTS
tokens (1 WETH -> ~3500 USDC, not 1:1) and its rate DEGRADES with size (price
impact -> concave output). So we solve the correct member of the flow family:

    min-cost / convex-cost flow via SUCCESSIVE SHORTEST AUGMENTING PATHS.

Each iteration:
  1. price every edge's *marginal* rate at its current fill; edge cost = -log(rate)
  2. Bellman-Ford from token_in finds the max-product-rate path to token_out
     (the classic -log shortest-path = best exchange rate; Bellman-Ford because
     cross-token -log weights are signed, and no-arbitrage => no negative cycle)
  3. push one chunk of input along that path, propagating the real amount hop by
     hop and updating each edge's fill (so the next chunk sees the worse rate)
  4. repeat until the input is spent or no positive-output path remains

Because a filled path's marginal rate drops, later chunks spill onto other paths
-> the router splits across multiple paths automatically, single- or multi-hop.
This is the graph generalization of `split_router.py` (parallel pools only).

Pure / deterministic / stdlib-only, so it is unit-testable without SDK or RPC.
Edges take a concave `output(amount)->amount_out` function, so V3, Aerodrome,
and constant-product pools compose uniformly. Ties break on insertion order.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Edge:
    """A directed converting edge token_in -> token_out backed by one pool.

    output_fn(total_in) -> total_out delivered for a CUMULATIVE input of
    `total_in` (concave, non-decreasing, 0 if infeasible). `filled` tracks how
    much input has already been routed through this edge so marginal rates
    reflect price impact as the solve progresses.
    """
    key: str
    token_in: str
    token_out: str
    output_fn: Callable[[int], int]
    filled: int = 0

    def marginal_out(self, add: int) -> int:
        """Extra output from pushing `add` more input at the current fill."""
        if add <= 0:
            return 0
        return self.output_fn(self.filled + add) - self.output_fn(self.filled)

    def push(self, add: int) -> int:
        """Commit `add` input; return the incremental output delivered."""
        out = self.marginal_out(add)
        self.filled += add
        return out


class TokenGraph:
    """Directed multigraph of tokens; edges are pool directions.

    Build once from on-chain data, then `add_pool` more as data streams in.
    `best_route` runs the successive-shortest-augmenting-path solve.
    """

    def __init__(self) -> None:
        self._adj: dict[str, list[Edge]] = {}
        self._edges: list[Edge] = []

    # ── construction / incremental updates ────────────────────────────
    def add_pool(self, token_a: str, token_b: str,
                 out_ab: Callable[[int], int],
                 out_ba: Callable[[int], int],
                 key: str | None = None) -> None:
        """Add a pool as two directed converting edges (A->B and B->A)."""
        a, b = token_a.lower(), token_b.lower()
        k = key or f"{a[:6]}/{b[:6]}:{len(self._edges)}"
        self._add_edge(Edge(f"{k}:ab", a, b, out_ab))
        self._add_edge(Edge(f"{k}:ba", b, a, out_ba))

    def add_directed(self, token_in: str, token_out: str,
                     output_fn: Callable[[int], int], key: str | None = None) -> None:
        """Add a single directed edge (e.g. a one-way bridge leg)."""
        self._add_edge(Edge(key or f"{token_in[:6]}->{token_out[:6]}:{len(self._edges)}",
                            token_in.lower(), token_out.lower(), output_fn))

    def _add_edge(self, e: Edge) -> None:
        self._adj.setdefault(e.token_in, []).append(e)
        self._adj.setdefault(e.token_out, self._adj.get(e.token_out, []))
        self._edges.append(e)

    def reset_fills(self) -> None:
        for e in self._edges:
            e.filled = 0

    # ── routing ───────────────────────────────────────────────────────
    def best_route(self, token_in: str, token_out: str, amount_in: int,
                   *, chunks: int = 128, probe_frac: float = 1.0,
                   max_hops: int = 4) -> "RouteResult":
        """Route `amount_in` src->dst maximizing output; may split across paths.

        chunks:     granularity of augmentation (higher = finer split, slower).
        probe_frac: marginal probe size as a fraction of the chunk (1.0 = the
                    whole chunk; smaller linearizes better on steep curves).
        max_hops:   cap on path length (guards pathological deep paths).
        """
        src, dst = token_in.lower(), token_out.lower()
        self.reset_fills()
        if src == dst or amount_in <= 0 or src not in self._adj:
            return RouteResult({}, 0, amount_in)

        n = max(1, min(chunks, amount_in))
        base = amount_in // n
        rem = amount_in - base * n
        chunk_sizes = [base + (1 if i < rem else 0) for i in range(n)]

        # path_signature -> {"in": total_in, "out": total_out, "hops": [edge.key,...]}
        routes: dict[tuple, dict] = {}
        total_out = 0
        routed_in = 0

        for size in chunk_sizes:
            if size <= 0:
                continue
            probe = max(1, int(size * probe_frac))
            path = self._best_marginal_path(src, dst, probe, max_hops)
            if path is None:
                break  # no path delivers positive output anymore
            # push the real chunk along the path, hop by hop
            amt = size
            delivered = self._push_path(path, amt)
            if delivered <= 0:
                break
            sig = tuple(e.key for e in path)
            r = routes.setdefault(sig, {"in": 0, "out": 0,
                                        "hops": [(e.token_in, e.token_out, e.key) for e in path]})
            r["in"] += amt
            r["out"] += delivered
            total_out += delivered
            routed_in += amt

        return RouteResult(routes, total_out, amount_in - routed_in)

    # ── internals ─────────────────────────────────────────────────────
    def _best_marginal_path(self, src: str, dst: str, probe: int,
                            max_hops: int) -> list[Edge] | None:
        """Bellman-Ford: max product of marginal rates = min sum of -log(rate).

        Edge weight = -log(marginal_out(probe) / probe). Marginal rate 0 -> edge
        skipped (weight +inf). No-arbitrage => no negative cycle, so BF is safe.
        """
        INF = float("inf")
        dist: dict[str, float] = {src: 0.0}
        prev: dict[str, Edge | None] = {src: None}
        hops: dict[str, int] = {src: 0}

        # Bellman-Ford relaxation, bounded by max_hops.
        for _ in range(max_hops):
            improved = False
            for u, edges in self._adj.items():
                if u not in dist:
                    continue
                if hops[u] >= max_hops:
                    continue
                for e in edges:
                    rate = e.marginal_out(probe) / probe
                    if rate <= 0:
                        continue
                    w = -math.log(rate)
                    nd = dist[u] + w
                    v = e.token_out
                    if nd < dist.get(v, INF) - 1e-15:
                        dist[v] = nd
                        prev[v] = e
                        hops[v] = hops[u] + 1
                        improved = True
            if not improved:
                break

        if dst not in prev and dst != src:
            return None
        # reconstruct
        path: list[Edge] = []
        node = dst
        seen = set()
        while node != src:
            e = prev.get(node)
            if e is None or node in seen:
                return None
            seen.add(node)
            path.append(e)
            node = e.token_in
        path.reverse()
        return path or None

    def _push_path(self, path: list[Edge], amount_in: int) -> int:
        """Propagate amount_in through the path, committing each edge's fill."""
        amt = amount_in
        for e in path:
            amt = e.push(amt)
            if amt <= 0:
                return 0
        return amt


# ── building the graph from on-chain pool data ────────────────────────────
def add_v3_pool(graph: "TokenGraph", token0: str, token1: str,
                sqrt_price_x96: int, liquidity: int, fee_ppm: int,
                key: str | None = None) -> None:
    """Add a Uniswap-V3-style pool to the graph as two converting edges.

    Uses `pool_math.compute_v3_output`, so the edge output curve matches the
    quoter's single-tick concentrated-liquidity math (0 beyond the ~1% impact
    cap). `output_fn(total_in)` is a pure function of the amount, which is
    exactly the cumulative-output semantics the flow router needs.
    """
    from strategies.dex_aggregator.pool_math import compute_v3_output

    def out01(amt: int) -> int:  # token0 -> token1 (zero_for_one=True)
        return compute_v3_output(sqrt_price_x96, liquidity, amt, True, fee_ppm)

    def out10(amt: int) -> int:  # token1 -> token0
        return compute_v3_output(sqrt_price_x96, liquidity, amt, False, fee_ppm)

    graph.add_pool(token0, token1, out01, out10, key=key)


def build_graph_from_pool_states(pool_states: dict, only_v3: bool = True) -> "TokenGraph":
    """Build (or seed) a TokenGraph from the solver's discovered pool_states.

    `pool_states` is the same dict the baseline discovery fills: keyed by pool
    address, each value carrying token0/token1/fee/sqrtPriceX96/liquidity. Call
    this at startup for the initial graph, and call `add_v3_pool` incrementally
    as more pools are discovered per order (the graph is cumulative — routing
    resets only the per-edge FILL, never the topology).
    """
    g = TokenGraph()
    for addr, ps in (pool_states or {}).items():
        try:
            t0 = ps.get("token0"); t1 = ps.get("token1")
            liq = int(ps.get("liquidity", 0) or 0)
            sp = int(ps.get("sqrtPriceX96", 0) or 0)
            fee = int(ps.get("fee", 3000) or 3000)
            if not t0 or not t1 or liq <= 0 or sp <= 0:
                continue
            add_v3_pool(g, t0, t1, sp, liq, fee, key=str(addr))
        except Exception:
            continue  # skip malformed rows; a bad pool never breaks the graph
    return g


@dataclass
class RouteResult:
    routes: dict          # path_signature -> {"in","out","hops"}
    total_output: int     # sum of delivered output across all paths
    unrouted_in: int = 0  # input that couldn't be profitably routed
    paths: int = field(default=0)

    def __post_init__(self):
        self.paths = len([r for r in self.routes.values() if r["in"] > 0])

    @property
    def is_split(self) -> bool:
        return self.paths > 1

    def leg_summary(self) -> list[dict]:
        """Human-readable per-path summary, largest input first."""
        out = []
        for sig, r in self.routes.items():
            hop_str = " -> ".join(
                [h[0][:8] for h in r["hops"]] + [r["hops"][-1][1][:8]]
            ) if r["hops"] else ""
            out.append({"path": hop_str, "in": r["in"], "out": r["out"], "keys": list(sig)})
        out.sort(key=lambda x: x["in"], reverse=True)
        return out
