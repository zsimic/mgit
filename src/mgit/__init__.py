"""
Manage git projects en masse
"""

import collections
import logging
import os
import re
import sys

from cached_property import cached_property

from mgit import colored
from mgit.git import GitDir, GitRunReport
from mgit.utils import Cache, pretty_path, RestWrapper


try:
    input = raw_input
except NameError:
    pass


LOG = logging.getLogger(__name__)
CACHE = Cache(os.path.expanduser("~/.cache"), 3600)


def abort(message=None):
    if message:
        sys.exit(colored.problem(message))
    sys.exit(1)


def git_parent_path(path):
    """
    :param str path: Path to search
    :return str|None: First parent of 'path' that has a .git folder, if any
    """
    if not path or len(path) <= 5:
        return None
    if os.path.isdir(os.path.join(path, ".git")):
        return path
    return git_parent_path(os.path.dirname(path))


def find_actual_path(path):
    """
    :param str|None path: Base path, if None or '.': look for first parent folder with a .git subfolder
    :return str: Actual path to use as target
    """
    if not path or path == ".":
        try:
            current_dir = os.getcwd()
            path = git_parent_path(current_dir) or current_dir
        except Exception:
            return None
    return os.path.abspath(os.path.expanduser(str(path)))


def get_target(path, **kwargs):
    """
    :param str path: Path to target
    :param dict **kwargs: Optional preferences
    """
    prefs = MgitPreferences(**kwargs)
    actual_path = find_actual_path(path)
    if not actual_path or not os.path.isdir(actual_path):
        abort("'%s' is not a directory" % pretty_path(actual_path))
    if os.path.isdir(os.path.join(actual_path, ".git")):
        return GitCheckout(actual_path, prefs=prefs)
    return ProjectDir(actual_path, prefs=prefs)


class MgitPreferences:
    """Various prefs"""

    name_size = None                                # How many chars to align names when displaying list of checkouts
    align = True                                    # Whether to align names or not
    verbose = False                                 # Show verbose output
    all = False                                     # Show all entries, including missing/invalid checkout folders
    fetch = False                                   # Auto-fetch before showing status
    pull = False                                    # Auto-pull before showing status
    inspect_remotes = False                         # Inspect remote branches to report cleanable (slower)

    def __init__(self, **kwargs):
        self.update(**kwargs)

    def __repr__(self):
        result = [self._value_representation(k) for k in sorted(self.__dict__)]
        return ' '.join(s for s in result if s is not None)

    def _value_representation(self, name):
        value = getattr(self, name, None)
        if value is None:
            return None
        if value is True:
            return name
        if value is False:
            return "!%s" % name
        return "%s=%s" % (name, value)

    def set_short(self, value):
        """
        :param bool|None value: Value from parsed click command line:
                                None (default): align, verbose for individual git checkouts, short one line otherwise
                                True (--short): everything compact
                                False (--verbose): everything verbose
        """
        self.align = value is None
        self.verbose = value is False

    def update(self, **kwargs):
        for name, value in kwargs.items():
            if hasattr(self, name):
                setattr(self, name, value)
                continue
            func = getattr(self, "set_%s" % name)
            if func:
                func(value)
                continue
            raise Exception("Internal error: add support for flag '%s'" % name)


class RemoteProjectInfo:
    """Info on a remote project"""

    forkable = True
    id = 0
    name = ""
    public = False
    scmid = ""
    slug = ""
    state = ""
    statusMessage = ""

    clone_url = ""

    def __init__(self, data):
        """
        :param dict data: Data from stash REST call
        """
        self.data = data
        for k, v in data.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.clone_url = ""
        for link in data.get("links", {}).get("clone", []):
            if link.get("name") == "ssh" or not self.clone_url:
                self.clone_url = link.get("href", self.clone_url)

    def __repr__(self):
        return "%s%s" % (self.slug, "" if self.state == "AVAILABLE" else " [%s]" % self.state)


