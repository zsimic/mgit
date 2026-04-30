from __future__ import annotations

import collections
import logging
import re
import subprocess
import time
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import runez

from mgit import output

LOG = logging.getLogger(__name__)
FETCH_AGE_FILES = ("FETCH_HEAD", "HEAD")
FRESHNESS_THRESHOLD = 12 * runez.date.SECONDS_IN_ONE_HOUR
BRANCH_INVALID_CHARS = "~^: \t\\"
GIT_ERROR_PREFIXES = {"git", "error", "fatal"}

RE_GITHUB_SSH = re.compile(r"^git@([^:]+):(\w+)/([^/]+)$")
RE_BRANCH_STATUS = re.compile(r"^## (.+)\.\.\.(([^/]+)/)?([^ ]+)\s*(\[(.+)])?$")


def is_valid_branch_name(name):
    """
    :param str|None name: Branch name to validate
    :return bool: True if branch name appears valid, as per https://wincent.com/wiki/Legal_Git_branch_names
    """
    if not name or name[0] == "." or ".." in name or name.endswith(("/", ".lock")):
        return False

    return not any(ord(char) < 32 or char in BRANCH_INVALID_CHARS for char in name)


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

    def __init__(self, *args, **kwargs):
        self._progress = []
        self._note = []
        self._problem = []
        self.add(*args, **kwargs)

    def __repr__(self):
        return f"{len(self._problem)} problems, {len(self._progress)} progress, {len(self._note)} notes"

    def __contains__(self, text):
        """
        :param str text: Text to look up
        :return bool: True if 'text' is mentioned in one of the messages in self._problem
        """
        return bool(text) and any(text in problem for problem in self._problem)

    @classmethod
    def not_git(cls):
        return GitRunReport(problem="<not a git checkout")

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

    def _add(self, target, items):
        """
        :param list target: Where to add 'items'
        :param items: items to add
        """
        if not items:
            return

        if isinstance(items, (list, tuple)):
            for item in items:
                self._add(target, item)

        elif items not in target:
            target.append(items)

    def cumulate(self, other):
        """
        :param GitRunReport other: Cumulate 'other' with current report
        :return GitRunReport: Returns self
        """
        if isinstance(other, GitRunReport):
            self._add(self._progress, other._progress)
            self._add(self._note, other._note)
            self._add(self._problem, other._problem)

        return self

    def add(self, *args, **kwargs):
        """
        :param args: Optional, other reports to cumulate
        :param kwargs: Optional, attributes to add
        :return GitRunReport: Returns self
        """
        for item in args:
            self.cumulate(item)

        for key, value in kwargs.items():
            attribute_name = f"_{key}"
            target = getattr(self, attribute_name, None)
            if target is None:
                raise Exception(f"Internal error: invalid GitRunReport target '{key}'")

            if isinstance(value, (list, tuple)):
                for item in value:
                    self.add(**{key: item})

            elif isinstance(value, GitRunReport):
                self._add(target, getattr(value, attribute_name))

            else:
                self._add(target, value)

        return self


class GitURL:
    """Parse and extract meaningful info from a git repo url"""

    def __init__(self):
        self.url = None
        self.protocol = None
        self.hostname = None
        self.relative_path = None
        self.username = None
        self.name = None
        self.repo = None

    def __repr__(self):
        return self.url or ""

    def _set_name(self, basename):
        """
        :param str|None basename: Set 'self.name' from 'basename' of url
        """
        if basename and basename.endswith(".git"):
            basename = basename[:-4]

        self.name = basename or "unknown"

    def _set_repo(self, dirname):
        """
        :param str|None dirname: Set 'self.repo' from 'dirname' of url
        """
        if dirname and "/" in dirname:
            dirname = PurePosixPath(dirname).name

        self.repo = dirname or "unknown"

    def set(self, url):
        """
        :param str url: Set fields of this object, extracted from git repo 'url'
        """
        self.url = url or ""
        if not url:
            self.protocol = "unknown"
            self.hostname = "unknown"
            self.relative_path = ""
            self.username = None
            self._set_name(None)
            self._set_repo(None)
            return

        if url.startswith("git@"):
            m = RE_GITHUB_SSH.match(url)
            if m:
                self.protocol = "ssh"
                self.hostname = m.group(1) or "unknown"
                self.relative_path = f"{m.group(2)}/{m.group(3)}"
                self.username = "git"
                self._set_name(m.group(3))
                self._set_repo(m.group(2))
                return
            url = f"ssh://{url}"

        p = urlparse(url)
        self.protocol = p.scheme or "file"
        self.hostname = p.hostname or "local"
        self.relative_path = p.path.rstrip("/")
        self.username = p.username
        url_path = PurePosixPath(self.relative_path)
        parent = "" if url_path.parent == PurePosixPath(".") else str(url_path.parent)
        self._set_name(url_path.name)
        self._set_repo(parent)


