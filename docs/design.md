# Design notes

A `GitDir` lives for one command run. It caches the git state that would otherwise take repeated
subprocess calls, in two snapshots built on first access.

## The two snapshots

- `GitDir.lazy_status` is a `GitStatus`, parsed from `git status --porcelain=v2 --branch`: pending
  changes and ahead/behind counts. It knows nothing about refs, a gone upstream for example comes
  from `GitRefs`.
- `GitDir.lazy_refs` is a `GitRefs`, built from `git for-each-ref` over local and remote branches.
  `GitRefs.all_branches` has one `BranchInfo` per branch: a local branch and the remote branch it
  tracks share an entry (keyed by the local name), an untracked remote branch gets its own (keyed
  like `origin/topic`). There is deliberately no separate index of remote refs.
- `GitRefs.default_branch` is `origin/HEAD` when set, otherwise `main` or `master`, whichever
  exists.

Plain inspection never runs `git remote`, only `pull` does (to report "no remotes").

## Cleanup proofs are lazy

`BranchInfo.cleanable`, `.local_cleanup` and `.remote_cleanup` are evaluated on first access, for
every branch of the snapshot at once. One `git for-each-ref --merged=<default branch>` finds the
regularly merged branches, and only the remaining candidates get an individual `git merge-tree`
check, which is what recognizes squash-merged ones. It stays lazy because flows like `main` and
`pull` look at refs, then immediately invalidate them.

## Invalidation

What each state-changing operation does to the snapshots of the `GitDir` it runs on:

| Operation | `status` | `refs` | Reason |
| --- | --- | --- | --- |
| `fetch_now()` | stale | stale | Ahead/behind and remote branches can change, pruning can remove branches and change cleanup proofs. |
| checkout | stale | stale | The current branch, and what status shows, can change. |
| `pull()` | stale | stale | Worktree and remote branches can change, even when the pull fails midway. |
| delete local branch | unchanged in `groom` | stale | The set of local branches changes, deletion happens after checkout. |
| delete remote branch | unchanged in `groom` | stale | The set of remote branches changes. |

`default_branch` and the cleanup proofs live and die with their `GitRefs` snapshot: a fresh one
recomputes everything. The methods making a snapshot stale reset its backing field (`_status`,
`_refs`) to `None` themselves, keeping invalidation next to the operation that causes it rather
than in a generic cache reset.
