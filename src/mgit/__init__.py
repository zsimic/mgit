from __future__ import annotations

import collections
import logging
from pathlib import Path

import runez

from mgit import output
from mgit.git import GitDir, GitRunReport

LOG = logging.getLogger(__name__)


def find_actual_path(path: Path) -> Path:
    """
    :param Path path: Base path, current folder targets look for first parent folder with a .git subfolder
    :return Path: Actual path to use as target
    """
    path = path.expanduser().absolute()
    current = Path.cwd()
    if path != current:
        return path

    for candidate in (current, *current.parents):
        if (candidate / ".git").is_dir():
            return candidate

    return current


def get_target(path: Path, fetch: bool, fetch_age: int | None, pull: bool):
    """
    :param Path path: Path to target
    """
    prefs = MgitPreferences(fetch=fetch, fetch_age=fetch_age, pull=pull)
    actual_path = find_actual_path(path)
    if not actual_path.is_dir():
        runez.abort(f"No folder '{runez.short(actual_path)}'")

    if (actual_path / ".git").is_dir():
        return GitCheckout(actual_path, prefs=prefs)

    return ProjectDir(actual_path, prefs=prefs)


def print_modified(items, state_style, worktree_style=None):
    for item in items:
        state = item[0:2]
        if worktree_style:
            state = f"{state_style(item[0])}{worktree_style(item[1])}"

        elif state_style:
            state = state_style(state)

        print(f"  {state} {item[3:]}")


class MgitPreferences:
    """Various prefs"""

    def __init__(self, name_size: int | None = None, fetch=False, fetch_age: int | None = 30, pull=False, inspect_remotes=False):
        self.name_size = name_size  # How many chars to align names when displaying list of checkouts
        self.fetch = fetch  # Auto-fetch before showing status
        self.fetch_age = fetch_age  # Auto-fetch only when older than this many seconds, None means always
        self.pull = pull  # Auto-pull before showing status
        self.inspect_remotes = inspect_remotes  # Inspect remote branches to report cleanable (slower)


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
        return f"{self.type}/{self.name}"

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

        return UnknownProject(url)

    @property
    def type(self):
        return self.__class__.__name__.lower()[:-7]

    def projects(self):
        """
        :return dict: Projects on server hashed by their canonical name, if this is a stash server
        """
        LOG.warning("Ignoring --all option, no implementation for listing %s projects", self.type)
        return {}


class StashProject(RemoteProject):
    """Bitbucket stash repo"""


class GithubProject(RemoteProject):
    """Github repo"""


class UnknownProject(RemoteProject):
    """Unknown repo"""


