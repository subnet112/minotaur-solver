# Minimal image for the standalone lean solver.
#
# Deliberately NOT the champion's Dockerfile: theirs COPYs requirements.txt and
# an sdk_overlay/ tree we do not ship. The base image already provides the SDK
# (minotaur_subnet 1.0.0 at /app/minotaur_subnet) and web3 7.16.0 — verified by
# importing IntentSolver/SolverMetadata/ExecutionPlan/Interaction inside it — and
# solver.py imports nothing else.
FROM ghcr.io/subnet112/solver-base:v1
COPY . /app/solver/
WORKDIR /app/solver
