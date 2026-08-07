# Minotaur Solver

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Subnet 112](https://img.shields.io/badge/bittensor-subnet112-purple)](https://github.com/subnet112/minotaur_subnet)

Reference miner solver for [Subnet 112 (Minotaur)](https://github.com/subnet112/minotaur_subnet) — the Bittensor subnet for distributed intent execution.

Miners fork this repo, modify the `MinerSolver` class in `solver.py` to ship a smarter routing strategy, and submit the pinned commit hash through Minotaur's git-based submission pipeline. The validator's screening pipeline clones the repo, builds the Docker image, benchmarks the solver, and considers it for champion adoption if it beats the current incumbent.

## What's in here

| Path | Purpose |
|---|---|
| `solver.py` | Top-level entry. Exports `SOLVER_CLASS`, which the runner harness imports and instantiates. Default extends `BaselineSwapSolver` with no override — all routing comes from upstream. |
| `common/abi_utils.py` | Generic ERC-20 calldata encoder (`encode_approve`). |
| `common/parsing.py` | App-agnostic input normalisation (JSON list/map). |
| `strategies/dex_aggregator/baseline_solver.py` | The reference DEX-aggregator solver. RPC-first pool discovery, V3 math, multi-hop routing through configured intermediaries. Aware of Uniswap V3 and Aerodrome Slipstream pools on Base. |
| `strategies/dex_aggregator/aerodrome.py` | Aerodrome Slipstream integration: factory pool discovery + Slipstream `SwapRouter` calldata encoding. |
| `strategies/dex_aggregator/pool_math.py` | Uniswap V3 single-tick math + best-pool / best-route selection. |
| `strategies/dex_aggregator/swap_solver.py` | `SwapIntentProcessor` — single-hop Uni V3 plan generation. |
| `strategies/dex_aggregator/v3_codec.py` | Uniswap V3 SwapRouter calldata encoders (V1/V2 auto-select, multi-hop path). |
| `strategies/dex_aggregator/uniswap_v3.py`, `strategies/dex_aggregator/token_math.py` | Per-strategy helpers. |
| `strategies/<other_app>/` | Add your own per-app strategy modules here. |
| `draft/strategies/yield_optimizer/yield_solver.py` | Reference yield-strategy solver — staged here until the YieldOptimizer app is promoted out of draft. |
| `Dockerfile` | Submission image definition. Must `FROM ghcr.io/subnet112/solver-base:v1` and must not declare `CMD` or `ENTRYPOINT` (the base image owns the runner). |
| `requirements.txt` | Optional extra Python dependencies. The base image already ships everything `BaselineSwapSolver` needs. |

## How miners should work here

1. **Fork** this repo.
2. **Edit `MinerSolver`** in `solver.py` — override `generate_plan` to run your strategy. The default just delegates to `BaselineSwapSolver`, which is what you're trying to beat.
3. **(Optional) Add per-app strategies** under `strategies/<app_id>/strategy.py` if your routing differs per Minotaur App.
4. **Test locally** against the local-testnet bundled in [`subnet112/minotaur_subnet`](https://github.com/subnet112/minotaur_subnet) before submitting.
5. **Push a commit** and submit the commit hash through the miner submission API. The validator builds the image, runs the 3-stage screening pipeline (no-network, sandbox-network, full-RPC), benchmarks it, and — if it beats the current champion — proposes it for adoption via off-chain consensus.

## Strategy ideas worth trying

- **Multi-DEX route splitting** — split a single trade across Uni V3 + Aerodrome pools to reduce price impact on large orders.
- **Aerodrome Slipstream-aware multi-hop** — the upstream baseline only does Uni V3 packed-path multi-hop. Add `exactInput` packed-path support for Slipstream too.
- **More DEXes** — Curve, Balancer V2, Maverick. Each is a new pool discovery + plan emitter.
- **Smarter intermediaries** — `_DEFAULT_INTERMEDIARIES` in `strategies/dex_aggregator/pool_math.py` only tries WETH/USDC. Add cbBTC, USDbC, AERO for more route diversity on Base.
- **Snapshot warming** — pre-compute pool states off-path so quote latency drops below RPC roundtrip.
- **Learning from past orders** — `on_score_received` lets you track which strategies won/lost and adapt parameters per app.

## Submission requirements

The screening pipeline expects:
- `Dockerfile` at repo root
- `solver.py` at repo root, exporting `SOLVER_CLASS`
- `README.md`

The Dockerfile must use `FROM ghcr.io/subnet112/solver-base:v1` (or a pinned digest of the same image). Other base images are rejected by the validator — the harness lives in the base image and cannot be substituted.

## License

MIT — see [LICENSE](./LICENSE).
