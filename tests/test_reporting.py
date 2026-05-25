from __future__ import annotations

from mgit.git import GitRunReport, Reporter


def check_sorting(given: GitRunReport | str, expected, max_chars=120):
    if not isinstance(given, GitRunReport):
        report = GitRunReport()
        for problem in given.split():
            report.add(problem=problem)

        given = report

    assert isinstance(given, GitRunReport)
    s = given.representation(max_chars=max_chars)
    assert s == expected


def test_reporting():
    # Sorting
    check_sorting("a b c", "a; b; c")  # Messages stay in order they were provided
    check_sorting("a b c b a", "a; b; c")  # No dupes
    check_sorting("a <b c", "b; a; c")  # < pushes message to front
    check_sorting("a <b <c d", "c; b; a; d")  # < ordered pushing
    check_sorting("a <b >c d", "b; a; d; c")  # > pushed message to back
    check_sorting("a <b >c <d >e f", "d; b; a; f; c; e")  # > ordered pushing

    # Typical issues
    check_sorting(GitRunReport().cant_pull(), "can't pull")
    check_sorting(GitRunReport().cant_pull("foo"), "can't pull; foo")

    # Empty messages are ignored
    check_sorting(GitRunReport().cant_pull().add(), "can't pull")
    check_sorting(GitRunReport().cant_pull().add(problem=""), "can't pull")

    # Adding another report
    r1 = GitRunReport(problem="p1", note="n1")
    r2 = GitRunReport(problem="p2", note="n2")
    check_sorting(GitRunReport(r1).add(r2), "p1; p2; n1; n2")

    # Problems come ahead of notes
    check_sorting(GitRunReport().add(problem="p1").add(problem="p2").add(problem="p3"), "p1; p2; p3")
    check_sorting(GitRunReport().add(problem="p1", note="n1").add(problem="p2"), "p1; p2; n1")

    # Progress comes ahead of notes, but after problems
    report = GitRunReport(problem="prob1")
    report.add(note="n1").add(note="<n2")
    report.add(progress="p1").add(progress="p2").add(progress="<p3")
    check_sorting(report, "prob1; p3; p1; p2; n2; n1")


def test_joining_display_fragments():
    assert Reporter.joined("main", None, "", False, 0, ["✅", "", "0"]) == "main ✅ 0"
    assert Reporter.joined("main", GitRunReport(), GitRunReport(note="note")) == "main note"
    assert Reporter.joined_lines(["first", "", None, ["second", 0]], header="header", indent="  ") == "header\n  first\n  second"


def test_truncating():
    # Lots of reports
    problems = ["some problem", "some other problem", "and yet another"]
    progress = ["some progress", "and some more"]
    notes = ["one note", "two notes", "and some really looooong note that just has to be truncated", "yup"]

    expected = "some problem; some other problem; and yet another; some progress; and some more; one note; two notes; and some really..."

    r = GitRunReport()
    for problem in problems:
        r.add(problem=problem)

    for progress_message in progress:
        r.add(progress=progress_message)

    for note in notes:
        r.add(note=note)

    check_sorting(r, expected)

    # Really long problem shadowing progress/notes
    problems = ["some problem", "plus some other problem", "and yet another"]
    problems.append("even more problems")
    problems.append("and some really really really loooong problem report that just has to be truncated")
    progress = ["progress won't show", "since problem too long"]

    expected = "some problem; plus some other problem; and yet another; even more problems; and some really really really loooong pro..."
    r = GitRunReport(note="note won't show either")
    for problem in problems:
        r.add(problem=problem)

    for progress_message in progress:
        r.add(progress=progress_message)

    check_sorting(r, expected)

    check_sorting(r, "some problem;...", max_chars=16)
