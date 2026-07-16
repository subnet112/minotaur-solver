FROM ghcr.io/subnet112/solver-base:v1

# Screening builds this with `--no-cache --network=none` (validator side).
# Consequences that shape this file:
#  * --network=none: a `pip install` RUN can NEVER reach PyPI here, so a deps
#    fallback is an illusion — the base image (solver-base:v1) already ships web3
#    and every dep the SDK needs. If the base ever drops a dep, Stage 2's import
#    check fails with a clear `import_failed`, which is the honest signal anyway.
#  * --no-cache: splitting requirements.txt into its own COPY layer buys zero
#    cache reuse, so we collapse to a single context copy.
# .dockerignore keeps the copied context lean (no __pycache__/tests/draft/dead
# artifacts), which is the only build-time lever the miner controls.
COPY . /app/solver/
WORKDIR /app/solver
