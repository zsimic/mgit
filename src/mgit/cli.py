from __future__ import annotations

import argparse
import logging
import re
import sys
from abc import ABC, abstractmethod
from importlib.metadata import version
from pathlib import Path

import runez

from mgit import ProjectDir, Reporter
from mgit.git import git_error_message, GitDir


def command_name_from_class(cls: type) -> str:
    name = cls.__name__.removesuffix("Command")
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


class CliCommand(ABC):
    """API for all CLI commands."""

    short_name: str | None = None

    @classmethod
    def command_name(cls) -> str:
        return command_name_from_class(cls)

    @classmethod
    def summary(cls) -> str:
        """Every command class must have a summary (intentional crash otherwise)"""
        assert cls.__doc__  # noqa: S101, internal error
        return cls.__doc__.splitlines()[0]

    @classmethod  # noqa: B027 - optional hook
    def add_arguments(cls, _parser: argparse.ArgumentParser) -> None:
        """Add command-specific arguments."""

    @classmethod
    @abstractmethod
    def from_namespace(cls, _namespace: argparse.Namespace) -> CliCommand:
        """Create a command from parsed CLI arguments."""

    @abstractmethod
    def run(self) -> int:
        """Run the command."""


class FolderTargetCommand(CliCommand):
    folder: Path | None = None

    def __init__(self, folder: Path | None):
        self.folder = folder

    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("folder", nargs="?", type=Path)

    @classmethod
    def from_namespace(cls, namespace: argparse.Namespace) -> FolderTargetCommand:
        return cls(folder=namespace.folder)

    @staticmethod
    def current_checkout() -> Path | None:
        current = Path.cwd()
        for candidate in (current, *current.parents):
            if (candidate / ".git").is_dir():
                return candidate

    def target(self) -> GitDir | ProjectDir:
        if self.folder is None:
            current = self.current_checkout()
            if current:
                return GitDir(current)

        folder = (self.folder or Path(".")).expanduser().absolute()
        Reporter.abort_if(not folder.is_dir(), f"No folder '{runez.short(folder)}'")
        if (folder / ".git").is_dir():
            return GitDir(folder)

        return ProjectDir(folder)

    def run(self) -> int:
        """Run the command."""
        target = self.target()
        if isinstance(target, GitDir):
            return self.run_single(target)

        return self.run_multi(target)

    @staticmethod
    def status_suffix(text: str | None) -> str:
        return f" ({text})" if text else ""

    @staticmethod
    def print_status(git: GitDir, suffix: str | None = None, show_details=True) -> None:
        print(f"{git.status_line()}{FolderTargetCommand.status_suffix(suffix)}")
        if show_details:
            for line in git.status_detail_lines():
                print(f"  {line}")

    @staticmethod
    def print_project_status(project_dir: ProjectDir, git: GitDir, suffix: str | None = None) -> None:
        print(project_dir.prefixed_line(git, f"{git.status_line()}{FolderTargetCommand.status_suffix(suffix)}"))

    @abstractmethod
    def run_single(self, git: GitDir) -> int:
        """Run this command for one git dir."""

    def run_multi(self, _project_dir: ProjectDir) -> int:
        """Run this command for all git dirs in `project_dir`."""
        Reporter.abort(f"{self.command_name()} only supports one git checkout")


COMMANDS: list[type[CliCommand]] = []
COMMAND_BY_TOKEN: dict[str, type[CliCommand]] = {}


def register_cli_command(name: str | None, command: type[CliCommand]):
    assert name  # noqa: S101, this would be an internal error, detected at test time
    assert name not in COMMAND_BY_TOKEN  # noqa: S101
    COMMAND_BY_TOKEN[name] = command


def cli_command(command: type[CliCommand]) -> type[CliCommand]:
    COMMANDS.append(command)
    register_cli_command(command.command_name(), command)
    register_cli_command(command.short_name, command)
    return command


@cli_command
class StatusCommand(FolderTargetCommand):
    """Show repo or workspace status."""

    short_name = "s"

    def run_single(self, git: GitDir) -> int:
        self.print_status(git)
        return 0

    def run_multi(self, project_dir: ProjectDir) -> int:
        project_dir.print_header()
        for git in project_dir.git_dirs:
            self.print_project_status(project_dir, git)
        return 0


@cli_command
class FetchCommand(FolderTargetCommand):
    """Fetch remotes, then show status."""

    short_name = "f"

    def fetch_status(self, git: GitDir) -> tuple[int, str | None]:
        should_fetch = git.age is None or git.age > 30
        report = git.fetch()
        if report.has_problems:
            return 1, report.representation()

        return 0, "fetched" if should_fetch else "fresh"

    def run_single(self, git: GitDir) -> int:
        exit_code, suffix = self.fetch_status(git)
        self.print_status(git, suffix)
        return exit_code

    def run_multi(self, project_dir: ProjectDir) -> int:
        project_dir.print_header()
        exit_code = 0
        for git in project_dir.git_dirs:
            current_exit, suffix = self.fetch_status(git)
            exit_code = max(exit_code, current_exit)
            self.print_project_status(project_dir, git, suffix)

        return exit_code


