FROM ghcr.io/subnet112/solver-base:v1

COPY requirements.txt /app/solver/requirements.txt
# solver-base already ships web3 (the SDK needs it); skip the pip/PyPI
# roundtrip when satisfied -- the screening box is CPU/network-starved and
# build_timeout (120s) rejections are killing whole rounds of candidates.
# Falls back to a real install if the base image ever drops the dep.
RUN python -c "import web3" 2>/dev/null || pip install --no-cache-dir -r /app/solver/requirements.txt

COPY . /app/solver/
# SDK v2 migration (#1233): the base image ships SDK 1.0.0 and `v1` is the only published
# tag, so the 1.1.0 marker has to be vendored. Overlay onto the COMPLETE base package --
# never a partial minotaur_subnet/ in the tree root, which would shadow the real package
# (container sys.path puts cwd=/app/solver first) and kill every other import.
COPY sdk_overlay/minotaur_subnet/ /app/minotaur_subnet/
WORKDIR /app/solver
