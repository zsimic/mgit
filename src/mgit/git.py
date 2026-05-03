from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from functools import cached_property
from typing import Mapping, TYPE_CHECKING

import runez

from mgit import output

if TYPE_CHECKING:
    from pathlib import Path

LOG = logging.getLogger(__name__)
FETCH_AGE_FILES = ("FETCH_HEAD", "HEAD")
FRESHNESS_THRESHOLD = 12 * runez.date.SECONDS_IN_ONE_HOUR
GIT_ERROR_PREFIXES = {"git", "error", "fatal"}

REMOTE_REF_PREFIX = "refs/remotes/"
LOCAL_REF_PREFIX = "refs/heads/"
_CACHED_GIT_STATE = (
    "default_branch",
    "status",
    "refs",
    "orphan_branches",
    "cleanable_base_ref",
    "local_cleanable_branches",
)


def shortened_message(text, keep_lines=2, separator=" "):
    """
    :param str text: Original git error message (those can be verbose, and include progress)
    :param int keep_lines: Max lines to keep
    :param str separator: Lines are split for shortening, separator to use to re-join lines
    :return str: Shortened git error message
    """
    lines = []
    prefixed = []
    for line in text.strip().split("\n"):
        line = line.strip().strip(".")
        if not line:
            continue

        p = line.partition(":")
        if p[2] and p[0] in GIT_ERROR_PREFIXES:
            prefixed.append(p[2].strip())

        else:
            lines.append(line)

    if prefixed:
        lines = prefixed

    if keep_lines and len(lines) > keep_lines:
        lines = lines[:keep_lines]

    return separator.join(lines).replace("  ", " ").strip()


class GitRunReport:
    """Convenient and easy to compose reporting class"""

    def __init__(
        self,
        other: GitRunReport | None = None,
        *,
        progress: str | None = None,
        note: str | None = None,
        problem: str | None = None,
    ):
        self._progress = []
        self._note = []
        self._problem = []
        self.add(other, progress=progress, note=note, problem=problem)

    def __contains__(self, text):
        """
        :param str text: Text to look up
        :return bool: True if 'text' is mentioned in one of the messages in self._problem
        """
        return bool(text) and any(text in problem for problem in self._problem)

    def cant_pull(self, reason=None):
        self.add(problem="<can't pull")
        if reason:
            self.add(problem=reason)

        return self

    @property
    def has_problems(self):
        return bool(self._problem)

    def representation(self, progress=True, note=True, max_chars=160, separator="; "):
        """
        :param bool progress: Show repos with progress mention (pulled/cloned)
        :param bool note: Show repos with notes
        :param int max_chars: Max chars to show (truncate if messages are longer)
        :param str separator: Separator to use
        :return str: Textual representation
        """
        result = []
        n = _add_sorted(result, self._problem, output.problem, 0, max_chars)

        if progress:
            n = _add_sorted(result, self._progress, output.progress, n, max_chars)

        if note:
            _add_sorted(result, self._note, output.note, n, max_chars)

        result = separator.join(result)
        if len(result) > max_chars:
            result = f"{result[: max_chars - 3]}..."

        return result

    def add(
        self,
        other: GitRunReport | None = None,
        *,
        progress: str | None = None,
        note: str | None = None,
        problem: str | None = None,
    ) -> GitRunReport:
        if other is not None:
            _add_messages(self._progress, other._progress)
            _add_messages(self._note, other._note)
            _add_messages(self._problem, other._problem)

        _add_messages(self._progress, progress)
        _add_messages(self._note, note)
        _add_messages(self._problem, problem)
        return self


@dataclass(frozen=True)
class BranchUpstream:
    """Configured upstream for a local branch."""

    remote: str
    branch: str
    ref: str
    short_ref: str


