# mgit v2 Current-State Notes

This is a compact inventory of the existing codebase after the first v2 command
slice and the April 29, 2026 cleanup commits. `docs/rewrite.md` remains the
historical starting point and should not be edited as the live plan changes.

## Files Examined

- Runtime code: `src/mgit/__init__.py`, `src/mgit/cli.py`, `src/mgit/git.py`.
- Tests: `tests/conftest.py`, `tests/test_cli.py`, `tests/test_groom.py`,
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

- `CliCommand` models shared command behavior, while `FolderTargetCommand`
  supplies the common optional `folder` argument, resolves the target, and
  dispatches to `run_single(GitDir)` or `run_multi(ProjectDir)`.
- When no folder is supplied, target resolution climbs to a parent git checkout,
  then falls back to the current directory as a workspace. When a folder is
  supplied explicitly, even `.`, that folder is used as-is.
- `StatusCommand`, `FetchCommand`, and `PullCommand` spell out their run
  behavior directly rather than routing through shared fetch/pull flags.
- Command handlers do not aggregate numeric exit codes: a single-checkout
  operation aborts immediately when its report fails, while workspace fetch and
  pull display per-checkout failures and continue successfully.
- `normalized_cli_args()` normalizes argv before parsing: it inserts `status` when
  the first non-global token is not a command, expands short names such as `f`
  to `fetch`, and then lets the top-level argparse parser dispatch through real
  subparsers.
- `mgit --help` shows argparse's command list with aliases, while command help
  such as `mgit s --help` is normalized to the full command name before parsing.
- The registry currently includes status, fetch, pull, main, branches, and
  groom.

`src/mgit/__init__.py` now holds only the lightweight workspace container:

- `ProjectDir` represents a valid requested workspace as one or more depth-1
  `GitDir` children; scanning aborts immediately if none are present.
- It provides the workspace header and aligned line prefixes for
  multi-checkout output.
- The old `MgitPreferences` object and Stash/GitHub/unknown remote grouping
  were removed. URL parsing can be modeled later where clone/config behavior
  actually needs it.

`Reporter` in `src/mgit/git.py` currently holds color/style helpers. Git-derived
status and branch rendering now lives on `GitDir` via `status_line()`,
`status_details()`, and `branch_details()`. The detail methods return complete
multi-line display blocks, leaving commands to decide when to print them.
Branch names are always bold in status, branch displays, and successful action
output, with default branches green and orphaned branches orange. Status
markers such as `✅`, `☑️`, and `🪦` are not passed through text color styles.

`src/mgit/git.py` holds most git-specific behavior:

- `GitRunReport` composes problems, progress, and notes with stable ordering.
- `GitDir` is the main git runner and state facade.
- `CleanableLocalBranch` carries the result of a local branch cleanup proof,
  including whether deletion needs `git branch --delete --force`.
- `GitRefs` is the repository ref snapshot. It uses `git remote`,
  `git symbolic-ref`, and `git for-each-ref` to gather current/local branches,
  remote branches, `origin/HEAD` default-branch information, and exact local
  branch upstreams. The older `GitBranches`, `GitConfig`, and `GitURL` helpers
  were removed; clone URL parsing will be redesigned with `clone`.
- `GitDir.default_branch` resolves `origin/HEAD` first and falls back to
  `main` or `master`.
- `GitDir.age` is a simple per-command freshness snapshot captured when the
  `GitDir` is created. Successful fetch and pull operations update it directly.
- `fetch` commands use `GitDir.fetch_now()` directly; the earlier conditional
  fetch helper has been removed.
- `GitDir.status_line(report=None)` composes the compact one-line
  branch/freshness/status output used by single and workspace status-like
  commands, appending any rendered operation report problem or note. Ambient
  notes for stale fetch age, cleanable local branches, and detached `HEAD` use
  that same report path.
- Dirty status lines retain the freshness marker, since freshness and pending
  changes are separate signals; an orphan tombstone supersedes the marker.
  Additional local branches are represented separately as `[+N]`.
- `GitDir.status_details()` and `GitDir.branch_details()` compose the indented
  expanded displays used only where a command requests detail output.
- Successful `GitDir.pull()` reports use note messages such as `was 1 behind`
  or `was up-to-date`, so their status-line recap uses note styling.
- `GitStatus.upstream_delta()` supplies shared compact upstream-divergence text
  for live status lines and pre-pull recap notes.
- `GitStatus` parses `git status --porcelain=v2 --branch`, keeping worktree
  status and structured ahead/behind reporting separate from ref discovery.
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
- `GitRefs` loading of current/local/remote/default branches and exact branch
  upstreams.
- `GitStatus` parsing of `git status --porcelain=v2 --branch`.
- The guarded `pull()` behavior that checks remotes, all pending changes
  (including untracked paths), and status problems directly before pulling.
- Direct-child workspace scanning for multi-repo folders.
- The default folder behavior: when no folder is supplied, use the current git
  checkout if the current directory is inside one.
- Explicit folder arguments do not climb to parent checkouts.
- Commands dispatch through explicit `run_single(GitDir)` and
  `run_multi(ProjectDir)` methods.
- `main` is treated as a user-facing command for "default branch", not a
  literal branch name.
- `groom` is local-only and currently single-repo only. When run from a
  non-default branch, it refuses to switch branches unless the current branch is
  also cleanable. `groom` owns its step-by-step output directly and renders its
  final pull recap through `GitDir.status_line(pull_report)`.

## Remaining Work

- `src/mgit/__init__.py` mixes public package imports, repo discovery, models,
  and workspace alignment.
- `GitDir` mixes command execution, cached state, mutations, and reporting.
- `clone` is planned but not implemented, and the config guide does not exist
  yet.
- The CLI no longer uses Click, and Click is not a runtime dependency.
- `runez` remains central for cached properties, paths, durations, aborts,
  colors, and test helpers.
- Packaging says `license-files = ["LICENSE.txt"]`, while the repository file
  is `LICENSE`; this should be revisited during packaging cleanup.
- Workspace support for `groom` remains maybe-later work.

## Current Test Coverage

Existing tests cover:

- Report composition, sorting, filtering, and truncation.
- CLI help, command dispatch, and default command behavior.
- Broad status checks for workspaces, single checkouts, pending path output, and
  parent-checkout discovery from a subfolder.
- The fact that `-v/--verbose` controls logging, not output shape.
- Workspace branch reports.
- Workspace pull recap output.
- Single-checkout fetch/pull failure aborts and workspace fetch/pull
  continuation on per-checkout failure.
- `main` checkout behavior.
- Single-repo `groom` deleting a stale tracked branch, refusing pending changes,
  and refusing an uncleanable current branch.

Coverage is light around:

- Branch/status parsing from realistic git output fixtures.
- More varied workspace fetch/pull git transport failures and mixed-state
  reporting.
- Clone config matching.
- Color policy.
- Packaging and dependency cleanup.
