"""Tests for the faceless long-form pipeline (no real TTS/render/API)."""

from __future__ import annotations

from unittest.mock import MagicMock

from longform.schema import LongformScript, Segment
from longform.script import ScriptWriter


def test_slug_is_filesystem_safe():
    from longform.runner import _slug

    assert _slug("The Neutron Star: Defies Everything!") == "the-neutron-star-defies-everything"
    assert _slug("") == "video"
    assert len(_slug("x" * 200)) <= 50


def test_wrap_breaks_long_lines():
    from PIL import Image, ImageDraw, ImageFont

    from longform.assemble import _wrap

    draw = ImageDraw.Draw(Image.new("RGB", (100, 100)))
    font = ImageFont.load_default()
    lines = _wrap(draw, "word " * 50, font, 200)
    assert len(lines) > 1  # wrapped into multiple lines


def test_script_writer_returns_parsed(monkeypatch):
    script = LongformScript(
        title="Amazing Space Fact",
        description="A short doc.",
        hook="What if a teaspoon weighed a billion tons?",
        segments=[
            Segment(narration="Neutron stars are incredibly dense.",
                    on_screen_text="Dense", visual_query="galaxy stars"),
            Segment(narration="They spin hundreds of times a second.",
                    on_screen_text="Fast", visual_query="spinning galaxy"),
        ],
    )
    writer = ScriptWriter.__new__(ScriptWriter)
    writer.model = "claude-sonnet-4-6"
    parsed = MagicMock()
    parsed.parsed_output = script
    writer.client = MagicMock()
    writer.client.messages.parse.return_value = parsed

    out = writer.write("space facts", 2)
    assert out.title == "Amazing Space Fact"
    assert len(out.segments) == 2
    # The niche + segment count should be in the prompt
    sent = writer.client.messages.parse.call_args.kwargs["messages"][0]["content"]
    assert "space facts" in sent
    assert "2 segments" in sent


def test_schema_roundtrip():
    s = LongformScript(
        title="t", description="d", hook="h",
        segments=[Segment(narration="n", on_screen_text="o", visual_query="q")],
    )
    assert s.segments[0].narration == "n"
    assert s.segments[0].visual_query == "q"


def test_stock_available_reflects_key(monkeypatch):
    from longform import stock

    monkeypatch.setenv("PEXELS_API_KEY", "")
    assert stock.available() is False
    monkeypatch.setenv("PEXELS_API_KEY", "abc123")
    assert stock.available() is True


def test_stock_fetch_returns_none_without_key(monkeypatch, tmp_path):
    from longform import stock

    monkeypatch.setenv("PEXELS_API_KEY", "")
    assert stock.fetch_clip("galaxy", tmp_path / "x.mp4") is None


def test_thumbnail_is_created(tmp_path):
    from longform.thumbnail import make_thumbnail

    dest = make_thumbnail("Some Bold Title About Space", tmp_path / "thumb.png")
    assert dest.exists()
    from PIL import Image

    img = Image.open(dest)
    assert img.size == (1280, 720)
