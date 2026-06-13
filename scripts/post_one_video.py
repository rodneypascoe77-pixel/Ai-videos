"""Post ONE specific video live to YouTube (private). Verification one-shot.

    OFFLINE_MODE=false uv run python scripts/post_one_video.py <video_id>
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from config import get_settings
from db.models import Post, Video
from db.session import session_scope
from posting.publisher import get_publisher
from posting.runner import _post_one


def main() -> None:
    video_id = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    settings = get_settings()
    publisher = get_publisher()
    print(f"Publisher: {publisher.name}  | privacy: {settings.YOUTUBE_PRIVACY}")
    if publisher.name != "youtube":
        print("Not in live mode (set OFFLINE_MODE=false). Aborting.")
        return

    print(f"Uploading video {video_id} to YouTube (this can take 10-60s)...")
    ok = _post_one(video_id, publisher, settings.YOUTUBE_PRIVACY)

    with session_scope() as session:
        post = (
            session.query(Post)
            .filter(Post.video_id == video_id)
            .order_by(Post.id.desc())
            .first()
        )
        video = session.get(Video, video_id)
        if ok and post:
            print("\nSUCCESS")
            print("Title:   ", post.title.encode("ascii", "replace").decode("ascii"))
            print("Privacy: ", post.privacy)
            print("YouTube: ", post.post_url)
            print("Video status:", video.status.value)
        else:
            print("\nFAILED")
            if post:
                print("Error:", (post.error or "")[:500])


if __name__ == "__main__":
    main()