@dataclass(frozen=True)
class GitRefs:
    """Repository ref and upstream snapshot."""

    current: str = ""
    detached: bool = False
    local: frozenset[str] = frozenset()
    remotes: frozenset[str] = frozenset()
    by_remote: Mapping[str, frozenset[str]] = field(default_factory=dict)
    default_branches: Mapping[str, str] = field(default_factory=dict)
    upstreams: Mapping[str, BranchUpstream] = field(default_factory=dict)

    @classmethod
    def load(cls, parent: GitDir) -> GitRefs:
        current, detached = parent._current_branch()
        remotes = parent._remote_names()
        local: set[str] = set()
        by_remote: dict[str, set[str]] = {}
        default_branches: dict[str, str] = {}
        upstreams: dict[str, BranchUpstream] = {}

        output, error = parent.run_git_command(
            "for-each-ref",
            "--format=%(refname)%09%(HEAD)%09%(upstream:short)%09%(upstream:remotename)%09%(upstream:remoteref)%09%(symref)",
            "refs/heads",
            "refs/remotes",
        )
        if error.has_problems:
            LOG.debug("Could not inspect git refs: [%s]", error.representation())

        for line in output.splitlines():
            refname, marker, upstream_short, upstream_remote, upstream_ref, symref = _padded_fields(line, 6)
            if refname.startswith(LOCAL_REF_PREFIX):
                name = refname[len(LOCAL_REF_PREFIX) :]
                local.add(name)
                if marker == "*":
                    current = name
                    detached = False

                upstream = _branch_upstream(upstream_remote, upstream_ref, upstream_short)
                if upstream:
                    upstreams[name] = upstream

            elif refname.startswith(REMOTE_REF_PREFIX):
                remote, branch = _remote_ref_parts(refname)
                if not remote or not branch:
                    continue

                if branch == "HEAD":
                    default = _remote_default_branch(remote, symref)
                    if default:
                        default_branches[remote] = default

                    continue

                by_remote.setdefault(remote, set()).add(branch)

        return cls(
            current=current,
            detached=detached,
            local=frozenset(local),
            remotes=remotes,
            by_remote={name: frozenset(branches) for name, branches in by_remote.items()},
            default_branches=default_branches,
            upstreams=upstreams,
        )

    def has_remote(self, remote: str) -> bool:
        return remote in self.remotes

    def has_remote_branch(self, remote: str, branch: str) -> bool:
        return branch in self.by_remote.get(remote, frozenset())

    def upstream_gone(self, branch: str) -> bool:
        upstream = self.upstreams.get(branch)
        return bool(upstream and not self.has_remote_branch(upstream.remote, upstream.branch))


def _padded_fields(line: str, count: int) -> list[str]:
    fields = line.split("\t")
    if len(fields) < count:
        fields.extend("" for _ in range(count - len(fields)))

    return fields[:count]


def _remote_ref_parts(refname: str) -> tuple[str, str]:
    name = refname[len(REMOTE_REF_PREFIX) :]
    remote, _, branch = name.partition("/")
    return remote, branch


def _remote_default_branch(remote: str, symref: str) -> str:
    prefix = f"{REMOTE_REF_PREFIX}{remote}/"
    if symref.startswith(prefix):
        return symref[len(prefix) :]

    return ""


def _branch_upstream(remote: str, ref: str, short_ref: str) -> BranchUpstream | None:
    if not remote or not ref:
        return None

    branch = ref[len(LOCAL_REF_PREFIX) :] if ref.startswith(LOCAL_REF_PREFIX) else ref
    return BranchUpstream(remote=remote, branch=branch, ref=ref, short_ref=short_ref)


def _ahead_behind(value: str) -> tuple[int, int]:
    ahead = 0
    behind = 0
    for item in value.split():
        if item.startswith("+"):
            ahead = int(item[1:] or "0")

        elif item.startswith("-"):
            behind = int(item[1:] or "0")

    return ahead, behind


