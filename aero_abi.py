"""aero_abi — word/selector/calldata primitives shared by aero_pin's leg builders.

SPLIT OUT OF aero_pin.py 2026-08-05, pure move + common-subexpression lift; every
byte emitted here is identical to the pre-split code. Two motives:

  * `screening.max_region_nodes` is the largest AST region in ANY file and every
    FILE gets its own module region, so moving this block shrinks aero_pin's.
  * `_path_bytes` and `_pad` were written out TWICE, verbatim, inside
    `_v3_exact_input` and `_quote_v3` (75 and ~20 nodes each time). One copy is
    both smaller in every enclosing region and incapable of drifting.

Aave selectors. aTokens are 1:1 interest-bearing deposit receipts, NOT pool assets —
there is no DEX pool to route them through, which is why the whole aToken family sits
on the SOTAmeter blindspot list uncovered by every solver (aEthUSDC->aEthWETH 29x on
L1; aBasUSDC->aBasWETH 48x, aBasUSDC->aBascbBTC 39x, aBasWETH->USDC 36x, aBascbBTC->
aBasUSDC 35x, aBascbBTC->USDC 33x on Base). Aave redeems 1:1 against the reserve, so
depth is the RESERVE ($2.1B USDC / 2.12M WETH on L1), not a thin pool. Fork-proven
2026-08-03: 100,000 aEthUSDC -> 52.38931487 aEthWETH delivered to the settlement
contract, all 5 calls status 0x1.
"""
from __future__ import annotations
_AAVE_WITHDRAW = '0x69328dec'
_AAVE_SUPPLY = '0x617ba037'
_ERC20_APPROVE = '0x095ea7b3'
_V3_EXACT_IN = '0xc04b8d59'

def _w(x):
    """32-byte word for an address or int."""
    if isinstance(x, str):
        return x.lower().replace('0x', '').rjust(64, '0')
    return hex(int(x))[2:].rjust(64, '0')

def _sel(text):
    """0x-prefixed 4-byte selector. Was an inline lambda inside `_aunwind_ixs`."""
    from eth_utils import keccak as _k
    return '0x' + _k(text=text)[:4].hex()

def _path_bytes(path_toks, fees):
    """Uniswap V3 packed path: tok0 | fee0 | tok1 | fee1 | tok2 …

    Lifted verbatim out of `_v3_exact_input` and `_quote_v3`, which each built it
    with identical code."""

    def _dz315():
        nonlocal raw
        for f, t in zip(fees, path_toks[1:]):
            raw += hex(int(f))[2:].rjust(6, '0') + t[2:].lower()
    raw = path_toks[0][2:].lower()
    _dz315()
    return bytes.fromhex(raw)

def _pad(b):
    """Packed path as hex, right-padded to a whole number of 32-byte words."""
    return b.hex().ljust((len(b) + 31) // 32 * 64, '0')

def _ix(cid, target, data):
    """One Interaction with this layer's invariant fields (value 0, checksummed
    target, chain pinned). Was the `add` closure in `_atoken_ixs` plus two
    hand-rolled copies in `_aunwind_ixs`."""
    from eth_utils import to_checksum_address as _ck
    from minotaur_subnet.shared.types import Interaction as _IX
    return _IX(target=_ck(target), value='0', call_data=data, chain_id=int(cid))

def _withdraw_cd(und, amt, to):
    """Aave Pool.withdraw(asset, amount, to)."""
    return '0x' + _AAVE_WITHDRAW[2:] + _w(und) + _w(amt) + _w(to)

def _approve_cd(spender, amt):
    """ERC20.approve(spender, amount)."""
    return '0x' + _ERC20_APPROVE[2:] + _w(spender) + _w(amt)

def _supply_cd(und, amt, to):
    """Aave Pool.supply(asset, amount, onBehalfOf, referralCode=0)."""
    return '0x' + _AAVE_SUPPLY[2:] + _w(und) + _w(amt) + _w(to) + _w(0)

def _pair_swap_cd(a0, a1, rcpt):
    """Solidly/V2 pair.swap(amount0Out, amount1Out, to, data) with empty `data`."""
    return _sel('swap(uint256,uint256,address,bytes)') + _w(a0) + _w(a1) + _w(rcpt) + _w(128) + _w(0)

def _quote_cd(amt_in, b):
    """QuoterV2.quoteExactInput(path, amountIn)."""
    return '0xcdca1753' + _w(64) + _w(amt_in) + _w(len(b)) + _pad(b)

def _v3_exact_input(path_toks, fees, rcpt, amt_in, min_out=0):
    """SwapRouter exactInput calldata. The tuple is dynamic, so the head is an OUTER
    offset (0x20) THEN the in-tuple path offset (0xa0) — omitting the outer word is a
    silent revert (cost one prototype round 2026-08-03)."""
    b = _path_bytes(path_toks, fees)
    return '0x' + _V3_EXACT_IN[2:] + _w(32) + _w(160) + _w(rcpt) + _w(9999999999) + _w(amt_in) + _w(min_out) + _w(len(b)) + _pad(b)