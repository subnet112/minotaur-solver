"""uid220 champion-delta — current champion + wider multi-hop intermediaries.

Preserves the current champion composition verbatim — Part 1
(`_champion_entry.SOLVER_CLASS`, refreshed each round) plus Part 2
(`minopot_flow.FlowEnhanceMixin`, the fixed water-fill split) — and layers ONE
regression-safe change: `_intermediaries_for_chain` adds USDT/DAI/WBTC
(Ethereum) and USDbC/DAI (Base) beyond the champion's WETH+USDC set, sourced
from the trusted SDK token registry (chain-correct addresses).

Regression-safe: the router keeps the max-output route, so extra intermediary
candidates can only match or beat the champion's existing best — never worse.
If the champion's discovery ignores this hook, the override is a harmless no-op.
"""
from __future__ import annotations

from _champion_entry import SOLVER_CLASS as _ChampionBase
from minopot_flow import FlowEnhanceMixin

# Extra intermediary symbols to add per chain, resolved from the trusted registry.
_EXTRA_INTERMEDIARY_SYMBOLS = ("USDT", "DAI", "WBTC", "USDbC")


class MinerSolver(FlowEnhanceMixin, _ChampionBase):
    """Current champion (flow-split) + wider multi-hop intermediaries."""

    def _intermediaries_for_chain(self, chain_id):
        mids = list(super()._intermediaries_for_chain(chain_id))
        from minotaur_subnet.blockchain.tokens import TOKENS

        token_chain = 1 if chain_id == 31337 else chain_id
        toks = TOKENS.get(token_chain, {})
        have = {m.lower() for m in mids}
        for sym in _EXTRA_INTERMEDIARY_SYMBOLS:
            addr = toks.get(sym)
            if addr and addr.lower() not in have:
                mids.append(addr)
                have.add(addr.lower())
        return mids


SOLVER_CLASS = MinerSolver
