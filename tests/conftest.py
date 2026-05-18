from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import runez
from runez.conftest import cli, ClickRunner  # noqa: F401, fixtures

from mgit.cli import main

ClickRunner.default_main = main
GIT_PATH = shutil.which("git")


class TempGitRepo:
    def __init__(self, relative_path: str, configure=True):
        cwd = Path.cwd().resolve()
        # Ensure this fixture is used together with `cli` fixture, which ensures we're in a temp folder
        # We can reconsider this later... but git operations here assume we're working in a temp folder
        assert cwd.is_relative_to(Path(tempfile.gettempdir()).resolve())
        self.cwd = cwd / relative_path
        if configure:
            self.run_git("config", "user.email", "tester@example.com")
            self.run_git("config", "user.name", "Test User")

    @classmethod
    def clone(cls, remote_url: str, relative_path: str) -> TempGitRepo:
        cls.ensure_parent(relative_path)
        cls.run_git_command("clone", remote_url, relative_path)
        repo = cls(relative_path)
        return repo

    @classmethod
    def init(cls, relative_path: str, configure=True, initial_branch="main", include_readme=True) -> TempGitRepo:
        cls.ensure_parent(relative_path)
        args = []
        if initial_branch:
            args.append(f"--initial-branch={initial_branch}")

        cls.run_git_command("init", *args, relative_path)
        repo = cls(relative_path, configure=configure)
        if include_readme:
            repo.add_file("README.md", f"# README for {relative_path}")
            repo.commit("Initial commit")

        return repo

    @classmethod
    def init_bare(cls, relative_path: str, initial_branch="main") -> TempGitRepo:
        cls.ensure_parent(relative_path)
        cls.run_git_command("init", "--bare", f"--initial-branch={initial_branch}", relative_path)
        return TempGitRepo(relative_path, configure=False)

    @staticmethod
    def ensure_parent(relative_path: str):
        parent = Path(relative_path).parent
        if parent != Path("."):
            parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def run_git_command(*args, check=True, cwd=None) -> str:
        if cwd:
            args = ["-C", str(cwd), *args]

        assert GIT_PATH
        proc = subprocess.run([GIT_PATH, *args], check=check, capture_output=True, text=True)  # noqa: S603
        return proc.stdout.strip()

    @classmethod
    def seeded(cls, relative_path="work") -> TempGitRepo:
        """Repo seeded with a remote"""
        return cls.seeded_set(relative_path).work

    @classmethod
    def seeded_set(cls, relative_path="work") -> SeededRepoSet:
        """Set of 3 repos, one remote, one seed and one work repo"""
        return SeededRepoSet(relative_path)

    def run_git(self, *args, check=True) -> str:
        return self.run_git_command(*args, check=check, cwd=self.cwd)

    def add(self, relative_path: str) -> str:
        return self.run_git("add", relative_path)

    def add_file(self, relative_path: str, contents: str):
        self.write_file(relative_path, contents)
        self.add(relative_path)

    def branch(self, *args) -> str:
        return self.run_git("branch", *args)

    def commit_file(self, relative_path: str, contents: str, message: str):
        self.add_file(relative_path, contents)
        self.commit(message)

    def checkout(self, *args) -> str:
        return self.run_git("checkout", *args)

    def commit(self, message="Initial commit") -> str:
        return self.run_git("commit", "-m", message)

    def push(self, *args) -> str:
        return self.run_git("push", *args)

    def remote(self, *args) -> str:
        return self.run_git("remote", *args)

    @property
    def current_branch(self) -> str:
        return self.branch("--show-current")

    def has_branch(self, name: str) -> bool:
        return bool(self.branch("--list", name))

    def write_file(self, relative_path: str, contents: str):
        runez.write(self.cwd / relative_path, contents + "\n", logger=None)


class SeededRepoSet:
    def __init__(self, relative_path: str):
        self.remote = TempGitRepo.init_bare(f"{relative_path}-bare.git")
        self.seed = TempGitRepo.init(f"{relative_path}-seed")
        self.seed.remote("add", "origin", self.remote_url)
        self.seed.push("-u", "origin", "main")
        self.work = TempGitRepo.clone(self.remote_url, relative_path)

    @property
    def remote_url(self):
        return str(self.remote.cwd)


@pytest.fixture
def git():
    return TempGitRepo
