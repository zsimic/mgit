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

from mgit import GitCheckout, ProjectDir
from mgit.git import GitRunReport
from mgit.output import color_context

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
    def from_namespace(cls, _namespace: argparse.Namespace) -> CliCommand:
        return cls()

    def run(self) -> int:
        raise NotImplementedError


@dataclass(frozen=True)
class FolderTargetCommand(CliCommand):
    folder: Path = Path(".")

    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("folder", nargs="?", type=Path, default=cls.folder)

    @classmethod
    def from_namespace(cls, namespace: argparse.Namespace) -> FolderTargetCommand:
        return cls(folder=namespace.folder)

    def actual_folder(self) -> Path:
        folder = self.folder.expanduser().absolute()
        current = Path.cwd()
        if folder == current:
            for candidate in (current, *current.parents):
                if (candidate / ".git").is_dir():
                    folder = candidate
                    break

        if not folder.is_dir():
            runez.abort(f"No folder '{runez.short(folder)}'")

        return folder


@dataclass(frozen=True)
class ProjectCommand(FolderTargetCommand):
    """Command operating on a project directory or single checkout."""

    def get_project_dir(self) -> ProjectDir:
        return ProjectDir(self.actual_folder())


@dataclass(frozen=True)
class SingleCheckoutCommand(FolderTargetCommand):
    """Command operating on one git checkout."""

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
class StatusCommand(ProjectCommand):
    """Show repo or workspace status."""

    short_name = "s"

    def run(self) -> int:
        project_dir = self.get_project_dir()
        project_dir.print_status()
        return 0


@cli_command
class FetchCommand(ProjectCommand):
    """Fetch remotes, then show status."""

    short_name = "f"

    def run(self) -> int:
        project_dir = self.get_project_dir()
        reports = {}
        for checkout in project_dir.checkouts:
            fetch_report = checkout.git.fetch(age=FETCH_COOLDOWN_SECONDS)
            reports[checkout] = checkout.status_report(fetch_report)

        project_dir.print_status(reports)
        return 0


@cli_command
class PullCommand(ProjectCommand):
    """Pull with rebase when the worktree is safe."""

    short_name = "p"

    def run(self) -> int:
        project_dir = self.get_project_dir()
        reports = {}
        for checkout in project_dir.checkouts:
            pull_report = checkout.git.pull()
            reports[checkout] = checkout.status_report(pull_report)

        project_dir.print_status(reports)
        return 0


@cli_command
class MainCommand(SingleCheckoutCommand):
    """Checkout the default branch."""

    short_name = "m"

    def run(self) -> int:
        target = self.get_git_checkout()
        report = target.git.checkout_default_branch()
        target.print_status(report)
        return 1 if report.has_problems else 0


@cli_command
class BranchesCommand(ProjectCommand):
    """Show local branches."""

    short_name = "b"

    def run(self) -> int:
        project_dir = self.get_project_dir()
        project_dir.print_branch_reports()
        return 0


@cli_command
class GroomCommand(SingleCheckoutCommand):
    """Fetch, return to default branch, pull, and clean stale local branches."""

    short_name = "g"

    def run(self) -> int:
        target = self.get_git_checkout()
        report = GitRunReport()

        fetch_report = target.git.fetch(age=None)
        if fetch_report.has_problems:
            report.add(fetch_report).add(problem="<can't groom")
            target.print_status(report)
            return 1

        if target.git.status.has_pending_changes:
            target.print_status(target.git.status.pending_changes_report())
            return 1

        current_report = target.current_branch_cleanable_report()
        if current_report.has_problems:
            target.print_status(current_report)
            return 1

        report.add(current_report)

        checkout_report = target.git.checkout_default_branch()
        if checkout_report.has_problems:
            report.add(checkout_report).add(problem="<can't groom")
            target.print_status(report)
            return 1

        report.add(checkout_report)
        if target.git.status.has_pending_changes:
            target.print_status(target.git.status.pending_changes_report())
            return 1

        pull_report = target.git.pull()
        if pull_report.has_problems:
            report.add(pull_report).add(problem="<can't groom")
            target.print_status(report)
            return 1

        report.add(pull_report)
        report.add(target.delete_stale_local_branches())
        target.print_status(report)
        return 1 if report.has_problems else 0


def command_for(token: str) -> type[CliCommand] | None:
    return COMMAND_BY_TOKEN.get(token)


class CommandHelpFormatter(argparse.HelpFormatter):
    """Show subcommands as a compact command list."""

    def _format_action(self, action: argparse.Action) -> str:
        if isinstance(action, argparse._SubParsersAction):
            return "".join(self._format_action(choice_action) for choice_action in action._get_subactions())

        return super()._format_action(action)


def add_command_parser(subparsers: argparse._SubParsersAction, command: type[CliCommand]) -> None:
    aliases = [command.short_name] if command.short_name else []
    parser = subparsers.add_parser(
        command.command_name(),
        aliases=aliases,
        description=command.summary(),
        formatter_class=CommandHelpFormatter,
        help=command.summary(),
        prog=f"mgit {command.command_name()}",
    )
    parser._action_groups[0].title = "Arguments"
    command.add_arguments(parser)
    parser.set_defaults(command_type=command)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="mgit",
        usage="mgit [GLOBAL_OPTIONS] [COMMAND] [ARGS...]",
        description="Inspect and update git checkouts.",
        formatter_class=CommandHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging.")
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto", help="Control ANSI color output.")
    parser.add_argument("--version", action="version", version=f"mgit {version('mgit')}")
    subparsers = parser.add_subparsers(dest="command", title="Commands", metavar="COMMAND")
    subparsers.required = True
    for command in COMMANDS:
        add_command_parser(subparsers, command)

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


def normalized_cli_args(args: list[str]) -> list[str]:
    global_args, command_args = split_global_args(args)
    if global_args and global_args[-1] == "--color":
        return global_args

    if command_args:
        command = command_for(command_args[0])
        if command:
            command_args[0] = command.command_name()

        else:
            command_args.insert(0, StatusCommand.command_name())

    else:
        command_args.append(StatusCommand.command_name())

    return global_args + command_args


def parse_cli_args(argv=None, parser=None):
    args = list(sys.argv[1:] if argv is None else argv)
    parser = parser or build_parser()
    namespace = parser.parse_args(normalized_cli_args(args))
    command = namespace.command_type.from_namespace(namespace)
    return CliInvocation(
        flags=GlobalFlags(verbose=namespace.verbose, color=namespace.color),
        command=command,
    )


def configure_runtime(verbose=False):
    runez.system.AbortException = SystemExit
    runez.date.DEFAULT_DURATION_SPAN = -2
    runez.log.setup(debug=verbose, level=logging.INFO, console_format="%(levelname)s %(message)s", locations=None)


def run_invocation(invocation):
    configure_runtime(invocation.flags.verbose)
    return invocation.command.run()


def main(argv=None):
    invocation = parse_cli_args(argv)
    with color_context(invocation.flags.color):
        return run_invocation(invocation)
