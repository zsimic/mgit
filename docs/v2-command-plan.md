# mgit v2 Command Plan

This file captures the working command design for v2. It is intentionally a
plan, not a promise. Update it as decisions settle.

## Design Goals

- Keep `mgit` fast to type and easy to reason about.
- Make `mgit` with no command mean status.
- Use subcommands instead of behavior-heavy flags.
- Support short aliases for common commands where the alias is unambiguous.
- Let each command declare whether it supports one repo, many repos, or both.
- Keep one compact default output style, with `-v/--verbose` for extra detail.
- Prefer stdlib implementation unless a dependency removes enough complexity to
  justify itself.
- Use argparse for v2 unless a concrete issue proves Click is still worth the
  dependency.

## Proposed CLI Shape

```shell
mgit [GLOBAL_OPTIONS] [COMMAND] [ARGS...]
```

Global options:

- `--color auto|always|never`
- `-v, --verbose`
- `--version`
- `--help`

The v1 action flags are intentionally not part of v2. For example, use
`mgit f`, not `mgit -f`; use `mgit p`, not `mgit -p`.

Not planned for the first iteration:

- `--debug`
- `--short`

Default command:

- `mgit` is equivalent to `mgit status`.

Common workflow:

```shell
mgit      # inspect local status and fetch freshness
mgit f    # update remote refs and show whether anything is behind/cleanable
mgit p    # pull only after seeing what fetch found
mgit      # keep checking status while working
mgit f    # after PR merge, refresh branch state
mgit g    # return to default branch, pull safely, clean local stale branches
```

This split is intentional. `fetch` and `pull` should stay separate for ordinary
updates so the user can inspect remote state before pulling. `groom` is the
workflow bundle for the post-merge cleanup case.

Target handling:

- Most commands accept an optional path target.
- If no target is supplied and the current directory is inside a git checkout,
  the target is that checkout.
- If no target is supplied and the current directory is not inside a checkout,
  the target is the current directory as a workspace.
- A single unknown token is treated as a `status` target, so `mgit path`
  inspects that path. Extra positional tokens are invalid usage.
- A workspace scan is depth 1 only: inspect direct children matching
  `<workspace>/*/.git`. Nested descendants are out of scope for now.

## Command Registry

The implementation should use an explicit command registry. Each command should
define:

- canonical name
- aliases
- help summary
- accepted scope: single, multi, or both
- whether it mutates local state
- whether it mutates remote state
- handler function

First-iteration command candidates:

| Command | Aliases | Scope | Mutates | Meaning |
| --- | --- | --- | --- | --- |
| `status` | `s` | both | no | Show repo or workspace status. |
| `fetch` | `f` | both | local refs | Run `git fetch --all --prune`, then status. |
| `pull` | `p` | both | worktree | Pull with rebase only when safe. |
| `main` | `m` | single | worktree | Checkout the default branch. |
| `groom` | `g` | single first, both later | local branches | Run the local branch-cleanup workflow. |
| `branches` | `b` | both | no | Show local branches, useful across workspaces. |
| `clone` | `c` | command-specific | filesystem | Clone URL into configured best-match location. |

Maybe-later destructive commands:

| Command | Aliases | Scope | Destructive action |
| --- | --- | --- | --- |
| `groom-remote` | none | single first | Delete merged remote branches. |
| `groom-all` | none | single first | Delete local and merged remote branches. |
| `zap-zap` | none | single | Reset hard and delete untracked files. |

Alias policy:

- One-letter aliases are for high-frequency commands only.
- Ambiguous aliases should fail with a helpful message.
- `g` is the one deliberate exception to the dangerous-alias rule because local
  grooming is a core workflow. Remote deletion and reset commands should not get
  one-letter aliases.

## Command Semantics

`status`:

- Read-only.
- Shows branch, freshness, pending diffs, untracked count, ahead/behind/gone
  state, and stale fetch notes.
- Verbose mode shows modified/untracked paths.

`fetch`:

- Runs `git fetch --all --prune`.
- In a workspace, runs per checkout and reports failures per repo.
- Reports the resulting status so the user can decide whether to pull or groom.
- Should avoid refetching if a freshness threshold is provided in the future;
  v2 can start with explicit fetch always fetching.

