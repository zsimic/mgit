from pathlib import Path

import runez

from mgit import find_actual_path


def test_usage(cli):
    cli.expect_success("--help")
    cli.expect_success("--version")
    cli.expect_failure("--foo", "unrecognized arguments")


def test_status(cli):
    # Note: using explicit lists below, to support case where used directory path may have a space in it
    # [wouldn't work if args passed as string, due to naive split in run()]
    # Status on a non-existing folder should fail
    cli.expect_failure("foo")

    # Status on this test folder should succeed and report no git folders found
    cli.expect_success(cli.tests_folder, "no git folders")

    # Status on project folder should succeed (we're not calling fetch)
    project = runez.DEV.project_folder
    cli.expect_success(project, "mgit")
    with runez.CurrentFolder(project):
        cli.run()
        assert cli.succeeded
        assert cli.logged.stdout.contents().startswith("mgit: ")


def test_find_actual_path_returns_absolute_checkout_parent(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    child = repo / "src"
    (repo / ".git").mkdir(parents=True)
    child.mkdir()
    monkeypatch.chdir(child)

    assert find_actual_path(Path(".")) == repo.absolute()
    assert find_actual_path(Path.cwd()) == repo.absolute()
    assert find_actual_path(Path("nested")) == (child / "nested").absolute()


def test_find_actual_path_defaults_to_current_folder(tmp_path, monkeypatch):
    child = tmp_path / "workspace" / "child"
    child.mkdir(parents=True)
    monkeypatch.chdir(child)

    assert find_actual_path(Path(".")) == Path(".").absolute()
