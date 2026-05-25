# AGENTS.md

Guidance for future Codex sessions working in this repository.

## Project Shape

`mgit` is a small Python CLI for inspecting and operating on one git checkout
or a workspace containing many git checkouts. The CLI uses argparse subcommands,
short aliases, separation between command dispatch, git state modeling, repo discovery,
and output rendering.

Important files:

- `src/mgit/cli.py`: current Click entry point, option parsing, and clean flows.
- `src/mgit/git.py`: git command runner, URL parsing, branch/status/config
  parsers, reports, fetch/pull/clone helpers, and cleanable-branch detection.
- `tests/`: current pytest coverage, prefer exercising CLI in general rather than unit tests.

## Development Commands

Use these from the repo root:

- `.venv/bin/pytest -q` for fast iteration.
- `.venv/bin/pytest -vv` when you want the full test names.
- `.venv/bin/pytest -vv --cov=src tests` for local coverage checks.
- `ruff check` and `ruff format --diff` directly; `ruff` is on `PATH`.
- `tox -e style` for the packaged style environment.
- `tox -e py39` for the minimum supported Python version.
- `tox -e py314` for the newest supported Python version.
- `tox` as the final confidence run; it exercises multiple Python versions,
  coverage, and linters.

`uv run pytest ...` also works when the synced environment is desired, but the
local `.venv/bin/pytest` path is usually faster while iterating.

The repo uses `ruff`, `pyright`, `tox`, and `setuptools-scm`.

## Working Rules

- Prefer `rg` and `rg --files` for navigation.
- Preserve user changes.
- Use `apply_patch` for manual edits.
- Keep changes scoped. This repo is intentionally small.
- Do not add new runtime dependencies without consulting with user.

## Safety Notes

Plain status inspection is safe. Some current v1 code paths are mutating:

- `fetch` runs `git fetch --all --prune`.
- `pull` runs `git pull --rebase`, guarded by pending-change checks.
- `groom` can delete one local and/or remote branch.

Do not run destructive clean/reset paths casually while planning or testing.
