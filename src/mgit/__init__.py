from __future__ import annotations

from typing import TYPE_CHECKING

import runez

from mgit.git import git_error_message, GitDir, GitRunReport, Reporter

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

    def header(self, report: GitRunReport | None = None) -> str:
        """One-line header to show for this git checkout"""
        report = GitRunReport(report)
        result = self.basename
        if self.parent and self.parent.name_size:
            result = f"{result:>{self.parent.name_size}}"

        result = f"{result}:"
        branch = Reporter.branch_current(self.git.refs.current)
        n = len(self.git.refs.local)
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

    def print_status(self, report=None, show_details=True):
        print(self.header(report))
        if show_details:
            orphan_branches = self.git.orphan_branches
            if len(orphan_branches) > 1:
                print(f"  Orphan branches: {', '.join(orphan_branches)}")

            status = self.git.status
            self.print_modified(status.modified, Reporter.index_change, Reporter.worktree_change)
            self.print_modified(status.untracked, Reporter.untracked_change)

    @staticmethod
    def print_modified(items, state_style, worktree_style=None):
        for item in items:
            state = item[0:2]
            if worktree_style:
                state = f"{state_style(item[0])}{worktree_style(item[1])}"

            elif state_style:
                state = state_style(state)

            print(f"  {state} {item[3:]}")

    @staticmethod
    def branch_annotations(name, default_branch, orphan_branches, is_protected):
        annotations = []
        if name == default_branch:
            annotations.append(Reporter.branch_default("[default]"))

        if name in orphan_branches and not is_protected:
            annotations.append(Reporter.branch_orphaned("[orphaned]"))

        return annotations

    def branch_lines(self):
        default_branch = self.git.default_branch
        orphan_branches = set(self.git.orphan_branches)
        width = max(len(name) for name in self.git.refs.local)
        for name in sorted(self.git.refs.local):
            line = f"{'*' if name == self.git.refs.current else ' '} {name:<{width}}"
            annotations = self.branch_annotations(name, default_branch, orphan_branches, self.git.is_protected_branch(name))
            if annotations:
                line += f"  {' '.join(annotations)}"

            yield line

    def print_branch_report(self, indent=""):
        for line in self.branch_lines():
            print(f"{indent}{line}")

    def current_branch_cleanable_report(self) -> GitRunReport:
        current = self.git.refs.current
        default_branch = self.git.default_branch
        if current == default_branch:
            return GitRunReport(note=f"already on {default_branch} branch")

        if self.git.is_cleanable_local_branch(current, include_current=True):
            return GitRunReport()

        return GitRunReport(problem="<can't groom").add(problem="current branch can't be cleaned")

    def delete_stale_local_branches(self) -> GitRunReport:
        report = GitRunReport()
        branches = self.git.stale_tracked_local_branches()
        if not branches:
            return report.add(note="no stale local branches")

        current = self.git.refs.current
        base_ref = self.git.cleanable_base_ref
        attempted_delete = False
        for branch in branches:
            if branch == current:
                report.add(problem=f"can't delete current branch '{branch}'")
                continue

            args = ["branch", "--delete", branch]
            if base_ref and not self.git.is_ancestor(branch, base_ref):
                args.insert(2, "--force")

            proc = self.git.run_git_command(*args)
            attempted_delete = True
            if proc.returncode:
                report.add(problem=f"couldn't delete '{branch}': {git_error_message(proc)}")

            else:
                report.add(progress=f"deleted {branch}")

        if attempted_delete:
            self.git.clear_cached_state()

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
        text = f"{Reporter.workspace_path(runez.short(self.path))}:"
        Reporter.abort_if(not self.checkouts, f"{text} no git folders")
        return text

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
