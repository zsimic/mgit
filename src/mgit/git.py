from __future__ import annotations

import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from functools import cached_property
from typing import NoReturn, TYPE_CHECKING

import runez

if TYPE_CHECKING:
    from pathlib import Path


class Reporter:
    """Central user-facing reporting helpers."""

    log = logging.getLogger("mgit")

    branch_default = runez.green
    branch_orphaned = runez.orange
    problem = runez.red
    note = runez.purple
    progress = runez.plain
    index_change = runez.teal
    worktree_change = runez.red
    untracked_change = runez.orange

    @staticmethod
    def joined(*args, separator=" "):
        """Join non-false-ish display fragments."""
        return runez.joined(*args, delimiter=separator, keep_empty=None)

    @staticmethod
    def joined_lines(*args, header="", indent="", separator="\n"):
        """Join non-false-ish display lines with optional header and indentation."""
        lines = [f"{indent}{line}" for line in runez.flattened(args, keep_empty=None)]
        return Reporter.joined(header, lines, separator=separator)

    @staticmethod
    def abort(message, exit_code: int = 1) -> NoReturn:
        print(Reporter.problem(message), file=sys.stderr)
        sys.exit(exit_code)

    @staticmethod
    def abort_if(condition: object, message, exit_code: int = 1):
        if condition:
            Reporter.abort(message, exit_code=exit_code)

    @staticmethod
    def debug(message: str, *args: object):
        Reporter.log.debug(message, *args)


FRESH_FETCH_THRESHOLD = 30
FRESHNESS_THRESHOLD = 12 * runez.date.SECONDS_IN_ONE_HOUR
LOCAL_REF_PREFIX = "refs/heads/"
REMOTE_REF_PREFIX = "refs/remotes/"


def git_error_message(proc: subprocess.CompletedProcess[str]) -> str | None:
    """Short user-facing description of a failed git command."""
    if proc.returncode:
        detail = (proc.stderr or proc.stdout).strip() or f"git exited with code {proc.returncode}"
        detail = detail.strip().lower()
        if "following untracked" in detail:
            return "untracked files would be overwritten"

        if "repository not found" in detail:
            return "repository not found"

        lines = []
        prefixed = []
        for line in detail.splitlines():
            line = line.strip().strip(".")
            if line:
                p = line.partition(":")
                if p[2] and p[0] in ("git", "error", "fatal"):
                    prefixed.append(p[2].strip())

                else:
                    lines.append(line)

        return " ".join((prefixed or lines)[:2]).replace("  ", " ").strip()


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

    def __str__(self):
        return self.representation()

    def require_success(self, operation: str) -> GitRunReport:
        if self.has_problems:
            Reporter.abort(self.add(problem=f"<can't {operation}"))

        return self

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
        n = _add_sorted(result, self._problem, Reporter.problem, 0, max_chars)

        if progress:
            n = _add_sorted(result, self._progress, Reporter.progress, n, max_chars)

        if note:
            _add_sorted(result, self._note, Reporter.note, n, max_chars)

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


def git_error_report(proc: subprocess.CompletedProcess[str]) -> GitRunReport:
    """GitRunReport describing a failed git command."""
    return GitRunReport(problem=git_error_message(proc))


@dataclass
class BranchUpstream:
    """Configured upstream for a local branch."""

    remote: str
    branch: str


@dataclass(frozen=True)
class CleanableLocalBranch:
    """Local branch that is safe to delete."""

    name: str
    force_delete: bool = False


@dataclass(frozen=True)
class CleanableRemoteBranch:
    """Tracked remote branch that is safe to delete with an exact-ref lease."""

    remote: str
    branch: str
    expected_oid: str