class GitDir:
    """Model a local git repo"""

    def __init__(self, path: Path):
        """
        :param Path path: Path to local repo
        """
        self.path = path

    def report(self, bare=False) -> GitRunReport:
        """
        :param bool bare: Bare report only
        :return GitRunReport: General report on current checkout state
        """
        result = GitRunReport()
        refs = self.refs

        if not refs.remotes:
            result.add(problem="no remotes")

        if bare:
            return result

        age = self.age
        if age is not None and age > FRESHNESS_THRESHOLD:
            result.add(note=f"last fetch {runez.represented_duration(age)} ago")

        orphan_branches = self.orphan_branches
        if refs.current in orphan_branches:
            # Current is no more on its remote (should possibly checkout another branch and cleanup, or push)
            orphan_branches = orphan_branches[:]
            orphan_branches.remove(refs.current)
            result.add(note=f"current branch '{refs.current}' is orphaned")

        cleanable = sorted(self.local_cleanable_branches)
        if len(cleanable) == 1:
            result.add(note=f"local branch '{cleanable[0]}' can be pruned")

        elif cleanable:
            result.add(note=f"{runez.plural(cleanable, 'local branch')} can be pruned")

        if refs.detached:
            result.add(note="HEAD detached")

        return result

    def run_git_command(self, *args) -> tuple[str, GitRunReport]:
        """
        :param args: Execute git command with provided args
        :return str, GitRunReport: Output from git command + report on eventual error
        """
        cmd = ["git", "-C", str(self.path), *args]
        LOG.debug("Running: git -C %s %s", runez.short(self.path), " ".join(args))
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)  # noqa: S603
        output, error = proc.communicate()
        if proc.returncode == 0:
            return output, GitRunReport()

        if not error:
            return output, GitRunReport(problem=f"git exited with code {proc.returncode}")

        return output, GitRunReport(problem=shortened_message(error))

    def clear_cached_state(self) -> None:
        """Discard cached git state after a command may have changed refs or worktree state."""
        for name in _CACHED_GIT_STATE:
            self.__dict__.pop(name, None)

    def _current_branch(self) -> tuple[str, bool]:
        output, error = self.run_git_command("symbolic-ref", "--quiet", "--short", "HEAD")
        if not error.has_problems:
            return output.strip(), False

        output, error = self.run_git_command("rev-parse", "--verify", "--quiet", "HEAD")
        if not error.has_problems and output.strip():
            return "HEAD", True

        return "", False

    def _remote_names(self) -> frozenset[str]:
        output, error = self.run_git_command("remote")
        if error.has_problems:
            LOG.debug("Could not inspect git remotes: [%s]", error.representation())
            return frozenset()

        return frozenset(line.strip() for line in output.splitlines() if line.strip())

    def fetch(self, age: int | None = 30) -> GitRunReport:
        """
        :param int|None age: Fetch if age is older than specified number of seconds, use None to fetch unconditionally
        :return GitRunReport:
        """
        if age is not None:
            current_age = self.age
            if current_age is not None and current_age <= age:
                return GitRunReport()

        _, error = self.run_git_command("fetch", "--all", "--prune")
        self.clear_cached_state()
        return error

    def checkout_default_branch(self) -> GitRunReport:
        """
        :return GitRunReport: Checkout report
        """
        branch = self.default_branch
        if self.refs.current == branch:
            return GitRunReport()

        _, error = self.run_git_command("checkout", branch)
        self.clear_cached_state()
        if error.has_problems:
            return GitRunReport(error).add(problem="<can't checkout default branch")

        return GitRunReport(progress=f"checked out {branch}")

    def pull(self) -> GitRunReport:
        """Pull from tracked remote"""
        report = self.report(bare=True)
        if report.has_problems:
            return report.cant_pull()

        status = self.status
        if status.modified:
            return GitRunReport().cant_pull("pending changes")

        if status.report.has_problems:
            status.report.add(problem="<can't pull")
            return status.report

        refs = self.refs
        if not refs.current:
            return GitRunReport(problem="no remote branch")

        if refs.detached:
            # Untracked HEAD
            output, error = self.run_git_command("checkout", self.default_branch)
            self.clear_cached_state()
            if error.has_problems:
                return error

        output, error = self.run_git_command("pull", "--rebase")
        self.clear_cached_state()

        if error.has_problems:
            if "following untracked" in error:
                return GitRunReport().cant_pull("untracked files would be overwritten")

            if "Repository not found" in error:
                return GitRunReport().cant_pull("repository not found")

            return error.cant_pull()

        if "up to date" in output or "up-to-date" in output:
            return GitRunReport(progress="")

        if "Fast-forward" in output:
            return GitRunReport(progress="pulled successfully")

        # Shouldn't be reached
        LOG.debug("Check pull --rebase output: %s, error: %s", output, error)
        lines = []
        if output:
            lines.extend(s.strip() for s in output.strip().split("\n") if s.strip())

        lines.append(error.representation(progress=False, note=False).strip())
        output = lines[0] if lines else "no output"
        return GitRunReport(note=f"pull may have been unsuccessful ({output})")

    @property
    def age(self) -> int | None:
        """
        :return int|None: Elapsed time in seconds since last fetch
        """
        for name in FETCH_AGE_FILES:
            try:
                last_fetch = (self.path / ".git" / name).stat().st_mtime
                return int(time.time() - last_fetch)

            except OSError:
                pass

    @cached_property
    def default_branch(self) -> str:
        """
        :param mgit.git.GitDir git: Checkout model
        :return str|None: Default branch name
        """
        refs = self.refs
        branch = refs.default_branches.get("origin")
        if branch:
            return branch

        origin_branches = refs.by_remote.get("origin", set())
        for candidate in ("main", "master"):
            if candidate in refs.local or candidate in origin_branches:
                return candidate

        return "main"

    @cached_property
    def status(self) -> GitStatus:
        """
        :return GitStatus: Parsed info from 'git status --porcelain=v2 --branch'
        """
        return GitStatus(self)

    @cached_property
    def refs(self) -> GitRefs:
        return GitRefs.load(self)

    @cached_property
    def orphan_branches(self) -> list[str]:
        """
        :return list(str): Local branch names that were deleted on their corresponding remote
        """
        result = []
        refs = self.refs
        for name in sorted(refs.local):
            upstream = refs.upstreams.get(name)
            if not upstream or not refs.has_remote_branch(upstream.remote, upstream.branch):
                result.append(name)

        return result

    def is_protected_branch(self, name: str) -> bool:
        """
        :param str name: Local branch name
        :return bool: True if branch should not be cleaned or reported as orphaned
        """
        return bool(name and (name == self.default_branch or name in self.refs.default_branches.values()))

    def _default_ref_for_remote(self, remote: str, refs: GitRefs | None = None) -> str | None:
        """
        :param str remote: Remote name
        :return str|None: Remote ref for the remote's default branch, if known locally
        """
        refs = refs or self.refs
        remote_branches = refs.by_remote.get(remote)
        if not remote_branches:
            return None

        candidates = [refs.default_branches.get(remote), self.default_branch, "main", "master"]
        for branch in candidates:
            if branch and branch in remote_branches:
                return f"{remote}/{branch}"

        return None

    @cached_property
    def cleanable_base_ref(self) -> str | None:
        """
        :return str|None: Ref that cleanup candidates must already be merged into
        """
        refs = self.refs
        if refs.has_remote("origin"):
            remote_ref = self._default_ref_for_remote("origin", refs=refs)
            if remote_ref:
                return remote_ref

        if self.default_branch in refs.local:
            return self.default_branch

        return None

    def is_ancestor(self, ref: str, target_ref: str) -> bool:
        """
        :param str ref: Candidate ref
        :param str target_ref: Ref that should contain the candidate
        :return bool: True if 'ref' is an ancestor of 'target_ref'
        """
        if not ref or not target_ref:
            return False

        _, error = self.run_git_command("merge-base", "--is-ancestor", ref, target_ref)
        return not error.has_problems

    def tree_id(self, ref: str) -> str | None:
        """
        :param str ref: Ref to inspect
        :return str|None: Tree object id for 'ref'
        """
        output, error = self.run_git_command("rev-parse", f"{ref}^{{tree}}")
        if error.has_problems:
            return None

        return output.strip() or None

    def merge_is_noop(self, ref: str, target_ref: str) -> bool:
        """
        :param str ref: Candidate ref
        :param str target_ref: Ref that should already contain the candidate content
        :return bool: True if merging 'ref' into 'target_ref' would leave 'target_ref' unchanged
        """
        target_tree = self.tree_id(target_ref)
        if not target_tree:
            return False

        output, error = self.run_git_command("merge-tree", "--write-tree", "--no-messages", target_ref, ref)
        if error.has_problems:
            return False

        trees = [line.strip() for line in output.splitlines() if line.strip()]
        return len(trees) == 1 and trees[0] == target_tree

    def is_cleanable_merged(self, ref: str, target_ref: str) -> bool:
        """
        :param str ref: Candidate ref
        :param str target_ref: Ref that should already contain the candidate
        :return bool: True if 'ref' is safely contained in 'target_ref'
        """
        if not ref or not target_ref:
            return False

        return self.is_ancestor(ref, target_ref) or self.merge_is_noop(ref, target_ref)

    def is_cleanable_local_branch(self, name: str, include_current=False) -> bool:
        """
        :param str name: Local branch name
        :param bool include_current: If True, allow checking the current branch
        :return bool: True if local branch is safe to clean
        """
        base_ref = self.cleanable_base_ref
        refs = self.refs
        return bool(
            base_ref
            and name
            and not self.is_protected_branch(name)
            and (include_current or name != refs.current)
            and self.is_cleanable_merged(name, base_ref)
        )

    @cached_property
    def local_cleanable_branches(self) -> set[str]:
        """
        :return set: Local branches that can be cleaned
        """
        return {name for name in self.refs.local if self.is_cleanable_local_branch(name)}

    def stale_tracked_local_branches(self) -> list[str]:
        """Local branches whose tracked remote branch is gone"""
        result = []
        refs = self.refs
        for branch in sorted(self.local_cleanable_branches):
            if refs.upstream_gone(branch):
                result.append(branch)

        return result


