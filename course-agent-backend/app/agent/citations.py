from __future__ import annotations

from contextvars import ContextVar, Token
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CitationCollector:
    """Collect verified retrieval evidence for one Agent request."""

    _items: list[dict[str, Any]] = field(default_factory=list)
    _by_chunk_id: dict[int, dict[str, Any]] = field(default_factory=dict)

    def register(self, item: dict[str, Any]) -> dict[str, Any]:
        chunk_id = int(item["chunk_id"])
        existing = self._by_chunk_id.get(chunk_id)
        if existing is not None:
            return deepcopy(existing)

        index = len(self._items) + 1
        citation = {
            **item,
            "citation_id": f"C{index}",
            "index": index,
            "chunk_id": chunk_id,
        }
        self._items.append(citation)
        self._by_chunk_id[chunk_id] = citation
        return deepcopy(citation)

    def snapshot(self) -> list[dict[str, Any]]:
        return deepcopy(self._items)


_active_collector: ContextVar[CitationCollector | None] = ContextVar(
    "active_agent_citation_collector",
    default=None,
)


def activate_citation_collector(collector: CitationCollector) -> Token:
    return _active_collector.set(collector)


def get_citation_collector() -> CitationCollector | None:
    return _active_collector.get()


def reset_citation_collector(token: Token) -> None:
    _active_collector.reset(token)
