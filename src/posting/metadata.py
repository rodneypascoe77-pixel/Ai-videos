"""Build YouTube upload metadata (title/description/tags) from a script + trend.

Deterministic, no AI cost. Respects YouTube limits (title <=100 chars, tags
total <=500 chars).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from db.models import Script, Trend

# YouTube category 23 = Comedy
COMEDY_CATEGORY_ID = "23"

_STOPWORDS = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "his", "her"}


@dataclass
class PostMetadata:
    title: str
    description: str
    tags: list[str]
    category_id: str = COMEDY_CATEGORY_ID


def _keywords(text: str, limit: int = 8) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9']+", text.lower())
    seen: list[str] = []
    for w in words:
        if w in _STOPWORDS or len(w) < 3 or w in seen:
            continue
        seen.append(w)
        if len(seen) >= limit:
            break
    return seen


def build_metadata(script: Script, trend: Trend) -> PostMetadata:
    title = (script.title or trend.name or "AI Short").strip()[:100]

    hashtags = "#shorts #ai #comedy #funny"
    description = (
        f"{(script.premise or '').strip()}\n\n"
        f"{hashtags}\n\n"
        "Made with an automated AI video pipeline."
    ).strip()

    tag_pool = _keywords(f"{trend.name} {script.title} {script.premise or ''}")
    base_tags = ["AI", "shorts", "comedy", "funny", "AI video"]
    # Dedupe (case-insensitive) and cap total length to YouTube's ~500 char budget.
    tags: list[str] = []
    seen_lower = set()
    for t in base_tags + tag_pool:
        tl = t.lower()
        if tl in seen_lower:
            continue
        if sum(len(x) for x in tags) + len(t) > 480:
            break
        tags.append(t)
        seen_lower.add(tl)

    return PostMetadata(title=title, description=description[:5000], tags=tags)