class GitDir:
    """Model a local git repo"""

    def __init__(self, path: Path):
        """
        :param Path path: Path to local repo
        """
        self.path = path
        self.folder_exists = self.path.exists()
        self.is_git_checkout = self.folder_exists and (self.path / ".git").is_dir()
        self.remote_info = None

    def __repr__(self):
        if not self.is_git_checkout:
            return f"! {self.path}"

        return str(self.path)

    def report(self, bare=False, inspect_remotes=False) -> GitRunReport:
        """
        :param bool bare: Bare report only
        :param bool inspect_remotes: If True, report on which remote branches are cleanable
        :return GitRunReport: General report on current checkout state
        """
        if not self.is_git_checkout:
            if self.remote_info:
                return GitRunReport(problem="not cloned yet")

            return GitRunReport.not_git()

        result = GitRunReport()

        if not self.config.remotes:
            result.add(problem="no remotes")

        if bare:
            return result

        age = self.age
        if age is not None and age > FRESHNESS_THRESHOLD:
            result.add(note=f"last fetch {runez.represented_duration(age)} ago")

        orphan_branches = self.orphan_branches
        if self.branches.current in orphan_branches:
            # Current is no more on its remote (should possibly checkout another branch and cleanup, or push)
            orphan_branches = orphan_branches[:]
            orphan_branches.remove(self.branches.current)
            result.add(note=f"current branch '{self.branches.current}' is orphaned")

        cleanable = sorted(self.local_cleanable_branches)
        if len(cleanable) == 1:
            result.add(note=f"local branch '{cleanable[0]}' can be pruned")

        elif cleanable:
            result.add(note=f"{runez.plural(cleanable, 'local branch')} can be pruned")

        result.add(self.branches.report)

        if inspect_remotes and self.remote_cleanable_branches:
            if len(self.remote_cleanable_branches) == 1:
                cleanable = f"'{next(iter(self.remote_cleanable_branches))}'"

            else:
                cleanable = runez.plural(self.remote_cleanable_branches, "remote branch")

            result.add(note=f"{cleanable} can be cleaned")

        return result

    def _git_command(self, args) -> tuple[list[str], str]:
        """
        :param list|tuple args: Git command + args to use
        :return list, str: Full git invocation + human friendly representation
        """
        cmd = ["git"]
        represented_args = [str(arg) for arg in args]
        joined_args = " ".join(represented_args)
        if args and args[0] == "clone":
            args_represented = f"git {joined_args}"

        else:
            args_represented = f"git -C {runez.short(self.path)} {joined_args}"
            cmd.extend(["-C", str(self.path)])

        cmd.extend(represented_args)
        return cmd, args_represented

    def run_git_command(self, *args) -> tuple[str, GitRunReport]:
        """
        :param args: Execute git command with provided args
        :return str, GitRunReport: Output from git command + report on eventual error
        """
        cmd, pretty_args = self._git_command(args)
        LOG.debug("Running: %s", pretty_args)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)  # noqa: S603
        output, error = proc.communicate()
        if proc.returncode == 0:
            return output, GitRunReport()

        if not error:
            return output, GitRunReport(problem=f"git exited with code {proc.returncode}")

        return output, GitRunReport(problem=shortened_message(error))

    def reset_cached_properties(self):
        """Reset cached properties that may have changed after a fetch or pull"""
        runez.cached_property.reset(self)

    def fetch(self, age: int | None = 30) -> GitRunReport:
        """
        :param int|None age: Fetch if age is older than specified number of seconds, use None to fetch unconditionally
        :return GitRunReport:
        """
        if not self.is_git_checkout:
            return GitRunReport.not_git()

        if age is not None:
            current_age = self.age
            if current_age is not None and current_age <= age:
                return GitRunReport()

        _, error = self.run_git_command("fetch", "--all", "--prune")
        self.reset_cached_properties()
        return error

    def pull(self) -> GitRunReport:
        """Pull from tracked remote"""
        if not self.is_git_checkout:
            return GitRunReport.not_git().cant_pull()

        report = self.report(bare=True)
        if report.has_problems:
            return report.cant_pull()

        if self.status.modified:
            return GitRunReport().cant_pull("pending changes")

        if self.status.report.has_problems:
            return GitRunReport(problem=self.status.report).cant_pull()

        if not self.branches.current:
            return GitRunReport(problem="no remote branch")

        if self.branches.current == "HEAD" and self.branches.current in self.orphan_branches:
            # Untracked HEAD
            output, error = self.run_git_command("checkout", self.default_branch)
            if error.has_problems:
                self.reset_cached_properties()
                return error

        output, error = self.run_git_command("pull", "--rebase")
        self.reset_cached_properties()

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

    def clone(self, url) -> GitRunReport:
        if self.folder_exists:
            return GitRunReport(problem="folder already exists, can't clone")

        _, error = self.run_git_command("clone", url, self.path)
        self.folder_exists = self.path.exists()
        self.is_git_checkout = self.folder_exists and (self.path / ".git").is_dir()
        self.reset_cached_properties()

        if error.has_problems:
            return error.add(problem="<can't clone")

        return GitRunReport(progress="cloned successfully")

    @runez.cached_property
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

    @runez.cached_property
    def default_branch(self) -> str:
        """
        :param mgit.git.GitDir git: Checkout model
        :return str|None: Default branch name
        """
        branch = self.branches.default_branches.get("origin")
        if branch:
            return branch

        origin_branches = self.branches.by_remote.get("origin", set())
        for candidate in ("main", "master"):
            if candidate in self.branches.local or candidate in origin_branches:
                return candidate

        return "main"

    @runez.cached_property
    def status(self) -> GitStatus:
        """
        :return GitStatus: Parsed info from 'git status --porcelain --branch'
        """
        return GitStatus(self)

    @runez.cached_property
    def config(self) -> GitConfig:
        """
        :return GitConfig: Parsed info from 'git config --list'
        """
        return GitConfig(self)

    @runez.cached_property
    def branches(self) -> GitBranches:
        """
        :return GitConfig: Parsed info from 'git branch --list --all'
        """
        return GitBranches(self)

    @runez.cached_property
    def orphan_branches(self) -> list[str]:
        """
        :return list(str): Local branch names that were deleted on their corresponding remote
        """
        result = []
        for name in self.branches.local:
            remote = self.config.tracking_remote.get(name)
            if not remote or remote not in self.branches.by_remote or name not in self.branches.by_remote[remote]:
                result.append(name)

        return result

    @runez.cached_property
    def special_branches(self) -> set[str]:
        result = set(self.branches.default_branches.values())
        result.add("HEAD")
        result.add("main")
        result.add("master")
        return result

    def _default_ref_for_remote(self, remote: str) -> str | None:
        """
        :param str remote: Remote name
        :return str|None: Remote ref for the remote's default branch, if known locally
        """
        remote_branches = self.branches.by_remote.get(remote)
        if not remote_branches:
            return None

        candidates = [self.branches.default_branches.get(remote), self.default_branch, "main", "master"]
        for branch in candidates:
            if branch and branch in remote_branches:
                return f"{remote}/{branch}"

        return None

    @runez.cached_property
    def cleanable_base_ref(self) -> str | None:
        """
        :return str|None: Ref that cleanup candidates must already be merged into
        """
        if "origin" in self.config.remotes:
            remote_ref = self._default_ref_for_remote("origin")
            if remote_ref:
                return remote_ref

        if self.default_branch in self.branches.local:
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
        return bool(
            base_ref
            and name
            and name not in self.special_branches
            and (include_current or name != self.branches.current)
            and self.is_cleanable_merged(name, base_ref)
        )

    @runez.cached_property
    def local_cleanable_branches(self) -> set[str]:
        """
        :return set: Local branches that can be cleaned
        """
        return {name for name in self.branches.local if self.is_cleanable_local_branch(name)}

    @runez.cached_property
    def remote_cleanable_branches(self) -> set[str]:
        """
        :return set: Remote branches that can be cleaned
        """
        result = set()
        for remote, branches in self.branches.by_remote.items():
            if remote not in self.config.remotes:
                continue

            default_ref = self._default_ref_for_remote(remote)
            if not default_ref:
                continue

            for branch in branches:
                if branch in self.special_branches:
                    continue

                ref = f"{remote}/{branch}"
                if ref != default_ref and self.is_cleanable_merged(ref, default_ref):
                    result.add(ref)

        return result


