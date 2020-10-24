import collections
import logging
import os
import re
import subprocess  # nosec
import time

try:
    from urlparse import urlparse

except ImportError:
    from urllib.parse import urlparse

import runez
from cached_property import cached_property


LOG = logging.getLogger(__name__)
FETCH_AGE_FILES = ["FETCH_HEAD", "HEAD"]
FRESHNESS_THRESHOLD = 12 * runez.date.SECONDS_IN_ONE_HOUR
BRANCH_INVALID_CHARS = "~^: \t\\"
GIT_ERROR_PREFIXES = {"git", "error", "fatal"}

RE_GITHUB_SSH = re.compile(r"^git@([^:]+):(\w+)/([^/]+)$")
RE_BRANCH_STATUS = re.compile(r"^## (.+)\.\.\.(([^/]+)/)?([^ ]+)\s*(\[(.+)])?$")


def reset_cached_properties(obj, names=None):
    """
    :param obj: Object which cached properties to reset
    :param str|None names: Optional list of cached property names to reset (all properties if no 'names' given)
    """
    if not obj:
        return

    if names:
        if hasattr(names, "startswith") and names.startswith("-"):
            names = set(obj.__class__.__dict__) - set(names[1:].split())

        elif hasattr(names, "split"):
            names = names.split()

    else:
        names = obj.__class__.__dict__

    for k in names:
        v = getattr(obj.__class__, k, None)
        if isinstance(v, cached_property) and k in obj.__dict__:
            del obj.__dict__[k]


def is_valid_branch_name(name):
    """
    :param str|None name: Branch name to validate
    :return bool: True if branch name appears valid, as per https://wincent.com/wiki/Legal_Git_branch_names
    """
    if not name or name[0] == "." or ".." in name or name.endswith("/") or name.endswith(".lock"):
        return False

    for char in name:
        if ord(char) < 32 or char in BRANCH_INVALID_CHARS:
            return False

    return True


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
        return "%s problems, %s progress, %s notes" % (len(self._problem), len(self._progress), len(self._note))

    def __contains__(self, text):
        """
        :param str text: Text to look up
        :return bool: True if 'text' is mentioned in one of the messages in self._problem
        """
        if not text:
            return False

        for problem in self._problem:
            if text in problem:
                return True

        return False

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
        n = _add_sorted(result, self._problem, runez.red, 0, max_chars)

        if progress:
            n = _add_sorted(result, self._progress, runez.plain, n, max_chars)

        if note:
            _add_sorted(result, self._note, runez.purple, n, max_chars)

        result = separator.join(result)
        if len(result) > max_chars:
            result = "%s..." % (result[: max_chars - 3])

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
            attribute_name = "_%s" % key
            target = getattr(self, attribute_name, None)
            if target is None:
                raise Exception("Internal error: invalid GitRunReport target '%s'" % key)

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
            dirname = os.path.basename(dirname)

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
                self.relative_path = "%s/%s" % (m.group(2), m.group(3))
                self.username = "git"
                self._set_name(m.group(3))
                self._set_repo(m.group(2))
                return
            url = "ssh://%s" % url

        p = urlparse(url)
        self.protocol = p.scheme or "file"
        self.hostname = p.hostname or "local"
        self.relative_path = p.path.rstrip("/")
        self.username = p.username
        self._set_name(os.path.basename(self.relative_path))
        self._set_repo(os.path.dirname(self.relative_path))


