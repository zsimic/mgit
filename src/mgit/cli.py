from __future__ import annotations

import argparse
import inspect
import logging
import re
import sys
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import ClassVar

import runez

from mgit import find_actual_path, GitCheckout, print_modified, ProjectDir
from mgit.git import GitRunReport
from mgit.output import branch_current, branch_default, branch_orphaned, color_context, index_change, untracked_change, worktree_change

FETCH_COOLDOWN_SECONDS = 30


@dataclass(frozen=True)
class GlobalFlags:
    verbose: bool = False
    color: str = "auto"


@dataclass(frozen=True)
class CliInvocation:
    flags: GlobalFlags
    command: CliCommand


def command_name_from_class(cls: type) -> str:
    name = cls.__name__.removesuffix("Command")
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


class CliCommand:
    """API for all CLI commands."""

    short_name: ClassVar[str | None] = None

    @classmethod
    def command_name(cls) -> str:
        return command_name_from_class(cls)

    @classmethod
    def summary(cls) -> str:
        doc = inspect.getdoc(cls) or ""
        return doc.splitlines()[0] if doc else ""

    @classmethod
    def add_arguments(cls, _parser: argparse.ArgumentParser) -> None:
        """Add command-specific arguments."""

    @classmethod
    def parser(cls) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog=f"mgit {cls.command_name()}", description=cls.summary())
        cls.add_arguments(parser)
        return parser

    @classmethod
    def parse(cls, args: list[str]) -> CliCommand:
        namespace = cls.parser().parse_args(args)
        return cls.from_namespace(namespace)

    @classmethod
    def from_namespace(cls, _namespace: argparse.Namespace) -> CliCommand:
        return cls()

    def run(self) -> int:
        raise NotImplementedError


@dataclass(frozen=True)
class FolderCommand(CliCommand):
    folder: Path = Path(".")

    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("folder", nargs="?", type=Path, default=cls.folder)

    @classmethod
    def from_namespace(cls, namespace: argparse.Namespace) -> FolderCommand:
        return cls(folder=namespace.folder)

    def actual_folder(self) -> Path:
        folder = find_actual_path(self.folder)
        if not folder.is_dir():
            runez.abort(f"No folder '{runez.short(folder)}'")

        return folder

    def get_project_dir(self) -> ProjectDir:
        return ProjectDir(self.actual_folder())

    def get_git_checkout(self) -> GitCheckout:
        folder = self.actual_folder()
        if not (folder / ".git").is_dir():
            runez.abort(f"{self.command_name()} only supports one git checkout", code=2)

        return GitCheckout(folder)


COMMANDS: list[type[CliCommand]] = []
COMMAND_BY_TOKEN: dict[str, type[CliCommand]] = {}


def register_cli_command(name: str | None, command: type[CliCommand]):
    if name:
        assert name not in COMMAND_BY_TOKEN  # noqa: S101, this would be an internal error, detected at test time
        COMMAND_BY_TOKEN[name] = command


def cli_command(command: type[CliCommand]) -> type[CliCommand]:
    COMMANDS.append(command)
    register_cli_command(command.command_name(), command)
    register_cli_command(command.short_name, command)
    return command


@cli_command
class StatusCommand(FolderCommand):
    """Show repo or workspace status."""

    short_name = "s"

    def run(self) -> int:
        project_dir = self.get_project_dir()
        print_project_status(project_dir)
        return 0


@cli_command
class FetchCommand(FolderCommand):
    """Fetch remotes, then show status."""

    short_name = "f"

    def run(self) -> int:
        project_dir = self.get_project_dir()
        reports = {}
        for checkout in project_dir.checkouts:
            fetch_report = checkout.git.fetch(age=FETCH_COOLDOWN_SECONDS)
            reports[checkout] = checkout_status_report(checkout, fetch_report)

        print_project_status(project_dir, reports)
        return 0


@cli_command
class PullCommand(FolderCommand):
    """Pull with rebase when the worktree is safe."""

    short_name = "p"

    def run(self) -> int:
        project_dir = self.get_project_dir()
        reports = {}
        for checkout in project_dir.checkouts:
            pull_report = checkout.git.pull()
            reports[checkout] = checkout_status_report(checkout, pull_report)

        print_project_status(project_dir, reports)
        return 0