class GitAspect:
    """Common ancestor for info gathered from git"""

    _command = ""

    def __init__(self, parent: GitDir, auto_load=True):
        self._parent = parent
        self._lines = None  # Lines from output of last command run, for troubleshooting
        if auto_load:
            self.reload()

    def __repr__(self):
        return self._command or self.__class__.__name__

    def reload(self):
        for k in self.__class__.__dict__:
            if k.startswith("_"):
                continue

            v = getattr(self.__class__, k, None)
            if v is None or isinstance(v, (property, runez.cached_property)) or callable(v):
                continue

            v = collections.defaultdict(v.default_factory) if isinstance(v, collections.defaultdict) else v.__class__()
            setattr(self, k, v)

        if not self._parent.is_git_checkout or not self._command:
            return

        output, error = self._parent.run_git_command(*self._command.split())
        if error.has_problems:
            LOG.debug("Prev git command had error output: [%s]", error.representation())

        self._lines = [line for line in output.split("\n") if line.strip()]
        for line in self._lines:
            self._process_line(line)

    def _process_line(self, line: str) -> None:
        """Process `line`"""


class GitBranches(GitAspect):
    """Branch info"""

    _command = "branch --list --all"
    _remote_prefix = "remotes/"

    def __init__(self, parent: GitDir, auto_load=True):
        self.current = ""  # Current local branch
        self.local = set()  # Local branches
        self.by_remote = collections.defaultdict(set)  # Branches by remote (usually origin and optionally upstream)
        self.default_branches: dict[str, str] = {}  # Default branch per remote
        self.report = GitRunReport()
        super().__init__(parent, auto_load=auto_load)

    @property
    def shortened_current_branch(self) -> str:
        return str(self.current or "HEAD").replace("feature/", "f/").replace("bugfix/", "b/")

    def _process_line(self, line):
        if not line or len(line) <= 3 or line[0] not in " *" or line[1] != " ":
            LOG.warning("Internal error: malformed branch --list line: %s", line)
            return

        name = line[2:]
        if name.startswith(self._remote_prefix):
            name = name[len(self._remote_prefix) :]
            default = None
            try:
                i = name.index(" -> ")
                first = name[:i]
                if first.endswith("/HEAD"):
                    default = name = name[i + 4 :]

            except ValueError:
                pass

            remote, _, name = name.partition("/")
            self.by_remote[remote].add(name)
            if default:
                self.default_branches[remote] = name

            return

        if name.startswith("("):
            name = name[1:]
            if name.endswith(")"):
                name = name[:-1]

            name, _, problem = name.partition(" ")
            self.report.add(note=f"{name} {problem}")

        self.local.add(name)
        if line[0] == "*":
            self.current = name


