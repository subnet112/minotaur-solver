FROM ghcr.io/subnet112/solver-base:v1

COPY requirements.txt /app/solver/requirements.txt
# solver-base already ships web3 (the SDK needs it); skip the pip/PyPI
# roundtrip when satisfied -- the screening box is CPU/network-starved and
# build_timeout (120s) rejections are killing whole rounds of candidates.
# Falls back to a real install if the base image ever drops the dep.
RUN python -c "import web3" 2>/dev/null || pip install --no-cache-dir -r /app/solver/requirements.txt

COPY . /app/solver/
WORKDIR /app/solver

# ── minoPot lean cover overlay: identity + fill-only-empty blind-spot covers ──
# Version is set at RUNTIME to v1.{id}.{month}.{day} in the solver's metadata().
# No flow/split engine is shipped (it regressed and tripped the deadwood floor).
ENV MINOTAUR_SOLVER_NAME=minoPot_solver
ENV ENABLE_3HOP_COVER=1
ENV ENABLE_PSM_COVER=1
ENV ENABLE_STATIC_COVER=1
