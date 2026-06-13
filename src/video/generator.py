"""Generate a video for a single selected script via the configured provider.

Creates a Video row (pending), calls the provider, and records the outcome
(completed + URL, or failed + error). On success the source Script is marked used.
"""

from __future__ import annotations

from datetime import datetime, timezone

from db.logging import get_logger
from db.models import Script, ScriptStatus, Video, VideoStatus
from db.session import session_scope
from video.prompt import build_prompts
from video.provider import VideoProvider, VideoProviderError, get_provider

log = get_logger("video.generator")


class VideoGenerator:
    def __init__(self, provider: VideoProvider | None = None) -> None:
        self.provider = provider or get_provider()

    def generate_for_script(self, script_id: int) -> int | None:
        """Generate one video for a script. Returns the Video row id (or None on failure)."""
        with session_scope() as session:
            script = session.get(Script, script_id)
            if script is None:
                raise ValueError(f"Script {script_id} not found")
            image_prompt, motion_prompt = build_prompts(script)

            video = Video(
                script_id=script_id,
                provider=self.provider.name,
                image_prompt=image_prompt,
                prompt_text=motion_prompt,
                status=VideoStatus.generating,
            )
            session.add(video)
            session.flush()
            video_id = video.id

        try:
            result = self.provider.generate(image_prompt, motion_prompt)
        except VideoProviderError as exc:
            log.error("Video generation failed", script_id=script_id, error=str(exc))
            with session_scope() as session:
                v = session.get(Video, video_id)
                v.status = VideoStatus.failed
                v.error = str(exc)[:2000]
            return None

        now = datetime.now(timezone.utc)
        with session_scope() as session:
            v = session.get(Video, video_id)
            v.status = VideoStatus.completed
            v.video_url = result.video_url
            v.provider_job_id = result.provider_job_id
            v.duration_seconds = result.duration_seconds
            v.completed_at = now
            # Mark the source script as used
            script = session.get(Script, script_id)
            if script is not None:
                script.status = ScriptStatus.used

        log.info(f"Video completed for script {script_id}", video_id=video_id)
        return video_id
