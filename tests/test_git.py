from cached_property import cached_property

from mgit.git import GitURL, is_valid_branch_name, reset_cached_properties


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


class SomeClass:
    """Object with 2 cached properties, each with their own side effect"""

    def __init__(self):
        self.number1 = 0
        self.number2 = 0

    @cached_property
    def touch1(self):
        self.number1 += 1
        return self.number1

    @cached_property
    def touch2(self):
        self.number2 += 1
        return self.number2

    @property
    def sum(self):
        return self.number1 + self.number2


def check_side_effect(obj, expected1, expected2):
    assert obj.touch1 == expected1
    assert obj.touch1 == expected1                          # Second call to cached property should have no effect
    assert obj.touch2 == expected2
    assert obj.touch2 == expected2
    assert obj.number1 == expected1
    assert obj.number2 == expected2
    assert obj.sum == expected1 + expected2


def test_cached_properties():
    # Verify that calling with None doesn't crash
    reset_cached_properties(None)
    reset_cached_properties(None, 'foo bar')

    # Verify that calling on an object that doesn't have cached properties has no effect
    obj = 'foo'
    reset_cached_properties(obj)
    reset_cached_properties(obj, 'foo')
    reset_cached_properties(obj, 'upper')
    assert obj == 'foo'

    # Test with an object that has cached properties
    obj = SomeClass()

    # First, verify that several calls have one side effect (cached property)
    check_side_effect(obj, 1, 1)

    # Verify that resetting bogus name has no effect
    reset_cached_properties(obj, 'foo')
    check_side_effect(obj, 1, 1)

    # Verify that resetting a non-cached-property has no effect
    reset_cached_properties(obj, 'sum')
    check_side_effect(obj, 1, 1)

    # Reset all cached properties, and verify all properties were indeed reset
    reset_cached_properties(obj)
    check_side_effect(obj, 2, 2)

    # Reset only the first one now, and verify it only has been touched
    reset_cached_properties(obj, 'touch1')
    check_side_effect(obj, 3, 2)

    # Reset multiple using an array
    reset_cached_properties(obj, ['touch1', 'touch2'])
    check_side_effect(obj, 4, 3)

    # Reset multiple using a string
    reset_cached_properties(obj, 'touch1 touch2')
    check_side_effect(obj, 5, 4)

    # Reset all except one
    reset_cached_properties(obj, '-touch1')
    check_side_effect(obj, 5, 5)

    # Reset all except both
    reset_cached_properties(obj, '-touch1 touch2')
    check_side_effect(obj, 5, 5)

    # Bogus except
    reset_cached_properties(obj, '-foo touch2')
    check_side_effect(obj, 6, 5)
