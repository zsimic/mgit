import os

import pytest
import runez

import mgit


def test_edge_cases():
    assert mgit.git_parent_path("/") is None
    assert mgit.git_parent_path(runez.DEV.tests_folder) == runez.DEV.project_folder

    prefs = mgit.MgitPreferences(all=True, fetch=False, pull=False, short=None)
    assert str(prefs) == "align all !fetch !pull !verbose"

    prefs = mgit.MgitPreferences(name_size=5)
    prefs.fetch = None
    assert str(prefs) == "name_size=5"

    prefs = mgit.MgitPreferences()
    assert not str(prefs)

    with pytest.raises(Exception):
        prefs.update(foo=1)


def test_usage(cli):
    cli.expect_success("--help")
    cli.expect_success("--version")
    cli.expect_failure("--foo", "No such option")


def test_status(cli):
    # Note: using explicit lists below, to support case where used directory path may have a space in it
    # [wouldn't work if args passed as string, due to naive split in run()]
    # Status on a non-existing folder should fail
    cli.expect_failure("foo", "No folder 'foo'")

    # Status on this test folder should succeed and report no git folders found
    cli.expect_success(cli.tests_folder, "no git folders")

    # Status on project folder should succeed (we're not calling fetch)
    project = runez.DEV.project_folder
    cli.expect_success(project, "mgit")
    with runez.CurrentFolder(project):
        cli.run()
        assert cli.succeeded
        assert "%s:" % os.path.basename(project) in cli.logged.stdout

        cli.expect_success("-cs")
