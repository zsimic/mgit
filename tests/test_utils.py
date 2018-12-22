import os

from mgit.utils import pretty_path, represented_duration, SECONDS_IN_ONE_DAY


def test_pretty_path():
    assert pretty_path(None) == '.'
    assert pretty_path('') == '.'
    assert pretty_path('/foo') == '/foo'
    assert pretty_path('../foo') == '../foo'

    user_home = os.path.expanduser('~')
    assert pretty_path(user_home) == '~'
    assert pretty_path(os.path.join(user_home, 'foo')) == '~/foo'


def test_duration_representation():
    assert represented_duration(None) == ""
    assert represented_duration('foo') == "foo"

    assert represented_duration(0, short=False) == "0 seconds"
    assert represented_duration(1, short=False) == "1 second"
    assert represented_duration(5.1, short=False) == "5 seconds"

    assert represented_duration(65, short=False) == "1 minute 5 seconds"
    assert represented_duration(65, short=True) == "1m 5s"
    assert represented_duration(3667, short=True) == "1h 1m"
    assert represented_duration(3667, short=True, top=None) == "1h 1m 7s"

    assert represented_duration(8 * SECONDS_IN_ONE_DAY + 3673, short=True) == "1w 1d"
    assert represented_duration(8 * SECONDS_IN_ONE_DAY + 3673, short=False, top=None) == "1 week 1 day 1 hour 1 minute 13 seconds"

    assert represented_duration(8 * SECONDS_IN_ONE_DAY + 9720, short=False, top=3) == "1 week 1 day 2 hours"
    assert represented_duration(8 * SECONDS_IN_ONE_DAY + 9720, short=False, top=0) == "1 week 1 day 2 hours 42 minutes"
    assert represented_duration(8 * SECONDS_IN_ONE_DAY + 9725, short=False, top=0) == "1 week 1 day 2 hours 42 minutes 5 seconds"

    assert represented_duration(38 * SECONDS_IN_ONE_DAY + 3605, short=True, top=2, separator=', ') == "5w, 3d"
    assert represented_duration(38 * SECONDS_IN_ONE_DAY + 3605, short=True, top=0, separator=', ') == "5w, 3d, 1h, 5s"

    assert represented_duration(752 * SECONDS_IN_ONE_DAY, short=False, top=3, separator='+') == "2 years+3 weeks+1 day"