class GitDir:
    """Model a local git repo"""

    def __init__(self, path):
        """
        :param str path: Path to local repo
        """
        self.path = path
        self.folder_exists = os.path.exists(path)
        self.is_git_checkout = self.folder_exists and os.path.isdir(os.path.join(path, ".git"))
        self.remote_info = None

    def __repr__(self):
        if not self.is_git_checkout:
            return "! %s" % self.path

        return self.path

    def report(self, bare=False, inspect_remotes=False):
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

        if self.age is not None and self.age > FRESHNESS_THRESHOLD:
            result.add(note="last fetch %s ago" % runez.represented_duration(self.age))

        orphan_branches = self.orphan_branches
        if self.branches.current in orphan_branches:
            # Current is no more on its remote (should possibly checkout another branch and cleanup, or push)
            orphan_branches = orphan_branches[:]
            orphan_branches.remove(self.branches.current)
            result.add(note="current branch '%s' is orphaned" % self.branches.current)

        if len(orphan_branches) == 1:
            result.add(note="local branch '%s' can be pruned" % orphan_branches[0])

        elif orphan_branches:
            result.add(note="%s can be pruned" % runez.plural(orphan_branches, "local branch"))

        result.add(self.branches.report)

        if inspect_remotes and self.remote_cleanable_branches:
            if len(self.remote_cleanable_branches) == 1:
                cleanable = "'%s'" % next(iter(self.remote_cleanable_branches))

            else:
                cleanable = runez.plural(self.remote_cleanable_branches, "remote branch")

            result.add(note="%s can be cleaned" % cleanable)

        return result

    def _git_command(self, args):
        """
        :param list|tuple args: Git command + args to use
        :return list, str: Full git invocation + human friendly representation
        """
        cmd = ["git"]
        if args and args[0] == "clone":
            args_represented = "git %s" % " ".join(args)

        else:
            args_represented = "git -C %s %s" % (runez.short(self.path), " ".join(args))
            cmd.extend(["-C", self.path])

        cmd.extend(args)
        return cmd, args_represented

    def run_raw_git_command(self, *args):
        """
        :param args: Execute git command with provided args, don't capture its output, but let it show through stdout/stderr
        :return GitRunReport: Report
        """
        cmd, pretty_args = self._git_command(args)
        pretty_args = "git %s" % " ".join(args)
        print("Running: %s" % runez.bold(pretty_args))
        proc = subprocess.Popen(cmd)  # nosec
        proc.communicate()
        if proc.returncode:
            return GitRunReport(problem="git exited with code %s" % proc.returncode)

        return GitRunReport()

    def run_git_command(self, *args):
        """
        :param args: Execute git command with provided args
        :return str, GitRunReport: Output from git command + report on eventual error
        """
        cmd, pretty_args = self._git_command(args)
        LOG.debug("Running: %s", pretty_args)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)  # nosec
        output, error = proc.communicate()
        output = runez.decode(output)
        error = runez.decode(error)
        if proc.returncode == 0:
            return output, GitRunReport()

        if not error:
            return output, GitRunReport(problem="git exited with code %s" % proc.returncode)

        return output, GitRunReport(problem=shortened_message(error))

    def fallback_branch(self):
        """
        :return str: Best branch to fallback to if we need to clean or reset
        """
        if self.branches.current not in self.orphan_branches:
            return self.branches.current

        for branch in self.branches.local:
            if branch not in self.orphan_branches:
                return branch

        return self.branches.default_branches.get("origin")

    def reset_cached_properties(self, partial=False):
        """Reset cached properties that may have changed after a fetch or pull"""
        if partial:
            reset_cached_properties(self, "-config")

        else:
            reset_cached_properties(self)

    def fetch(self, age=30):
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
        self.reset_cached_properties(partial=True)
        return error

    def pull(self):
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
            branch = self.fallback_branch()
            if not branch:
                return GitRunReport(problem="can't determine fallback branch")

            output, error = self.run_git_command("checkout", branch)
            if error.has_problems:
                self.reset_cached_properties(partial=True)
                return error

        output, error = self.run_git_command("pull", "--rebase")
        self.reset_cached_properties(partial=True)

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
        return GitRunReport(note="pull may have been unsuccessful (%s)" % output)

    def clone(self, url):
        if self.folder_exists:
            return GitRunReport(problem="folder already exists, can't clone")

        output, error = self.run_git_command("clone", url, self.path)
        self.folder_exists = os.path.exists(self.path)
        self.is_git_checkout = self.folder_exists and os.path.isdir(os.path.join(self.path, ".git"))
        self.reset_cached_properties()

        if error.has_problems:
            return error.add(problem="<can't clone")

        return GitRunReport(progress="cloned successfully")

    @cached_property
    def age(self):
        """
        :return int|None: Elapsed time in seconds since last fetch
        """
        for name in FETCH_AGE_FILES:
            try:
                last_fetch = os.path.getmtime(os.path.join(os.path.join(self.path, ".git"), name))
                return int(time.time() - last_fetch)

            except OSError:
                pass

    @cached_property
    def status(self):
        """
        :return GitStatus: Parsed info from 'git status --porcelain --branch'
        """
        return GitStatus(self)

    @cached_property
    def config(self):
        """
        :return GitConfig: Parsed info from 'git config --list'
        """
        return GitConfig(self)

    @cached_property
    def branches(self):
        """
        :return GitConfig: Parsed info from 'git branch --list --all'
        """
        return GitBranches(self)

    @cached_property
    def orphan_branches(self):
        """
        :return list(str): Local branch names that were deleted on their corresponding remote
        """
        result = []
        for name in self.branches.local:
            remote = self.config.tracking_remote.get(name)
            if not remote or remote not in self.branches.by_remote or name not in self.branches.by_remote[remote]:
                result.append(name)

        return result

    @cached_property
    def special_branches(self):
        result = set(self.branches.default_branches.values())
        result.add("HEAD")
        result.add("master")
        result.add("test")
        result.add("prod")
        return result

    @cached_property
    def local_cleanable_branches(self):
        """
        :return set: Local branches that can be cleaned
        """
        result = set(name for name in self.orphan_branches if name not in self.special_branches)
        for branch in self.remote_cleanable_branches:
            remote, _, name = branch.partition("/")
            tracking = self.config.tracking_remote.get(name)
            if tracking == remote:
                result.add(name)

        return result

    @cached_property
    def remote_cleanable_branches(self):
        """
        :return set: Remote branches that can be cleaned
        """
        result = set()
        aspect = GitBranches(self, auto_load=False)
        aspect._command = "branch --list --remote --merged"
        aspect._remote_prefix = ""
        default = self.branches.default_branches.get("origin")
        if default:
            aspect._command += " %s" % default

        aspect.reload()
        for remote, branches in aspect.by_remote.items():
            url = self.config.remotes.get(remote)
            if not url or url.protocol != "ssh":
                continue

            result.update(["%s/%s" % (remote, branch) for branch in branches if branch not in self.special_branches])

        return result


