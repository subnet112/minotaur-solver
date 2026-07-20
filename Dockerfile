FROM ghcr.io/subnet112/solver-base:v1

COPY requirements.txt /app/solver/requirements.txt
# solver-base already ships web3 (the SDK needs it); skip the pip/PyPI
# roundtrip when satisfied -- the screening box is CPU/network-starved and
# build_timeout (120s) rejections are killing whole rounds of candidates.
# Falls back to a real install if the base image ever drops the dep.
RUN python -c "import web3" 2>/dev/null || pip install --no-cache-dir -r /app/solver/requirements.txt

COPY . /app/solver/
WORKDIR /app/solver

# ── minoPot fixed overlay (Part 2): identity + N-way water-fill flow enhancer ──
# Version is set at RUNTIME to v1.0.{month}.{day} in the solver's metadata().
ENV MINOTAUR_SOLVER_NAME=minoPot_solver
ENV ENABLE_FLOW_ROUTER=1
ENV FLOW_IMPROVE_BPS=20
ENV ENABLE_3HOP_COVER=1
