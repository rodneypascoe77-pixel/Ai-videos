"""Shared retry decorator for external API calls (exponential back-off)."""

from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_exponential


def api_retry(max_attempts: int = 4, min_wait: float = 1.0, max_wait: float = 30.0):
    return retry(
        reraise=True,
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
    )
