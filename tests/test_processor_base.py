"""Tests for BaseProcessor, Issue, Fix."""

from __future__ import annotations

import pytest

from boozarr.processors.base import BaseProcessor, Fix, Issue


class TestIssueFix:
    def test_issue_defaults(self) -> None:
        i = Issue(
            processor="chapters",
            severity="warn",
            location="toc.ncx",
            description="Empty ToC",
        )
        assert i.fix_possible is True

    def test_fix_defaults(self) -> None:
        f = Fix(
            processor="chapters",
            location="toc.ncx",
            description="Injected 5 chapters",
            new_value="<navMap>...</navMap>",
        )
        assert f.old_value == ""


class TestBaseProcessor:
    def test_instantiate_abstract_raises(self) -> None:
        with pytest.raises(TypeError):
            BaseProcessor()  # type: ignore[abstract]

    def test_concrete_processor(self) -> None:
        class P(BaseProcessor):
            name = "test"

            def check(self, epub, config=None):  # type: ignore[no-untyped-def]
                return [Issue(self.name, "info", "loc", "desc")]

            def fix(self, epub, issues, config):  # type: ignore[no-untyped-def]
                return [Fix(self.name, "loc", "fixed", new_value="x")]

        p = P()
        assert p.name == "test"
        assert len(p.check(None)) == 1
        assert len(p.fix(None, [], {})) == 1
