"""Pure venue-quoting + calldata helpers for MultiVenueSolver, split out of
min_multivenue.py so each module's max-region (the scored factor) stays low.
No solver/state dependency — only (w3, block) + primitive args. Behaviour is
byte-identical to the originals; this is a pure relocation + two extractions."""
from __future__ import annotations
from eth_abi import encode as _menc, decode as _mdec
from eth_utils import keccak as _mk, to_checksum_address as _cs
from minotaur_subnet.shared.types import Interaction as _MIx

_QUOTER = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"   # UniV3 QuoterV2 (champion's quoter)
_META = "0xF98B45FA17DE75FB1aD0e7aFD971b0ca00e379fC"      # Curve MetaRegistry (find_pools/indices)
_FEES = (100, 500, 3000, 10000)
_WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"    # UniV3 routing hub (primary)
_USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"    # UniV3 routing hub (secondary)
_HUBS = (_WETH, _USDC)
_SWROUTER = "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"  # UniV3 SwapRouter02
_HUBFEES = (500, 3000, 10000)                             # fee tiers for the hub legs


def _sel(sig):
    return _mk(sig.encode())[:4]


def _call(w3, to, data, block):
    try:
        r = w3.eth.call({"to": _cs(to), "data": "0x" + data.hex() if isinstance(data, (bytes, bytearray)) else data}, block)
        return bytes(r)
    except Exception:
        return None


def _uni_v3_best(w3, tin, tout, amt, block):
    """Champion's UniV3 QuoterV2 best over fee tiers (single-hop)."""
    best = 0
    for fee in _FEES:
        data = _sel("quoteExactInputSingle((address,address,uint256,uint24,uint160))") + \
            _menc(["(address,address,uint256,uint24,uint160)"],
                  [(_cs(tin), _cs(tout), int(amt), fee, 0)])
        r = _call(w3, _QUOTER, data, block)
        if r and len(r) >= 32:
            try:
                best = max(best, int.from_bytes(r[:32], "big"))
            except Exception:
                pass
    return best


def _curve_dy(w3, pool, i, j, amt, block, sig):
    name = "get_dy(uint256,uint256,uint256)" if sig == "u256" else "get_dy(int128,int128,uint256)"
    types = ["uint256", "uint256", "uint256"] if sig == "u256" else ["int128", "int128", "uint256"]
    data = _sel(name) + _menc(types, [i, j, int(amt)])
    r = _call(w3, pool, data, block)
    if not r or len(r) < 32:
        return 0
    try:
        return int.from_bytes(r[:32], "big")
    except Exception:
        return 0


def _approve_cd(spender, amt):
    return "0x" + (b"\x09\x5e\xa7\xb3" + bytes.fromhex(spender[2:].rjust(64, "0")) +
                   int(amt).to_bytes(32, "big")).hex()


def _exchange_cd(w, amt, recipient):
    """exchange(i, j, dx, 1, receiver) — receiver-variant so output lands at the recipient."""
    types = ["uint256", "uint256", "uint256", "uint256", "address"] if w["ex"] == "u256_recv" \
        else ["int128", "int128", "uint256", "uint256", "address"]
    name = "exchange(%s,%s,uint256,uint256,address)" % (types[0], types[0])
    return "0x" + (_sel(name) + _menc(types, [w["i"], w["j"], int(amt), 1, _cs(recipient)])).hex()


def _curve_ix(w, amt, tin, recipient):
    """approve(pool, amt) + exchange(...) — the executable Curve cover interactions."""
    return [_MIx(target=tin, value="0", call_data=_approve_cd(w["pool"], amt), chain_id=1),
            _MIx(target=w["pool"], value="0", call_data=_exchange_cd(w, amt, recipient), chain_id=1)]


def _find_pools(w3, tin, tout, block):
    """All Curve pools for the pair (metaregistry find_pools_for_coins, plural)."""
    data = _sel("find_pools_for_coins(address,address)") + _menc(["address", "address"], [_cs(tin), _cs(tout)])
    r = _call(w3, _META, data, block)
    if not r:
        return []
    try:
        return [_cs(a) for a in _mdec(["address[]"], r)[0] if int(a, 16) != 0]
    except Exception:
        return []