@cli_command
class PullCommand(FolderTargetCommand):
    """Pull with rebase when the worktree is safe."""

    short_name = "p"

    @staticmethod
    def pull_summary(git: GitDir) -> str:
        status = git.status
        parts = []
        if status.behind:
            parts.append(f"was behind {status.behind}")

        if status.ahead:
            parts.append(f"was ahead {status.ahead}")

        return ", ".join(parts) or "was up-to-date"

    def pull_status(self, git: GitDir) -> tuple[int, str | None]:
        suffix = self.pull_summary(git)
        report = git.pull()
        if report.has_problems:
            return 1, report.representation()

        return 0, suffix

    def run_single(self, git: GitDir) -> int:
        exit_code, suffix = self.pull_status(git)
        self.print_status(git, suffix)
        return exit_code

    def run_multi(self, project_dir: ProjectDir) -> int:
        project_dir.print_header()
        exit_code = 0
        for git in project_dir.git_dirs:
            current_exit, suffix = self.pull_status(git)
            exit_code = max(exit_code, current_exit)
            self.print_project_status(project_dir, git, suffix)

        return exit_code


@cli_command
class MainCommand(FolderTargetCommand):
    """Checkout the default branch."""

    short_name = "m"

    def run_single(self, git: GitDir) -> int:
        report = git.checkout_default_branch()
        self.print_status(git, report.representation())
        return 1 if report.has_problems else 0


@cli_command
class BranchesCommand(FolderTargetCommand):
    """Show local branches."""

    short_name = "b"

    def run_single(self, git: GitDir) -> int:
        for line in git.branch_lines():
            print(line)

        return 0

    def run_multi(self, project_dir: ProjectDir) -> int:
        project_dir.print_header()
        show_names = len(project_dir.git_dirs) > 1
        for git in project_dir.git_dirs:
            if show_names:
                print(f"{git.basename}:")

            indent = "  " if show_names else ""
            for line in git.branch_lines():
                print(f"{indent}{line}")

        return 0


@cli_command
class GroomCommand(FolderTargetCommand):
    """Fetch, return to default branch, pull, and clean stale local branches."""

    short_name = "g"

    def _checkout_default_branch(self, git: GitDir, branch: str) -> None:
        proc = git.run_git_command("checkout", branch)
        git.clear_cached_state()
        if proc.returncode:
            Reporter.abort(f"can't groom: checkout {branch} failed: {git_error_message(proc)}")

        print(f"Checked out {branch} branch")

    def _delete_stale_local_branches(self, git: GitDir) -> None:
        cleanups = git.stale_tracked_local_branch_cleanups()
        if not cleanups:
            print("No stale local branches")
            return

        for cleanup in cleanups:
            args = ["branch", "--delete", cleanup.name]
            if cleanup.force_delete:
                args.insert(2, "--force")

            proc = git.run_git_command(*args)
            if proc.returncode:
                Reporter.abort(f"can't groom: couldn't delete '{cleanup.name}': {git_error_message(proc)}")

            else:
                print(f"Deleted branch {cleanup.name}")

        git.clear_cached_state()

    def run_single(self, git: GitDir) -> int:
        git.fetch_now().require_success("groom")
        status = git.status
        status.require_clean("groom")
        refs = git.refs
        current_branch = refs.current
        default_branch = git.default_branch
        if current_branch != default_branch and not git.cleanable_local_branch(current_branch, include_current=True):
            Reporter.abort(f"can't groom: current branch can't be cleaned: {current_branch}")

        if current_branch == default_branch:
            print(f"Already on {default_branch} branch")

        else:
            self._checkout_default_branch(git, default_branch)

        git.pull().require_success("groom")
        git.clear_cached_state()
        self._delete_stale_local_branches(git)
        print(git.status_line())
        return 0


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


def split_global_args(args: list[str]) -> tuple[list[str], list[str]]:
    global_args = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in {"--help", "-v", "--verbose", "--version"}:
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
        command = COMMAND_BY_TOKEN.get(command_args[0])
        if command:
            command_args[0] = command.command_name()

        else:
            command_args.insert(0, StatusCommand.command_name())

    else:
        command_args.append(StatusCommand.command_name())

    return global_args + command_args


def main():
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

    namespace = parser.parse_args(normalized_cli_args(sys.argv[1:]))
    command = namespace.command_type.from_namespace(namespace)
    with runez.ActivateColors(None if namespace.color == "auto" else namespace.color == "always"):
        runez.date.DEFAULT_DURATION_SPAN = -2
        runez.log.setup(debug=namespace.verbose, level=logging.INFO, console_format="%(levelname)s %(message)s", locations=None)
        return command.run()
