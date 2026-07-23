"""Authoritative video-model capabilities used by API, jobs, and UI projections."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


VideoKind = Literal["text_to_video", "image_to_video"]
VIDEO_RATIOS = ("16:9", "9:16", "1:1", "4:3", "3:4")
VIDEO_RESOLUTIONS = ("720P", "1080P")


@dataclass(frozen=True)
class VideoModelCapability:
    minimum_duration_seconds: int
    maximum_duration_seconds: int
    selectable_duration_seconds: tuple[int, ...]
    default_resolution: str
    supported_resolutions: tuple[str, ...]
    supports_ratio: bool
    generates_audio: bool


def video_capability_for(*, model: str, kind: VideoKind) -> VideoModelCapability:
    """Return the product-safe capability contract for a persisted model."""
    normalized_model = str(model or "").strip().lower()
    is_happyhorse = normalized_model.startswith("happyhorse-")
    return VideoModelCapability(
        # Preserve the historical Wan contract while keeping HappyHorse within
        # its documented 3-15 second native range.
        minimum_duration_seconds=3 if is_happyhorse else 2,
        maximum_duration_seconds=15,
        selectable_duration_seconds=(5, 10, 15),
        default_resolution="720P",
        supported_resolutions=VIDEO_RESOLUTIONS,
        # HappyHorse I2V preserves the first frame's aspect ratio.
        supports_ratio=not (is_happyhorse and kind == "image_to_video"),
        generates_audio=is_happyhorse,
    )


def validate_video_spec(
    *,
    model: str,
    kind: VideoKind,
    duration_seconds: int,
    ratio: str,
    resolution: str,
) -> VideoModelCapability:
    """Validate a billable request against the frozen model capability."""
    capability = video_capability_for(model=model, kind=kind)
    duration = int(duration_seconds)
    if not capability.minimum_duration_seconds <= duration <= capability.maximum_duration_seconds:
        raise ValueError(
            f"短视频时长需在 {capability.minimum_duration_seconds} 到 "
            f"{capability.maximum_duration_seconds} 秒之间"
        )
    if str(ratio) not in VIDEO_RATIOS:
        raise ValueError("不支持的视频比例")
    if str(resolution).upper() not in capability.supported_resolutions:
        raise ValueError("不支持的视频清晰度")
    return capability
