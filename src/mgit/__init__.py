from __future__ import annotations

from typing import TYPE_CHECKING

import runez

from mgit.git import GitDir, Reporter

if TYPE_CHECKING:
    from pathlib import Path


class ProjectDir:
    """One requested workspace, represented as one or more git dirs."""

    def __init__(self, path: Path):
        """
        :param Path path: Path to folder
        """
        self.path = path
        self.git_dirs: list[GitDir] = []
        self.name_size: int | None = None
        self.scan()

    def scan(self):
        self.git_dirs = [
            GitDir(source_path)
            for source_path in self.path.iterdir()
            if not source_path.name.startswith(".") and source_path.is_dir() and (source_path / ".git").is_dir()
        ]
        self.git_dirs = sorted(self.git_dirs, key=lambda x: x.basename)
        Reporter.abort_if(not self.git_dirs, f"{runez.short(self.path)}: no git folders")
        self.name_size = min(36, max(len(git.basename) for git in self.git_dirs)) if len(self.git_dirs) > 1 else None

    def prefixed_line(self, git: GitDir, line: str) -> str:
        name = git.basename
        if self.name_size:
            name = f"{name:>{self.name_size}}"

        return f"{name}: {line}"
