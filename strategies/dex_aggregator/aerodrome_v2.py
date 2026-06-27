"""Aerodrome v2 (Velodrome/Solidly-style AMM) integration for Base.

The shipped ``BaselineSwapSolver`` routes Uniswap V3 + Aerodrome **Slipstream**
(concentrated liquidity) only. It does NOT cover **Aerodrome v2** — the original
ve(3,3) AMM with volatile *and* stable pools — which holds the deepest Base
liquidity for stablecoin pairs (USDC/USDbC, USDC/DAI) and for many ve(3,3)-native
tokens (AERO, etc.). On those orders the baseline either gets a worse fill or has
no pool at all (scoring ~0). This module adds that venue.

Quoting is EXACT: Aerodrome's Router exposes ``getAmountsOut`` on-chain, which
runs the same stable/volatile invariant the swap uses — so the quoted output
equals the executed output at a pinned block. No off-chain stable-swap math to
get wrong, and nothing that can quote-high-then-revert.

Deliberately NO ``from __future__ import annotations`` (the harness loads solver
modules via ``exec_module`` without registering them in ``sys.modules``; PEP 563
string annotations on a module-level dataclass crash under that loader — and we
keep this module consistent with that constraint).
"""

import logging

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_hash.auto import keccak

from minotaur_subnet.shared.types import ExecutionPlan, Interaction

logger = logging.getLogger(__name__)

# Aerodrome v2 on Base (chain 8453). Router pulls input via transferFrom and
# dispatches to the correct (stable|volatile) pool from the default PoolFactory.
AERODROME_V2_ROUTER = {8453: "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43"}
AERODROME_V2_FACTORY = {8453: "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"}

# Deterministic far-future deadline (2100-01-01): never expired on a historical
# fork block, identical across validators — no wall-clock, no nondeterminism.
_FAR_FUTURE = 4102444800

# Route struct: struct Route { address from; address to; bool stable; address factory; }
_ROUTE_T = "(address,address,bool,address)"
_SEL_GET_AMOUNTS_OUT = keccak(
    b"getAmountsOut(uint256,(address,address,bool,address)[])"
)[:4]
_SEL_SWAP = keccak(
    b"swapExactTokensForTokens(uint256,uint256,(address,address,bool,address)[],address,uint256)"
)[:4]
_SEL_APPROVE = keccak(b"approve(address,uint256)")[:4]


def aerodrome_v2_supported(chain_id):
    """True if Aerodrome v2 is deployed on this chain (Base only today)."""
    return int(chain_id) in AERODROME_V2_ROUTER


def _get_amounts_out(w3, router, amount_in, route):
    """Call Router.getAmountsOut for a single-hop route; return output or 0.

    Exact: getAmountsOut runs the same invariant as the swap, so this equals the
    delivered output at the same block. Any revert (no such pool) -> 0.
    """
    data = _SEL_GET_AMOUNTS_OUT + abi_encode(
        ["uint256", _ROUTE_T + "[]"], [amount_in, [route]]
    )
    try:
        ret = w3.eth.call(
            {"to": w3.to_checksum_address(router), "data": "0x" + data.hex()}
        )
        amounts = abi_decode(["uint256[]"], ret)[0]
    except Exception:
        return 0
    return int(amounts[-1]) if amounts else 0


def best_v2_quote(w3, chain_id, token_in, token_out, amount_in):
    """Best direct Aerodrome v2 fill across the stable and volatile pools.

    Returns ``(amount_out, route_tuple)`` where route_tuple is the Route the
    swap will use, or ``(0, None)`` if neither pool exists / quotes positive.
    """
    chain_id = int(chain_id)
    if not aerodrome_v2_supported(chain_id) or amount_in <= 0:
        return 0, None
    router = AERODROME_V2_ROUTER[chain_id]
    factory = w3.to_checksum_address(AERODROME_V2_FACTORY[chain_id])
    ti = w3.to_checksum_address(token_in)
    to = w3.to_checksum_address(token_out)
    best_out, best_route = 0, None
    for stable in (False, True):  # try both pool types, keep the deeper fill
        route = (ti, to, stable, factory)
        out = _get_amounts_out(w3, router, amount_in, route)
        if out > best_out:
            best_out, best_route = out, route
    return best_out, best_route


def build_v2_plan(intent_id, chain_id, token_in, route, amount_in, min_out, recipient, nonce):
    """Build approve + swapExactTokensForTokens for the chosen v2 route.

    The proxy holds the input token (the app pulled it from the user), so we
    approve the router then swap; output goes to ``recipient`` (the app
    contract), which is where scoreIntent measures the gained output.
    """
    chain_id = int(chain_id)
    router = AERODROME_V2_ROUTER[chain_id]
    approve_cd = "0x" + (
        _SEL_APPROVE + abi_encode(["address", "uint256"], [router, amount_in])
    ).hex()
    swap_cd = "0x" + (
        _SEL_SWAP
        + abi_encode(
            ["uint256", "uint256", _ROUTE_T + "[]", "address", "uint256"],
            [amount_in, min_out, [route], recipient, _FAR_FUTURE],
        )
    ).hex()
    return ExecutionPlan(
        intent_id=intent_id,
        interactions=[
            Interaction(target=token_in, value="0", call_data=approve_cd, chain_id=chain_id),
            Interaction(target=router, value="0", call_data=swap_cd, chain_id=chain_id),
        ],
        deadline=_FAR_FUTURE,
        nonce=nonce,
        metadata={
            "solver": "aerodrome_v2",
            "route": "aerodrome_v2_stable" if route[2] else "aerodrome_v2_volatile",
            "stable": route[2],
            "token_in": token_in,
            "token_out": route[1],
            "amount_in": str(amount_in),
        },
    )
