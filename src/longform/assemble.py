"""Assemble a narrated video.

Visual layer, in order of preference:
  1. Stock footage (Pexels) matched to each segment, with a caption overlay.
  2. Fallback: a dark caption slide (Pillow) — used when no PEXELS_API_KEY.

Audio is edge-tts narration. No ImageMagick / system ffmpeg required.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from db.logging import get_logger
from longform import stock
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
    words, lines, cur = text.split(), [], ""
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
    """Opaque dark slide with a big centered caption (fallback visual)."""
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.text((80, 60), title[:70], font=_font(48), fill=ACCENT)

    cfont = _font(96)
    lines = _wrap(draw, caption, cfont, W - 320)
    line_h = (cfont.getbbox("Ay")[3] - cfont.getbbox("Ay")[1]) + 24
    y = (H - line_h * len(lines)) // 2
    for ln in lines:
        w = draw.textlength(ln, font=cfont)
        draw.text(((W - w) // 2, y), ln, font=cfont, fill=FG)
        y += line_h
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return dest


def _caption_overlay(caption: str, dest: Path) -> Path:
    """Transparent PNG: a lower-third bar + caption, to overlay on stock footage."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cfont = _font(72)
    lines = _wrap(draw, caption, cfont, W - 240)
    line_h = (cfont.getbbox("Ay")[3] - cfont.getbbox("Ay")[1]) + 18
    block_h = line_h * len(lines) + 80
    bar_top = H - block_h - 80
    # Semi-transparent bar
    draw.rectangle([0, bar_top, W, H - 40], fill=(10, 12, 16, 180))
    y = bar_top + 40
    for ln in lines:
        w = draw.textlength(ln, font=cfont)
        # simple shadow for legibility
        draw.text(((W - w) // 2 + 2, y + 2), ln, font=cfont, fill=(0, 0, 0, 220))
        draw.text(((W - w) // 2, y), ln, font=cfont, fill=(245, 245, 245, 255))
        y += line_h
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return dest


def _stock_background(clip_path: Path, duration: float):
    """A 1920x1080 stock clip covering the frame, looped/trimmed to `duration`."""
    from moviepy import VideoFileClip, concatenate_videoclips

    raw = VideoFileClip(str(clip_path)).without_audio()
    scale = max(W / raw.w, H / raw.h)
    sized = raw.resized(scale)
    sized = sized.cropped(width=W, height=H, x_center=sized.w / 2, y_center=sized.h / 2)

    if sized.duration >= duration:
        return sized.subclipped(0, duration)
    # loop by repeating until long enough
    reps = int(duration // sized.duration) + 1
    return concatenate_videoclips([sized] * reps).subclipped(0, duration)


def build_video(script: LongformScript, voice: str, out_dir: Path, fps: int = 24) -> Path:
    from moviepy import AudioFileClip, CompositeVideoClip, ImageClip, concatenate_videoclips

    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "_work"
    work.mkdir(exist_ok=True)

    use_stock = stock.available()
    log.info(f"Visual mode: {'stock footage' if use_stock else 'caption slides'}")

    # (narration, caption, visual_query)
    first_q = script.segments[0].visual_query if script.segments else script.title
    beats = [(script.hook, script.title, first_q)]
    beats += [(s.narration, s.on_screen_text, s.visual_query) for s in script.segments]

    clips = []
    for i, (narration, caption, query) in enumerate(beats):
        audio = AudioFileClip(str(speak(narration, voice, work / f"seg_{i}.mp3")))
        dur = audio.duration

        clip = None
        if use_stock:
            sclip = stock.fetch_clip(query, work / f"seg_{i}.mp4", min_duration=dur)
            if sclip is not None:
                try:
                    bg = _stock_background(sclip, dur)
                    overlay = (
                        ImageClip(str(_caption_overlay(caption, work / f"cap_{i}.png")))
                        .with_duration(dur)
                    )
                    clip = CompositeVideoClip([bg, overlay]).with_audio(audio)
                except Exception as exc:
                    log.warning(f"Stock compose failed (seg {i}); using slide", error=str(exc))

        if clip is None:  # fallback slide
            png = _slide(caption, script.title, work / f"seg_{i}.png")
            clip = ImageClip(str(png)).with_duration(dur).with_audio(audio)

        clips.append(clip)

    video = concatenate_videoclips(clips, method="chain")
    out_path = out_dir / "video.mp4"
    video.write_videofile(
        str(out_path), fps=fps, codec="libx264", audio_codec="aac", logger=None
    )
    log.info(f"Assembled long-form video: {out_path} ({video.duration:.0f}s)")
    return out_path
