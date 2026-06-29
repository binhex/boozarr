"""Tests for boozarr utility functions."""

from __future__ import annotations

from boozarr.utils import normalize_css_value


class TestNormalizeCssValue:
    def test_bare_int_string_gets_px(self) -> None:
        assert normalize_css_value("10") == "10px"

    def test_negative_int_string_gets_px(self) -> None:
        assert normalize_css_value("-5") == "-5px"

    def test_zero_string_no_px(self) -> None:
        assert normalize_css_value("0") == "0"

    def test_int_value_gets_px(self) -> None:
        assert normalize_css_value(10) == "10px"

    def test_int_zero_no_px(self) -> None:
        assert normalize_css_value(0) == "0"

    def test_float_zero_no_px(self) -> None:
        assert normalize_css_value(0.0) == "0"

    def test_whole_float_gets_px(self) -> None:
        """normalize_css_value(10.0) should return '10px' not '10.0px'."""
        assert normalize_css_value(10.0) == "10px"

    def test_decimal_float_gets_px(self) -> None:
        """normalize_css_value(10.5) should return '10.5px'."""
        assert normalize_css_value(10.5) == "10.5px"

    def test_string_with_unit_unchanged(self) -> None:
        assert normalize_css_value("2em") == "2em"

    def test_string_decimals_unchanged(self) -> None:
        assert normalize_css_value("1.2") == "1.2"

    def test_string_negative_decimals_unchanged(self) -> None:
        assert normalize_css_value("-0.5") == "-0.5"

    def test_keyword_unchanged(self) -> None:
        assert normalize_css_value("center") == "center"
