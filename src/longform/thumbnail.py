"""Generate a simple, bold YouTube thumbnail (1280x720) with Pillow."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TW, TH = 1280, 720


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("arialbd.ttf", "arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make_thumbnail(title: str, dest: Path, bg_image: Path | None = None) -> Path:
    """Bold title card. If bg_image is given, use it darkened behind the text."""
    img = None
    if bg_image and bg_image.exists():
        try:
            base = Image.open(bg_image).convert("RGB").resize((TW, TH))
            img = Image.blend(base, Image.new("RGB", (TW, TH), (0, 0, 0)), 0.45)
        except Exception:
            img = None
    if img is None:
        img = Image.new("RGB", (TW, TH), (12, 14, 20))

    draw = ImageDraw.Draw(img)
    font = _font(96)
    # shrink font until it fits in ~4 lines
    lines = _wrap(draw, title.upper(), font, TW - 120)
    while len(lines) > 4 and font.size > 48:
        font = _font(font.size - 8)
        lines = _wrap(draw, title.upper(), font, TW - 120)

    line_h = (font.getbbox("Ay")[3] - font.getbbox("Ay")[1]) + 16
    y = (TH - line_h * len(lines)) // 2
    for ln in lines:
        w = draw.textlength(ln, font=font)
        x = (TW - w) // 2
        draw.text((x + 3, y + 3), ln, font=font, fill=(0, 0, 0))         # shadow
        draw.text((x, y), ln, font=font, fill=(255, 214, 89))            # gold
        y += line_h

    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return dest
