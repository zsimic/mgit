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


FRESH_FETCH_THRESHOLD = 30
FRESHNESS_THRESHOLD = 12 * runez.date.SECONDS_IN_ONE_HOUR
LOCAL_REF_PREFIX = "refs/heads/"
REMOTE_REF_PREFIX = "refs/remotes/"


class Reporter:
    """Central user-facing reporting helpers."""

    log = logging.getLogger("mgit")

    branch_default = runez.green
    branch_cleanable = runez.orange
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

    i_fresh = "✅"
    i_not_fresh = "☑️"
    i_stale = "⌛"
    i_local = "💾"
    i_remote = "☁️"
    i_cleanable = "🪦"
    i_detached = "👻"
    i_modified = "✏️"
    i_deleted = "🗑️"
    i_untracked = "🆕"

    @classmethod
    def legend(cls) -> str:
        """Explanation of status and branch symbols."""
        fresh = runez.represented_duration(FRESH_FETCH_THRESHOLD, span=1)
        stale = runez.represented_duration(FRESHNESS_THRESHOLD, span=1)
        return Reporter.joined_lines(
            f"{cls.i_fresh} repo freshly fetched (within {fresh})",
            f"{cls.i_not_fresh} repo not freshly fetched (more than {fresh} ago)",
            f"{cls.i_stale} repo fetch notably stale (more than {stale} ago)",
            f"{cls.i_local} branch present locally",
            f"{cls.i_remote} configured upstream present in fetched remote refs",
            f"{cls.i_cleanable} cleanable branch",
            f"{cls.i_detached} detached HEAD",
            f"{cls.i_modified} modified files",
            f"{cls.i_deleted} deleted files",
            f"{cls.i_untracked} new (untracked) files",
            f"[+N{cls.i_cleanable}+N] cleanable and remaining local branches",
        )


def compact_git_error(proc: subprocess.CompletedProcess[str]) -> str | None:
    """Short detail from a failed git command, suitable for a status line."""
    if not proc.returncode:
        return None

    detail = (proc.stderr or proc.stdout).strip() or f"git exited with code {proc.returncode}"
    lines = [line.strip().rstrip(".") for line in detail.splitlines() if line.strip()]
    for line in lines:
        prefix, separator, message = line.partition(":")
        if separator and prefix in ("git", "error", "fatal"):
            return message.strip()

    return lines[0]


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


@dataclass(frozen=True)
class BranchInfo:
    """Presence and cleanup proof for one displayed local branch."""

    name: str
    has_local: bool
    upstream: BranchUpstream | None = None
    has_remote: bool = False
    local_cleanup: CleanableLocalBranch | None = None
    remote_cleanup: CleanableRemoteBranch | None = None

    @property
    def cleanable(self) -> bool:
        """True if each present ref represented by this branch can be removed."""
        return bool(self.local_cleanup and (not self.has_remote or self.remote_cleanup))


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
        r = parent.run_git_command("symbolic-ref", "--quiet", "--short", "HEAD", exit_codes=(0, 1))
        self.detached = r.returncode != 0
        self.current = r.stdout.strip() if r.returncode == 0 else "HEAD"
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
    def default_branch(self) -> str:
        """Default branch name."""
        branch = self.default_branches.get("origin")
        if not branch:
            all_branches = self.local
            origin_branches = self.by_remote.get("origin")
            if origin_branches:
                all_branches = all_branches | origin_branches

            branch = next((name for name in ("main", "master") if name in all_branches), "main")

        return branch

    def is_protected_branch(self, name: str) -> bool:
        """True if branch should not be cleaned."""
        return bool(name and (name == self.default_branch or name in self.default_branches.values()))

    def cleanable_base_ref(self) -> str:
        """Ref that cleanup candidates must already be merged into."""
        base_ref = self.default_branch
        remote_branches = self.by_remote.get("origin")
        if remote_branches and base_ref in remote_branches:
            base_ref = f"origin/{base_ref}"

        return base_ref

    def represented_branch(self, name: str, *, cleanable=False) -> str:
        """Styled representation of a branch name."""
        if name == self.default_branch:
            name = Reporter.branch_default(name)

        elif cleanable:
            name = Reporter.branch_cleanable(name)

        return runez.bold(name)


