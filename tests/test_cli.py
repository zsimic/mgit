import shutil
import subprocess

import pytest

from mgit.cli import main, parse_cli_args
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


def make_checkout(tmp_path):
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    work = tmp_path / "work"

    git_init("init", "--bare", "--initial-branch=main", str(remote))
    git_init("init", "--initial-branch=main", str(seed))
    git(seed, "config", "user.email", "tester@example.com")
    git(seed, "config", "user.name", "Test User")
    (seed / "README.md").write_text("hello\n")
    git(seed, "add", "README.md")
    git(seed, "commit", "-m", "initial")
    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "-u", "origin", "main")
    git_init("clone", str(remote), str(work))
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


def test_parse_rejects_extra_targets():
    with pytest.raises(SystemExit) as e:
        parse_cli_args(["fetch", "one", "two"])

    assert e.value.code == 2


def test_workspace_status_aligns_repo_names(tmp_path, capsys):
    make_repo(tmp_path / "short")
    make_repo(tmp_path / "longer-name")

    assert main(["--color", "never", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "\n      short:" in output
    assert "\nlonger-name:" in output


def test_main_checks_out_default_branch(tmp_path):
    work = make_checkout(tmp_path)
    git(work, "checkout", "-b", "feature")

    assert main(["--color", "never", "m", str(work)]) == 0
    assert git(work, "branch", "--show-current") == "main"


def test_groom_deletes_stale_tracked_branch(tmp_path, capsys):
    work = make_checkout(tmp_path)
    make_stale_tracked_branch(work)

    assert main(["--color", "never", "g", str(work)]) == 0

    output = capsys.readouterr().out
    assert "deleted stale" in output
    assert git(work, "branch", "--show-current") == "main"
    assert not git(work, "branch", "--list", "stale")


def test_groom_refuses_pending_changes(tmp_path, capsys):
    work = make_checkout(tmp_path)
    make_stale_tracked_branch(work)
    (work / "scratch.txt").write_text("pending\n")

    assert main(["--color", "never", "groom", str(work)]) == 1

    output = capsys.readouterr().out
    assert "pending changes" in output
    assert git(work, "branch", "--show-current") == "stale"
    assert git(work, "branch", "--list", "stale")
