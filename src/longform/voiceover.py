"""Text-to-speech via edge-tts (free Microsoft neural voices, no API key)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from db.logging import get_logger

log = get_logger("longform.voiceover")


async def _synthesize(text: str, voice: str, dest: Path) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(dest))


def speak(text: str, voice: str, dest: Path) -> Path:
    """Synthesize `text` to an mp3 at `dest`. Returns the path."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(_synthesize(text, voice, dest))
    return dest


if __name__ == "__main__":
    from config import get_settings

    out = Path("data/longform/_voice_test.mp3")
    speak("This is a test of the faceless narration voice.", get_settings().LONGFORM_VOICE, out)
    print(f"Saved {out} ({out.stat().st_size} bytes)")
