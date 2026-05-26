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

- `GitDir.lazy_refs`: A `GitRefs` snapshot centered on
  `GitRefs.all_branches: dict[str, BranchInfo]`. Local branches are keyed by
  their local name; unpaired remote-tracking branches use a qualified key such
  as `origin/topic`. Each `BranchInfo` carries raw local/tracked-remote refs,
  OIDs, trees, upstream configuration, protection, and evaluated cleanup
  proofs, plus its owning `GitRefs` snapshot for lazily derived ref metadata
  such as protection. The snapshot in turn owns its `GitDir`, which branches
  use for exceptional proof commands. A local branch and its tracked remote
  share one `BranchInfo`; a remote branch with no matching local upstream gets
  a qualified entry instead of a parallel remote-ref index. Plain inspection
  does not run `git remote`; the pull flow queries configured remotes only
  when it needs to distinguish a missing remote.

- `GitRefs.default_branch`: The default branch derived for a particular refs
  snapshot, preferring `origin/HEAD` and falling back to a visible `main` or
  `master` branch.

- `BranchInfo.cleanable`, `local_cleanup`, and `remote_cleanup`: Lazily ask
  their owning `GitRefs` snapshot to fill merge and cleanup proof fields.
  Normal ancestry-merged branches are discovered in one
  `git for-each-ref --merged=<base>` query. Candidates not found there require
  individual `git merge-tree` checks to retain squash-merge/content
  equivalence support. This remains lazy because flows such as checkout and
  pull may inspect and then immediately invalidate a refs snapshot.

## Invalidation Requirements

The operations below may run during one lifetime of a `GitDir` instance:

| Operation | `status` | `refs` | Reason |
| --- | --- | --- | --- |
| `fetch_now()` | stale | stale | Ahead/behind and remote-tracking branches can change; pruning can alter branch presence and cleanup proof. |
| checkout | stale | stale | The checked-out branch and displayed status can change. |
| `pull()` | stale | stale | Worktree/status and remote-tracking refs may change, including when the pull fails after doing some work. |
| delete local branch | unchanged in the `groom` flow | stale | The local branch collection changes; deletion occurs after checkout. |
| delete remote branch | unchanged in the `groom` flow | stale | The remote-tracking branch collection changes. |

`default_branch` and evaluated `BranchInfo` cleanup state share the lifetime
of their owning `GitRefs` snapshot. Replacing stale `refs` discards the branch
map so raw refs and cleanup state are recomputed from the fresh snapshot.

## Current Implementation Note

`GitDir.lazy_status` and `GitDir.lazy_refs` are ordinary lazy properties backed by
`_status` and `_refs`. State-changing `GitDir` methods explicitly set the
affected backing field to `None` according to the table above. This keeps
invalidation local to the operation that makes a snapshot stale and avoids a
generic cache reset.
