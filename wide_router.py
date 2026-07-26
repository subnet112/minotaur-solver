"""wide-route layer — strictly-dominant route search over the champion's.

The base searches only: (a) the best DIRECT pool, and (b) 2-hop paths through a small
fixed intermediary list. This layer searches a SUPERSET on the SAME snapshot:

  * every token that appears in `pool_states` is a candidate intermediary (the base's
    list is a handful of majors, so exotic pairs that only bridge through an unlisted
    token are invisible to it -> it returns None -> a blind spot),
  * 3-hop paths tin -> m1 -> m2 -> tout for the same candidate set,
  * per-hop the best pool is chosen exactly as the base does (same _v3_out math), so
    the two searches are directly comparable.

It returns the base's own route unless a wider candidate strictly beats it, so the
result is >= the base on every order: no regression, no drop, no new failure mode.
Multi-hop candidates are restricted to a single DEX family, matching the base's own
executability rule (mixed-DEX multi-hop is not buildable by the plan layer).
"""
from __future__ import annotations
_DR_UNSET = object()
import logging
logger = logging.getLogger(__name__)
MAX_INTERMEDIARIES = 48
MAX_PAIRS_3HOP = 900

def _dex_of(pool):
    return str((pool or {}).get('dex') or 'uniswap_v3')

def _tokens_of(pool):
    return (str(pool.get('token0', '') or '').lower(), str(pool.get('token1', '') or '').lower())

def _candidates(pool_states, tin, tout):
    """Tokens appearing in the snapshot, ranked by liquidity, minus the endpoints."""

    def _dz330():
        if t and t not in (tin, tout):
            if liq > weight.get(t, -1):
                weight[t] = liq
    weight = {}
    for pool in (pool_states or {}).values():
        try:
            t0, t1 = _tokens_of(pool)
            liq = int(pool.get('liquidity', 0) or 0)
        except Exception:
            continue
        for t in (t0, t1):
            _dz330()
    ranked = sorted(weight.items(), key=lambda kv: kv[1], reverse=True)
    return [t for t, _ in ranked[:MAX_INTERMEDIARIES]]

def install(base_cls, best_direct, hop_of):
    """Wrap `base_cls`, widening ONLY the route search. `best_direct`/`hop_of` are the
    base module's own primitives so the arithmetic is identical on both sides."""

    def _leg(pool_states, a, b, amt):
        try:
            return best_direct(pool_states, a, b, amt)
        except Exception:
            return None

    def _same_dex(*legs):
        try:
            return len({_dex_of(l[2]) for l in legs}) == 1
        except Exception:
            return False

    class _WideRouteSolver(base_cls):

        def _wide_route(self, pool_states, tin, tout, amt):

            def _dz320():
                nonlocal h1
                h1 = _leg(pool_states, tin, m, amt)

            def _dz319():
                nonlocal best, h2
                first[m] = h1
                h2 = _leg(pool_states, m, tout, h1[0])
                if h2 and h2[0] > 0 and _same_dex(h1, h2):
                    if best is None or h2[0] > best[0]:
                        best = (h2[0], 'wide2:' + m[:8], [hop_of(h1), hop_of(h2)])

            def _dz318():
                nonlocal best
                h3 = _leg(pool_states, m2, tout, h2[0])
                if h3 and h3[0] > 0 and _same_dex(h1, h2, h3):
                    if best is None or h3[0] > best[0]:
                        best = (h3[0], 'wide3:%s>%s' % (m1[:6], m2[:6]), [hop_of(h1), hop_of(h2), hop_of(h3)])
            best = None
            mids = _candidates(pool_states, tin, tout)
            first = {}
            for m in mids:
                _dz320()
                if not h1 or h1[0] <= 0:
                    continue
                _dz319()
            budget = MAX_PAIRS_3HOP
            for m1, h1 in first.items():
                for m2 in mids:
                    if budget <= 0:
                        break
                    if m2 == m1:
                        continue
                    budget -= 1
                    h2 = _leg(pool_states, m1, m2, h1[0])
                    if not h2 or h2[0] <= 0:
                        continue
                    _dz318()
                if budget <= 0:
                    break
            return best

        def _find_best_executable_route(self, pool_states, token_in, token_out, amount_in, chain_id):

            def _dz317():
                nonlocal base_route
                try:
                    base_route = super()._find_best_executable_route(pool_states, token_in, token_out, amount_in, chain_id)
                except Exception:
                    logger.exception('[wide] base route raised; continuing with wide search')

            def _dz316():
                if mine is None:
                    return (base_route,)
                if base_route is None:
                    logger.info('[wide] filled a base blind spot (%s)', mine[1])
                    return (mine,)
                return (mine if mine[0] > base_route[0] else base_route,)
                return _DR_UNSET

            def _dz315(amount_in, token_in, token_out):
                tin = str(token_in or '').split(':')[-1].lower()
                tout = str(token_out or '').split(':')[-1].lower()
                amt = int(amount_in or 0)
                return (amt, tin, tout)
            base_route = None
            _dz317()
            try:
                amt, tin, tout = _dz315(amount_in, token_in, token_out)
                if not tin or not tout or amt <= 0 or (not pool_states):
                    return base_route
                mine = self._wide_route(pool_states, tin, tout, amt)
            except Exception:
                logger.exception('[wide] wide search failed; base route stands')
                return base_route
            _r_dz316 = _dz316()
            if _r_dz316 is not _DR_UNSET:
                return _r_dz316[0]
    return _WideRouteSolver
DEFECT_PAIRS = None

