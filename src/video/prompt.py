"""Turn a Script into the two prompts a video provider needs.

Runway's pipeline is text-to-image (a first frame) then image-to-video (motion).
We derive both from the script deterministically — no extra LLM call — so this
stage stays free and predictable. The script's premise gives the visual setup;
the title and premise give the motion intent.
"""

from __future__ import annotations

from db.models import Script

_STYLE = (
    "cinematic, high detail, natural lighting, single coherent scene, "
    "suitable for a short comedic vertical video"
)


def build_prompts(script: Script) -> tuple[str, str]:
    """Return (image_prompt, motion_prompt) for a script."""
    premise = (script.premise or script.title or "").strip()

    image_prompt = f"{premise}. {_STYLE}."

    motion_prompt = (
        f"{premise} Subtle, natural motion and camera movement that brings the "
        f"comedic moment to life. Keep the framing stable and the action readable."
    )
    return image_prompt[:1000], motion_prompt[:1000]
