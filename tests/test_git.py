from mgit.git import GitURL, is_valid_branch_name


def test_valid_branch_names():
    assert is_valid_branch_name("foo")
    assert is_valid_branch_name("feature/foo")
    assert is_valid_branch_name("feature/foo.bar")


def test_invalid_branch_names():
    assert not is_valid_branch_name(None)
    assert not is_valid_branch_name("")
    assert not is_valid_branch_name("~/foo")
    assert not is_valid_branch_name("foo..bar")
    assert not is_valid_branch_name("foo bar")


def check_url(url, protocol, hostname, username, relative_path, repo, name):
    u = GitURL()
    u.set(url)
    assert str(u) == (url or '')
    assert u.url == (url or '')
    assert u.protocol == protocol
    assert u.hostname == hostname
    assert u.username == username
    assert u.relative_path == relative_path
    assert u.name == name
    assert u.repo == repo


def test_git_urls():
    check_url(None, "unknown", "unknown", None, "", "unknown", "unknown")
    check_url("", "unknown", "unknown", None, "", "unknown", "unknown")
    check_url("~/foo/bar", "file", "local", None, "~/foo/bar", "foo", "bar")
    check_url("/some/repo/foo", "file", "local", None, "/some/repo/foo", "repo", "foo")

    check_url(
        "ssh://git@stash.corp.foo.com:7999/myproject/bin.git",
        "ssh",
        "stash.corp.foo.com",
        "git",
        "/myproject/bin.git",
        "myproject",
        "bin"
    )
    check_url(
        "https://user@stash.corp.foo.com/scm/myproject/bin.git",
        "https",
        "stash.corp.foo.com",
        "user",
        "/scm/myproject/bin.git",
        "myproject",
        "bin"
    )

    check_url("git@github.com:foo/vmaf.git", "ssh", "github.com", "git", "foo/vmaf.git", "foo", "vmaf")
    check_url("https://github.com/foo/vmaf.git", "https", "github.com", None, "/foo/vmaf.git", "foo", "vmaf")

    check_url("git@example.com:80/foo/vmaf.git", "ssh", "example.com", "git", "/foo/vmaf.git", "foo", "vmaf")
