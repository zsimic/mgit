import shutil
import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from mgit.cli import parse_cli_args
from mgit.commands import command_for, COMMANDS

GIT = shutil.which("git") or "git"


def git(cwd, *args, check=True):
    proc = subprocess.run(  # noqa: S603
        [GIT, "-C", str(cwd), *args],
        check=check,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def git_init(*args):
    subprocess.run([GIT, *args], check=True, capture_output=True, text=True)  # noqa: S603


def make_checkout(base):
    base.mkdir(parents=True, exist_ok=True)
    remote = base / "remote.git"
    seed = base / "seed"
    work = base / "work"

    git_init("init", "--bare", "--initial-branch=main", str(remote))
    git_init("init", "--initial-branch=main", str(seed))
    git(seed, "config", "user.email", "tester@example.com")
    git(seed, "config", "user.name", "Test User")
    (seed / "README.md").write_text("hello\n")
    git(seed, "add", "README.md")
    git(seed, "commit", "-m", "initial")
    remote_url = str(remote.resolve())
    git(seed, "remote", "add", "origin", remote_url)
    git(seed, "push", "-u", "origin", "main")
    git_init("clone", remote_url, str(work))
    git(work, "config", "user.email", "tester@example.com")
    git(work, "config", "user.name", "Test User")
    return work


def make_repo(path):
    git_init("init", "--initial-branch=main", str(path))
    git(path, "config", "user.email", "tester@example.com")
    git(path, "config", "user.name", "Test User")
    (path / "README.md").write_text(f"{path.name}\n")
    git(path, "add", "README.md")
    git(path, "commit", "-m", "initial")


def make_stale_tracked_branch(work):
    git(work, "checkout", "-b", "stale")
    git(work, "push", "-u", "origin", "stale")
    git(work, "checkout", "main")
    git(work, "push", "origin", "--delete", "stale")
    git(work, "checkout", "stale")


def test_command_registry_core_slice():
    assert {command.name: command.aliases for command in COMMANDS} == {
        "status": ("s",),
        "fetch": ("f",),
        "pull": ("p",),
        "main": ("m",),
        "groom": ("g",),
    }
    assert command_for("g").name == "groom"
    assert command_for("status").scope == "both"
    assert command_for("groom").scope == "single"


@pytest.mark.parametrize(
    ("argv", "command", "target"),
    [
        ([], "status", None),
        (["status"], "status", None),
        (["s"], "status", None),
        (["fetch"], "fetch", None),
        (["f"], "fetch", None),
        (["pull"], "pull", None),
        (["p"], "pull", None),
        (["groom"], "groom", None),
        (["g"], "groom", None),
        (["main"], "main", None),
        (["m"], "main", None),
        (["status", "repo"], "status", "repo"),
        (["repo"], "status", "repo"),
    ],
)
def test_parse_core_commands(argv, command, target):
    invocation = parse_cli_args(argv)
    assert invocation.command.name == command
    assert invocation.target == target


def test_parse_rejects_extra_targets(cli):
    cli.run("fetch one two")

    assert cli.failed
    assert cli.exit_code == 2
    assert "fetch accepts at most one target" in cli.logged


def test_workspace_status_alignment(cli):
    make_repo(Path("my-workspace/short"))
    make_repo(Path("my-workspace/longer-name"))

    expected = dedent("""\
        my-workspace: 2 unknown/unknown
        longer-name: [main] up to date  no remotes; current branch 'main' is orphaned
              short: [main] up to date  no remotes; current branch 'main' is orphaned
    """)

    cli.run("my-workspace")
    assert cli.succeeded
    assert cli.logged.stdout.contents() == expected


def test_main_checks_out_default_branch(cli):
    work = make_checkout(Path("checkout"))
    git(work, "checkout", "-b", "feature")

    cli.run("m checkout/work")

    assert cli.succeeded
    assert git(work, "branch", "--show-current") == "main"


def test_groom_deletes_stale_tracked_branch(cli):
    work = make_checkout(Path("checkout"))
    make_stale_tracked_branch(work)

    cli.run("g checkout/work")

    assert cli.succeeded
    assert "deleted stale" in cli.logged
    assert git(work, "branch", "--show-current") == "main"
    assert not git(work, "branch", "--list", "stale")


def test_groom_refuses_pending_changes(cli):
    work = make_checkout(Path("checkout"))
    make_stale_tracked_branch(work)
    (work / "scratch.txt").write_text("pending\n")

    cli.run("groom checkout/work")

    assert cli.failed
    assert cli.exit_code == 1
    assert "pending changes" in cli.logged
    assert git(work, "branch", "--show-current") == "stale"
    assert git(work, "branch", "--list", "stale")