@cli_command
class MainCommand(FolderCommand):
    """Checkout the default branch."""

    short_name = "m"

    def run(self) -> int:
        target = self.get_git_checkout()
        report = checkout_default_branch(target)
        print_checkout_status(target, report)
        return 1 if report.has_problems else 0


@cli_command
class BranchesCommand(FolderCommand):
    """Show local branches."""

    short_name = "b"

    def run(self) -> int:
        project_dir = self.get_project_dir()
        if project_dir.is_single_checkout:
            target = project_dir.checkouts[0]
            print_branch_report(target)
            return 0

        for checkout in project_dir.checkouts:
            if checkout.git.is_git_checkout:
                print(f"{checkout.name}:")
                print_branch_report(checkout, indent="  ")

        return 0


@cli_command
class GroomCommand(FolderCommand):
    """Fetch, return to default branch, pull, and clean stale local branches."""

    short_name = "g"

    def run(self) -> int:
        target = self.get_git_checkout()
        report = GitRunReport()

        fetch_report = target.git.fetch(age=None)
        if fetch_report.has_problems:
            report.add(fetch_report).add(problem="<can't groom")
            print_checkout_status(target, report)
            return 1

        if has_pending_changes(target):
            print_checkout_status(target, pending_changes_report(target))
            return 1

        current_report = current_branch_cleanable_report(target)
        if current_report.has_problems:
            print_checkout_status(target, current_report)
            return 1

        report.add(current_report)

        checkout_report = checkout_default_branch(target)
        if checkout_report.has_problems:
            report.add(checkout_report).add(problem="<can't groom")
            print_checkout_status(target, report)
            return 1

        report.add(checkout_report)
        if has_pending_changes(target):
            print_checkout_status(target, pending_changes_report(target))
            return 1

        pull_report = target.git.pull()
        if pull_report.has_problems:
            report.add(pull_report).add(problem="<can't groom")
            print_checkout_status(target, report)
            return 1

        report.add(pull_report)
        report.add(delete_stale_local_branches(target))
        print_checkout_status(target, report)
        return 1 if report.has_problems else 0


def command_for(token: str) -> type[CliCommand] | None:
    return COMMAND_BY_TOKEN.get(token)


def command_help() -> str:
    lines = ["commands:"]
    for command in COMMANDS:
        text = command.command_name()
        if command.short_name:
            text += f", {command.short_name}"

        lines.append(f"  {text:<14} {command.summary()}")

    return "\n".join(lines)


def split_command_args(args: list[str]) -> tuple[type[CliCommand], list[str]]:
    if args:
        command = command_for(args[0])
        if command:
            return command, args[1:]

    return StatusCommand, args


