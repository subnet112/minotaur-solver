"""Calldata builders per venue — ported from the lineage's `_shp_*` family
(king_base.py:370-1281) and the v3/aerodrome codecs.

Only the venues that actually decide Base rounds are implemented: uniswap_v3
(single + path), aerodrome_slipstream (single + path), pancake_v3 and the V2
forks. Exotic venues (maverick, algebra, equalizer, V4/UR) are NOT rebuilt —
every corpus order that needs them is already frozen as raw calldata in the
replay bank, which we serve verbatim, so reimplementing their encoders would add
risk for no coverage.

Selector provenance:
  0x04e45aaf  SwapRouter02.exactInputSingle  (Base/OP/Arb — no deadline field)
  0x414bf389  SwapRouter.exactInputSingle    (mainnet V1 — deadline field)
  0xc04b8d59  exactInput (packed path)
  0xa026383e  Slipstream exactInputSingle    (tickSpacing, not fee)
  0x095ea7b3  ERC-20 approve
"""
from __future__ import annotations
from abi_util import encode_path
from addrs import routers, selectors

def encode_approve(spender, amount):
    from eth_abi.abi import encode
    from eth_utils import to_checksum_address as ck
    payload = encode(['address', 'uint256'], [ck(spender), int(amount)])
    return '0x' + (selectors()['approve'] + payload).hex()

def _deadline():
    """The lineage pins a far-future deadline (king_base.py:1299)."""
    return 9999999999

def _v3_single_layout(chain_id):
    """(selector-key, tuple-sig, needs_deadline) for this chain's SwapRouter.

    SwapRouter02 (Base/OP/Arb) dropped the deadline field; mainnet V1 keeps it.
    """
    if int(chain_id) in (8453, 10, 42161):
        return ('v3_single_v2router', '(address,address,uint24,address,uint256,uint256,uint160)', False)
    return ('v3_single_v1router', '(address,address,uint24,address,uint256,uint256,uint256,uint160)', True)

def _v3_args(tin, tout, fee, recipient, amount, min_out, deadline, ck):
    head = (ck(tin), ck(tout), int(fee), ck(recipient))
    tail = (int(amount), int(min_out), 0)
    return head + ((_deadline(),) + tail if deadline else tail)


def _v3_single(tin, tout, fee, recipient, amount, min_out, chain_id):
    """SwapRouter02 (no deadline) on Base; V1 layout (with deadline) on mainnet."""
    from eth_abi.abi import encode
    from eth_utils import to_checksum_address as ck
    key, sig, deadline = _v3_single_layout(chain_id)
    args = _v3_args(tin, tout, fee, recipient, amount, min_out, deadline, ck)
    return '0x' + (selectors()[key] + encode([sig], [args])).hex()

def _slipstream_single(tin, tout, tick, recipient, amount, min_out):
    from eth_abi.abi import encode
    from eth_utils import to_checksum_address as ck
    sig = '(address,address,int24,address,uint256,uint256,uint256,uint160)'
    args = (ck(tin), ck(tout), int(tick), ck(recipient), _deadline(), int(amount), int(min_out), 0)
    payload = encode([sig], [args])
    return '0x' + (selectors()['slipstream_single'] + payload).hex()

def _exact_input_path(path, recipient, amount, min_out=0):
    """exactInput(ExactInputParams) over an ALREADY-packed path."""
    from eth_abi.abi import encode
    from eth_utils import to_checksum_address as ck
    sig = '(bytes,address,uint256,uint256,uint256)'
    args = (path, ck(recipient), _deadline(), int(amount), int(min_out))
    return '0x' + (selectors()['exact_input'] + encode([sig], [args])).hex()

def _exact_input(tokens, params, recipient, amount, min_out):
    """Packed-path exactInput — same layout for uniswap and slipstream."""
    return _exact_input_path(encode_path(tokens, params), recipient, amount, min_out)

def _single_call(venue, param, tin, tout, recipient, amount, min_out, chain_id):
    """Single-hop dispatch -> (router, calldata), or None if not a single-hop venue."""
    rt = routers(chain_id)
    if venue in ('uniswap_v3', 'pancake_v3') and venue in rt:
        return (rt[venue], _v3_single(tin, tout, param, recipient, amount, min_out, chain_id))
    if venue == 'aerodrome_slipstream' and venue in rt:
        return (rt[venue], _slipstream_single(tin, tout, param, recipient, amount, min_out))
    return None

def _path_call(venue, param, mid, tin, tout, recipient, amount, min_out, chain_id):
    """2-hop packed-path dispatch -> (router, calldata), or None."""
    if not mid:
        return None
    rt = routers(chain_id)
    router = rt['uniswap_v3'] if venue.startswith('uniswap') else rt['aerodrome_slipstream']
    return (router, _exact_input((tin, mid, tout), tuple(param), recipient, amount, min_out))

def _swap_call(cand, tin, tout, recipient, amount, min_out, chain_id):
    """Venue dispatch -> (router, calldata). None when the venue isn't rebuilt."""
    venue, param = (cand.get('venue'), cand.get('param'))
    if venue == 'uniswap_v2':
        return _v2_swap_call(param, tin, tout, recipient, amount, chain_id)
    if venue in ('uniswap_v3_multihop', 'aerodrome_slipstream_multihop'):
        return _path_call(venue, param, cand.get('mid'), tin, tout, recipient, amount, min_out, chain_id)
    return _single_call(venue, param, tin, tout, recipient, amount, min_out, chain_id)


def _v2_swap_call(param, tin, tout, recipient, amount, chain_id):
    """(router, calldata) for a Uniswap-V2 swap over the quoted path, or None."""
    import consts
    import v2_codec
    router = consts.v2_routers(chain_id).get('uniswap_v2')
    if not router:
        return None
    path = list(param) if param else [tin, tout]
    return router, v2_codec._v2_call(path, amount, recipient)

def build(cand, tin, tout, recipient, amount, min_out, chain_id):
    """approve + swap interactions for a chosen candidate, or None if unbuildable.

    ``amount_out_minimum`` is pinned to 0 on the swap leg, matching the lineage
    (king_base.py:1288-1294): the harness already enforces the order's min_output
    invariant at the intent level and the quoter verified this venue clears it,
    so a per-swap min only adds spurious slippage reverts. ``min_out`` stays in
    the signature because selection still filters on it upstream.
    """
    call = _swap_call(cand, tin, tout, recipient, amount, 0, chain_id)
    if call is None:
        return None
    router, data = call
    return [{'target': tin, 'value': '0', 'data': encode_approve(router, int(amount))}, {'target': router, 'value': '0', 'data': data}]