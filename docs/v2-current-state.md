# mgit v2 Current-State Notes

This is a compact inventory of the existing codebase after the first v2 command
slice and the April 29, 2026 cleanup commits. `docs/rewrite.md` remains the
historical starting point and should not be edited as the live plan changes.

## Files Examined

- Runtime code: `src/mgit/__init__.py`, `src/mgit/cli.py`,
  `src/mgit/commands.py`, `src/mgit/git.py`, `src/mgit/output.py`.
- Tests: `tests/conftest.py`, `tests/test_cli.py`, `tests/test_git.py`,
  `tests/test_mgit.py`, `tests/test_reporting.py`.
- Packaging and tooling: `pyproject.toml`, `tox.ini`, `MANIFEST.in`,
  `.github/workflows/tests.yml`, `.github/workflows/release.yml`.
- Docs: `README.rst`, `docs/contributing.rst`, `docs/v2-command-plan.md`,
  `docs/v2-roadmap.md`, `docs/rewrite.md`.

## Current CLI

The active CLI is now argparse based:

```shell
mgit [GLOBAL_OPTIONS] [COMMAND] [TARGET]
```

Default behavior is status. A single unknown token is treated as a status
target, so `mgit path` means `mgit status path`. Extra positional tokens are
invalid usage.

Global options are intentionally small:

- `-v, --verbose`: enable debug logging. It does not change output shape.
- `--color auto|always|never`: control ANSI color.
- `--version`
- `--help`

Implemented commands:

- `status` / `s`: show repo or workspace status. This is the default.
- `fetch` / `f`: run `git fetch --all --prune`, then status.
- `pull` / `p`: pull with rebase when the checkout passes safety checks.
- `main` / `m`: checkout the detected default branch.
- `branches` / `b`: list local branches with annotations.
- `groom` / `g`: single-repo local cleanup workflow.

The legacy v1 action flags (`-f`, `-p`, `--clean`, `-cs`, `-cl`, `-cr`,
`-ca`) are no longer part of the v2 command shape. `--short` and `--long` are
still deferred.

## Current Runtime Model

`src/mgit/cli.py` owns the argparse entry point:

- `CliInvocation` captures the selected command, target, verbosity, and color
  policy.
- `parse_cli_args()` maps command tokens and aliases onto the command registry.
- `target_preferences()` bridges command intent into the existing target model
  for `status`, `fetch`, and `pull`.
- Command handlers currently live here for branch reports, `main`, and
  single-repo `groom`.

`src/mgit/commands.py` is the explicit command registry:

- `CommandSpec` is a frozen dataclass with canonical name, aliases, help
  summary, scope, mutation flags, and handler id.
- The registry currently includes status, fetch, pull, main, branches, and
  groom.

`src/mgit/__init__.py` still combines target discovery, workspace modeling,
preferences, and some status rendering:

- `git_parent_path()` climbs from the current directory to find a parent git
  checkout.
- `find_actual_path()` resolves the target path, defaulting to the containing
  git checkout when run inside one.
- `get_target()` returns either `GitCheckout` or `ProjectDir`.
- `MgitPreferences` has been simplified to active fields only: name alignment,
  fetch/fetch age, pull, and optional remote inspection.
- `GitCheckout` wraps one local path and prints status.
- `ProjectDir` scans direct child directories only, collects git checkouts,
  detects predominant remote project grouping, and prints multi-repo status.
- `RemoteProject` classes currently identify GitHub, Stash, or unknown remotes,
  but server-side project listing is not implemented.

`src/mgit/output.py` holds color/style helpers. The rendering split is only
partial: color policy has moved out, but status and workspace line composition
still live in `cli.py` and `__init__.py`.

`src/mgit/git.py` holds most git-specific behavior:

- `GitRunReport` composes problems, progress, and notes with stable ordering.
- `GitURL` parses file, HTTPS, SSH, GitHub-style SSH, and unknown URLs. Name
  and repo fallbacks are sanitized to `"unknown"` rather than leaking `None`.
- `GitDir` is the main git runner and state facade.
- `GitDir.default_branch` is now a cached property, resolving `origin/HEAD`
  first and falling back to `main` or `master`.
- `GitAspect` is a base class for parsed git-command output.
- `GitBranches`, `GitConfig`, and `GitStatus` parse branch, config, and status
  output.
- Cleanable local and remote branches are proven with
  `git merge-base --is-ancestor` against the relevant default branch ref, or by
  using `git merge-tree --write-tree` to prove that merging the branch into the
  default branch would leave the default branch tree unchanged. This catches
  squash/content-equivalent merges without trusting branch names or current
  checkout state. Local squash-cleanable branches use force deletion only after
  that no-op merge proof.

## Settled Pieces

- The v2 command registry and argparse parser are in place for the first
  command slice.
- URL parsing coverage and behavior from `GitURL`.
- `GitRunReport` semantics, especially deduping, ordering, truncation, and
  problem/progress/note separation.
- `GitStatus` parsing of `git status --porcelain --branch`.
- `GitBranches` parsing of current/local/remote/default branches.
- The guarded `pull()` behavior that refuses when there are pending changes or
  status problems.
- Direct-child workspace scanning for multi-repo folders.
- The default target behavior: when no target is supplied, use the current git
  checkout if the current directory is inside one.
- `main` is treated as a user-facing command for "default branch", not a
  literal branch name.
- `groom` is local-only and currently single-repo only. When run from a
  non-default branch, it refuses to switch branches unless the current branch is
  also cleanable.

## Remaining Work

- `src/mgit/__init__.py` mixes public package imports, repo discovery, models,
  preferences, and status rendering.
- `GitDir` mixes command execution, cached state, mutations, and reporting.
- `clone` is planned but not implemented, and the config guide does not exist
  yet.
- `remote_cleanable_branches` only considers SSH remotes.
- The CLI no longer uses Click, but `click<9` is still listed as a runtime
  dependency.
- `runez` remains central for cached properties, paths, durations, aborts,
  colors, and test helpers.
- Packaging says `license-files = ["LICENSE.txt"]`, while the repository file
  is `LICENSE`; this should be revisited during packaging cleanup.
- Workspace support for `groom` remains maybe-later work.

## Current Test Coverage

Existing tests cover:

- Branch-name validation.
- Git URL parsing.
- Report composition, sorting, filtering, and truncation.
- Argparse command parsing, aliases, default command behavior, and invalid
  positional usage.
- Workspace status alignment and the fact that `-v/--verbose` controls logging,
  not output shape.
- Single-checkout pending path output.
- Branch reports for single repos and workspaces.
- `main` checkout behavior.
- Single-repo `groom` deleting a stale tracked branch and refusing pending
  changes.
- Basic CLI help/version/error/status behavior.

Coverage is light around:

- Branch/status parsing from realistic git output fixtures.
- Workspace fetch/pull failures and result aggregation.
- Clone config matching.
- Color policy.
- Exit-code matrix.
- Packaging and dependency cleanup.
