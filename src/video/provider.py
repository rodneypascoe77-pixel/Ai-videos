"""Video-generation provider abstraction.

Two implementations behind one interface:
  * StubVideoProvider  — deterministic fake output, FREE. Used when OFFLINE_MODE.
  * RunwayVideoProvider — real RunwayML calls (text-to-image -> image-to-video), PAID.

get_provider() picks based on config so the rest of the pipeline never branches
on which one is active.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass

from config import get_settings
from db.logging import get_logger

log = get_logger("video.provider")


@dataclass
class VideoResult:
    """Outcome of a single generation request."""

    video_url: str
    provider_job_id: str | None = None
    duration_seconds: int | None = None


class VideoProviderError(RuntimeError):
    """Raised when a provider fails to produce a video."""


class VideoProvider(ABC):
    name: str

    @abstractmethod
    def generate(self, image_prompt: str, motion_prompt: str) -> VideoResult:
        """Produce a video from a first-frame image prompt + a motion/scene prompt."""
        ...


class StubVideoProvider(VideoProvider):
    """Free, offline fake. Returns a deterministic placeholder URL — no API calls."""

    name = "stub"

    def generate(self, image_prompt: str, motion_prompt: str) -> VideoResult:
        digest = hashlib.sha1((image_prompt + "|" + motion_prompt).encode()).hexdigest()[:12]
        log.info("Stub video generated", job=digest)
        return VideoResult(
            video_url=f"https://stub.local/videos/{digest}.mp4",
            provider_job_id=f"stub_{digest}",
            duration_seconds=5,
        )


class RunwayVideoProvider(VideoProvider):
    """Real RunwayML provider: text-to-image (first frame) then image-to-video."""

    name = "runway"

    def __init__(
        self,
        api_key: str,
        model: str,
        image_model: str,
        ratio: str,
        duration: int,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.image_model = image_model
        self.ratio = ratio
        self.duration = duration

    def _client(self):
        # Lazy import so the SDK is only needed when actually running live.
        from runwayml import RunwayML

        return RunwayML(api_key=self.api_key)

    def generate(self, image_prompt: str, motion_prompt: str) -> VideoResult:
        from runwayml import TaskFailedError

        client = self._client()
        try:
            # 1) First frame: text -> image
            image_task = client.text_to_image.create(
                model=self.image_model,
                prompt_text=image_prompt,
                ratio=_image_ratio(self.ratio),
            ).wait_for_task_output()
            image_url = image_task.output[0]

            # 2) Animate: image -> video
            video_task = client.image_to_video.create(
                model=self.model,
                prompt_image=image_url,
                prompt_text=motion_prompt,
                ratio=self.ratio,
                duration=self.duration,
            ).wait_for_task_output()
            video_url = video_task.output[0]
        except TaskFailedError as exc:
            raise VideoProviderError(f"RunwayML task failed: {exc.task_details}") from exc
        except Exception as exc:  # network, auth, SDK errors
            raise VideoProviderError(f"RunwayML error: {exc}") from exc

        return VideoResult(
            video_url=video_url,
            provider_job_id=getattr(video_task, "id", None),
            duration_seconds=self.duration,
        )


def _image_ratio(video_ratio: str) -> str:
    """gen4_image expects slightly different ratios than gen4.5 video.

    Map the common landscape/portrait video ratios to supported image ratios.
    """
    return {
        "1280:720": "1360:768",
        "720:1280": "768:1360",
    }.get(video_ratio, "1360:768")


def get_provider() -> VideoProvider:
    """Return the configured provider. Stub when OFFLINE_MODE, else RunwayML."""
    settings = get_settings()
    if settings.OFFLINE_MODE:
        return StubVideoProvider()
    if not settings.RUNWAY_API_KEY:
        raise VideoProviderError(
            "OFFLINE_MODE is false but RUNWAY_API_KEY is not set. "
            "Add the key to .env or set OFFLINE_MODE=true."
        )
    return RunwayVideoProvider(
        api_key=settings.RUNWAY_API_KEY,
        model=settings.VIDEO_MODEL,
        image_model=settings.VIDEO_IMAGE_MODEL,
        ratio=settings.VIDEO_RATIO,
        duration=settings.VIDEO_DURATION,
    )
