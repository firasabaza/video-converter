"""Tests de l'API web locale."""

import shutil
import time

import pytest
from fastapi.testclient import TestClient

from video_converter.encoders import Capabilities, detect
from video_converter.server import create_app, safe_name


def test_safe_name():
    assert safe_name("../../etc/passwd") == "passwd"
    assert safe_name("C:\\Users\\moi\\film.mkv") == "film.mkv"
    assert safe_name("") == "video"


def test_rejects_invalid_parameters(tmp_path):
    client = TestClient(create_app(Capabilities(hardware={}, cpu={"h264": "libx264"}), tmp_path))
    assert client.post("/api/jobs?name=a.mkv&format=flv&codec=h264", content=b"x").status_code == 400
    assert client.post("/api/jobs?name=a.mkv&format=webm&codec=h264", content=b"x").status_code == 400
    assert client.post("/api/jobs?name=a.mkv&format=mp4&codec=h264&backend=nvenc", content=b"x").status_code == 400


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg n'est pas installé")
def test_upload_and_convert(tmp_path):
    import subprocess

    src = tmp_path / "in.mkv"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc2=size=320x240:rate=25:duration=1", "-c:v", "libx264", str(src)], check=True)
    client = TestClient(create_app(detect(), tmp_path / "out"))
    assert client.get("/").status_code == 200
    job = client.post("/api/jobs?name=Mon%20clip.mkv&format=mp4&codec=h264", content=src.read_bytes()).json()
    for _ in range(100):
        job = next(j for j in client.get("/api/jobs").json() if j["id"] == job["id"])
        if job["status"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert job["status"] == "done", job["message"]
    assert job["output_name"] == "Mon clip.mp4"
    assert client.get(f"/api/jobs/{job['id']}/download").content[4:8] == b"ftyp"
