from __future__ import annotations

from pathlib import Path

import runez

from mgit import output
from mgit.git import GitDir, GitRunReport


def find_actual_path(folder: Path) -> Path:
    """
    :param Path folder: Base folder, current folder requests look for first parent folder with a .git subfolder
    :return Path: Actual folder to use
    """
    folder = folder.expanduser().absolute()
    current = Path.cwd()
    if folder != current:
        return folder

    for candidate in (current, *current.parents):
        if (candidate / ".git").is_dir():
            return candidate

    return current


def print_modified(items, state_style, worktree_style=None):
    for item in items:
        state = item[0:2]
        if worktree_style:
            state = f"{state_style(item[0])}{worktree_style(item[1])}"

        elif state_style:
            state = state_style(state)

        print(f"  {state} {item[3:]}")


class GitCheckout:
    """Represents a local git checkout"""

    def __init__(self, path: Path, parent: ProjectDir | None = None):
        """
        :param Path path: Full path to local checkout
        :param ProjectDir|None parent: Parent project dir
        """
        self.path = path
        self.basename = self.path.name
        self.git = GitDir(self.path)
        self.parent = parent

    def __repr__(self):
        return self.basename

    @runez.cached_property
    def name(self):
        """
        :return str: Basename of local git folder
        """
        return self.basename

    @runez.cached_property
    def aligned_name(self):
        name = self.name
        if self.parent and self.parent.name_size:
            name = f"{name:>{self.parent.name_size}}"

        return name

    def header(self, report=None):
        """
        :param GitRunReport|None report: Optional report to show (defaults to self.git.report)
        :return str: Textual representation
        """
        report = GitRunReport(report if report is not None else self.git.report())

        result = f"{self.aligned_name}:"

        if self.git.is_git_checkout:
            branch = output.branch_current(self.git.branches.shortened_current_branch)
            n = len(self.git.branches.local)
            if n > 1:
                branch += f" +{n - 1}"

            result += f" [{branch}]"

            freshness = self.git.status.freshness
            if freshness:
                result += f" {freshness}"

        rep = report.representation()
        if rep:
            result += f"  {rep}"

        return result


class ProjectDir:
    """One requested folder, represented as zero or more git checkouts."""

    def __init__(self, path: Path):
        """
        :param Path path: Path to folder
        """
        self.path = path
        self.is_single_checkout = (self.path / ".git").is_dir()
        self.checkouts: list[GitCheckout] = []
        self.name_size: int | None = None
        self.scan()

    def __repr__(self):
        return self.path.name

    def scan(self):
        if self.is_single_checkout:
            self.checkouts = [GitCheckout(self.path, parent=self)]
            self.name_size = None
            return

        self.checkouts = [
            GitCheckout(source_path, parent=self)
            for source_path in self.path.iterdir()
            if not source_path.name.startswith(".") and source_path.is_dir() and (source_path / ".git").is_dir()
        ]
        self.checkouts = sorted(self.checkouts, key=lambda x: x.basename)
        self.name_size = min(36, max(len(c.name) for c in self.checkouts)) if len(self.checkouts) > 1 else None

    @runez.cached_property
    def header(self):
        result = f"{output.workspace_path(runez.short(self.path))}:"
        if not self.checkouts:
            return f"{result} {output.warning('no git folders')}"

        return result
