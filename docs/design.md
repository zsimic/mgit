# Design Notes

This document records implementation decisions and constraints that are useful
when changing `mgit`. It is intentionally broader than a user-facing
architecture overview: add notes here when they explain how a part of the CLI
should continue to evolve.

## Cached Repository State

`GitDir` is used for one command run and lazily captures git state that can
otherwise require repeated subprocess calls.

- `GitDir.default_branch`: The default branch selected for the command run.
  Once selected, it should remain stable while a command proceeds, including
  while `groom` checks out, pulls, and deletes branches. A newly fetched
  `origin/HEAD` could influence the initial selection if this property has not
  yet been read.

- `GitDir.status`: A `GitStatus` snapshot produced from
  `git status --porcelain=v2 --branch`. It includes pending changes and
  upstream ahead/behind information.

- `GitDir.refs`: A `GitRefs` snapshot of the current branch, local branches,
  configured remotes, remote-tracking branches, remote default branches, and
  upstream configuration.

- `GitRefs.orphan_branches`: Derived cached data owned by a particular
  `GitRefs` snapshot. It is discarded naturally when `GitDir.refs` is
  replaced, so it must not be invalidated separately.

## Invalidation Requirements

The operations below may run during one lifetime of a `GitDir` instance:

| Operation | `status` | `refs` | Reason |
| --- | --- | --- | --- |
| `fetch_now()` | stale | stale | Ahead/behind and remote-tracking branches can change; pruning can alter orphan detection. |
| checkout | stale | stale | The checked-out branch and displayed status can change. |
| `pull()` | stale | stale | Worktree/status and remote-tracking refs may change, including when the pull fails after doing some work. |
| delete local branch | unchanged in the `groom` flow | stale | The local branch collection changes; deletion occurs after checkout. |
| delete remote branch | unchanged in the `groom` flow | stale | The remote-tracking branch collection changes. |

`default_branch` is deliberately not listed as transient state to clear after
these operations: it is the command run's chosen target branch. Fetch should
occur before its first access in any flow that wants freshly observed remote
default-branch information.

## Current Implementation Note

`GitDir.clear_cached_state()` currently discards every cached property on
`GitDir`. This is broader than the invalidation requirements above and clears
`default_branch` unnecessarily. Also, `fetch_now()` currently updates `age`
without clearing an already materialized `status` or `refs` snapshot; existing
command flows rely on fetching before reading them.

A follow-up refactor should replace the generic reset with explicit
invalidation of `status` and `refs` at the mutation points above, including
`fetch_now()`.