class GitRefs:
    """Repository ref and upstream snapshot."""

    current: str
    detached: bool
    local: set[str]
    remotes: list[str]
    by_remote: dict[str, set[str]]
    default_branches: dict[str, str]
    upstreams: dict[str, BranchUpstream]

    def __init__(self, parent: GitDir):
        self.current, self.detached = parent._current_branch()
        self.local = set()
        self.remotes = parent.checked_git_command_lines("remote")
        self.by_remote = {}
        self.default_branches = {}
        self.upstreams = {}
        lines = parent.checked_git_command_lines(
            "for-each-ref",
            "--format=%(refname)%09%(upstream:remotename)%09%(upstream:remoteref)%09%(symref)",
            "refs/heads",
            "refs/remotes",
        )
        for line in lines:
            self._add_line(line)

    def _add_line(self, line: str):
        fields = (line + "\t" * 3).split("\t")
        refname, upstream_remote, upstream_ref, symref = fields[:4]
        if refname.startswith(LOCAL_REF_PREFIX):
            local_branch_name = refname[len(LOCAL_REF_PREFIX) :]
            self.local.add(local_branch_name)

            if upstream_remote and upstream_ref:
                upstream_branch = upstream_ref[len(LOCAL_REF_PREFIX) :] if upstream_ref.startswith(LOCAL_REF_PREFIX) else upstream_ref
                upstream = BranchUpstream(remote=upstream_remote, branch=upstream_branch)
                self.upstreams[local_branch_name] = upstream

        elif refname.startswith(REMOTE_REF_PREFIX):
            remote, _, branch = refname[len(REMOTE_REF_PREFIX) :].partition("/")
            if remote and branch:
                if branch == "HEAD":
                    prefix = f"{REMOTE_REF_PREFIX}{remote}/"
                    if len(symref) > len(prefix) and symref.startswith(prefix):
                        self.default_branches[remote] = symref[len(prefix) :]

                else:
                    self.by_remote.setdefault(remote, set()).add(branch)

    def has_remote_branch(self, remote: str, branch: str) -> bool:
        remote_branches = self.by_remote.get(remote)
        return bool(remote_branches and (branch in remote_branches))

    def upstream_gone(self, branch=None) -> bool:
        upstream = self.upstreams.get(branch or self.current)
        return bool(upstream and not self.has_remote_branch(upstream.remote, upstream.branch))

    @cached_property
    def orphan_branches(self) -> list[str]:
        """Local branch names that were deleted on their corresponding remote."""
        result = []
        for name in sorted(self.local):
            upstream = self.upstreams.get(name)
            if not upstream or not self.has_remote_branch(upstream.remote, upstream.branch):
                result.append(name)

        return result


