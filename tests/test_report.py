"""Tests for Report formatter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from boozarr.report import Report

if TYPE_CHECKING:
    from pathlib import Path


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
        # Top and bottom borders
        assert s.startswith("─" * 40)
        assert "Files processed:  4  (1 skipped, 1 errors)" in s
        assert "Issues found:     2" in s
        assert "Fixes applied:    3" in s
        # No fix breakdown since no fix_details were provided
        assert "Fixes by processor:" not in s
        assert "Duration: 12.4s" in s
        assert s.endswith("Duration: 12.4s")

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
        # Border lines
        assert s.startswith("─" * 40)
        assert "Files processed:  2  (0 skipped, 0 errors)" in s
        assert "Issues found:     5" in s
        assert "Fixes applied:    4" in s
        # Fix breakdown section
        assert "Fixes by processor:" in s
        assert "borders           1   Normalised CSS (border)" in s
        assert "chapters          1   Added 3 chapter entries" in s
        assert "metadata          2   Inferred title 'T', Inferred author 'A'" in s
        assert "Duration: 5.0s" in s

    def test_log_line_shows_dry_run_indicator(self) -> None:
        r = Report()
        line = r.log_line("/path/book.epub", "warn", issues=2, fixes=0, dry_run=True)
        assert "(dry-run)" in line, "Dry-run indicator should be in output"
        assert "2 issues, 0 fixes" in line

    def test_log_line_no_dry_run_indicator_when_not_dry(self) -> None:
        r = Report()
        line = r.log_line("/path/book.epub", "warn", issues=2, fixes=1, dry_run=False)
        assert "(dry-run)" not in line, "No dry-run indicator in normal mode"

    def test_pipeline_dry_run_includes_fix_details(self, tmp_path: Path) -> None:
        """Dry-run should include fix_details in the result, same as fix mode."""
        import zipfile

        from boozarr.db import ProcessingDB
        from boozarr.pipeline import Pipeline

        epub_path = tmp_path / "book.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
            zf.writestr("OEBPS/styles.css", "body { border: 5px; }")
            zf.writestr("OEBPS/ch1.xhtml", "<p>Text</p>")

        db = ProcessingDB(tmp_path / "test.db")
        from boozarr.processors.borders import BordersProcessor

        pipeline = Pipeline(
            db=db,
            processors=[BordersProcessor()],
            config={"border": "1px"},
            fix=False,
        )
        result = pipeline.process_epub(epub_path)

        # Should have fix_details even though it's a dry-run
        assert "fix_details" in result
        assert len(result["fix_details"]) > 0, f"Dry-run should have fix_details, got {result['fix_details']}"
        assert "border" in result["fix_details"][0].lower()
        assert result["dry_run"] is True