class GitStatus:
    """Currently modified files"""

    def __init__(self, parent: GitDir):
        self._parent = parent
        self._lines = []
        self.head = ""
        self.upstream = ""
        self.ahead = 0
        self.behind = 0
        self.modified = []
        self.untracked = []
        self.report = GitRunReport()
        self.reload()

    @property
    def freshness(self) -> str:
        """Short freshness overview"""
        result = []
        if self.report._problem:
            result.append(output.problem(" ".join(self.report._problem)))

        if self.modified:
            result.append(output.problem(runez.plural(self.modified, "diff")))

        if self.untracked:
            result.append(output.warning(f"{len(self.untracked)} untracked"))

        if self.report._note:
            result.append(output.note(" ".join(self.report._note)))

        if not self.report._problem and not self.report._note and self._parent.age is not None:
            result.append(output.ok("up to date"))

        return ", ".join(result)

    @property
    def has_pending_changes(self) -> bool:
        return bool(self.modified or self.untracked)

    def pending_changes_report(self) -> GitRunReport:
        report = GitRunReport(problem="<can't groom").add(problem="pending changes")
        if self.modified:
            report.add(note=runez.plural(self.modified, "diff"))

        if self.untracked:
            report.add(note=f"{len(self.untracked)} untracked")

        return report

    def reload(self):
        self._lines = []
        self.head = ""
        self.upstream = ""
        self.ahead = 0
        self.behind = 0
        self.modified = []
        self.untracked = []
        self.report = GitRunReport()

        output, error = self._parent.run_git_command("status", "--porcelain=v2", "--branch")
        if error.has_problems:
            LOG.debug("Could not inspect git status: [%s]", error.representation())

        self._lines = [line for line in output.splitlines() if line.strip()]
        for line in self._lines:
            self._process_line(line)

        self._add_ref_report()

    def _process_line(self, line):
        if line.startswith("# "):
            self._process_branch_header(line[2:])
            return

        prefix = line[0]
        if prefix == "?":
            self.untracked.append(f"?? {line[2:]}")
            return

        if prefix == "1":
            self._add_modified(line, maxsplit=8)
            return

        if prefix == "2":
            self._add_modified(line, maxsplit=9)
            return

        if prefix == "u":
            self._add_modified(line, maxsplit=10)

    def _process_branch_header(self, line: str) -> None:
        key, _, value = line.partition(" ")
        if key == "branch.head":
            self.head = value
            if value == "(detached)":
                self.report.add(note="HEAD detached")

        elif key == "branch.upstream":
            self.upstream = value

        elif key == "branch.ab":
            ahead, behind = _ahead_behind(value)
            if ahead:
                self.ahead = ahead
                self.report.add(problem=f"ahead {ahead}")

            if behind:
                self.behind = behind
                self.report.add(note=f"behind {behind}")

    def _add_modified(self, line: str, maxsplit: int) -> None:
        fields = line.split(" ", maxsplit)
        if len(fields) <= maxsplit:
            LOG.warning("Unrecognised git status line: '%s'", line)
            return

        state = fields[1].replace(".", " ")
        path = fields[-1].split("\t", 1)[0]
        self.modified.append(f"{state} {path}")

    def _add_ref_report(self) -> None:
        refs = self._parent.refs
        current = refs.current
        if current and refs.upstream_gone(current):
            self.report.add(problem="remote branch gone")


