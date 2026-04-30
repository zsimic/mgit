from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSpec:
    """Metadata for a v2 command."""

    name: str
    aliases: tuple[str, ...]
    summary: str
    scope: str
    mutates_local: bool = False
    mutates_remote: bool = False
    handler: str = ""

    @property
    def names(self):
        return (self.name, *self.aliases)


COMMANDS = (
    CommandSpec("status", ("s",), "Show repo or workspace status.", "both", handler="status"),
    CommandSpec("fetch", ("f",), "Fetch remotes, then show status.", "both", mutates_local=True, handler="fetch"),
    CommandSpec("pull", ("p",), "Pull with rebase when the worktree is safe.", "both", mutates_local=True, handler="pull"),
    CommandSpec("main", ("m",), "Checkout the default branch.", "single", mutates_local=True, handler="main"),
    CommandSpec("branches", ("b",), "Show local branches.", "both", handler="branches"),
    CommandSpec(
        "groom",
        ("g",),
        "Fetch, return to default branch, pull, and clean stale local branches.",
        "single",
        mutates_local=True,
        handler="groom",
    ),
)

COMMAND_BY_TOKEN = {token: command for command in COMMANDS for token in command.names}


def default_command() -> CommandSpec:
    """Default command used when no command token is provided."""
    return COMMAND_BY_TOKEN["status"]


def command_for(token: str) -> CommandSpec | None:
    """
    :param str token: Command name or alias
    :return CommandSpec|None: Matching command
    """
    return COMMAND_BY_TOKEN.get(token)


def command_help():
    """Human-friendly command list for argparse help output."""
    lines = ["commands:"]
    for command in COMMANDS:
        names = ", ".join(command.names)
        lines.append(f"  {names:<14} {command.summary}")

    return "\n".join(lines)