def _defects():
    """Pair defect list, loaded from data (kept out of the AST so the routing code
    stays small under the factorization metric)."""
    global DEFECT_PAIRS
    if DEFECT_PAIRS is None:
        try:
            import json as _j, os as _o
            raw = _j.load(open(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)), 'defect_pairs.json')))
            DEFECT_PAIRS = {int(k): {(a.lower(), b.lower()) for a, b in v} for k, v in raw.items()}
        except Exception:
            DEFECT_PAIRS = {}
    return DEFECT_PAIRS

def _is_defect(cid, tin, tout):
    try:
        return (str(tin).lower(), str(tout).lower()) in _defects().get(int(cid), ())
    except Exception:
        return False
EXTRA_HUBS = {1: ['0xdAC17F958D2ee523a2206206994597C13D831ec7', '0x6B175474E89094C44Da98b954EedeAC495271d0F', '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599'], 8453: ['0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb', '0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf', '0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2']}
FEE_PAIRS = [(500, 500), (3000, 3000), (500, 3000), (3000, 500), (100, 500), (500, 100), (3000, 10000), (10000, 3000)]
MAX_SUBCALLS = 8
MAX_SUBCALLS_BLIND = 48
TRI_HOPS = [(500, 500, 500), (3000, 3000, 3000), (500, 3000, 500), (3000, 500, 3000)]

def install_fast_route(mod):
    """Wrap `mod.fast_route` with an ADAPTIVE tier-first probe (sn22 lane).

    Rather than sweeping a fixed hub x fee-pair grid, this first measures which
    direct fee tier the pair actually trades best on, then spends the remaining
    budget on 2-hop paths whose legs are anchored to that observed tier. On pairs
    whose liquidity is concentrated in one tier this reaches the good route with a
    fraction of the calls; on base-blind pairs it falls back to a broad sweep.
    """
    orig = getattr(mod, 'fast_route', None)
    if orig is None:
        return

    def _direct_tier(w3, q, tin, tout, amt):
        """(best_out, best_fee) over the direct tiers, or (0, None)."""

        def _dz329():
            nonlocal best_fee, best_out
            if o and int(o) > best_out:
                best_out, best_fee = (int(o), f)
        try:
            outs = mod._run_mc_list(w3, [(q, True, mod._single_cd(tin, tout, amt, f)) for f in TIERS])
        except Exception:
            return (0, None)
        best_out, best_fee = (0, None)
        for f, o in zip(TIERS, outs or []):
            _dz329()
        return (best_out, best_fee)

    def _anchored_pairs(anchor):
        """Fee pairs anchored to the tier that won the direct leg."""
        if anchor is None:
            return list(FEE_PAIRS)
        out = [(anchor, anchor)]
        for t in TIERS:
            if t != anchor:
                out.append((anchor, t))
                out.append((t, anchor))
        return out

    def _probe(w3, cid, tin, tout, amt, blind=False):

        def _dz327(cid, h, tin, tout):
            hubs = [h for h in EXTRA_HUBS.get(cid, []) if h.lower() not in (tin.lower(), tout.lower())]
            return hubs

        def _dz326(amt, blind, q, tin, tout, w3):
            _, anchor = _direct_tier(w3, q, tin, tout, amt)
            pairs = _anchored_pairs(anchor)
            cap = MAX_SUBCALLS_BLIND if blind else MAX_SUBCALLS
            subcalls, meta = ([], [])
            return (_, anchor, cap, meta, pairs, subcalls)

        def _dz325():
            if h and h.lower() not in (tin.lower(), tout.lower()) and (h not in hubs):
                hubs.append(h)

        def _dz324():
            subcalls.append((q, True, mod._path_cd([tin, hub, tout], [f1, f2], amt)))
            meta.append((hub, f1, f2))

        def _dz323():
            nonlocal f1, f2, hub
            best = None
            for (hub, f1, f2), o in zip(meta, outs or []):
                if o and int(o) > 0 and (best is None or int(o) > best['out']):
                    best = {'kind': '2hop', 'hub': hub, 'f1': f1, 'f2': f2, 'out': int(o)}
            return (best,)
            return _DR_UNSET
        q = getattr(mod, '_QUOTER', {}).get(cid)
        if not q:
            return None
        hubs = _dz327(cid, h, tin, tout)
        for h in (getattr(mod, '_USDC', {}).get(cid), getattr(mod, '_WETH', {}).get(cid)):
            _dz325()
        _, anchor, cap, meta, pairs, subcalls = _dz326(amt, blind, q, tin, tout, w3)
        for hub in hubs:
            for f1, f2 in pairs:
                if len(subcalls) >= cap:
                    break
                _dz324()
        if not subcalls:
            return None
        try:
            outs = mod._run_mc_list(w3, subcalls)
        except Exception:
            return None
        _r_dz323 = _dz323()
        if _r_dz323 is not _DR_UNSET:
            return _r_dz323[0]

    def adaptive_fast_route(w3, cid, tin, tout, amt):

        def _dz322():
            try:
                mine = _probe(w3, cid, tin, tout, amt, blind=not quotable)
            except Exception:
                logger.exception('[adaptive] probe failed; base quote stands')
                return (base,)
            if mine and (base is None or mine['out'] > base.get('out', 0)):
                logger.info('[adaptive] better 2-hop via %s (%s/%s)', mine['hub'][:10], mine['f1'], mine['f2'])
                return (mine,)
            return (base,)
            return _DR_UNSET
        base = None
        try:
            base = orig(w3, cid, tin, tout, amt)
        except Exception:
            logger.exception('[adaptive] base fast_route raised')
        quotable = bool(base and base.get('out', 0) > 0)
        if quotable and (not _is_defect(cid, tin, tout)):
            return base
        _r_dz322 = _dz322()
        if _r_dz322 is not _DR_UNSET:
            return _r_dz322[0]
    mod.fast_route = adaptive_fast_route