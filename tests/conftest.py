from runez.conftest import cli, ClickRunner  # noqa: F401, fixtures

from mgit.cli import main

ClickRunner.default_main = main
