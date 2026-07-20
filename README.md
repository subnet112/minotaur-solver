# Polar-Bear-Router

A Subnet 112 (Minotaur) intent solver.

`solver.py` exports `SOLVER_CLASS = PolarBearRouter`. It runs the certified
champion solver stack first, and adds a **fill-only-empty** cover layer: when the
underlying stack returns no plan for an order, Polar-Bear-Router attempts a lean,
chain-correct best-of-fee-tiers Uniswap V3 fill (Ethereum SwapRouter V1 / Base
SwapRouter02, QuoterV2 per chain). Because the cover only fires on an otherwise
empty result, it can lift an unserved order to a delivery but never regresses or
drops a served one.

Base image: `ghcr.io/subnet112/solver-base:v1` (no CMD/ENTRYPOINT — the harness owns the runner).
