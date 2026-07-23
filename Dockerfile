FROM ghcr.io/subnet112/solver-base:v1
ENV MINOTAUR_SOLVER_NAME=mam26

COPY requirements.txt /app/solver/requirements.txt
# solver-base already ships web3 (the SDK needs it); skip the pip/PyPI
# roundtrip when satisfied -- the screening box is CPU/network-starved and
# build_timeout (120s) rejections are killing whole rounds of candidates.
# Falls back to a real install if the base image ever drops the dep.
RUN python -c "import web3" 2>/dev/null || pip install --no-cache-dir -r /app/solver/requirements.txt

COPY . /app/solver/
WORKDIR /app/solver
