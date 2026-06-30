# Minotaur Subnet 112 solver image.
# The validator builds this with `--network=none` and runs the solver in a
# read-only, no-network sandbox. Do NOT add a CMD or ENTRYPOINT — the harness
# manages the entry point. Including either one fails screening (Stage 1).
FROM ghcr.io/subnet112/solver-base:v1

# Extra deps (web3/eth-abi/eth-utils already ship in the base image; this is
# here so the build still works if you add more later).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app
WORKDIR /app