def _coin_indices(w3, pool, tin, tout, block):
    data = _sel("get_coin_indices(address,address,address)") + _menc(["address", "address", "address"], [_cs(pool), _cs(tin), _cs(tout)])
    r = _call(w3, _META, data, block)
    if not r or len(r) < 64:
        return None
    try:
        v = _mdec(["int128", "int128", "bool"], r); return int(v[0]), int(v[1])
    except Exception:
        return None


def _curve_best_live(w3, tin, tout, amt, block):
    """Best (dy, pool, i, j, sig) across ALL Curve pools for the pair, quoted live."""
    best = (0, None, None, None, None)
    for pool in _find_pools(w3, tin, tout, block)[:6]:
        ij = _coin_indices(w3, pool, tin, tout, block)
        if not ij:
            continue
        for sig in ("u256", "i128"):
            dy = _curve_dy(w3, pool, ij[0], ij[1], amt, block, sig)
            if dy > best[0]:
                best = (dy, pool, ij[0], ij[1], sig)
                break
    return best


def _v3_path(tin, fa, hub, tout, fb):
    """Encode a 2-hop UniV3 path tin -(fa)-> hub -(fb)-> tout."""
    return (bytes.fromhex(tin[2:].rjust(40, "0")) + int(fa).to_bytes(3, "big") +
            bytes.fromhex(hub[2:]) + int(fb).to_bytes(3, "big") +
            bytes.fromhex(tout[2:].rjust(40, "0")))


def _v3_quote_one(w3, path, amt, block):
    data = _sel("quoteExactInput(bytes,uint256)") + _menc(["bytes", "uint256"], [path, int(amt)])
    r = _call(w3, _QUOTER, data, block)
    if r and len(r) >= 32:
        try:
            return int.from_bytes(r[:32], "big")
        except Exception:
            return 0
    return 0


def _v3_paths(tin, tout):
    return [_v3_path(tin, fa, hub, tout, fb)
            for hub in _HUBS if tin != hub.lower() and tout != hub.lower()
            for fa in _HUBFEES for fb in _HUBFEES]


def _uni_v3_multi_best(w3, tin, tout, amt, block):
    """Best 2-hop (tin->hub->tout) UniV3 quote over hubs {WETH,USDC} x fee-pairs, quoted in
    PARALLEL (matches the champion's own parallel quoting so it won't blow the solve budget).
    Returns (out, path_bytes) or (0, None)."""
    paths = _v3_paths(tin, tout)
    if not paths:
        return 0, None
    best = (0, None)
    try:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as ex:
            for p, out in zip(paths, ex.map(lambda pp: _v3_quote_one(w3, pp, amt, block), paths)):
                if out > best[0]:
                    best = (out, p)
        return best
    except Exception:
        pass
    for path in paths:                       # sequential fallback if threads unavailable
        out = _v3_quote_one(w3, path, amt, block)
        if out > best[0]:
            best = (out, path)
    return best


def _v3_ix(tin, path, amt, recipient):
    """approve(router, amt) + exactInput(path, recipient, amt, minOut=1) — drop-safe cover."""
    params = _menc(["(bytes,address,uint256,uint256)"], [(path, _cs(recipient), int(amt), 1)])
    return [_MIx(target=tin, value="0", call_data=_approve_cd(_SWROUTER, amt), chain_id=1),
            _MIx(target=_SWROUTER, value="0",
                 call_data="0x" + (_sel("exactInput((bytes,address,uint256,uint256))") + params).hex(),
                 chain_id=1)]


def _best_blindfill_ix(w3, block, tin, tout, amt, recip):
    """Best live route across venues (Curve all-pools + UniV3 2-hop), as executable
    interactions, or None. Drop-safe: caller only invokes on a champion-blind order."""
    dy, pool, i, j, sig = _curve_best_live(w3, tin, tout, amt, block)
    v3_out, v3_path = _uni_v3_multi_best(w3, tin, tout, amt, block)
    if v3_out > dy and v3_path is not None:
        return _v3_ix(tin, v3_path, amt, recip)
    if dy > 0 and pool:
        w = {"pool": pool, "i": i, "j": j, "ex": "u256_recv" if sig == "u256" else "i128_recv"}
        return _curve_ix(w, amt, tin, recip)
    return None
