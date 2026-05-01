# mgit v2 Current-State Notes

This is a compact inventory of the existing codebase after the first v2 command
slice and the April 29, 2026 cleanup commits. `docs/rewrite.md` remains the
historical starting point and should not be edited as the live plan changes.

## Files Examined

- Runtime code: `src/mgit/__init__.py`, `src/mgit/cli.py`,
  `src/mgit/git.py`, `src/mgit/output.py`.
- Tests: `tests/conftest.py`, `tests/test_cli.py`,
  `tests/test_reporting.py`.
- Packaging and tooling: `pyproject.toml`, `tox.ini`, `MANIFEST.in`,
  `.github/workflows/tests.yml`, `.github/workflows/release.yml`.
- Docs: `README.rst`, `docs/contributing.rst`, `docs/v2-command-plan.md`,
  `docs/v2-roadmap.md`, `docs/rewrite.md`.

## Current CLI

The active CLI is now argparse based:

```shell
mgit [GLOBAL_OPTIONS] [COMMAND] [FOLDER]
```

Default behavior is status. A single unknown token is treated as a status
folder, so `mgit folder` means `mgit status folder`. Extra positional tokens are
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

`src/mgit/cli.py` owns the argparse entry point and command classes:

- `GlobalFlags` captures top-level verbosity and color policy separately from
  command-specific arguments.
- `CliInvocation` captures the selected parsed command object and global flags.
- `CliCommand` and `FolderCommand` model commands directly. `FolderCommand`
  supplies the common optional `folder` argument used by status/fetch/pull/main,
  branches, and groom.
- `FolderCommand.get_project_dir()` returns a `ProjectDir` for commands that
  work across one checkout or a workspace.
- `FolderCommand.get_git_checkout()` is used by single-checkout commands and
  returns a typed `GitCheckout`.
- `StatusCommand`, `FetchCommand`, and `PullCommand` spell out their run
  behavior directly rather than routing through shared fetch/pull flags.
- `parse_cli_args()` parses leading global flags, resolves the command token or
  short name, defaults to status when no command matches, and then delegates the
  remaining arguments to the selected command parser.
- `mgit --help` shows the command list, while command help such as
  `mgit s --help` is handled by the resolved command parser.
- The registry currently includes status, fetch, pull, main, branches, and
  groom.

`src/mgit/__init__.py` still combines target discovery, workspace modeling, and
some status rendering:

- `find_actual_path()` resolves the requested folder and is the folder
  normalization boundary. Current-folder requests climb to a parent git
  checkout, then fall back to the current directory.
- `GitCheckout` wraps one local path and renders its status header.
- `ProjectDir` represents the requested folder as zero or more git checkouts.
  It handles a requested single checkout and direct-child workspace scans with
  the same model.
- The old `MgitPreferences` object and Stash/GitHub/unknown remote grouping
  were removed. URL parsing can be modeled later where clone/config behavior
  actually needs it.

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
- `GitRunReport` semantics, especially deduping, ordering, truncation, and
  problem/progress/note separation.
- `GitStatus` parsing of `git status --porcelain --branch`.
- `GitBranches` parsing of current/local/remote/default branches.
- The guarded `pull()` behavior that refuses when there are pending changes or
  status problems.
- Direct-child workspace scanning for multi-repo folders.
- The default folder behavior: when no folder is supplied, use the current git
  checkout if the current directory is inside one.
- `main` is treated as a user-facing command for "default branch", not a
  literal branch name.
- `groom` is local-only and currently single-repo only. When run from a
  non-default branch, it refuses to switch branches unless the current branch is
  also cleanable.

## Remaining Work

- `src/mgit/__init__.py` mixes public package imports, repo discovery, models,
  and status rendering.
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

- Report composition, sorting, filtering, and truncation.
- CLI help, command dispatch, and default command behavior.
- Workspace status alignment and the fact that `-v/--verbose` controls logging,
  not output shape.
- Single-checkout pending path output.
- Branch reports for single repos and workspaces.
- `main` checkout behavior.
- Single-repo `groom` deleting a stale tracked branch and refusing pending
  changes.

Coverage is light around:

- Branch/status parsing from realistic git output fixtures.
- Workspace fetch/pull failures and result aggregation.
- Clone config matching.
- Color policy.
- Exit-code matrix.
- Packaging and dependency cleanup.
