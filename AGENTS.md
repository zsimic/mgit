# AGENTS.md

Guidance for future Codex sessions working in this repository.

## Project Shape

`mgit` is a small Python CLI for inspecting and operating on one git checkout
or a workspace containing many git checkouts. The current v1 CLI is flag based
and Click powered. The planned v2 CLI should move to argparse subcommands,
short aliases, fewer runtime dependencies, and clearer separation between
command dispatch, git state modeling, repo discovery, and output rendering.

Important files:

- `src/mgit/cli.py`: current Click entry point, option parsing, and clean flows.
- `src/mgit/__init__.py`: target resolution, repo/workspace models, display
  preferences, project grouping, and status printing.
- `src/mgit/git.py`: git command runner, URL parsing, branch/status/config
  parsers, reports, fetch/pull/clone helpers, and cleanable-branch detection.
- `tests/`: current pytest coverage for URL parsing, report formatting, edge
  cases, and basic CLI usage.
- `docs/rewrite.md`: user-authored historical v2 draft. Do not edit it.
- `docs/v2-*.md`: planning notes for the v2 rewrite. Keep these current as
  implementation decisions settle.

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

The repo already uses `ruff`, `pyright`, `tox`, and `setuptools-scm`.

## Working Rules

- Prefer `rg` and `rg --files` for navigation.
- Preserve user changes. Do not edit `docs/rewrite.md`; it is the historical
  starting point for the rewrite.
- Use `apply_patch` for manual edits.
- Keep changes scoped. This repo is intentionally small.
- Do not add new runtime dependencies without documenting the reason in
  `docs/v2-command-plan.md`.
- Keep CLI behavior covered by tests before changing parser behavior.

## Safety Notes

Plain status inspection is safe. Some current v1 code paths are mutating:

- `--fetch` runs `git fetch --all --prune`.
- `--pull` runs `git pull --rebase`, guarded by pending-change checks.
- `--clean local` deletes local branches.
- `--clean remote` and `--clean all` can run `git push --delete`.
- `--clean reset` runs `git reset --hard`, `git clean -fdx`, checkout, and pull.

Do not run destructive clean/reset paths casually while planning or testing.
For v2, `groom`/`g` is priority first-iteration work even though it deletes
local branches. It must stay local-only, guarded, and clearly described. Remote
branch deletion and reset-style commands are maybe-later work.

## v2 Direction

The v2 plan is not final. Current preferred direction:

- Default `mgit` remains status.
- Keep `fetch`/`f` and `pull`/`p` as separate commands. The normal update loop
  is intentionally inspect-then-act: fetch to see remote changes, then pull.
- First-letter aliases are supported where unambiguous, for example
  `mgit s`, `mgit f`, `mgit p`, `mgit m`, `mgit g`, and `mgit c`.
- Commands declare whether they support one repo, many repos, or both.
- A workspace scan is depth 1 only: inspect `<workspace>/*/.git`, not nested
  descendants.
- `main` means checkout the default branch, even when the actual branch is
  named `master` or something else.
- `groom`/`g` is the priority workflow command: fetch, return to the default
  branch, pull safely, and clean local stale branches.
- Only `clone` uses `~/.config/mgit/config.toml`; status/fetch/pull/main/groom
  do not require config.
- `clone` requires config and should fail with setup guidance if
  `~/.config/mgit/config.toml` is missing.
- `clone` expects a full HTTPS URL in the first implementation. Do not infer
  GitHub from `owner/repo` shorthand yet.
- First-iteration global options are intentionally small: `-v/--verbose`,
  `--color`, `--version`, and `--help`. `-v/--verbose` is for logging
  verbosity; it must not control short or long status output.
- Prefer stdlib color/output first. Reconsider `rich` only if it clearly
  simplifies tables, wrapping, or cross-platform color enough to justify the
  dependency.

Update the v2 docs before or alongside implementation when decisions change.