class GitDir:
    """Model a local git repo"""

    def __init__(self, path: Path):
        """
        :param Path path: Path to local repo
        """
        self.path = path
        self.basename = path.name
        self.age = self._current_age()

    def _branch_annotations(self, name):
        return Reporter.joined(
            name == self.default_branch and Reporter.branch_default("[default]"),
            self.is_orphan_branch(name) and Reporter.branch_orphaned("[orphaned]"),
        )

    @staticmethod
    def _detail_lines(items, state_style, worktree_style=None) -> list[str]:
        lines = []
        for item in items:
            state = item[0:2]
            if worktree_style:
                state = f"{state_style(item[0])}{worktree_style(item[1])}"

            elif state_style:
                state = state_style(state)

            lines.append(f"{state} {item[3:]}")

        return lines

    def status_line(self, report: GitRunReport | None = None) -> str:
        refs = self.refs
        status = self.status
        edits, deletes, new = status.pending_change_counts()
        report = GitRunReport(report)
        if self.age is not None and self.age > FRESHNESS_THRESHOLD:
            report.add(note=f"⌛{runez.represented_duration(self.age)}")

        other_branches = refs.local - {refs.current, self.default_branch}
        cleanable = len(other_branches & self._local_cleanable_branches())
        remaining = len(other_branches) - cleanable
        branch_summary = Reporter.joined(cleanable and f"+{cleanable}🪦", remaining and f"+{remaining}", separator="")
        if branch_summary:
            branch_summary = f"[{branch_summary}]"

        return Reporter.joined(
            self.represented_current_branch(),
            branch_summary,
            status.upstream_delta(),
            edits and f"✏️{edits}",
            deletes and f"🗑️{deletes}",
            new and f"🆕{new}",
            report,
        )

    def represented_current_branch(self) -> str:
        refs = self.refs
        branch = refs.current
        if refs.detached:
            icon = " 👻"

        elif self.is_orphan_branch(branch):
            icon = " 🪦"

        else:
            icon = " ✅" if self.age is not None and self.age <= FRESH_FETCH_THRESHOLD else " ☑️"

        return self.represented_branch(branch) + icon

    def status_details(self, indent="  ") -> str:
        result = []
        refs = self.refs
        orphan_branches = [branch for branch in refs.orphan_branches if branch != refs.current and self.is_orphan_branch(branch)]
        if orphan_branches:
            result.append(f"Orphan branches: {', '.join(self.represented_branch(branch) for branch in orphan_branches)}")

        status = self.status
        result.extend(self._detail_lines(status.modified, Reporter.index_change, Reporter.worktree_change))
        result.extend(self._detail_lines(status.untracked, Reporter.untracked_change))
        return Reporter.joined_lines(result, indent=indent)

    def branch_details(self, indent="") -> str:
        refs = self.refs
        branches = sorted(refs.local) or [refs.current]
        width = max(len(name) for name in branches)
        result = []
        for name in branches:
            padding = " " * (width - len(name))
            line = f"{'*' if name == refs.current else ' '} {self.represented_branch(name)}{padding}"
            annotations = self._branch_annotations(name)
            if annotations:
                line += f"  {annotations}"

            result.append(line)

        return Reporter.joined_lines(result, indent=indent)

    def run_git_command(self, *args: str) -> subprocess.CompletedProcess[str]:
        """
        :param args: Execute git command with provided args
        :return subprocess.CompletedProcess: Result from git
        """
        cmd = ["git", "-C", str(self.path), *args]
        Reporter.debug("Running: git -C %s %s", runez.short(self.path), " ".join(args))
        return subprocess.run(cmd, check=False, capture_output=True, text=True)  # noqa: S603

    def checked_git_command(self, *args: str) -> str:
        """
        :param args: Execute git command with provided args
        :return str: Output from git command, aborting if git fails
        """
        proc = self.run_git_command(*args)
        Reporter.abort_if(proc.returncode, f"git {' '.join(args)} failed: {git_error_message(proc)}")
        return proc.stdout.strip()

    def checked_git_command_lines(self, *args: str) -> list[str]:
        return [line.strip() for line in self.checked_git_command(*args).splitlines() if line.strip()]

    def clear_cached_state(self):
        """Discard cached git state after a command may have changed refs or worktree state."""
        for k, v in vars(self.__class__).items():
            if isinstance(v, cached_property) and k in self.__dict__:
                self.__dict__.pop(k, None)

    def _current_branch(self) -> tuple[str, bool]:
        proc = self.run_git_command("symbolic-ref", "--quiet", "--short", "HEAD")
        if proc.returncode == 0:
            return proc.stdout.strip(), False

        Reporter.abort_if(proc.returncode != 1, f"Could not inspect git branch: {git_error_message(proc)}")
        proc = self.run_git_command("rev-parse", "--verify", "--quiet", "HEAD")
        if proc.returncode == 0 and proc.stdout.strip():
            return "HEAD", True

        Reporter.abort(f"Could not inspect git HEAD: {git_error_message(proc)}")

    def fetch_now(self) -> GitRunReport:
        proc = self.run_git_command("fetch", "--all", "--prune")
        if proc.returncode == 0:
            self.age = 0

        return git_error_report(proc)

    def checkout_default_branch(self) -> GitRunReport:
        """
        :return GitRunReport: Checkout report
        """
        branch = self.default_branch
        if self.refs.current == branch:
            return GitRunReport()

        self.checked_git_command("checkout", branch)
        self.clear_cached_state()
        return GitRunReport(progress=f"checked out {self.represented_branch(branch)}")

    def pull(self) -> GitRunReport:
        """Pull from tracked remote"""
        refs = self.refs
        if not refs.remotes:
            return GitRunReport().cant_pull("no remotes")

        if refs.detached:
            return GitRunReport().cant_pull("HEAD detached")

        status = self.status
        if status.has_pending_changes or status.report.has_problems:
            reason = "pending changes" if status.has_pending_changes else None
            return GitRunReport(status.report).cant_pull(reason)

        note = status.upstream_delta() or "up-to-date"
        proc = self.run_git_command("pull", "--rebase")
        self.clear_cached_state()
        report = GitRunReport(note=f"was {note}")
        if proc.returncode:
            report.cant_pull(git_error_message(proc))

        else:
            self.age = 0

        return report

    def _current_age(self) -> int | None:
        """Elapsed time in seconds since last fetch"""
        for name in ("FETCH_HEAD", "HEAD"):
            try:
                last_fetch = (self.path / ".git" / name).stat().st_mtime
                return int(time.time() - last_fetch)

            except OSError:
                pass

    @cached_property
    def default_branch(self) -> str:
        """Default branch name"""
        refs = self.refs
        branch = refs.default_branches.get("origin")
        if branch:
            return branch

        origin_branches = refs.by_remote.get("origin")
        if origin_branches:
            for candidate in ("main", "master"):
                if candidate in refs.local or candidate in origin_branches:
                    return candidate

        return "main"

    @cached_property
    def status(self) -> GitStatus:
        """Parsed info from 'git status --porcelain=v2 --branch'"""
        return GitStatus(self)

    @cached_property
    def refs(self) -> GitRefs:
        return GitRefs(self)

    def is_protected_branch(self, name: str) -> bool:
        """True if branch should not be cleaned or reported as orphaned"""
        return bool(name and (name == self.default_branch or name in self.refs.default_branches.values()))

    def is_orphan_branch(self, name: str) -> bool:
        """True if branch is an unprotected orphan."""
        return bool(name and name in self.refs.orphan_branches and not self.is_protected_branch(name))

    def represented_branch(self, name: str) -> str:
        """Styled representation of a branch name."""
        result = runez.bold(name)
        if name == self.default_branch:
            return runez.green(result)

        if self.is_orphan_branch(name):
            return runez.orange(result)

        return result

    def is_ancestor(self, ref: str, target_ref: str) -> bool:
        """
        :param str ref: Candidate ref
        :param str target_ref: Ref that should contain the candidate
        :return bool: True if 'ref' is an ancestor of 'target_ref'
        """
        proc = self.run_git_command("merge-base", "--is-ancestor", ref, target_ref)
        Reporter.abort_if(proc.returncode > 1, f"Could not inspect git ancestry: {git_error_message(proc)}")
        return proc.returncode == 0

    def merge_is_noop(self, ref: str, target_ref: str) -> bool:
        """
        :param str ref: Candidate `ref`
        :param str target_ref: Ref that should already contain the candidate content
        :return bool: True if merging 'ref' into `target_ref` would leave `target_ref` unchanged
        """
        target_tree = self.checked_git_command("rev-parse", f"{target_ref}^{{tree}}")
        proc = self.run_git_command("merge-tree", "--write-tree", "--no-messages", target_ref, ref)
        if proc.returncode:
            return False

        trees = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        return len(trees) == 1 and bool(target_tree) and trees[0] == target_tree

    def cleanable_local_branch(self, name: str, include_current=False) -> CleanableLocalBranch | None:
        """
        :param str name: Local branch name
        :param bool include_current: If True, allow checking the current branch
        :return CleanableLocalBranch|None: Cleanup details if local branch is safe to clean
        """
        base_ref = self._cleanable_base_ref()
        refs = self.refs
        if not base_ref or not name or self.is_protected_branch(name) or (not include_current and name == refs.current):
            return None

        if self.is_ancestor(name, base_ref):
            return CleanableLocalBranch(name)

        if self.merge_is_noop(name, base_ref):
            return CleanableLocalBranch(name, force_delete=True)

        return None

    def cleanable_current_remote_branch(self) -> CleanableRemoteBranch | None:
        """Return cleanup details for the current branch's safely deletable origin ref."""
        refs = self.refs
        upstream = refs.upstreams.get(refs.current)
        default_branch = self.default_branch
        if (
            not upstream
            or upstream.remote != "origin"
            or upstream.branch == default_branch
            or not refs.has_remote_branch(upstream.remote, upstream.branch)
            or not refs.has_remote_branch(upstream.remote, default_branch)
        ):
            return None

        branch_ref = f"{REMOTE_REF_PREFIX}{upstream.remote}/{upstream.branch}"
        base_ref = f"{REMOTE_REF_PREFIX}{upstream.remote}/{default_branch}"
        if not self.is_ancestor(branch_ref, base_ref) and not self.merge_is_noop(branch_ref, base_ref):
            return None

        expected_oid = self.checked_git_command("rev-parse", branch_ref)
        return CleanableRemoteBranch(upstream.remote, upstream.branch, expected_oid)

    def _cleanable_base_ref(self) -> str:
        """Ref that cleanup candidates must already be merged into"""
        base_ref = self.default_branch
        remote_branches = self.refs.by_remote.get("origin")
        if remote_branches and base_ref in remote_branches:
            base_ref = f"origin/{base_ref}"

        return base_ref

    def _local_cleanable_branches(self) -> set[str]:
        """Local branches that can be cleaned"""
        return {name for name in self.refs.local if self.cleanable_local_branch(name)}


