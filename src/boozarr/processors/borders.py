"""CSS border/margin/padding normalisation processor."""

from __future__ import annotations

from typing import Any

from boozarr.processors.base import BaseProcessor, Fix, Issue

_TARGET = [
    "border",
    "border-width",
    "margin",
    "padding",
    "margin-left",
    "margin-right",
    "padding-left",
    "padding-right",
]


class BordersProcessor(BaseProcessor):
    name = "borders"

    def check(self, epub: Any) -> list[Issue]:
        issues: list[Issue] = []
        props = getattr(epub, "css_properties", {})
        for prop in _TARGET:
            val = props.get(prop)
            if val and val not in ("none", "0", "1em"):
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
        target_map = {
            "border": config.get("border", "none"),
            "border-width": config.get("border", "none"),
            "margin": config.get("margin", "1em"),
            "margin-left": config.get("margin", "1em"),
            "margin-right": config.get("margin", "1em"),
            "padding": config.get("padding", "0"),
            "padding-left": config.get("padding", "0"),
            "padding-right": config.get("padding", "0"),
        }
        return [
            Fix(
                processor=self.name,
                location=i.location,
                description=f"Normalised {i.location}",
                old_value=i.description,
                new_value=target_map.get(i.location.split()[-1].strip("()"), "none"),
            )
            for i in issues
        ]
