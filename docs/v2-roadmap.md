# mgit v2 Roadmap

This roadmap breaks the rewrite into small checkpoints. Keep the checkboxes
accurate as work proceeds.

## Principles

- Preserve useful behavior while replacing the v1 flag-oriented CLI.
- Make the command model explicit.
- Keep git command execution easy to test.
- Separate parsing, state modeling, command handlers, and rendering.
- Make destructive behavior clear and guarded. `groom`/`g` may delete only the
  safely proven current local branch and its leased tracked `origin` branch;
  broad remote deletion and reset stay later.
- Prefer fewer dependencies.
- Use `workspace` for multi-repo folders and scan only direct children:
  `<workspace>/*/.git`.

## Phase 0: Baseline

- [x] Inventory current source, tests, docs, and tooling.
- [x] Capture current behavior and reuse candidates.
- [x] Draft v2 command and migration plan docs.
- [ ] Run the existing test suite from a clean environment.
- [ ] Add focused tests around current branch/status parsing before moving code.

## Phase 1: Architecture Skeleton

- [x] Introduce a command registry with command classes.
- [x] Introduce argparse parsing for the v2 command shape.
- [ ] Move target discovery into a dedicated module.
- [x] Enforce depth-1 workspace scanning.
- [x] Add an output/color helper module.
- [ ] Move remaining status/report rendering into a dedicated module.
- [x] Remove `MgitPreferences` and make commands own their fetch/pull behavior.
- [x] Make default-branch resolution a cached `GitDir.default_branch`
  property.
- [ ] Keep `GitRunReport` rendering tests and high-level CLI behavior tests
  green during moves.

Suggested module split:

- `mgit.cli`: argparse entry point, top-level error handling, command registry,
  and command handlers.
- `mgit.discovery`: target resolution and workspace scanning.
- `mgit.git`: low-level git command runner and git state parsers.
- `mgit.config`: v2 TOML config loading and clone-location matching.
- `mgit.output`: color policy and formatting.

## Phase 2: Core Commands

- [x] Implement `status` and `s`.
- [x] Implement `fetch` and `f`.
- [x] Implement `pull` and `p`.
- [x] Implement single-repo `groom` and `g` as the priority cleanup workflow.
- [x] Implement `main` and `m`.
- [x] Implement `branches` and `b`.
- [x] Keep output shape independent of `-v/--verbose`.
- [x] Defer `--short`/`--long` unless they become clearly useful.
- [x] Wire `-v/--verbose` to logging verbosity.
- [x] Require cleanable branches to be merged or content-equivalent to the
  default branch.
- [x] Refuse `groom` from non-default branches that are not cleanable.
- [x] Delete the still-present tracked `origin` branch being groomed only after
  an independent merge/content proof and an exact-ref lease.
- [x] Add CLI tests for default command, short names, explicit commands,
  invalid usage, and folders.

## Phase 3: Clone Command

- [ ] Add `~/.config/mgit/config.toml` loader.
- [ ] Add short config documentation, likely `docs/config.md`.
- [ ] Make `clone` fail with setup guidance when config is missing.
- [ ] Implement location match normalization.
- [ ] Implement best-match scoring.
- [ ] Require full clone URLs for the first implementation.
- [ ] Fail with `clone location not configured for url` when no location
  matches.
- [ ] Implement `clone` and `c`.
- [ ] Cover URL variants and tie-breaking in tests.

## Maybe Later: Destructive Commands

- [ ] Add workspace support for `groom` if the single-repo behavior proves out.
- [ ] Decide dry-run and confirmation policy for broad remote branch deletion.
- [ ] Implement `groom-remote` if safety rules are settled.
- [ ] Implement `groom-all` if safety rules are settled.
- [ ] Decide whether `zap-zap` belongs in v2.0 or a later v2.x.

## Phase 4: Dependency And Packaging Cleanup

- [x] Remove the unused Click dependency from package metadata.
- [ ] Decide whether to remove `runez` or keep a small dependency on it.
- [ ] If removing `runez`, replace cached properties, paths, durations, aborts,
  and coloring with stdlib code.
- [ ] Revisit `license-files` vs the actual `LICENSE` file.
- [x] Update README examples and help synopsis for the implemented v2 commands.
- [x] Update contributing docs for the current `pyproject.toml`/`uv` workflow.
- [ ] Add release notes.

## Completed First Implementation Slice

The first coding slice serves the two common command loops first:

1. Parser and command-registry tests cover `mgit`, `mgit status`, `mgit s`,
   `mgit fetch`, `mgit f`, `mgit pull`, `mgit p`, `mgit groom`, and `mgit g`.
2. An argparse entry point maps those commands onto existing
   git/status behavior.
3. The inspect-then-act update loop is preserved: `mgit f` reports remote
   state, and `mgit p` pulls only when explicitly requested.
4. The single-repo `g` workflow fetches/prunes, resolves the default branch,
   refuses on pending changes, checks out the default branch when needed, pulls
   safely, lease-deletes its still-present proven-cleanable `origin` branch,
   and deletes only the safely proven local branch it started on.
5. `mgit main`/`m` uses the same default-branch resolution.
6. `-v/--verbose` stays out of output-shape decisions.
7. `--short`/`--long` remain deferred.
8. Legacy v1 action flags were not carried into v2; use commands such as `mgit f`
   and `mgit p` instead.

This makes the most common loops work first: `mgit`, then `mgit f`/`mgit p`
for ordinary updates, and `mgit g` after the PR is merged.

## Open Decisions

- Should mutating commands ask for confirmation by default?
- Should workspace `pull` continue across failures or offer fail-fast?
- Should output alignment stay fixed-width text, or move to a small table
  renderer?
- Should v2.0 be stdlib-only at runtime?

Later clone QoL:

- Should `clone` accept shorthand `owner/repo` inputs?
- Should clone config support SSH or per-location protocol preference?
