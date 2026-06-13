"""Base interface for all trend sources.

A source fetches raw items from one external platform and returns them as
FetchedItem dataclasses. Persisting to the raw_trends table is handled centrally
by save_items() so every source stores evidence identically.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from db.models import RawTrend, Source
from db.session import session_scope


@dataclass
class FetchedItem:
    """A single raw item from a source, before it touches the DB."""

    source: Source
    title: str
    description: str | None = None
    url: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


class TrendSource(ABC):
    """Subclass per platform. Implement fetch(); call run() to fetch + persist."""

    source: Source  # set by subclass

    @abstractmethod
    def fetch(self) -> list[FetchedItem]:
        """Pull raw items from the platform. Implementations retry internally."""
        ...

    def run(self) -> list[int]:
        """Fetch then persist. Returns the new raw_trends row ids."""
        items = self.fetch()
        return save_items(items)


def save_items(items: list[FetchedItem]) -> list[int]:
    """Persist FetchedItems as RawTrend rows. Returns new row ids."""
    new_ids: list[int] = []
    if not items:
        return new_ids
    with session_scope() as session:
        for item in items:
            row = RawTrend(
                source=item.source,
                title=item.title[:1024],
                description=item.description,
                url=item.url,
                metrics_json=item.metrics or None,
            )
            session.add(row)
            session.flush()
            new_ids.append(row.id)
    return new_ids
