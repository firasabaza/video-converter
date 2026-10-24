"""Tests unitaires de la construction des arguments (sans lancer FFmpeg)."""

import pytest

from video_converter.encoders import BACKENDS, CPU_ENCODERS, QUALITIES, Capabilities, codec_of, video_args

ALL_ENCODERS = [e for b in BACKENDS.values() for e in b["encoders"].values()] + [
    e for encs in CPU_ENCODERS.values() for e in encs
]


@pytest.mark.parametrize("encoder", ALL_ENCODERS)
@pytest.mark.parametrize("quality", list(QUALITIES))
def test_every_encoder_has_args(encoder, quality):
    va = video_args(encoder, quality)
    assert va.args[:2] == ["-c:v", encoder]
    assert len(va.args) > 2, "aucun réglage de qualité"
    assert codec_of(encoder) is not None


def test_vaapi_uploads_frames_to_gpu():
    va = video_args("h264_vaapi", "balanced")
    assert va.pre_input[0] == "-vaapi_device"
    assert "format=nv12,hwupload" in va.args


def test_quality_presets_are_ordered():
    crf = [int(video_args("libx264", q).args[video_args("libx264", q).args.index("-crf") + 1]) for q in QUALITIES]
    assert crf == sorted(crf)


def test_pick_prefers_hardware_then_falls_back_to_cpu():
    caps = Capabilities(hardware={"nvenc": {"h264": "h264_nvenc"}}, cpu={"h264": "libx264", "hevc": "libx265"})
    assert caps.pick("h264") == "h264_nvenc"
    assert caps.pick("hevc") == "libx265"  # pas de HEVC matériel : CPU
    assert caps.pick("h264", "cpu") == "libx264"
    assert caps.pick("h264", "qsv") == "libx264"  # back-end absent : CPU
