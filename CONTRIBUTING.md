# Contributing

Thanks for your interest in the Minotaur reference solver. This guide covers the basics — how to file an issue, how to run the tests locally, and what to expect from the review process.

## Reporting issues

- **Bugs**: open a GitHub issue with a minimal reproduction (commands run, expected vs. actual). Include version info — git commit hash, Python/Node/Foundry versions, OS.
- **Security vulnerabilities**: do **not** open a public issue. See [SECURITY.md](./SECURITY.md) for the responsible-disclosure path.
- **Feature requests / design discussion**: open an issue describing the use case and the constraint that motivates it. We're more likely to accept feature work that's grounded in a concrete user need than a pure idea.

## Pull requests

> **Submitting as a subnet-112 miner?** Two extra requirements apply on top of the steps below:
>
> - **Link your GitHub account to your hotkey first.** A submission's PR fork owner must be linked to your Bittensor hotkey, so nobody can submit your PR — or a copy of it — under their own key. Sign `MinotaurGithubLink:<github_login>:<hotkey>` with your hotkey, put `{"hotkey": "...", "signature": "..."}` in a **public gist on the account you submit from**, and `POST /v1/miner/link-github` with its id. A submission whose fork owner isn't linked to the submitting hotkey is rejected.
> - **Base your PR on the _current_ `main`.** Each champion is squash-merged to `main`, so `main` always holds the current champion's `solver.py`. A PR forked from an older `main` will conflict and **cannot be adopted even if it wins the benchmark**. After any champion change, **rebase onto the latest `main` and resubmit** — the validator auto-closes now-stale submission PRs with a rebase reminder.

1. Fork the repo and create a topic branch off `main`.
2. Keep PRs focused — one logical change per PR. Drive-by formatting fixes belong in their own PR.
3. Run the test suite locally before pushing:
   
   ```bash
   # The solver image is built and exercised by the validator pipeline.
   # Locally, build the image and verify it imports cleanly:
   docker build -t minotaur-solver-test .
   docker run --rm --entrypoint python3 minotaur-solver-test \
       -c "from solver import SOLVER_CLASS; print(SOLVER_CLASS().metadata())"
   ```
4. Open the PR with a description that covers: what the change does, why it's needed, what was tested.
5. CI runs on every PR; failing checks block merge.

## Code style

- Match the surrounding code's style — formatting, naming conventions, comment density.
- New public APIs should have docstrings explaining the contract, not just the implementation.
- Don't add comments that narrate what the code is doing; reserve comments for *why* a decision was made when it's non-obvious.

## Sign-off

By submitting a PR you agree to license your contribution under the project's [LICENSE](./LICENSE) (MIT).

## Getting in touch

For day-to-day questions that don't fit a GitHub issue, the project lives in the broader [Subnet 112 (Minotaur)](https://github.com/subnet112/minotaur_subnet) ecosystem — see that repo's README for community channels.
