# mgit — repo context

mgit is a small Python CLI showing the state of one git checkout, or of every checkout in a
workspace folder, and cleaning up merged branches.

## Docs — read before diving into the code

- **[`docs/`](./docs/index.md)** — how the repo works inside. Users read [`README.rst`](./README.rst).

## Working notes

- The repo is intentionally small: keep changes scoped, and no new runtime dependency (`runez` is
  the only one) without asking.
- Run tests with `.venv/bin/pytest`, or through tox (`tox.ini` is the hub, CI just calls its
  environments). Prefer exercising the CLI in tests over unit-testing internals.
- `fetch`, `pull` and `groom` change the checkout they run in (`groom` deletes branches, local and
  remote): don't point them at real checkouts while experimenting, the tests use temp repos.
