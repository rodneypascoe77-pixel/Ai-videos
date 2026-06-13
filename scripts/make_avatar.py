"""Generate a channel avatar with RunwayML text-to-image and save it locally.

    uv run python scripts/make_avatar.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from config import get_settings

PROMPT = (
    "A friendly cartoon Bigfoot mascot character portrait, big expressive happy eyes, "
    "slight playful smirk, fluffy warm-brown fur, bold flat colors, thick clean outlines, "
    "centered head-and-shoulders, simple solid mint-green background, modern vector "
    "illustration style, high contrast, cute and approachable, designed as a circular "
    "profile-picture avatar, no text, no watermark"
)

# Try square-ish ratios first (avatars are cropped to a circle).
RATIOS = ["1024:1024", "1080:1080", "960:960", "1360:768"]


def main() -> None:
    from runwayml import RunwayML, TaskFailedError

    settings = get_settings()
    if not settings.RUNWAY_API_KEY:
        print("No RUNWAY_API_KEY set.")
        return

    client = RunwayML(api_key=settings.RUNWAY_API_KEY)

    last_err = None
    for ratio in RATIOS:
        try:
            print(f"Generating avatar at ratio {ratio} ...")
            task = client.text_to_image.create(
                model=settings.VIDEO_IMAGE_MODEL,
                prompt_text=PROMPT,
                ratio=ratio,
            ).wait_for_task_output()
            url = task.output[0]
            break
        except TaskFailedError as e:
            last_err = e
            print(f"  ratio {ratio} failed: {e.task_details}")
        except Exception as e:
            last_err = e
            print(f"  ratio {ratio} error: {e}")
    else:
        print("All ratios failed.", last_err)
        return

    out_dir = Path(__file__).resolve().parent.parent / "data" / "branding"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "avatar.png"
    with httpx.Client(timeout=60, follow_redirects=True) as c:
        resp = c.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)

    print(f"\nSaved: {dest}  ({len(resp.content) // 1024} KB)")
    print(f"Source URL: {url}")


if __name__ == "__main__":
    main()
