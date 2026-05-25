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
from mgit.git import GitDir


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
    def add_arguments(cls, _parser: argparse.ArgumentParser):
        """Add command-specific arguments."""

    @classmethod
    @abstractmethod
    def from_namespace(cls, _namespace: argparse.Namespace) -> CliCommand:
        """Create a command from parsed CLI arguments."""

    @abstractmethod
    def run(self):
        """Run the command."""


class FolderTargetCommand(CliCommand):
    folder: Path | None = None

    def __init__(self, folder: Path | None):
        self.folder = folder

    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser):
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

    def run(self):
        """Run the command."""
        target = self.target()
        if isinstance(target, GitDir):
            return self.run_single(target)

        return self.run_multi(target)

    @abstractmethod
    def run_single(self, git: GitDir):
        """Run this command for one git dir."""

    def run_multi(self, _project_dir: ProjectDir) -> None:
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

    def run_single(self, git: GitDir):
        print(git.status_line())
        details = git.status_details()
        if details:
            print(details)

    def run_multi(self, project_dir: ProjectDir):
        for git in project_dir.git_dirs:
            print(project_dir.prefixed_line(git, git.status_line()))


@cli_command
class FetchCommand(FolderTargetCommand):
    """Fetch remotes, then show status."""

    short_name = "f"

    def run_single(self, git: GitDir):
        report = git.fetch_now().require_success("fetch")
        print(git.status_line(report))
        details = git.status_details()
        if details:
            print(details)

    def run_multi(self, project_dir: ProjectDir):
        for git in project_dir.git_dirs:
            report = git.fetch_now()
            print(project_dir.prefixed_line(git, git.status_line(report)))


@cli_command
class PullCommand(FolderTargetCommand):
    """Pull with rebase when the worktree is safe."""

    short_name = "p"

    def run_single(self, git: GitDir):
        report = git.pull().require_success("pull")
        print(git.status_line(report))
        details = git.status_details()
        if details:
            print(details)

    def run_multi(self, project_dir: ProjectDir):
        for git in project_dir.git_dirs:
            report = git.pull()
            print(project_dir.prefixed_line(git, git.status_line(report)))


@cli_command
class MainCommand(FolderTargetCommand):
    """Checkout the default branch."""

    short_name = "m"

    def run_single(self, git: GitDir):
        report = git.checkout_default_branch()
        print(git.status_line(report))
        details = git.status_details()
        if details:
            print(details)


@cli_command
class BranchesCommand(FolderTargetCommand):
    """Show local branches."""

    short_name = "b"

    def run_single(self, git: GitDir):
        details = git.branch_details()
        if details:
            print(details)

    def run_multi(self, project_dir: ProjectDir):
        show_names = len(project_dir.git_dirs) > 1
        for git in project_dir.git_dirs:
            if show_names:
                print(f"{git.basename}:")

            indent = "  " if show_names else ""
            details = git.branch_details(indent=indent)
            if details:
                print(details)


@cli_command
class GroomCommand(FolderTargetCommand):
    """Fetch, return to default branch, pull, and clean the groomed branch."""

    short_name = "g"

    def _checkout_default_branch(self, git: GitDir, branch: str):
        git.checked_git_command("checkout", branch)
        git.clear_cached_state()
        print(f"Checked out {git.represented_branch(branch)} branch")

    def _delete_local_branch(self, git: GitDir, cleanup):
        args = ["branch", "--delete", cleanup.name]
        if cleanup.force_delete:
            args.insert(2, "--force")

        git.checked_git_command(*args)
        print(f"Deleted branch {git.represented_branch(cleanup.name)}")
        git.clear_cached_state()

    def _delete_remote_branch(self, git: GitDir, cleanup):
        branch_ref = f"refs/heads/{cleanup.branch}"
        git.checked_git_command(
            "push",
            f"--force-with-lease={branch_ref}:{cleanup.expected_oid}",
            "--delete",
            cleanup.remote,
            branch_ref,
        )
        print(f"Deleted remote branch {cleanup.remote}/{git.represented_branch(cleanup.branch)}")
        git.clear_cached_state()

    def run_single(self, git: GitDir):
        report = git.fetch_now().require_success("groom")
        refs = git.refs
        current_branch = refs.current
        default_branch = git.default_branch
        if current_branch == default_branch:
            report.add(note="already on default branch")
            print(git.status_line(report))
            return

        git.status.require_clean("groom")
        local_cleanup = git.cleanable_local_branch(current_branch, include_current=True)
        if not local_cleanup:
            Reporter.abort(f"Branch {git.represented_branch(current_branch)} can't be cleaned")

        upstream = refs.upstreams.get(current_branch)
        remote_cleanup = None
        if upstream and refs.has_remote_branch(upstream.remote, upstream.branch):
            remote_cleanup = git.cleanable_current_remote_branch()
            if not remote_cleanup:
                Reporter.abort(f"Remote branch {upstream.remote}/{git.represented_branch(upstream.branch)} can't be cleaned automatically")

        self._checkout_default_branch(git, default_branch)
        report = git.pull().require_success("groom")
        git.clear_cached_state()
        if remote_cleanup:
            self._delete_remote_branch(git, remote_cleanup)

        self._delete_local_branch(git, local_cleanup)
        print(git.status_line(report))


class CommandHelpFormatter(argparse.HelpFormatter):
    """Show subcommands as a compact command list."""

    def _format_action(self, action: argparse.Action) -> str:
        if isinstance(action, argparse._SubParsersAction):
            return "".join(self._format_action(choice_action) for choice_action in action._get_subactions())

        return super()._format_action(action)


def add_command_parser(subparsers: argparse._SubParsersAction, command: type[CliCommand]):
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
        command.run()
