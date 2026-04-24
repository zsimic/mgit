# mgit v2 Current-State Notes

This is a compact inventory of the existing codebase as input to the v2 plan.
It reflects the repository as examined before the v2 rewrite starts.

## Files Examined

- Runtime code: `src/mgit/__init__.py`, `src/mgit/cli.py`,
  `src/mgit/git.py`.
- Tests: `tests/conftest.py`, `tests/test_git.py`, `tests/test_mgit.py`,
  `tests/test_reporting.py`.
- Packaging and tooling: `pyproject.toml`, `tox.ini`, `MANIFEST.in`,
  `.github/workflows/tests.yml`, `.github/workflows/release.yml`.
- Docs: `README.rst`, `docs/contributing.rst`, `docs/rewrite.md`.

## Current CLI

The v1 CLI has one command shape:

```shell
mgit [OPTIONS] [TARGET]
```

Default behavior is status. Options layer additional behavior:

- `-f, --fetch`: fetch all remotes before reporting.
- `-p, --pull`: pull from tracking remote before reporting, but only when the
  checkout is clean enough.
- `--clean show|local|remote|all|reset`: show or perform branch cleanup/reset.
- `-cs`, `-cl`, `-cr`, `-ca`: shortcuts for clean actions.
- `-s/-v`, `--short/--verbose`: output verbosity.
- `--debug`, `--color/--no-color`, `--log`, `--version`: inherited from
  `runez.click`.

For v2, `--debug` and `--short` are not planned first-iteration options.
Use `-v/--verbose` for extra detail and one compact default output style.

## Current Runtime Model

`src/mgit/__init__.py` currently combines target discovery, workspace modeling,
preferences, and output:

- `git_parent_path()` climbs from the current directory to find a parent git
  checkout.
- `find_actual_path()` resolves the target path, defaulting to the containing
  git checkout when run inside one.
- `get_target()` returns either `GitCheckout` or `ProjectDir`.
- `MgitPreferences` stores display and operation flags.
- `GitCheckout` wraps one local path and prints status.
- `ProjectDir` scans direct child directories, collects git checkouts, detects
  predominant remote project grouping, and prints multi-repo status.
- `RemoteProject` classes currently identify GitHub, Stash, or unknown remotes,
  but server-side project listing is not implemented.

`src/mgit/git.py` holds most git-specific behavior:

- `GitRunReport` composes problems, progress, and notes with stable ordering.
- `GitURL` parses file, HTTPS, SSH, GitHub-style SSH, and unknown URLs.
- `GitDir` is the main git runner and state facade.
- `GitAspect` is a base class for parsed git-command output.
- `GitBranches`, `GitConfig`, and `GitStatus` parse branch, config, and status
  output.
- Cleanable branches are derived from branch/config state and merged remote
  branches.

## Reusable Pieces

Good candidates to keep, possibly with relocation and dataclass-style cleanup:

- URL parsing coverage and behavior from `GitURL`.
- `GitRunReport` semantics, especially deduping, ordering, truncation, and
  problem/progress/note separation.
- `GitStatus` parsing of `git status --porcelain --branch`.
- `GitBranches` parsing of current/local/remote/default branches.
- The guarded `pull()` behavior that refuses when there are pending changes or
  status problems.
- Direct-child workspace scanning for multi-repo folders. In v2, use
  `workspace` as the user-facing name for this concept.
- The default target behavior: when no target is supplied, use the current git
  checkout if the current directory is inside one.

## Pain Points To Address

- Click decorators make command growth awkward for the desired subcommand API.
  Argparse is the preferred v2 direction so the CLI can drop one runtime
  dependency.
- `src/mgit/__init__.py` mixes public package imports, repo discovery, models,
  preferences, and rendering.
- `GitDir` mixes command execution, cached state, mutations, and reporting.
- Clean/reset behavior lives in the CLI layer and includes destructive actions.
  For v2, local grooming is first-iteration work because it is a primary usage
  path; remote cleanup and reset remain maybe-later work.
- `what in "remote all"` style checks are fragile because they are substring
  checks rather than membership checks.
- `remote_cleanable_branches` only considers SSH remotes.
- Runtime dependency goals are unsettled: current code depends on `click` and
  `runez`; the draft wants `argparse` and minimal dependencies.
- Packaging says `license-files = ["LICENSE.txt"]`, while the repository file
  is `LICENSE`; this should be revisited during packaging cleanup.

## Current Test Coverage

Existing tests cover:

- Branch-name validation.
- Git URL parsing.
- Report composition, sorting, filtering, and truncation.
- Preference string representation.
- Basic Click CLI help/version/error/status behavior.

Coverage is light around:

- Branch/status parsing from realistic git output fixtures.
- Workspace scans with multiple fake repos.
- Fetch/pull/main/groom command behavior, especially the `mgit g` flow.
- Clone config matching.
- Destructive command boundaries.
- Exit codes.
