"""Assemble a narrated video: caption slides (Pillow) + voiceover (edge-tts).

Each segment becomes a slide (dark background + big centered caption) shown for
exactly as long as its narration audio. Slides are concatenated into one MP4.
No ImageMagick needed — text is rendered with Pillow.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from db.logging import get_logger
from longform.schema import LongformScript
from longform.voiceover import speak

log = get_logger("longform.assemble")

W, H = 1920, 1080
BG = (15, 17, 21)
FG = (235, 235, 235)
ACCENT = (158, 193, 255)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("arialbd.ttf", "arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _slide(caption: str, title: str, dest: Path) -> Path:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Title strip at top
    tfont = _font(48)
    draw.text((80, 60), title[:70], font=tfont, fill=ACCENT)

    # Centered caption
    cfont = _font(96)
    lines = _wrap(draw, caption, cfont, W - 320)
    line_h = (cfont.getbbox("Ay")[3] - cfont.getbbox("Ay")[1]) + 24
    total_h = line_h * len(lines)
    y = (H - total_h) // 2
    for ln in lines:
        w = draw.textlength(ln, font=cfont)
        draw.text(((W - w) // 2, y), ln, font=cfont, fill=FG)
        y += line_h

    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return dest


def build_video(script: LongformScript, voice: str, out_dir: Path, fps: int = 24) -> Path:
    """Render the script to an MP4 in out_dir. Returns the output path."""
    from moviepy import AudioFileClip, ImageClip, concatenate_videoclips

    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "_work"
    work.mkdir(exist_ok=True)

    # Treat the hook as the first spoken beat (with the title as its caption).
    beats: list[tuple[str, str]] = [(script.hook, script.title)]
    beats += [(seg.narration, seg.on_screen_text) for seg in script.segments]

    clips = []
    for i, (narration, caption) in enumerate(beats):
        mp3 = speak(narration, voice, work / f"seg_{i}.mp3")
        audio = AudioFileClip(str(mp3))
        png = _slide(caption, script.title, work / f"seg_{i}.png")
        clip = ImageClip(str(png)).with_duration(audio.duration).with_audio(audio)
        clips.append(clip)
        log.debug(f"segment {i}: {audio.duration:.1f}s")

    video = concatenate_videoclips(clips, method="chain")
    out_path = out_dir / "video.mp4"
    video.write_videofile(
        str(out_path),
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )
    log.info(f"Assembled long-form video: {out_path} ({video.duration:.0f}s)")
    return out_path