class GitConfig(GitAspect):
    """Remote info"""

    _command = "config --list"

    def __init__(self, parent, auto_load=True):
        self.origin = GitURL()  # URL to remote called 'origin'
        self.remotes = {}  # GitURL by remote name map
        self.tracking_remote = {}  # Remotes that each local branch is tracking
        self.content = {}
        super().__init__(parent, auto_load=auto_load)

    @runez.cached_property
    def repo_name(self) -> str | None:
        """
        :return str: Most significant repository name
        """
        if self.origin:
            return self.origin.name

        for r in self.remotes.values():
            return r.name

        return None

    def _process_line(self, line):
        k, _, v = line.partition("=")
        self.content[k] = v
        if k.startswith("remote."):
            if k.endswith(".url"):
                k = k[7:-4]
                url = GitURL()
                url.set(v)
                self.remotes[k] = url
                if k == "origin":
                    self.origin = url

        elif k.startswith("branch.") and k.endswith(".remote"):
            self.tracking_remote[k[7:-7]] = v


class GitStatus(GitAspect):
    """Currently modified files"""

    _command = "status --porcelain --branch"

    def __init__(self, parent, auto_load=True):
        self.modified = []
        self.untracked = []
        self.report = GitRunReport()
        super().__init__(parent, auto_load=auto_load)

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

    def _process_line(self, line):
        if line[0] == "#":
            if "..." not in line:
                return

            m = RE_BRANCH_STATUS.match(line)
            if not m:
                LOG.warning("Unrecognised git status line: '%s'", line)
                return

            text = str(m.group(6) or "")  # behind, ahead, or gone
            if not text:
                return

            for message in text.split(","):
                message = message.strip()
                if "gone" in message:
                    line = line.lower()
                    if "no commits yet" in line or "initial commit on" in line:
                        self.report.add(note="no commits yet")

                    else:
                        self.report.add(problem="remote branch gone")

                elif "ahead" in message:
                    self.report.add(problem=message)

                else:
                    self.report.add(note=message)

            return

        if line[0] == "?":
            self.untracked.append(line)
            return

        self.modified.append(line)


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