class RemoteProject:
    """
    Hashable object representing a remote repo
    - 'type' will indicate whether it's a stash repo, or github or other
    - 'name' will correspond to project for stash, or owner for github etc
    """

    def __init__(self, url):
        """
        :param GitURL url: URL of remote repo
        """
        self.url = url
        self.name = url.repo or "unknown"

    def __repr__(self):
        return "%s/%s" % (self.type, self.name)

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        return str(self) == str(other)

    def __ne__(self, other):
        return str(self) != str(other)

    @classmethod
    def from_url(cls, url):
        if url and url.hostname:
            if "stash" in url.hostname:
                return StashProject(url)
            if "github" in url.hostname:
                return GithubProject(url)
        return UnkownProject(url)

    @property
    def type(self):
        return self.__class__.__name__.lower()[:-7]

    def projects(self, ignores):
        """
        :param Ignores ignores: Names to ignore from list
        :return dict: Projects on server hashed by their canonical name, if this is a stash server
        """
        LOG.warning("Ignoring --all option, no implementation for listing %s projects", self.type)
        return {}


class StashProject(RemoteProject):
    """Bitbucket stash repo"""

    client = None

    def projects(self, ignores):
        """
        :param Ignores ignores: Names to ignore from list
        :return dict: Projects on server hashed by their canonical name, if this is a stash server
        """
        self.client = RestWrapper("https://%s/rest/api/1.0/" % self.url.hostname, cache=CACHE)
        result = {}
        if not self.auto_configure():
            LOG.warning("No API token available for %s, can't honor --all option", self.url.hostname)
            return result
        for project in self.iterate_projects(ignores):
            result[project.slug] = project
        return result

    def iterate_projects(self, ignores, limit=1000):
        count = 0
        size = 25
        offset = 0
        while True:
            response = self.client.get("projects", self.url.repo, "repos", size=size, start=offset)
            for value in response["values"]:
                count += 1
                if not ignores.is_ignored(value["slug"]):
                    yield RemoteProjectInfo(value)
            if response["isLastPage"] or count > limit:
                return
            offset = response["nextPageStart"]

    def auto_configure(self):
        """Auto-configure access token for bitbucket"""
        if self.client.headers():
            # We already have a token, configuration is done
            return True

        if not colored.is_tty():
            # We're not on a tty, can't prompt user
            LOG.warning("Can't prompt for bitbucket token, not running with a tty")
            return False

        token = None
        while not token:
            token = input("Please paste bitbucket token from: https://%s/plugins/servlet/auth-token/user\n" % self.url.hostname)  # nosec
            if not token or len(token) > 120 or len(token) < 100:
                token = None
                print("Invalid token, you can try again")
                continue
            self.client.save_headers({"X-Auth-User": os.environ["USER"], "X-Auth-Token": token})
            sample = self.client.get("projects/ARGUS", ttl=1)  # public repo
            if not sample:
                self.client.save_headers({})
                token = None
                print("Could not validate your token, you can try again")
                continue
            if "description" in sample:
                print("Token is valid, configuration saved in %s" % pretty_path(self.client.cache_path("_headers")))
                return True
            print("Could not validate your token, you can try again: %s" % sample.get("message", "<no message>"))

        return False


class GithubProject(RemoteProject):
    """Github repo"""


class UnkownProject(RemoteProject):
    """Unknown repo"""


