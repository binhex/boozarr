"""Path and filesystem utility functions for boozarr."""

import re
from pathlib import Path

# Matches a bare integer (no decimal point, no letters) — used to detect
# bare-number CSS values that need a "px" suffix appended.
_BARE_INT_RE = re.compile(r"^-?\d+$")


def normalize_css_value(value: str | int | float) -> str:
    """Append ``px`` to bare numeric CSS values that lack a unit.

    CSS requires units on non-zero length values.  Integer and float
    values from Click options are converted to string with ``px``
    appended (except zero, which is unitless in CSS).  String values
    already carrying a unit (``"2em"``, ``"1.5"``), keywords
    (``"none"``, ``"center"``), and zero (``"0"``) are returned
    unchanged.
    """
    if isinstance(value, (int, float)):
        if value == 0:
            return "0"
        return str(int(value)) + "px" if value == int(value) else f"{value}px"
    if _BARE_INT_RE.match(value) and value.lstrip("-") != "0":
        return value + "px"
    return value


def get_project_root() -> Path:
    """Resolve the project root directory.

    Returns the directory containing the ``src`` folder by traversing up
    from this file's location. When the package is installed in a standard
    location (site-packages), this returns three levels above the module
    file, which may not be meaningful — callers should not rely on this
    for production paths.
    """
    return Path(__file__).resolve().parent.parent.parent