`pull`:

- Runs only when there are no pending modified/untracked files and no status
  problems.
- Uses `git pull --rebase`.
- In a workspace, skipped/problem repos should not stop the whole run unless a
  global fail-fast option is added later.

`main`:

- Resolves the default branch from `origin/HEAD` or remote config.
- Falls back to `main`, then `master`, only if no default can be detected.
- Treats the command name `main` as a user-facing concept, not a literal branch
  name.

`branches`:

- Read-only.
- For a single repo, equivalent to a compact branch report.
- Shows git-style local branches, preserving the `*` marker for the current
  branch.
- Annotates known facts such as `[default]` and `[orphaned]`.
- For a workspace, groups the same compact branch report under each checkout.

`groom`:

- Priority first-iteration command.
- Local-only cleanup command. It must not delete remote branches.
- Fetches first with prune so branch status is current.
- Refuses to switch or delete when the current worktree has pending changes.
- Resolves the default branch using the same `main` logic.
- Checks out the default branch when cleanup should proceed, then deletes only
  branches proven stale/cleanable.
- Pulls the default branch safely, using the same guardrails as `pull`.
- Deletes local branches whose tracked remote is gone, while never deleting
  default branches, `HEAD`, `main`, or `master`.
- Leaves non-tracking local branches alone in the first implementation.
- Reports what it did and what it skipped.
- First iteration should prioritize the single-repo flow. Workspace grooming can
  come after single-repo behavior is solid.

`groom-remote` and `groom-all`:

- Maybe-later destructive commands; not first-iteration work.
- Remote mutation should remain explicit and visibly named.
- Start single-repo only unless multi-repo safety rules are made concrete.
- Should have dry-run or confirmation policy before implementation is finalized.

`zap-zap`:

- Maybe-later destructive command; not first-iteration work.
- Destructive reset command.
- Single-repo only.
- Should require an explicit command name and be refused in a workspace.

## Clone Config

Config is used only by `mgit clone`. All other commands should work without any
mgit config file.

If `~/.config/mgit/config.toml` is missing, `mgit clone` should fail before
cloning and print a helpful message:

```text
Create ~/.config/mgit/config.toml first.
See https://github.com/zsimic/mgit/blob/main/docs/config.md
```

The exact URL should point to a short Markdown guide in this repo once that
guide exists.

Preferred TOML shape:

```toml
locations = [
    { match = "github.com/zsimic/*", dir = "~/github" },
    { match = "github.com/*",        dir = "~/ext" },
    { match = "git.mycompany.com/*", dir = "~/dev" },
]
```

Reasons to prefer the list form:

- It is easy to extend with future fields such as `protocol`, `remote`, or
  `name_template`.
- It keeps match rules explicit and predictable.
- It avoids TOML table-key escaping for paths like `~/github`.

Best-match behavior:

- `mgit clone` expects a full URL.
- First implementation assumes HTTPS URLs. SSH support or protocol preference
  can be added later if it becomes useful again.
- Normalize clone URLs into `host/owner/repo` style match keys.
- Match with shell-style wildcards using `fnmatch`.
- Pick the most specific match, where exact characters score higher than `*`.
- On ties, prefer the earlier config entry.
- Clone destination is `dir/repo-name`.
- If no location matches the URL, fail with `clone location not configured for
  url`.

Later quality-of-life ideas:

- Accept shorthand such as `owner/repo`.
- Support SSH or per-location protocol preference.

## Color And Output

Initial recommendation: use stdlib ANSI coloring with auto-detection.

Rules:

- `--color auto` colors only on TTY.
- `--color never` disables ANSI.
- `--color always` forces ANSI.
- Respect `NO_COLOR`.
- Keep output stable enough for tests by letting tests disable color.

Reconsider `rich` only if table layout, wrapping, or Windows color support
becomes a real implementation burden.

## Exit Codes

Draft policy:

- `0`: command completed without repo-level problems.
- `1`: command completed but one or more repos had problems.
- `2`: invalid CLI usage or config.

Workspace commands should continue across repos and summarize failures.