class GitCheckout:
    """Represents a local git checkout"""

    def __init__(self, path: Path, parent=None, prefs=None):
        """
        :param Path path: Full path to local checkout
        :param ProjectDir|None parent: Parent project dir
        :param MgitPreferences|None prefs: Optional prefs to use
        """
        # Basename of local git folder (usually matches remote repo base name)
        self.path = path
        self.basename = self.path.name
        self.directory_exists = self.path.is_dir()
        self.git = GitDir(self.path)
        self.parent = parent
        self._prefs = prefs or MgitPreferences()

    def __repr__(self):
        return self.basename

    @property
    def prefs(self):
        if self.parent:
            return self.parent.prefs

        return self._prefs

    @runez.cached_property
    def name(self):
        """
        :return str: Basename of local git folder + remote basename if it differs
        """
        return self.basename

    @runez.cached_property
    def origin_project(self):
        return RemoteProject.from_url(self.git.config.origin)

    @runez.cached_property
    def aligned_name(self):
        name = self.name
        if self.parent and self.parent.prefs.name_size:
            name = f"{name:>{self.parent.prefs.name_size}}"

        return name

    def header(self, report=None):
        """
        :param GitRunReport|None report: Optional report to show (defaults to self.git.report)
        :return str: Textual representation
        """
        report = GitRunReport(report or self.git.report(inspect_remotes=self.prefs.inspect_remotes))

        result = f"{self.aligned_name}:"

        if self.git.is_git_checkout:
            branch = output.branch(self.git.branches.shortened_current_branch)
            n = len(self.git.branches.local)
            if n > 1:
                branch += f" +{n - 1}"

            result += f" [{branch}]"

            freshness = self.git.status.freshness
            if freshness:
                result += f" {freshness}"

        if not report.has_problems and self.parent and self.parent.predominant and self.origin_project != self.parent.predominant:
            report.add(note=f"not part of {self.parent.predominant}")

        if report:
            rep = report.representation()
            if rep:
                result += f"  {rep}"

        return result

    def apply(self):
        """Apply switches as specified by prefs"""
        report = GitRunReport()
        if self.prefs.pull:
            if not self.git.folder_exists:
                if self.git.remote_info and self.git.remote_info.clone_url:
                    report.add(self.git.clone(self.git.remote_info.clone_url))

                else:
                    return report.cant_pull("couldn't determine clone url")

            else:
                report.add(self.git.pull())

        elif self.prefs.fetch:
            report.add(self.git.fetch(age=self.prefs.fetch_age))

        if not report.has_problems:
            report.add(self.git.report(inspect_remotes=self.prefs.inspect_remotes))

        return report

    def print_status(self):
        """Show checkout status"""
        report = self.apply()
        print(self.header(report))
        if not self.parent:
            if len(self.git.orphan_branches) > 1:
                orphan_branches = ", ".join(self.git.orphan_branches)
                print(f"  Orphan branches: {orphan_branches}")

            print_modified(self.git.status.modified, output.index_change, output.worktree_change)
            print_modified(self.git.status.untracked, output.untracked_change)


class ProjectDir:
    """Info shown for a given directory"""

    def __init__(self, path: Path, prefs=None):
        """
        :param Path path: Path to folder
        :param MgitPreferences|None prefs: Display prefs
        """
        self.path = path  # Path to folder to examine
        self.prefs = prefs or MgitPreferences()  # Preferences on how to output result
        self.checkouts = []  # Actual git checkouts in 'path'
        self.projects = collections.defaultdict(set)  # Seen remotes
        self.predominant = None  # Predominant remote, if any
        self.additional = None  # Additional projects (sorted by checkouts, descending)
        self.stash_projects = {}  # Corresponding projects from stash, when applicable
        self.scan()

    def __repr__(self):
        return self.path.name

    def scan(self):
        self.checkouts = []
        for source_path in self.path.iterdir():
            if source_path.name.startswith("."):
                continue

            if source_path.is_dir():
                r = GitCheckout(source_path, parent=self)
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

        if not self.predominant:
            self.stash_projects = {}

        else:
            self.stash_projects = self.predominant.projects()
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

                path = self.path / name
                if path.is_dir():
                    path = path.with_name(f"{path.name}.1")

                r = GitCheckout(path, parent=self)
                r.git.remote_info = project
                self.checkouts.append(r)

        self.checkouts = sorted(self.checkouts, key=lambda x: x.basename)
        visible = [c for c in self.checkouts if c.git.is_git_checkout]
        if self.projects and visible:
            self.prefs.name_size = min(36, max(len(c.name) for c in visible))

        else:
            self.prefs.name_size = None

    @runez.cached_property
    def header(self):
        result = f"{output.workspace_path(runez.short(self.path))}:"

        if not self.projects:
            return f"{result} {output.warning('no git folders')}"

        if self.predominant:
            result += output.workspace_primary(f" {len(self.projects[self.predominant])} {self.predominant}")

        else:
            result += output.warning(" no predominant project")

        if self.additional:
            details = ", ".join(f"+{len(self.projects[project])} {project}" for project in self.additional)
            result += f" ({output.workspace_detail(details)})"

        return result

    def print_status(self):
        """Show checkout status"""
        print(self.header)
        for checkout in self.checkouts:
            if checkout.git.is_git_checkout:
                checkout.print_status()
