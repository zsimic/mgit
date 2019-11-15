import os

import runez
from runez.conftest import cli

from mgit.cli import main


cli.default_main = main


def test_usage(cli):
    cli.expect_success("--help", "Manage git projects en masse")
    cli.expect_success("--version", "version")

    cli.expect_failure("--foo", "no such option")


def test_status(cli):
    # Note: using explicit lists below, to support case where used directory path may have a space in it
    # [wouldn't work if args passed as string, due to naive split in run()]
    # Status on a non-existing folder should fail
    bogus_path = "foo/non existing folder/bar"
    cli.expect_failure(["--no-color", bogus_path], "No folder", bogus_path)

    # Status on this test folder should succeed and report no git folders found
    test_folder = os.path.dirname(os.path.abspath(__file__))
    cli.expect_success(["--no-color", test_folder], "no git folders")

    # Status on project folder should succeed (we're not calling fetch)
    project_folder = os.path.dirname(test_folder)
    cli.expect_success(["--no-color", project_folder], "mgit")
    cli.expect_success(["--color", project_folder], "mgit")

    project = os.path.dirname(test_folder)
    with runez.CurrentFolder(test_folder):
        cli.run([])
        assert cli.succeeded
        assert "%s:" % os.path.basename(project) in cli.logged.stdout

        cli.expect_success(["-cs"])
        cli.expect_failure(["--ignore", "show"], "applies to collections of checkouts")
