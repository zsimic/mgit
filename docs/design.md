# Design Notes

This document records implementation decisions and constraints that are useful
when changing `mgit`. It is intentionally broader than a user-facing
architecture overview: add notes here when they explain how a part of the CLI
should continue to evolve.

## Cached Repository State

`GitDir` is used for one command run and lazily captures git state that can
otherwise require repeated subprocess calls.

- `GitDir.lazy_status`: A `GitStatus` snapshot produced from
  `git status --porcelain=v2 --branch`. It includes pending changes and
  upstream ahead/behind information. It does not classify ref-derived
  conditions such as a gone upstream; command flows combine that information
  with `GitRefs` where needed.

- `GitDir.lazy_refs`: A `GitRefs` snapshot of the current branch, local branches,
  configured remotes, remote-tracking branches, remote default branches, and
  upstream configuration.

- `GitRefs.default_branch`: The default branch derived for a particular refs
  snapshot, preferring `origin/HEAD` and falling back to a visible `main` or
  `master` branch.

- `GitDir.branch_infos`: Derived branch display data combining a local ref,
  its configured upstream presence, and local/remote cleanup proofs. It is
  invalidated together with `GitDir.lazy_refs`, because either ref movement or
  fetch/prune results can change whether a branch is cleanable.

## Invalidation Requirements

The operations below may run during one lifetime of a `GitDir` instance:

| Operation | `status` | `refs` | Reason |
| --- | --- | --- | --- |
| `fetch_now()` | stale | stale | Ahead/behind and remote-tracking branches can change; pruning can alter branch presence and cleanup proof. |
| checkout | stale | stale | The checked-out branch and displayed status can change. |
| `pull()` | stale | stale | Worktree/status and remote-tracking refs may change, including when the pull fails after doing some work. |
| delete local branch | unchanged in the `groom` flow | stale | The local branch collection changes; deletion occurs after checkout. |
| delete remote branch | unchanged in the `groom` flow | stale | The remote-tracking branch collection changes. |

`default_branch` shares the lifetime of its owning `GitRefs` snapshot.
Replacing stale `refs` also discards derived `branch_infos` so cleanup state
is recomputed from the fresh snapshot.

## Current Implementation Note

`GitDir.lazy_status` and `GitDir.lazy_refs` are ordinary lazy properties backed by
`_status` and `_refs`. State-changing `GitDir` methods explicitly set the
affected backing field to `None` according to the table above. This keeps
invalidation local to the operation that makes a snapshot stale and avoids a
generic cache reset.
