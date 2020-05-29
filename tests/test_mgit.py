import os

import pytest
import runez
from runez.conftest import project_folder, tests_folder

import mgit


def test_edge_cases():
    assert mgit.git_parent_path("/") is None
    assert mgit.git_parent_path(tests_folder()) == project_folder()

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
    cli.expect_success("--help", "Manage git projects en masse")
    cli.expect_success("--version", "version")

    cli.expect_failure("--foo", "no such option")


def test_status(cli):
    # Note: using explicit lists below, to support case where used directory path may have a space in it
    # [wouldn't work if args passed as string, due to naive split in run()]
    # Status on a non-existing folder should fail
    cli.expect_failure("foo", "No folder 'foo'")

    # Status on this test folder should succeed and report no git folders found
    cli.expect_success(tests_folder(), "no git folders")

    # Status on project folder should succeed (we're not calling fetch)
    project = project_folder()
    cli.expect_success(project, "mgit")

    with runez.CurrentFolder(project):
        cli.run()
        assert cli.succeeded
        assert "%s:" % os.path.basename(project) in cli.logged.stdout

        cli.expect_success("-cs")
        cli.expect_failure("--ignore show", "applies to collections of checkouts")
