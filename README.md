# Lean Router — Minotaur Solver

An independent chain-1 DEX aggregator for subnet112. Routes swap intents across
Uniswap V3 (all fee tiers, single + 2-hop via WETH/USDC), Uniswap V2, and SushiSwap,
delivering to the intent recipient. Compact by design (small functions, low max-region)
so it stays lean while covering the champion's blind spots.

## Structure
- `solver.py` — the solver (`SOLVER_CLASS`), SDK `IntentSolver` subclass.
- `Dockerfile` — build from `solver-base`.
- `requirements.txt` — web3.

## License
MIT.