class GitDir:
    """Model a local git repo"""

    def __init__(self, path: Path):
        """
        :param Path path: Path to local repo
        """
        self.path = path
        self.basename = path.name
        self.age = self._current_age()
        self._status: GitStatus | None = None
        self._refs: GitRefs | None = None
        self._branch_infos: list[BranchInfo] | None = None

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
        refs = self.lazy_refs
        status = self.lazy_status
        edits, deletes, new = status.pending_change_counts()
        report = GitRunReport(report)
        if self.age is not None and self.age > FRESHNESS_THRESHOLD:
            report.add(note=f"{Reporter.i_stale}{runez.represented_duration(self.age)}")

        other_branches = [info for info in self.branch_infos if info.name not in (refs.current, refs.default_branch)]
        cleanable = sum(info.cleanable for info in other_branches)
        remaining = len(other_branches) - cleanable
        branch_summary = Reporter.joined(cleanable and f"+{cleanable}{Reporter.i_cleanable}", remaining and f"+{remaining}", separator="")
        if branch_summary:
            branch_summary = f"[{branch_summary}]"

        return Reporter.joined(
            self.represented_current_branch(),
            branch_summary,
            status.upstream_delta(),
            edits and f"{Reporter.i_modified}{edits}",
            deletes and f"{Reporter.i_deleted}{deletes}",
            new and f"{Reporter.i_untracked}{new}",
            report,
        )

    def represented_current_branch(self) -> str:
        refs = self.lazy_refs
        branch = refs.current
        if refs.detached:
            return f"{refs.represented_branch(branch)} {Reporter.i_detached}"

        info = next((candidate for candidate in self.branch_infos if candidate.name == branch), None)
        cleanable = bool(info and info.cleanable)
        if cleanable:
            icon = Reporter.i_cleanable

        elif self.age is not None and self.age <= FRESH_FETCH_THRESHOLD:
            icon = Reporter.i_fresh

        else:
            icon = Reporter.i_not_fresh

        return f"{refs.represented_branch(branch, cleanable=cleanable)} {icon}"

    def status_details(self, indent="  ") -> str:
        result = []
        refs = self.lazy_refs
        cleanable_branches = [info for info in self.branch_infos if info.name != refs.current and info.cleanable]
        if cleanable_branches:
            names = ", ".join(refs.represented_branch(info.name, cleanable=True) for info in cleanable_branches)
            result.append(f"Cleanable branches: {names}")

        status = self.lazy_status
        result.extend(self._detail_lines(status.modified, Reporter.index_change, Reporter.worktree_change))
        result.extend(self._detail_lines(status.untracked, Reporter.untracked_change))
        return Reporter.joined_lines(result, indent=indent)

    def run_git_command(self, *args: str, exit_codes: tuple[int, ...] | None = None) -> subprocess.CompletedProcess[str]:
        """
        :param args: Execute git command with provided args
        :param exit_codes: Acceptable return codes, or None to return failures for reporting
        :return subprocess.CompletedProcess: Result from git
        """
        cmd = ["git", "-C", str(self.path), *args]
        Reporter.debug("Running: git -C %s %s", runez.short(self.path), " ".join(args))
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)  # noqa: S603
        if exit_codes is not None and proc.returncode not in exit_codes:
            detail = (proc.stderr or proc.stdout).rstrip() or f"git exited with code {proc.returncode}"
            Reporter.abort(f"git {' '.join(args)} failed:\n{detail}")

        return proc

    def checked_git_command(self, *args: str) -> str:
        """
        :param args: Execute git command with provided args
        :return str: Output from git command, aborting if git fails
        """
        proc = self.run_git_command(*args, exit_codes=(0,))
        return proc.stdout.strip()

    def checked_git_command_lines(self, *args: str) -> list[str]:
        return [line.strip() for line in self.checked_git_command(*args).splitlines() if line.strip()]

    def fetch_now(self, *, abort_on_failure=False) -> GitRunReport:
        exit_codes = (0,) if abort_on_failure else None
        proc = self.run_git_command("fetch", "--all", "--prune", exit_codes=exit_codes)
        self._status = None
        self._refs = None
        self._branch_infos = None
        if proc.returncode == 0:
            self.age = 0

        return GitRunReport(problem=compact_git_error(proc))

    def checkout_default_branch(self) -> GitRunReport:
        """
        :return GitRunReport: Checkout report
        """
        refs = self.lazy_refs
        branch = refs.default_branch
        report = GitRunReport()
        if refs.current != branch:
            self.checked_git_command("checkout", branch)
            report.add(progress=f"checked out {refs.represented_branch(branch)}")
            self._status = None
            self._refs = None
            self._branch_infos = None

        return report

    def pull(self, *, abort_on_failure=False) -> GitRunReport:
        """Pull from tracked remote"""
        refs = self.lazy_refs
        if not refs.remotes:
            return GitRunReport().cant_pull("no remotes")

        if refs.detached:
            return GitRunReport().cant_pull("HEAD detached")

        if refs.upstream_gone():
            return GitRunReport().cant_pull("remote branch gone")

        status = self.lazy_status
        if status.has_pending_changes:
            return GitRunReport().cant_pull("pending changes")

        note = status.upstream_delta() or "up-to-date"
        exit_codes = (0,) if abort_on_failure else None
        proc = self.run_git_command("pull", "--rebase", exit_codes=exit_codes)
        self._status = None
        self._refs = None
        self._branch_infos = None
        report = GitRunReport(note=f"was {note}")
        if proc.returncode:
            report.cant_pull(compact_git_error(proc))

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

    @property
    def lazy_status(self) -> GitStatus:
        """Parsed info from 'git status --porcelain=v2 --branch'"""
        if self._status is None:
            self._status = GitStatus(self)

        return self._status

    @property
    def lazy_refs(self) -> GitRefs:
        if self._refs is None:
            self._refs = GitRefs(self)

        return self._refs

    def branch_info(self, name: str) -> BranchInfo:
        """Summarize the local branch and its configured upstream."""
        refs = self.lazy_refs
        upstream = refs.upstreams.get(name)
        has_local = name in refs.local
        has_remote = bool(upstream and refs.has_remote_branch(upstream.remote, upstream.branch))
        local_cleanup = self.cleanable_local_branch(name, include_current=True) if has_local else None
        remote_cleanup = self.cleanable_remote_branch(upstream) if has_remote else None
        return BranchInfo(name, has_local, upstream, has_remote, local_cleanup, remote_cleanup)

    @property
    def branch_infos(self) -> list[BranchInfo]:
        """Local branches together with tracked remote presence and cleanup proof."""
        if self._branch_infos is None:
            self._branch_infos = [self.branch_info(name) for name in sorted(self.lazy_refs.local)]

        return self._branch_infos

    def branch_symbols(self, info: BranchInfo) -> str:
        """Compact branch presence and cleanup symbols for display."""
        refs = self.lazy_refs
        if info.name == refs.default_branch:
            return ""

        return "".join(
            (
                Reporter.i_local if info.has_local else "",
                Reporter.i_remote if info.has_remote else "",
                Reporter.i_cleanable if info.cleanable else "",
            )
        )

    def annotated_branch(self, width: int, info: BranchInfo) -> str:
        refs = self.lazy_refs
        symbols = self.branch_symbols(info)
        padding = " " * (width - len(info.name) - len(symbols))
        name = f"{refs.represented_branch(info.name, cleanable=info.cleanable)}{symbols}{padding}"
        result = ["*" if info.name == refs.current else " ", name]
        if info.name == refs.default_branch:
            result.append(Reporter.branch_default("[default]"))

        if info.name == refs.current:
            result.append("[current]")

        if info.cleanable:
            result.append(Reporter.branch_cleanable("[cleanable]"))

        return Reporter.joined(result)

    def branch_details(self, indent="") -> str:
        infos = self.branch_infos or [self.branch_info(self.lazy_refs.current)]
        width = max(len(info.name) + len(self.branch_symbols(info)) for info in infos)
        return Reporter.joined_lines((self.annotated_branch(width, info) for info in infos), indent=indent)

    def delete_local_branch(self, cleanup: CleanableLocalBranch):
        args = ["branch", "--delete", cleanup.name]
        if cleanup.force_delete:
            args.insert(2, "--force")

        self.checked_git_command(*args)
        self._refs = None
        self._branch_infos = None

    def delete_remote_branch(self, cleanup: CleanableRemoteBranch):
        branch_ref = f"refs/heads/{cleanup.branch}"
        self.checked_git_command(
            "push",
            f"--force-with-lease={branch_ref}:{cleanup.expected_oid}",
            "--delete",
            cleanup.remote,
            branch_ref,
        )
        self._refs = None
        self._branch_infos = None

    def is_ancestor(self, ref: str, target_ref: str) -> bool:
        """
        :param str ref: Candidate `ref`
        :param str target_ref: Ref that should contain the candidate
        :return bool: True if 'ref' is an ancestor of 'target_ref'
        """
        proc = self.run_git_command("merge-base", "--is-ancestor", ref, target_ref, exit_codes=(0, 1))
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
        refs = self.lazy_refs
        base_ref = refs.cleanable_base_ref()
        if not base_ref or not name or refs.is_protected_branch(name) or (not include_current and name == refs.current):
            return None

        if self.is_ancestor(name, base_ref):
            return CleanableLocalBranch(name)

        if self.merge_is_noop(name, base_ref):
            return CleanableLocalBranch(name, force_delete=True)

        return None

    def cleanable_remote_branch(self, upstream: BranchUpstream | None) -> CleanableRemoteBranch | None:
        """Return cleanup details for a safely deletable tracked origin ref."""
        refs = self.lazy_refs
        default_branch = refs.default_branch
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

    def cleanable_current_remote_branch(self) -> CleanableRemoteBranch | None:
        """Return cleanup details for the current branch's safely deletable origin ref."""
        refs = self.lazy_refs
        return self.cleanable_remote_branch(refs.upstreams.get(refs.current))


class GitStatus:
    """Currently modified files"""

    def __init__(self, parent: GitDir):
        self.ahead = 0
        self.behind = 0
        self.modified = []
        self.untracked = []
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
