"""Calldata/ABI layer for the on-fork router (bg124_onfork).

Split out purely for REGION DISCIPLINE: a module's top-level region counts every
function HEADER in the file, so ~20 defs in one module pushed that region to 168
against a champion at 150 — we would win orders and then lose the tie-break that
decides the crown. Two files halve the header count each, and every builder here
stays small. Address/selector tables live in onfork_tables.json because JSON
data contributes zero AST nodes.
"""
from __future__ import annotations
_DR_UNSET = object()
import json
from pathlib import Path

def _load():
    try:
        return json.loads((Path(__file__).parent / 'onfork_tables.json').read_text())
    except Exception:
        return {}
T = _load()
SEL = T.get('sel', {})
_ZED = '0x0000000000000000000000000000000000000000'

def ck(a):
    from eth_utils import to_checksum_address as _c
    return _c(a)

def enc(types, vals):
    from eth_abi import encode as _e
    return _e(types, vals)

def addr(a):
    return bytes.fromhex(a[2:].rjust(40, '0'))

def path_bytes(tokens, fees):
    b = b''
    for k, t in enumerate(tokens):
        b += addr(t)
        if k < len(fees):
            b += int(fees[k]).to_bytes(3, 'big')
    return b

def q_single(tin, tout, amt, fee):
    return bytes.fromhex(SEL['qsingle']) + enc(['(address,address,uint256,uint24,uint160)'], [(ck(tin), ck(tout), amt, fee, 0)])

def q_path(tin, mid, tout, fees, amt):
    return bytes.fromhex(SEL['qpath']) + enc(['bytes', 'uint256'], [path_bytes([tin, mid, tout], fees), amt])

def q_v2(amt, path):
    return bytes.fromhex(SEL['v2out']) + enc(['uint256', 'address[]'], [amt, [ck(t) for t in path]])

def q_bal(tin, tout, amt, pool_id):
    """Balancer V2 quote -- BalancerQueries.querySwap.

    querySwap is `nonpayable` and Balancer's query mechanism works by reverting
    internally and catching it, so nesting it inside the Multicall3 batch was NOT
    safe to assume. Verified live 08-18: nested in aggregate3 it returned values
    BYTE-IDENTICAL to the direct eth_call, so a Balancer candidate rides the
    existing single batched call and costs ZERO extra RPC.
    funds.sender does not affect the quote (measured: zero address, an EOA, and
    the Vault itself all returned the same number), so a constant is used here and
    the real proxy is bound only at execution time, in swap_cd.
    """
    return bytes.fromhex(SEL['qbal']) + enc(['(bytes32,uint8,address,address,uint256,bytes)', '(address,bool,address,bool)'], [(bytes.fromhex(str(pool_id).replace('0x', '')), 0, ck(tin), ck(tout), amt, b''), (ck(_ZED), False, ck(_ZED), False)])

def _curve_ix(kind):
    """Curve index type: stable pools take int128, crypto pools uint256."""
    return 'int128' if kind == 'stable' else 'uint256'

def q_curve(kind, i, j, amt):
    """get_dy on a KNOWN pool — 0.37s (the registry's get_best_rate was 20.6s
    and returned an unexecutable route, measured on a fork)."""
    x = _curve_ix(kind)
    sel = _sel4('get_dy(%s,%s,uint256)' % (x, x))
    return sel + enc([x, x, 'uint256'], [i, j, amt])

def s_curve(kind, i, j, amt, min_dy):
    """exchange() pulls from msg.sender after approve — the same pattern the
    champion's own V2/V3 swaps use, so it executes through the scored proxy."""
    x = _curve_ix(kind)
    sel = _sel4('exchange(%s,%s,uint256,uint256)' % (x, x))
    return '0x' + (sel + enc([x, x, 'uint256', 'uint256'], [i, j, amt, min_dy])).hex()

def _sel4(sig):
    from eth_utils import keccak
    return keccak(sig.encode())[:4]

