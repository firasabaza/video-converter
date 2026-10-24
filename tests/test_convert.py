"""Tests d'intégration : vraies conversions avec le FFmpeg installé."""

import shutil
import subprocess
from pathlib import Path

import pytest

from video_converter.converter import Job, convert
from video_converter.encoders import detect

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg n'est pas installé")


@pytest.fixture(scope="module")
def sample(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("src") / "sample.mkv"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=2",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(path)],
        check=True,
    )
    return path


@pytest.fixture(scope="module")
def caps():
    return detect()


def probe(path: Path) -> str:
    return subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def run(sample, caps, out, fmt, codec, **kw) -> Job:
    job = Job(name=sample.name, input_path=sample, fmt=fmt, codec=codec, quality="small", **kw)
    convert(job, caps, out)
    assert job.status == "done", job.message
    assert job.output_path.exists()
    return job


@pytest.mark.parametrize("fmt,codec,expected", [
    ("mp4", "h264", "h264"),
    ("mkv", "hevc", "hevc"),
    ("mov", "h264", "h264"),
    ("webm", "vp9", "vp9"),
    ("avi", "mpeg4", "mpeg4"),
    ("mp4", "av1", "av1"),
    ("mp4", "copy", "h264"),
])
def test_formats(sample, caps, tmp_path, fmt, codec, expected):
    job = run(sample, caps, tmp_path, fmt, codec)
    assert job.output_path.suffix == "." + fmt
    assert probe(job.output_path) == expected


def test_uses_hardware_when_available(sample, caps, tmp_path):
    job = run(sample, caps, tmp_path, "mp4", "h264")
    if caps.hardware:
        assert job.encoder_used != "libx264" and not job.fallback
    else:
        assert job.encoder_used == "libx264"


def test_cpu_backend(sample, caps, tmp_path):
    job = run(sample, caps, tmp_path, "mp4", "h264", backend="cpu")
    assert job.encoder_used == "libx264" and job.accelerator == "CPU"


def test_forced_cpu_detection(sample, tmp_path):
    cpu_caps = detect(force_cpu=True)
    assert cpu_caps.hardware == {}
    job = run(sample, cpu_caps, tmp_path, "mkv", "hevc")
    assert job.encoder_used == "libx265"


def test_falls_back_to_cpu_when_hardware_encoder_fails(sample, caps, tmp_path):
    # Encodeur matériel absent de cette machine (ou mal configuré) : la conversion
    # doit échouer sur lui puis réussir automatiquement avec libx264.
    broken = "h264_nvenc" if "nvenc" not in caps.hardware else "h264_vaapi"
    job = run(sample, caps, tmp_path, "mp4", "h264", encoder=broken)
    assert job.fallback
    assert job.encoder_used == "libx264"
    assert probe(job.output_path) == "h264"


def test_unreadable_file_reports_error(caps, tmp_path):
    bad = tmp_path / "pas-une-video.mp4"
    bad.write_text("bonjour")
    job = Job(name=bad.name, input_path=bad, fmt="mp4", codec="h264", quality="balanced")
    convert(job, caps, tmp_path / "out")
    assert job.status == "error" and "illisible" in job.message
