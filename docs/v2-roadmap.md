# mgit v2 Roadmap

This roadmap breaks the rewrite into small checkpoints. Keep the checkboxes
accurate as work proceeds.

## Principles

- Preserve useful behavior while replacing the v1 flag-oriented CLI.
- Make the command model explicit.
- Keep git command execution easy to test.
- Separate parsing, state modeling, command handlers, and rendering.
- Make destructive behavior clear and guarded. `groom`/`g` is first-iteration
  local cleanup; remote deletion and reset stay later.
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

- [x] Introduce a command registry with command metadata.
- [x] Introduce argparse parsing for the v2 command shape.
- [ ] Move target discovery into a dedicated module.
- [ ] Enforce depth-1 workspace scanning.
- [ ] Move output/color/report rendering into a dedicated module.
- [ ] Keep `GitRunReport`, `GitURL`, and parser tests green during moves.

Suggested module split:

- `mgit.cli`: argparse entry point and top-level error handling.
- `mgit.commands`: command registry and command handlers.
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
- [ ] Implement `branches` and `b`.
- [x] Support `-v/--verbose`.
- [ ] Keep one compact default output style; defer `--short` unless it becomes
  clearly useful.
- [x] Add CLI tests for default command, aliases, explicit commands, invalid
  usage, and target paths.

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
- [ ] Decide dry-run and confirmation policy for remote branch deletion.
- [ ] Implement `groom-remote` if safety rules are settled.
- [ ] Implement `groom-all` if safety rules are settled.
- [ ] Decide whether `zap-zap` belongs in v2.0 or a later v2.x.

## Phase 4: Dependency And Packaging Cleanup

- [ ] Remove Click after argparse replacement is complete.
- [ ] Decide whether to remove `runez` or keep a small dependency on it.
- [ ] If removing `runez`, replace cached properties, paths, durations, aborts,
  and coloring with stdlib code.
- [ ] Revisit `license-files` vs the actual `LICENSE` file.
- [ ] Update README examples and help synopsis.
- [ ] Update contributing docs and release notes.

## First Implementation Slice

The first coding slice should serve the two common commands first:

1. Add parser and command-registry tests for `mgit`, `mgit status`, `mgit s`,
   `mgit fetch`, `mgit f`, `mgit pull`, `mgit p`, `mgit groom`, and `mgit g`.
2. Implement an argparse entry point that maps those commands onto existing
   git/status behavior.
3. Preserve the inspect-then-act update loop: `mgit f` reports remote state, and
   `mgit p` pulls only when explicitly requested.
4. Add the single-repo `g` workflow: fetch/prune, resolve default branch,
   refuse on pending changes, checkout default branch when needed, pull safely,
   and delete stale local branches.
5. Add `mgit main`/`m` and `-v/--verbose` around that core.
6. Defer `--debug` and `--short`.
7. Do not carry legacy v1 action flags into v2; use commands such as `mgit f`
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
