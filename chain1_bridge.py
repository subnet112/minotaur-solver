"""Compose two baked chain-1 PAIR routes through a shared hub token.

WHY THIS EXISTS. `_chain1_spec_key` is a DIRECT lookup: exact amount, then pair,
then a same-direction amount neighbour, then the mirror of the opposite
direction. Every one of those asks the table for `tin -> tout` as a single row.
A pair the baker never wrote in either direction falls through all four, reads
as un-baked, and `_chain1_baked_core` answers a non-major with `_CHAIN1_SKIP` --
a clean drop, scored zero.

That is what cost sub_a95f9e8cb546 its `dropped` row. `quote:q_edc7c9385b09` is
CVX -> TORN on chain 1, 696556741042020548608 in, and the incumbent delivered
16700032263392589565660. The table has no CVX -> TORN key in either direction,
so we returned nothing. But it holds BOTH halves as pair rows:

    1|<cvx>|<usdc>    tokens [CVX, WETH, USDC]   fees [10000, 500]
    1|<usdc>|<torn>   tokens [USDC, WETH, TORN]  fees [500, 10000]

Spliced at USDC and collapsed (below) that is CVX -10000-> WETH -10000-> TORN:
two hops, each one an eth_call-verified hop of a row the baker already proved.

WHY IT CANNOT REGRESS ANYTHING. It is reached ONLY after all four direct forms
miss, and `_chain1_bridge_spec` refuses a major pair before calling here. An
un-baked NON-major is exactly the case that returns `_CHAIN1_SKIP` today, so
every row this can reach delivers zero right now. Un-baked MAJORS still defer to
the proven zero-RPC fastpath, untouched -- that guard is the load-bearing part,
because overriding the fastpath WOULD be a regression on rows that work.

WHY THE COMPOSITION IS SOUND, hop by hop. A v3 pool is a pair, not a route: the
pools an eth_call verified for `tin -> hub` and for `hub -> tout` are the same
contracts the spliced path walks, in the same direction, at the same fee tiers.
Nothing is reversed and no pool is inferred. `_chain1_build_plan` keeps
min_out=0, so a composed route can be outbid but cannot revert -- the property
that makes it safe to reach on rows a cover might otherwise fill.

WHAT IS DELIBERATELY REFUSED, each for its own reason:
  - the AMOUNT form, on BOTH legs. An amount key names a size that was proven at
    that size. Leg 2's input is leg 1's OUTPUT, which is not known at plan time
    and is not the size the key names, so an amount row is evidence about a
    trade this path does not make. Only pair rows are valid at any size, which
    is precisely what `_key_forms` means by a min_out=0 route blanketing a pair.
  - `venue` on either leg. `curve` rows are (i, j, swap_type) index triples read
    against a fixed `route` array and `univ2` rows carry no fee tiers; neither
    packs into a v3 token+fee path, and splicing the addresses alone would point
    the indices at the wrong coins -- a revert, not a worse price.
  - `noroute`. The baker failing to find a leg is not evidence about the pair.
  - any row whose fee count does not match its hop count, or whose endpoints
    disagree with the key it was filed under. Malformed rather than a route.
  - a path that still repeats a token after collapsing. A route that revisits an
    asset is a cycle, and the encoder would pack a path that pays fees to end up
    where it already was.
"""


def _hub_addresses():
    """The five majors, resolved once and memoised on this function.

    Same set and same source as `_champ_base._chain1_is_major_pair`, read from
    king_consts rather than re-typed here so the two cannot drift apart. WETH
    leads because it is the mid the baker already routes almost everything
    through, so it collapses to the shortest path most often; the rest follow in
    descending order of how often they appear as a baked endpoint.
    """
    cached = getattr(_hub_addresses, 'v', None)
    if cached is None:
        from king_consts import _ETH_WETH, _ETH_USDC, _ETH_USDT, _ETH_WBTC, _ETH_DAI
        cached = tuple(a.lower() for a in (_ETH_WETH, _ETH_USDC, _ETH_USDT, _ETH_WBTC, _ETH_DAI))
        _hub_addresses.v = cached
    return cached


def _pair_leg(table, src, dst):
    """The PAIR-form baked (tokens, fees) for src -> dst, or None to refuse the leg.

    Every refusal in this module's docstring except the cycle check is decided
    here, in one place, so the splice below can assume two legs it is allowed to
    join. The endpoint check is not redundant with the key: a row filed under a
    key whose addresses disagree with its own token list would otherwise splice
    into a path that starts or ends at the wrong asset.
    """
    spec = table.get('1|%s|%s' % (src, dst))

    def _splicable():
        """Whether the row is a plain v3 route at all, before its path is read."""
        return isinstance(spec, dict) and not spec.get('noroute') and not spec.get('venue')

    def _path():
        """The row's (tokens, fees), lowercased and coerced to the encoder's types."""
        return ([str(t).lower() for t in (spec.get('tokens') or ())], [int(f) for f in (spec.get('fees') or ())])

    def _well_formed(toks, fees):
        """Whether the path is a walkable hop chain that starts and ends where the key says."""
        if len(toks) < 2 or len(fees) + 1 != len(toks):
            return False
        return toks[0] == src and toks[-1] == dst
    if not _splicable():
        return None
    toks, fees = _path()
    return (toks, fees) if _well_formed(toks, fees) else None


def _collapse(toks, fees):
    """Remove every immediate out-and-back excursion from a spliced path.

    Splicing at the hub joins two paths that each already route through a mid,
    so the hub is typically reached and left by the SAME asset: CVX -> WETH ->
    USDC spliced to USDC -> WETH -> TORN is [CVX, WETH, USDC, WETH, TORN], which
    pays two extra 0.05% hops and the slippage of a USDC pool to arrive back at
    WETH. `toks[i] == toks[i + 2]` detects exactly that shape; dropping the
    excursion and the two fees it spent leaves CVX -> WETH -> TORN.

    Restarting one index back rather than continuing forward matters: collapsing
    can bring two previously separated tokens into the same relation, and a
    single forward pass would leave the second excursion in the path.
    """
    i = 0
    while i + 2 < len(toks):
        if toks[i] == toks[i + 2]:
            del toks[i + 1:i + 3]
            del fees[i:i + 2]
            i = max(i - 1, 0)
        else:
            i += 1
    return (toks, fees)


def bridge_spec(table, lo_in, lo_out):
    """A v3 spec for lo_in -> lo_out composed through one hub, or None.

    Shortest collapsed path wins, so a hub that folds away beats one that leaves
    its mid in the route; ties keep `_hub_addresses` order, which makes the
    choice deterministic across runs rather than dependent on dict iteration.
    """
    def _through(hub):
        """The collapsed (tokens, fees) routed via this hub, or None if it does not compose.

        The hub is skipped when it is an endpoint: `tin -> tin` is not a leg the table
        holds, and a hub equal to `tout` would make leg 2 a self-pair."""
        if hub == lo_in or hub == lo_out:
            return None
        first = _pair_leg(table, lo_in, hub)
        second = _pair_leg(table, hub, lo_out)
        if first is None or second is None:
            return None
        toks, fees = _collapse(first[0] + second[0][1:], first[1] + second[1])
        if len(toks) < 2 or len(set(toks)) != len(toks):
            return None
        return (toks, fees)
    best = None
    for hub in _hub_addresses():
        cand = _through(hub)
        if cand is not None and (best is None or len(cand[0]) < len(best[0])):
            best = cand
    if best is None:
        return None
    return {'tokens': best[0], 'fees': best[1]}
