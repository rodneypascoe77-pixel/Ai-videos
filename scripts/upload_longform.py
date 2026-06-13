"""Upload a long-form deliverable folder's video.mp4 to YouTube (live).

    OFFLINE_MODE=false uv run python scripts/upload_longform.py <folder> ["Title"]

Uses the real YouTube publisher regardless of OFFLINE_MODE. Privacy comes from
YOUTUBE_PRIVACY (default private). Category = Education (27).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from config import get_settings
from posting.metadata import PostMetadata
from posting.publisher import YouTubePublisher


def main() -> None:
    folder = Path(sys.argv[1])
    video = folder / "video.mp4"
    if not video.exists():
        print(f"No video.mp4 in {folder}")
        return

    # Title/description: CLI arg, then title.txt, then folder name.
    if len(sys.argv) > 2:
        title = sys.argv[2]
    elif (folder / "title.txt").exists():
        title = (folder / "title.txt").read_text(encoding="utf-8").strip()
    else:
        title = folder.name.replace("-", " ").title()

    if (folder / "description.txt").exists():
        description = (folder / "description.txt").read_text(encoding="utf-8").strip()
    else:
        description = f"{title}\n\n#facts #educational #didyouknow"

    settings = get_settings()
    publisher = YouTubePublisher(token_file=settings.YOUTUBE_TOKEN_FILE)
    meta = PostMetadata(
        title=title[:100],
        description=description,
        tags=["facts", "educational", "space", "science", "did you know"],
        category_id="27",  # Education
    )

    print(f"Uploading {video.name} as '{title}' (privacy={settings.YOUTUBE_PRIVACY})...")
    result = publisher.publish(str(video), meta, settings.YOUTUBE_PRIVACY)
    print("\nSUCCESS")
    print("YouTube:", result.post_url)


if __name__ == "__main__":
    main()
