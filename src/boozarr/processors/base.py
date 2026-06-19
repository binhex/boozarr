"""Base processor abstract class and data models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class Issue:
    processor: str
    severity: str
    location: str
    description: str
    fix_possible: bool = True


@dataclass
class Fix:
    processor: str
    location: str
    description: str
    old_value: str = ""
    new_value: str = ""


class BaseProcessor(ABC):
    name: str = ""

    @abstractmethod
    def check(self, epub: Any) -> list[Issue]: ...

    @abstractmethod
    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]: ...