class GitCheckout:
    """Represents a local git checkout"""

    def __init__(self, path, parent=None, prefs=None):
        """
        :param str path: Full path to local checkout
        :param ProjectDir|None parent: Parent project dir
        :param MgitPreferences|None prefs: Optional prefs to use
        """
        # Basename of local git folder (usually matches remote repo base name)
        self.basename = os.path.basename(path)
        self.directory_exists = os.path.isdir(path)
        self.git = GitDir(path)
        self.parent = parent
        self._prefs = prefs if prefs or parent else MgitPreferences()

    def __repr__(self):
        return self.basename

    @property
    def prefs(self):
        if self.parent:
            return self.parent.prefs
        return self._prefs

    @cached_property
    def name(self):
        """
        :return str: Basename of local git folder + remote basename if it differs
        """
        if not self.git.config.repo_name or not self.git.is_git_checkout or self.basename == self.git.config.repo_name:
            return self.basename
        return "%s (%s)" % (self.basename, self.git.config.repo_name)

    @cached_property
    def origin_project(self):
        return RemoteProject.from_url(self.git.config.origin)

    @cached_property
    def aligned_name(self):
        name = self.name
        if self.parent and self.parent.prefs.name_size:
            name = ("%%%ss" % self.parent.prefs.name_size) % name
        return name

    def header(self, report=None, freshness=True):
        """
        :param GitRunReport|None report: Optional report to show (defaults to self.git.report)
        :return str: Textual representation
        """
        report = GitRunReport(report or self.git.report(inspect_remotes=self.prefs.inspect_remotes))

        result = "%s:" % self.aligned_name

        if self.git.is_git_checkout:
            branch = colored.highlight(self.git.branches.shortened_current_branch)
            n = len(self.git.branches.local)
            if n > 1:
                branch += " +%s" % (n - 1)
            result += " [%s]" % branch

            if freshness:
                freshness = self.git.status.freshness
                if freshness:
                    result += " %s" % freshness

        if not report.has_problems and self.parent and self.prefs and self.prefs.all and self.parent.predominant:
            if self.origin_project != self.parent.predominant:
                report.add(note="not part of %s" % self.parent.predominant)

        if report:
            rep = report.representation()
            if rep:
                result += "  %s" % rep

        return result

    def print_modified(self, name, items, color1=None, color2=None):
        for item in items:
            state = item[0:2]
            if color2:
                state = "%s%s" % (colored.colored(item[0], color1), colored.colored(item[1], color2))
            elif color1:
                state = colored.colored(state, color1)
            print("  %s %s" % (state, item[3:]))

    def apply(self):
        """Apply switches as specified by prefs"""
        report = GitRunReport()
        if self.prefs.pull:
            if self.prefs.all and not self.git.folder_exists:
                if self.git.remote_info and self.git.remote_info.clone_url:
                    report.add(self.git.clone(self.git.remote_info.clone_url))
                else:
                    return report.cant_pull("couldn't determine clone url")
            else:
                report.add(self.git.pull())

        elif self.prefs.fetch:
            report.add(self.git.fetch())

        if not report.has_problems:
            report.add(self.git.report(inspect_remotes=self.prefs.inspect_remotes))

        return report

    def print_status(self):
        """Show checkout status"""
        report = self.apply()
        print(self.header(report))
        if self.prefs.verbose or (not self.parent and self.prefs.align):
            if len(self.git.orphan_branches) > 1:
                print("  Orphan branches: %s" % (", ".join(self.git.orphan_branches)))
            self.print_modified("modified file", self.git.status.modified, colored.POP, colored.PROBLEM)
            self.print_modified("untracked file", self.git.status.untracked, colored.WARN)


class Ignores:
    """Feature allowing to ignore some remote repos"""

    def __init__(self, parent):
        self.parent = parent
        self.path = "ignores-%s.json" % pretty_path(parent.path).replace("/", "-").replace("~", "-").strip("-")
        self._values = None
        self._regex = None

    def __repr__(self):
        count = len(self._values) if self._values is not None else "?"
        return "%s %s" % (count, self.path)

    @property
    def values(self):
        if self._values is None:
            self._values = CACHE.get(self.path, ttl=0) or []
        return self._values

    def _normalized(self, pattern):
        if pattern.startswith("*") or pattern.startswith("+"):
            return ".%s" % pattern
        return pattern

    def save(self):
        if self._values is not None:
            self._regex = None
            CACHE.put(self._values, self.path)

    def is_ignored(self, name):
        if self._regex is None:
            values = self.values
            if values and isinstance(values, list):
                self._regex = re.compile("^(%s)$" % "|".join(values), flags=re.IGNORECASE)
            else:
                self._regex = ""
        if not self._regex:
            return False
        return self._regex.match(name)

    def clear(self):
        if self.values:
            self._regexes = None
            self._values = []
            self.save()

    def add(self, *ignores):
        """
        :param list *ignores: Values to add
        :return list: List of invalid (rejected) ignores, if any
        """
        result = []
        added = []
        for ignore in ignores:
            try:
                ignore = self._normalized(ignore)
                if ignore in self.values:
                    continue
                re.compile(ignore)
                self.values.append(ignore)
                added.append(ignore)
            except Exception:
                result.append(ignore)
        if added:
            self.save()
        return added, result

    def remove(self, *ignores):
        """
        :param list *ignores: Values to remove
        :return list: List of unknown ignores (that did not get remove), if any
        """
        result = []
        removed = []
        for ignore in ignores:
            ignore = self._normalized(ignore)
            if ignore in self.values:
                self.values.remove(ignore)
                removed.append(ignore)
            else:
                result.append(ignore)
        if removed:
            self.save()
        return removed, result