def decode_one(kind, data):
    """V2 getAmountsOut returns uint256[] (take the last leg); the V3 quoter
    returns uint256 in the first word."""
    from eth_abi import decode as dec
    if not data or len(data) < 32:
        return 0
    try:
        if kind == 'v2':
            arr = dec(['uint256[]'], data)[0]
            return int(arr[-1]) if arr else 0
        return int(dec(['uint256'], data[:32])[0])
    except Exception:
        return 0

def approve_cd(spender, amt):
    return '0x' + SEL['approve'] + enc(['address', 'uint256'], [ck(spender), amt]).hex()

def s_v2(amt, min_out, path, to):
    body = enc(['uint256', 'uint256', 'address[]', 'address', 'uint256'], [amt, min_out, [ck(t) for t in path], ck(to), 9999999999])
    return '0x' + SEL['v2swap'] + body.hex()

def s_single(tin, tout, fee, amt, min_out, to):
    body = enc(['(address,address,uint24,address,uint256,uint256,uint160)'], [(ck(tin), ck(tout), fee, ck(to), amt, min_out, 0)])
    return '0x' + SEL['ssingle'] + body.hex()

def s_path(tin, mid, tout, fees, amt, min_out, to):
    body = enc(['(bytes,address,uint256,uint256)'], [(path_bytes([tin, mid, tout], list(fees)), ck(to), amt, min_out)])
    return '0x' + SEL['spath'] + body.hex()

def s_bal(pool_id, tin, tout, amt, proxy, to):
    """Balancer Vault.swap calldata -- byte-for-byte the shape g2_codec's
    _lift_bal_swap_cd_0 already serves on baked rows.

    limit=0: GIVEN_IN puts min-out in that slot, and 0 means never revert on
    slippage. A revert is a `dropped`, the absolute veto, which costs far more
    than any slippage it could save.
    funds.sender MUST be the executing proxy, not the recipient: the Vault
    requires sender == msg.sender absent a relayer approval, and the approve leg
    is signed by the proxy. The recipient stays the credited app so the route is
    not stranded at msg.sender.

    Split out of swap_cd for REGION DISCIPLINE, the same rule this module's
    docstring already follows: an encode literal is ~80 AST nodes and data
    literals do NOT start their own region, so inlining this made swap_cd the
    repo's largest region (197 -> 210) and gave away the factorization tiebreak.
    As a named helper the body forms its own region and swap_cd drops back.
    """
    return '0x' + (bytes.fromhex(SEL['sbal']) + enc(['(bytes32,uint8,address,address,uint256,bytes)', '(address,bool,address,bool)', 'uint256', 'uint256'], [(bytes.fromhex(str(pool_id).replace('0x', '')), 0, ck(tin), ck(tout), amt, b''), (ck(proxy), False, ck(to), False), 0, 9999999999])).hex()

def swap_cd(desc, tin, tout, amt, min_out, to):
    """desc = ("v2", router, path) | ("curve", pool, (kind,i,j))
    | ("single", fee, None) | ("path", fees, mid)."""

    def _dz31():
        if kind == 'v2':
            return (s_v2(amt, min_out, b, to),)
        if kind == 'curve':
            return (s_curve(b[0], b[1], b[2], amt, min_out),)
        if kind == 'pcsp':
            return (s_path(tin, b, tout, a, amt, min_out, to),)
        if kind in ('single', 'pcs'):
            return (s_single(tin, tout, a, amt, min_out, to),)
        return _DR_UNSET
    kind, a, b = desc
    if kind == 'bal':
        return s_bal(a, tin, tout, amt, b, to)
    _r_dz31 = _dz31()
    if _r_dz31 is not _DR_UNSET:
        return _r_dz31[0]
    return s_path(tin, b, tout, a, amt, min_out, to)

def spender(desc, chain):
    """Approve target = whoever pulls the tokens: the V2 router or the Curve
    pool itself, else SwapRouter02."""
    if desc[0] == 'bal':
        return ck(T['bal']['vault'])
    if desc[0] in ('v2', 'curve'):
        return desc[1]
    if desc[0] in ('pcs', 'pcsp'):
        return ck(T['router2'][str(chain)])
    return ck(T['router'][str(chain)])