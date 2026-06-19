"""Path and filesystem utility functions for boozarr."""

from pathlib import Path


def get_project_root() -> Path:
    """Resolve the project root directory.

    Returns the directory containing the ``src`` folder by traversing up
    from this file's location. When the package is installed in a standard
    location (site-packages), this returns three levels above the module
    file, which may not be meaningful — callers should not rely on this
    for production paths.
    """
    return Path(__file__).resolve().parent.parent.parent
