from __future__ import absolute_import

import os

from click.testing import CliRunner

from mgit.cli import main


def run(args):
    """
    :param str|list args: Command line args
    :return click.testing.Result:
    """
    runner = CliRunner()
    if not isinstance(args, list):
        args = args.split()
    result = runner.invoke(main, args=args)
    return result


def expect_messages(result, *messages):
    for message in messages:
        if message[0] == '!':
            assert message[1:] not in result
        else:
            assert message in result


def expect_success(args, *messages):
    result = run(args)
    assert result.exit_code == 0
    expect_messages(result.output, *messages)


def expect_failure(args, *messages):
    result = run(args)
    assert result.exit_code != 0
    expect_messages(result.output, *messages)


def test_help():
    expect_success('--help', "Manage git projects en masse", "See http://go/mgit")


def test_invalid():
    expect_failure('--foo', "no such option")


def test_status():
    # Note: using explicit lists below, to support case where used directory path may have a space in it
    # [wouldn't work if args passed as string, due to naive split in run()]
    # Status on a non-existing folder should fail
    bogus_path = 'foo/non existing folder/bar'
    expect_failure(['--no-color', bogus_path], "is not a directory", bogus_path)

    # Status on this test folder should succeed and report no git folders found
    test_folder = os.path.dirname(os.path.abspath(__file__))
    expect_success(['--no-color', test_folder], "no git folders")

    # Status on project folder should succeed (we're not calling fetch)
    project_folder = os.path.dirname(test_folder)
    expect_success(['--no-color', project_folder], "mgit")
    expect_success(['--color', project_folder], "mgit")