class ProjectDir:
    """Info shown for a given directory"""

    def __init__(self, path, prefs=None):
        """
        :param str path: Path to folder
        :param MgitPreferences|None prefs: Display prefs
        """
        self.path = path                                # Path to folder to examine
        self.prefs = prefs or MgitPreferences()         # Prefs on how to output result
        self.checkouts = []                             # Actual git checkouts in 'path'
        self.projects = collections.defaultdict(set)    # Seen remotes
        self.predominant = None                         # Predominant remote, if any
        self.additional = None                          # Additional projects (sorted by checkouts, descending)
        self.stash_projects = {}                        # Corresponding projects from stash, when applicable
        self.ignores = Ignores(self)
        self.scan()

    def __repr__(self):
        return os.path.basename(self.path)

    def scan(self):
        self.checkouts = []
        for fname in os.listdir(self.path):
            if fname and fname.startswith("."):
                continue
            spath = os.path.join(self.path, fname)
            if os.path.isdir(spath):
                r = GitCheckout(spath, parent=self)
                self.checkouts.append(r)
                if r.git.is_git_checkout:
                    self.projects[r.origin_project].add(r)
        self.predominant = None
        self.additional = None
        counts = [(project, len(self.projects[project])) for project in sorted(self.projects, key=lambda x: -len(self.projects[x]))]
        if counts:
            self.additional = [t[0] for t in counts]
            top, top_count = counts.pop(0)
            threshold = top_count // 2
            if not counts or all(t[1] <= threshold for t in counts):
                self.predominant = top
                self.additional = self.additional[1:]
        if not self.prefs.all or not self.predominant:
            self.stash_projects = {}
        else:
            self.stash_projects = self.predominant.projects(self.ignores)
            seen = {}
            for checkout in self.checkouts:
                if not checkout.git.is_git_checkout:
                    continue
                canonical_name = checkout.git.config.repo_name
                seen[canonical_name] = True
                checkout.git.remote_info = self.stash_projects.get(canonical_name)
            for name, project in self.stash_projects.items():
                if name in seen:
                    continue
                path = os.path.join(self.path, name)
                if os.path.isdir(path):
                    path += ".1"
                r = GitCheckout(path, parent=self)
                r.git.remote_info = project
                self.checkouts.append(r)
        self.checkouts = sorted(self.checkouts, key=lambda x: x.basename)
        if self.prefs.align and self.projects:
            self.prefs.name_size = min(36, max(len(c.name) for c in self.checkouts))
        else:
            self.prefs.name_size = None

    @cached_property
    def header(self):
        result = "%s:" % colored.note(pretty_path(self.path))

        if not self.projects:
            return "%s %s" % (result, colored.warn("no git folders"))

        if self.predominant:
            result += colored.highlight(" %s %s" % (len(self.projects[self.predominant]), self.predominant))

        else:
            result += colored.warn(" no predominant project")

        if self.additional:
            result += " (%s)" % colored.note(", ".join("+%s %s" % (len(self.projects[project]), project) for project in self.additional))

        return result

    def print_status(self):
        """Show checkout status"""
        print(self.header)
        for checkout in self.checkouts:
            if self.prefs.all or checkout.git.is_git_checkout:
                checkout.print_status()
