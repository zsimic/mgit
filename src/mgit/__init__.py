from __future__ import annotations

from typing import TYPE_CHECKING

import runez

from mgit import output
from mgit.git import GitDir, GitRunReport

if TYPE_CHECKING:
    from pathlib import Path


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

    def header(self, report=None):
        """
        :param GitRunReport|None report: Optional report to show (defaults to self.git.report)
        :return str: Textual representation
        """
        report = GitRunReport(report if report is not None else self.git.report())

        result = self.basename
        if self.parent and self.parent.name_size:
            result = f"{result:>{self.parent.name_size}}"

        result = f"{result}:"
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

    def status_report(self, report=None) -> GitRunReport:
        report = GitRunReport(report)
        if not report.has_problems:
            report.add(self.git.report())

        return report

    def print_status(self, report=None, show_details=True):
        print(self.header(report))
        if not show_details:
            return

        if len(self.git.orphan_branches) > 1:
            orphan_branches = ", ".join(self.git.orphan_branches)
            print(f"  Orphan branches: {orphan_branches}")

        self.print_modified(self.git.status.modified, output.index_change, output.worktree_change)
        self.print_modified(self.git.status.untracked, output.untracked_change)

    @staticmethod
    def print_modified(items, state_style, worktree_style=None):
        for item in items:
            state = item[0:2]
            if worktree_style:
                state = f"{state_style(item[0])}{worktree_style(item[1])}"

            elif state_style:
                state = state_style(state)

            print(f"  {state} {item[3:]}")

    def branch_annotations(self, name):
        annotations = []
        if name == self.git.default_branch:
            annotations.append(output.branch_default("[default]"))

        if name in self.git.orphan_branches and name not in self.git.special_branches:
            annotations.append(output.branch_orphaned("[orphaned]"))

        return annotations

    def branch_lines(self):
        branches = sorted(self.git.branches.local)
        if not branches:
            return ["  no local branches"]

        width = max(len(name) for name in branches)
        lines = []
        for name in branches:
            is_current = name == self.git.branches.current
            marker = "*" if is_current else " "
            line = f"{marker} {name:<{width}}"
            if is_current:
                line = output.branch_current(line)

            annotations = self.branch_annotations(name)
            if annotations:
                line += f"  {' '.join(annotations)}"

            lines.append(line)

        return lines

    def print_branch_report(self, indent=""):
        for line in self.branch_lines():
            print(f"{indent}{line}")

    def current_branch_cleanable_report(self) -> GitRunReport:
        current = self.git.branches.current
        if current == self.git.default_branch:
            return GitRunReport(note=f"already on {self.git.default_branch} branch")

        if self.git.is_cleanable_local_branch(current, include_current=True):
            return GitRunReport()

        return GitRunReport(problem="<can't groom").add(problem="current branch can't be cleaned")

    def delete_stale_local_branches(self) -> GitRunReport:
        report = GitRunReport()
        branches = self.git.stale_tracked_local_branches()
        if not branches:
            return report.add(note="no stale local branches")

        for branch in branches:
            if branch == self.git.branches.current:
                report.add(problem=f"can't delete current branch '{branch}'")
                continue

            args = ["branch", "--delete", branch]
            base_ref = self.git.cleanable_base_ref
            if base_ref and not self.git.is_ancestor(branch, base_ref):
                args.insert(2, "--force")

            _, error = self.git.run_git_command(*args)
            if error.has_problems:
                report.add(problem=f"couldn't delete '{branch}': {error.representation()}")

            else:
                report.add(progress=f"deleted {branch}")

        self.git.reset_cached_properties()
        return report


class ProjectDir:
    """One requested folder, represented as zero or more git checkouts."""

    def __init__(self, path: Path):
        """
        :param Path path: Path to folder
        """
        self.path = path
        self.checkouts: list[GitCheckout] = []
        self.name_size: int | None = None
        self.scan()

    def scan(self):
        if (self.path / ".git").is_dir():
            self.checkouts = [GitCheckout(self.path, parent=self)]
            self.name_size = None
            return

        self.checkouts = [
            GitCheckout(source_path, parent=self)
            for source_path in self.path.iterdir()
            if not source_path.name.startswith(".") and source_path.is_dir() and (source_path / ".git").is_dir()
        ]
        self.checkouts = sorted(self.checkouts, key=lambda x: x.basename)
        self.name_size = min(36, max(len(c.basename) for c in self.checkouts)) if len(self.checkouts) > 1 else None

    @property
    def header(self):
        result = f"{output.workspace_path(runez.short(self.path))}:"
        if not self.checkouts:
            return f"{result} {output.warning('no git folders')}"

        return result

    def print_header(self):
        if len(self.checkouts) != 1:
            print(self.header)

    def print_status(self, reports=None):
        self.print_header()
        if self.checkouts:
            reports = reports or {}
            show_details = len(self.checkouts) == 1
            for checkout in self.checkouts:
                checkout.print_status(reports.get(checkout), show_details=show_details)

    def print_branch_reports(self):
        show_checkout_names = len(self.checkouts) > 1
        for checkout in self.checkouts:
            if show_checkout_names:
                print(f"{checkout.basename}:")

            checkout.print_branch_report(indent="  " if show_checkout_names else "")
