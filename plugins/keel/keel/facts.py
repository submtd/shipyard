"""Facts about the world. Tri-state throughout; no I/O in this module."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Tri(str, Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"

    @classmethod
    def of(cls, value):
        """Coerce an optional bool into a Tri. None -> UNKNOWN."""
        if value is None:
            return cls.UNKNOWN
        return cls.TRUE if value else cls.FALSE

    def __bool__(self):
        raise TypeError("Tri is three-valued; compare explicitly (x is Tri.TRUE).")


@dataclass(frozen=True)
class Facts:
    branch: str | None = None
    capability: Tri = Tri.UNKNOWN
    pr_base: str | None = None
    pr_head: str | None = None
    pr_is_fork: Tri = Tri.UNKNOWN
    pr_review_state: str | None = None
    changelog_ok: Tri = Tri.UNKNOWN
    changelog_present: Tri = Tri.UNKNOWN

    @classmethod
    def unknown(cls):
        return cls()