def _add_messages(target: list[str], messages: str | list[str] | None):
    if messages:
        if not isinstance(messages, list):
            messages = [messages]

        for message in messages:
            if message not in target:
                target.append(message)


def _add_sorted(result, target, color, n, max_chars) -> int:
    """
    :param list(str) result: Where to accumulate sorted report
    :param list(str) target: Target to sort, respecting '<' and '>' prefixing
    :param color: Optional color to use
    :param int n: How many chars were consumed so far
    :param int|None max_chars: Maximum number of characters to yield
    :return int: Number of chars accumulated
    """
    if max_chars and n > max_chars:
        # We already reached limit
        return n

    items = []
    for message in (s.lstrip("<>") for i, s in sorted(enumerate(target), key=_report_sorter)):
        size = len(message)
        if max_chars:
            remaining = max_chars - n
            if remaining < size:
                items.append(message[:remaining])
                n += size
                break

        n += size
        items.append(message)

    result.extend(color(s) for s in items)
    return n


def _report_sorter(enum):
    """
    :param tuple(int, str) enum: Tuple from enumerate()
    :return int: Value to use for sorting messages in this report
    """
    _, message = enum
    if message[0] == "<":
        return -enum[0]  # '<' makes message sort towards front, but keeping order with other such prefixed messages

    if message[0] == ">":
        return 1000000 + enum[0]  # '>' makes message sort towards end

    return enum[0]  # Non-prefixed message stay where they were
