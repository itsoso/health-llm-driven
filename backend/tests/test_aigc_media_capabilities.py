import pytest


def test_happyhorse_video_capability_exposes_safe_product_choices():
    from app.services.aigc_media_capabilities import video_capability_for

    capability = video_capability_for(
        model="happyhorse-1.1-t2v",
        kind="text_to_video",
    )

    assert capability.minimum_duration_seconds == 3
    assert capability.maximum_duration_seconds == 15
    assert capability.selectable_duration_seconds == (5, 8, 15)
    assert capability.default_resolution == "720P"
    assert capability.supported_resolutions == ("720P", "1080P")
    assert capability.supports_ratio is True
    assert capability.generates_audio is True


def test_happyhorse_image_to_video_preserves_source_ratio():
    from app.services.aigc_media_capabilities import video_capability_for

    capability = video_capability_for(
        model="happyhorse-1.1-i2v",
        kind="image_to_video",
    )

    assert capability.supports_ratio is False


def test_wan_video_capability_preserves_two_second_backward_compatibility():
    from app.services.aigc_media_capabilities import validate_video_spec

    capability = validate_video_spec(
        model="wan2.7-t2v-2026-06-12",
        kind="text_to_video",
        duration_seconds=2,
        ratio="9:16",
        resolution="720P",
    )

    assert capability.minimum_duration_seconds == 2
    assert capability.maximum_duration_seconds == 15


def test_video_capability_rejects_sixteen_second_native_request():
    from app.services.aigc_media_capabilities import validate_video_spec

    with pytest.raises(ValueError, match="3 到 15"):
        validate_video_spec(
            model="happyhorse-1.1-t2v",
            kind="text_to_video",
            duration_seconds=16,
            ratio="9:16",
            resolution="720P",
        )
