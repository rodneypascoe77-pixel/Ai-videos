"""Path B orchestration: topic -> script -> voiceover -> stock video -> package.

Each video is produced as a self-contained deliverable folder under
data/longform/<slug>/:
    video.mp4         the finished narrated video
    thumbnail.png     a 1280x720 YouTube thumbnail
    title.txt         the title
    description.txt   the description + tags
    script.json       the full script (so a buyer can edit/re-voice)

This package is exactly what you hand a client, upload yourself, or sell.

    python -m longform.runner                 # one video on the configured niche
    python -m longform.runner "black holes"   # one video on a specific topic
"""

from __future__ import annotations

import json
import re
import sys

from config import DATA_DIR, get_settings
from db.logging import get_logger
from longform.assemble import build_video
from longform.script import ScriptWriter
from longform.thumbnail import make_thumbnail

log = get_logger("longform.runner")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "video"


def make_one(
    topic: str | None = None, segments: int | None = None, niche: str | None = None
) -> dict:
    settings = get_settings()
    n = segments or settings.LONGFORM_SEGMENTS
    use_niche = niche or settings.LONGFORM_NICHE

    script = ScriptWriter().write(use_niche, n, topic=topic)
    out_dir = DATA_DIR / "longform" / _slug(script.title)
    out_dir.mkdir(parents=True, exist_ok=True)

    video_path = build_video(script, settings.LONGFORM_VOICE, out_dir)

    # Deliverable package
    frame = out_dir / "frame.png"
    thumb = make_thumbnail(
        script.title, out_dir / "thumbnail.png",
        bg_image=frame if frame.exists() else None,
    )
    (out_dir / "title.txt").write_text(script.title, encoding="utf-8")
    (out_dir / "description.txt").write_text(
        f"{script.description}\n\n#facts #educational #didyouknow", encoding="utf-8"
    )
    (out_dir / "script.json").write_text(
        json.dumps(script.model_dump(), indent=2), encoding="utf-8"
    )

    log.info(f"Packaged deliverable: {out_dir}")
    return {
        "title": script.title,
        "segments": len(script.segments) + 1,
        "folder": str(out_dir),
        "video_path": str(video_path),
        "thumbnail": str(thumb),
    }


def make_batch(count: int, niche: str | None = None) -> list[dict]:
    """Produce `count` videos on the niche — for stocking a channel or a client order."""
    results = []
    for i in range(count):
        log.info(f"Batch video {i + 1}/{count}")
        try:
            results.append(make_one(niche=niche))
        except Exception as exc:
            log.error("Batch video failed", index=i, error=str(exc))
    return results


if __name__ == "__main__":
    topic_arg = sys.argv[1] if len(sys.argv) > 1 else None
    result = make_one(topic=topic_arg)
    print("\nDeliverable ready:")
    print(f"  Title:     {result['title']}")
    print(f"  Folder:    {result['folder']}")
    print(f"  Video:     {result['video_path']}")
    print(f"  Thumbnail: {result['thumbnail']}")
