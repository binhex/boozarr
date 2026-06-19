"""Tests for Report formatter."""

from __future__ import annotations

from boozarr.report import Report


class TestReport:
    def test_log_line_ok(self) -> None:
        r = Report()
        line = r.log_line("/path/book.epub", "ok", issues=0, fixes=3)
        assert "OK" in line
        assert "book.epub" in line

    def test_log_line_warn(self) -> None:
        r = Report()
        line = r.log_line("/path/book.epub", "warn", issues=2, fixes=0)
        assert "WARN" in line

    def test_log_line_error(self) -> None:
        r = Report()
        line = r.log_line("/path/a.epub", "error", issues=0, fixes=0)
        assert "ERR" in line

    def test_log_line_skip(self) -> None:
        r = Report()
        line = r.log_line("/path/a.epub", "skip", issues=0, fixes=0)
        assert "SKIP" in line

    def test_final_summary_counts(self) -> None:
        r = Report()
        r.log_line("a.epub", "ok", issues=0, fixes=3)
        r.log_line("b.epub", "warn", issues=2, fixes=0)
        r.log_line("c.epub", "error", issues=0, fixes=0)
        r.log_line("d.epub", "skip", issues=0, fixes=0)
        s = r.final_summary(duration_s=12.4)
        assert "Processed: 4" in s
        assert "Issues found: 2" in s
        assert "Fixes applied: 3" in s

    def test_log_line_with_fix_details(self) -> None:
        r = Report()
        line = r.log_line(
            "/path/book.epub",
            "warn",
            issues=5,
            fixes=4,
            fix_details=[
                "metadata: Inferred title 'Foundation'",
                "metadata: Inferred author 'Isaac Asimov'",
                "borders: Normalised CSS (border)",
                "borders: Normalised CSS (margin)",
            ],
        )
        assert "5 issues, 4 fixes" in line
        assert "metadata" in line
        assert "Foundation" in line
        assert "borders" in line

    def test_final_summary_with_fix_breakdown(self) -> None:
        r = Report()
        r.log_line(
            "a.epub",
            "warn",
            issues=5,
            fixes=4,
            fix_details=[
                "chapters: Added 3 chapter entries",
                "metadata: Inferred title 'T'",
                "metadata: Inferred author 'A'",
                "borders: Normalised CSS (border)",
            ],
        )
        r.log_line("b.epub", "ok", issues=0, fixes=0)
        s = r.final_summary(duration_s=5.0)
        assert "Fixes applied: 4" in s
        assert "chapters" in s
        assert "metadata" in s
        assert "borders" in s
