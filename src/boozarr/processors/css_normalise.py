"""CSS font/line-height/paragraph normalisation processor."""

from __future__ import annotations

from typing import Any

from boozarr.processors.base import BaseProcessor, Fix, Issue

_PARAGRAPH_PROPS = ["font-size", "line-height", "text-align", "margin", "padding"]


class CssNormaliseProcessor(BaseProcessor):
    name = "css_normalise"

    def check(self, epub: Any) -> list[Issue]:
        issues: list[Issue] = []
        props = getattr(epub, "css_properties", {})
        for prop in _PARAGRAPH_PROPS:
            val = props.get(prop)
            if val and val not in ("1em", "1.5", "left", "0"):
                issues.append(
                    Issue(
                        processor=self.name,
                        severity="info",
                        location=f"CSS ({prop})",
                        description=f"Non-standard {prop}: '{val}'",
                        fix_possible=True,
                    )
                )
        return issues

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        mapping = {
            "font-size": config.get("font_size", "1em"),
            "line-height": config.get("line_height", "1.5"),
            "text-align": "left",
            "margin": config.get("paragraph_spacing", "1em"),
            "padding": "0",
        }
        return [
            Fix(
                processor=self.name,
                location=i.location,
                description=f"Normalised {i.location}",
                old_value=i.description,
                new_value=f"{mapping.get(i.location.split()[-1].strip('()'), '1em')}",
            )
            for i in issues
        ]