def build_parser():
    parser = argparse.ArgumentParser(
        prog="mgit",
        usage="mgit [GLOBAL_OPTIONS] [COMMAND] [ARGS...]",
        description="Inspect and update git checkouts.",
        epilog=command_help(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging.")
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto", help="Control ANSI color output.")
    parser.add_argument("--version", action="version", version=f"mgit {version('mgit')}")
    return parser


def split_global_args(args: list[str]) -> tuple[list[str], list[str]]:
    global_args = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in {"-h", "--help", "-v", "--verbose", "--version"}:
            global_args.append(arg)
            i += 1
            continue

        if arg == "--color":
            global_args.append(arg)
            i += 1
            if i < len(args):
                global_args.append(args[i])
                i += 1
            continue

        if arg.startswith("--color="):
            global_args.append(arg)
            i += 1
            continue

        if arg.startswith("-"):
            global_args.append(arg)
            i += 1

        break

    return global_args, args[i:]


def parse_cli_args(argv=None, parser=None):
    args = list(sys.argv[1:] if argv is None else argv)
    parser = parser or build_parser()
    global_args, command_args = split_global_args(args)
    namespace = parser.parse_args(global_args)
    command_type, command_args = split_command_args(command_args)
    command = command_type.parse(command_args)
    return CliInvocation(
        flags=GlobalFlags(verbose=namespace.verbose, color=namespace.color),
        command=command,
    )


def configure_runtime(verbose=False):
    runez.system.AbortException = SystemExit
    runez.date.DEFAULT_DURATION_SPAN = -2
    runez.log.setup(debug=verbose, level=logging.INFO, console_format="%(levelname)s %(message)s", locations=None)


def checkout_default_branch(target):
    """
    :param GitCheckout target: Checkout to move to its default branch
    :return GitRunReport: Checkout report
    """
    branch = target.git.default_branch
    if target.git.branches.current == branch:
        return GitRunReport()

    _, error = target.git.run_git_command("checkout", branch)
    target.git.reset_cached_properties()
    if error.has_problems:
        return GitRunReport(error).add(problem="<can't checkout default branch")

    return GitRunReport(progress=f"checked out {branch}")


def stale_tracked_local_branches(git):
    """
    :param mgit.git.GitDir git: Checkout model
    :return list[str]: Local branches whose tracked remote branch is gone
    """
    result = []
    for branch in sorted(git.local_cleanable_branches):
        remote = git.config.tracking_remote.get(branch)
        if remote and branch not in git.branches.by_remote.get(remote, set()):
            result.append(branch)

    return result


def delete_stale_local_branches(target):
    """
    :param GitCheckout target: Checkout to clean
    :return GitRunReport: Cleanup report
    """
    report = GitRunReport()
    branches = stale_tracked_local_branches(target.git)
    if not branches:
        return report.add(note="no stale local branches")

    for branch in branches:
        if branch == target.git.branches.current:
            report.add(problem=f"can't delete current branch '{branch}'")
            continue

        args = ["branch", "--delete", branch]
        base_ref = target.git.cleanable_base_ref
        if base_ref and not target.git.is_ancestor(branch, base_ref):
            args.insert(2, "--force")

        _, error = target.git.run_git_command(*args)
        if error.has_problems:
            report.add(problem=f"couldn't delete '{branch}': {error.representation()}")

        else:
            report.add(progress=f"deleted {branch}")

    target.git.reset_cached_properties()
    return report


def pending_changes_report(target):
    report = GitRunReport(problem="<can't groom").add(problem="pending changes")
    if target.git.status.modified:
        report.add(note=runez.plural(target.git.status.modified, "diff"))

    if target.git.status.untracked:
        report.add(note=f"{len(target.git.status.untracked)} untracked")

    return report


def current_branch_cleanable_report(target):
    current = target.git.branches.current
    if current == target.git.default_branch:
        return GitRunReport(note=f"already on {target.git.default_branch} branch")

    if target.git.is_cleanable_local_branch(current, include_current=True):
        return GitRunReport()

    return GitRunReport(problem="<can't groom").add(problem="current branch can't be cleaned")


def has_pending_changes(target):
    return bool(target.git.status.modified or target.git.status.untracked)


def checkout_status_report(target, report=None):
    report = GitRunReport(report)
    if not report.has_problems:
        report.add(target.git.report())

    return report


def print_project_status(project_dir, reports=None):
    if not project_dir.checkouts:
        print(project_dir.header)
        return

    if len(project_dir.checkouts) > 1:
        print(project_dir.header)

    reports = reports or {}
    show_details = project_dir.is_single_checkout
    for checkout in project_dir.checkouts:
        print_checkout_status(checkout, reports.get(checkout), show_details=show_details)


def print_checkout_status(target, report=None, show_details=True):
    print(target.header(report))
    if not show_details:
        return

    if len(target.git.orphan_branches) > 1:
        orphan_branches = ", ".join(target.git.orphan_branches)
        print(f"  Orphan branches: {orphan_branches}")

    print_modified(target.git.status.modified, index_change, worktree_change)
    print_modified(target.git.status.untracked, untracked_change)


def branch_annotations(target, name):
    annotations = []
    if name == target.git.default_branch:
        annotations.append(branch_default("[default]"))

    if name in target.git.orphan_branches and name not in target.git.special_branches:
        annotations.append(branch_orphaned("[orphaned]"))

    return annotations


def branch_lines(target):
    branches = sorted(target.git.branches.local)
    if not branches:
        return ["  no local branches"]

    width = max(len(name) for name in branches)
    lines = []
    for name in branches:
        is_current = name == target.git.branches.current
        marker = "*" if is_current else " "
        line = f"{marker} {name:<{width}}"
        if is_current:
            line = branch_current(line)

        annotations = branch_annotations(target, name)
        if annotations:
            line += f"  {' '.join(annotations)}"

        lines.append(line)

    return lines


def print_branch_report(target, indent=""):
    for line in branch_lines(target):
        print(f"{indent}{line}")


def run_invocation(invocation):
    configure_runtime(invocation.flags.verbose)
    return invocation.command.run()


def main(argv=None):
    invocation = parse_cli_args(argv)
    with color_context(invocation.flags.color):
        return run_invocation(invocation)