class GitStatus:
    """Currently modified files"""

    def __init__(self, parent: GitDir):
        self.ahead = 0
        self.behind = 0
        self.modified = []
        self.untracked = []
        self.report = GitRunReport()
        lines = parent.checked_git_command_lines("status", "--porcelain=v2", "--branch")
        for line in lines:
            prefix = line[0]
            info = line[2:]
            if prefix == "#":
                keyword, _, value = info.partition(" ")
                if keyword == "branch.ab":
                    ab = value.partition(" ")
                    self.ahead = int(ab[0])
                    self.behind = -int(ab[2])

            elif prefix == "?":
                self.untracked.append(f" ? {info}")

            else:
                fields = info.split(" ")
                state = fields[0].replace(".", " ")
                path = fields[-1].partition("\t")[0]
                self.modified.append(f"{state} {path}")

        if parent.refs.upstream_gone():
            self.report.add(problem="remote branch gone")

    @property
    def dirty_note(self) -> str:
        """Short overview of pending changes."""
        return Reporter.joined(
            self.modified and Reporter.problem(runez.plural(self.modified, "diff")),
            self.untracked and Reporter.untracked_change(f"{len(self.untracked)} untracked"),
        )

    @property
    def has_pending_changes(self) -> bool:
        return bool(self.modified or self.untracked)

    def upstream_delta(self) -> str:
        """Short report on divergence from the upstream branch."""
        return Reporter.joined(
            self.ahead and Reporter.note(f"{self.ahead} ahead"),
            self.behind and Reporter.note(f"{self.behind} behind"),
        )

    def pending_change_counts(self) -> tuple[int, int, int]:
        edits = 0
        deletes = 0
        new = len(self.untracked)
        for item in self.modified:
            state = item[0:2]
            if "D" in state:
                deletes += 1

            elif "A" in state:
                new += 1

            else:
                edits += 1

        return edits, deletes, new

    def require_clean(self, operation: str):
        if self.has_pending_changes:
            Reporter.abort(f"can't {operation}: pending changes: {self.dirty_note}")


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
