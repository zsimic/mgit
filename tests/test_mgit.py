import runez


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
