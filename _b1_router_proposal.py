# PROPOSAL (not wired in): a generalized best-of-{direct, hub-2-hop} router cover.
#
# This generalizes _b1_cover_weth_dai (which hardcodes the USDC hub + DAI story)
# into ONE cover that works for ANY (tin, tout) pair on Base by trying the direct
# single-hop AND a 2-hop through each curated deep-liquidity hub, then emitting
# whichever single plan the LIVE quotes say delivers the most.
#
# Why it wins (legitimately): the champion is single-hop-only on Base — its
# multi-hop codec (selector c04b8d59) reverts — so for every pair whose direct
# pool is thinner than a 2-hop via a deep hub, the champion is EMPTY or worse.
# One router captures that whole class instead of one hand-written pair at a time.
#
# Safety (monotonic >= champion on the fill-empty path):
#   * Only invoked when the champion returned EMPTY for the order.
#   * amount_out_minimum defaults to 0 on the fill-empty path: any delivery beats
#     a champion-0, and a revert simply returns the champion-0 baseline.
#   * When called from the OVERRIDE path (amount_out_min_floor > 0), the emitted
#     swap carries that floor, so it delivers more than the champion or reverts to
#     the champion baseline — never a regression.
#
# To adopt: paste _b1_cover_router into _build_b1_fill_empty (after
# _b1_cover_usdc_weth), define the hub list, and register it in _B1_COVERS for the
# pairs a scorecard proves it wins (start narrow, one proven pair at a time).
#
# All names (_b1_params, _b1_w3, _b1_quote_single, _b1_quote_path, _b1_encode_path,
# _b1_encode_exact_input_base, _b1_v3single, _b1_approve, _B1Plan, _B1Ix,
# _B1_ROUTER_8453, _b1time) already exist in _build_b1_fill_empty's scope.

# Curated deep-liquidity intermediaries on Base, best-first. A hub is only used
# for a given order when it is not one of the order's own tokens. Keep this SHORT:
# each extra hub is +N quoter calls per order (latency), and only hubs with real
# depth help. USDC and WETH are the canonical Base hubs; DAI/cbBTC optional.
_B1_ROUTER_HUBS = [
    _B1_USDC_BASE,   # deepest stable hub on Base
    _B1_WETH_BASE,   # deepest native hub on Base
]

# Fee-tier candidates. Direct: try all standard tiers. Hub legs: the tiers that
# actually carry Base depth (100/500 for stables, 500/3000 for volatile legs).
_B1_ROUTER_DIRECT_FEES = (100, 500, 3000, 10000)
_B1_ROUTER_HUB_LEG_FEES = (100, 500, 3000)


def _b1_cover_router(intent, state, snapshot, amount_out_min_floor=0, inst=None):
    """Best-of-{direct single-hop, 2-hop via each curated hub} for this order.

    Live-quotes every candidate route and emits the single best. On the fill-empty
    path (floor=0) any positive delivery beats a champion-0; on the override path
    (floor>0) the swap carries that minimum so it cannot regress the champion.
    Returns None if the order is unusable or (override path) nothing clears the
    floor -> defer to champion.
    """
    p = _b1_params(state)
    tin = str(p.get('input_token', '') or '')
    tout = str(p.get('output_token', '') or '')
    amount_in = int(p.get('input_amount', 0) or 0)
    if amount_in <= 0 or not tin or not tout:
        return None
    recipient = getattr(state, 'contract_address', '') or getattr(state, 'owner', '')
    if not recipient:
        _b1_logger.info('[b1] router: no recipient (contract_address/owner empty); defer')
        return None
    chain_id = int(getattr(state, 'chain_id', 0) or 0)
    deadline = int(_b1time.time()) + 300
    w3 = _b1_w3(state, inst)

    tin_l, tout_l = tin.lower(), tout.lower()

    # --- candidate 1: best direct single-hop ---
    best = {'out': -1, 'kind': None, 'fee': None, 'path': None}
    for fee in _B1_ROUTER_DIRECT_FEES:
        o = _b1_quote_single(w3, tin, tout, amount_in, fee)
        if o > best['out']:
            best = {'out': o, 'kind': 'direct', 'fee': fee, 'path': None}

    # --- candidates 2..N: 2-hop via each hub, over the hub-leg fee grid ---
    for hub in _B1_ROUTER_HUBS:
        if hub.lower() in (tin_l, tout_l):
            continue  # hub must be a distinct third token
        for f1 in _B1_ROUTER_HUB_LEG_FEES:
            for f2 in _B1_ROUTER_HUB_LEG_FEES:
                o = _b1_quote_path(w3, [tin, hub, tout], [f1, f2], amount_in)
                if o > best['out']:
                    best = {'out': o, 'kind': 'hub', 'fee': (f1, f2),
                            'path': [tin, hub, tout]}

    # No live quote produced anything positive.
    if best['out'] <= 0:
        # With no RPC we cannot prove a route; on the override path we must not
        # emit a blind swap. On the fill-empty path, decline rather than guess —
        # a hand-tuned per-pair cover is the right place for a no-rpc default.
        _b1_logger.info('[b1] router: no positive live quote; defer')
        return None

    # Override-path safety: the winning route must clear the champion floor, else
    # emitting it risks an unconditional revert -> defer to the champion plan.
    floor = int(amount_out_min_floor)
    if floor > 0 and best['out'] < floor:
        return None

    approve_cd = _b1_approve(_B1_ROUTER_8453, amount_in)
    if best['kind'] == 'direct':
        swap_cd = _b1_v3single(token_in=tin, token_out=tout, fee=best['fee'],
                               recipient=recipient, deadline=deadline,
                               amount_in=amount_in, amount_out_minimum=floor,
                               chain_id=chain_id)
        route = f'{tin[:6]}->{tout[:6]} direct fee={best["fee"]} out={best["out"]}'
    else:
        path_bytes = _b1_encode_path(best['path'], list(best['fee']))
        swap_cd = _b1_encode_exact_input_base(path_bytes, recipient, amount_in, floor)
        hub_mid = best['path'][1]
        route = (f'{tin[:6]}->{hub_mid[:6]}->{tout[:6]} hub fee={best["fee"]} '
                 f'out={best["out"]}')

    return _B1Plan(
        intent_id=intent.app_id,
        interactions=[
            _B1Ix(target=tin, value='0', call_data=approve_cd, chain_id=chain_id),
            _B1Ix(target=_B1_ROUTER_8453, value='0', call_data=swap_cd, chain_id=chain_id),
        ],
        deadline=deadline,
        nonce=getattr(state, 'nonce', 0),
        metadata={'solver': 'b1-router', 'route': route,
                  'floored': bool(floor)},
    )