class GitAspect:
    """Common ancestor for info gathered from git"""

    _command = None

    def __init__(self, parent, auto_load=True):
        self._parent = parent
        self._lines = None  # Lines from output of last command run, for troubleshooting
        if auto_load:
            self.reload()

    def __repr__(self):
        return self._command

    def reload(self):
        for k in self.__class__.__dict__:
            if k.startswith("_"):
                continue

            v = getattr(self.__class__, k, None)
            if v is None or isinstance(v, (property, cached_property)) or callable(v):
                continue

            if isinstance(v, collections.defaultdict):
                v = collections.defaultdict(v.default_factory)

            else:
                v = v.__class__()

            setattr(self, k, v)

        if not self._parent.is_git_checkout:
            return

        output, error = self._parent.run_git_command(*self._command.split())
        if error.has_problems:
            LOG.debug("Prev git command had error output: [%s]", error.representation())

        self._lines = [line for line in output.split("\n") if line.strip()]
        for line in self._lines:
            self._process_line(line)

    def _process_line(self, line):
        raise Exception("Not implemented")


class GitBranches(GitAspect):
    """Branch info"""

    _command = 'branch --list --all'
    _remote_prefix = 'remotes/'

    current = ''                                    # Current local branch
    local = set()                                   # Local branches
    by_remote = collections.defaultdict(set)        # Branches by remote (usually origin and optionally upstream)
    default_branches = {}                           # Default branch per remote
    report = GitRunReport()

    @property
    def shortened_current_branch(self):
        return str(self.current or 'HEAD').replace('feature/', 'f/').replace('bugfix/', 'b/')

    def _process_line(self, line):
        if not line or len(line) <= 3 or line[0] not in ' *' or line[1] != ' ':
            LOG.warning("Internal error: malformed branch --list line: %s", line)
            return

        name = line[2:]
        if name.startswith(self._remote_prefix):
            name = name[len(self._remote_prefix):]
            default = None
            try:
                i = name.index(' -> ')
                first = name[:i]
                if first.endswith('/HEAD'):
                    default = name = name[i + 4:]

            except ValueError:
                pass

            remote, _, name = name.partition('/')
            self.by_remote[remote].add(name)
            if default:
                self.default_branches[remote] = name

            return

        if name.startswith('('):
            name = name[1:]
            if name.endswith(')'):
                name = name[:-1]

            name, _, problem = name.partition(' ')
            self.report.add(note='%s %s' % (name, problem))

        self.local.add(name)
        if line[0] == '*':
            self.current = name


class GitConfig(GitAspect):
    """Remote info"""

    _command = 'config --list'
    origin = GitURL()                           # URL to remote called 'origin'
    remotes = {}                                # GitURL by remote name map
    tracking_remote = {}                        # Remotes that each local branch is tracking
    content = {}

    @cached_property
    def repo_name(self):
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

        elif k.startswith("branch."):
            if k.endswith(".remote"):
                self.tracking_remote[k[7:-7]] = v


class GitStatus(GitAspect):
    """Currently modified files"""

    _command = "status --porcelain --branch"

    modified = []
    untracked = []
    report = GitRunReport()

    @property
    def freshness(self):
        """Short freshness overview"""
        result = []
        if self.report._problem:
            result.append(runez.red(" ".join(self.report._problem)))

        if self.modified:
            result.append(runez.red(runez.plural(self.modified, "diff")))

        if self.untracked:
            result.append(runez.orange("%s untracked" % len(self.untracked)))

        if self.report._note:
            result.append(runez.purple(" ".join(self.report._note)))

        if not self.report._problem and not self.report._note and self._parent.age is not None:
            message = "up to date"
            if self._parent.age > FRESHNESS_THRESHOLD:
                message += "*"

            result.append(runez.teal(message))

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
    index, message = enum
    if message[0] == '<':
        return -enum[0]                 # '<' makes message sort towards front, but keeping order with other such prefixed messages

    if message[0] == '>':
        return 1000000 + enum[0]        # '>' makes message sort towards end

    return enum[0]                  # Non-prefixed message stay where they were


def _add_sorted(result, target, color, n, max_chars):
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
