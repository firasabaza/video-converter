"""Conversion d'un fichier avec FFmpeg, suivi de la progression et file d'attente."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .encoders import (
    BACKENDS,
    FORMATS,
    Capabilities,
    audio_args,
    backend_of,
    ffmpeg_path,
    ffprobe_path,
    video_args,
)


@dataclass
class SourceInfo:
    duration: float = 0.0
    width: int = 1920
    height: int = 1080
    fps: float = 30.0
    video_codec: str = ""
    has_audio: bool = False


def probe_source(path: str | Path) -> SourceInfo:
    out = subprocess.run(
        [ffprobe_path(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise ValueError(f"Fichier vidéo illisible : {out.stderr.strip() or 'format inconnu'}")
    data = json.loads(out.stdout or "{}")
    info = SourceInfo()
    streams = data.get("streams", [])
    video = next(
        (s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")),
        None,
    )
    if video is None:
        raise ValueError("Ce fichier ne contient pas de piste vidéo.")
    info.video_codec = video.get("codec_name", "")
    info.width = int(video.get("width") or info.width)
    info.height = int(video.get("height") or info.height)
    num, _, den = (video.get("avg_frame_rate") or "30/1").partition("/")
    try:
        info.fps = float(num) / float(den or 1) or 30.0
    except (ValueError, ZeroDivisionError):
        info.fps = 30.0
    info.has_audio = any(s.get("codec_type") == "audio" for s in streams)
    try:
        info.duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    except ValueError:
        info.duration = 0.0
    return info


def build_command(src: str | Path, dst: str | Path, fmt: str, codec: str, quality: str, encoder: str, info: SourceInfo) -> list[str]:
    container = FORMATS[fmt]
    if codec == "copy":
        pre, vargs = [], ["-c:v", "copy"]
        hevc = info.video_codec == "hevc"
    else:
        va = video_args(encoder, quality, info.width, info.height, info.fps)
        pre, vargs = va.pre_input, va.args
        hevc = codec == "hevc"
    cmd = [ffmpeg_path(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *pre, "-i", str(src)]
    cmd += ["-map", "0:V:0", "-map", "0:a?", *vargs]
    if info.has_audio:
        cmd += audio_args(container["audio"], quality)
    if fmt in ("mp4", "mov"):
        cmd += ["-movflags", "+faststart"]
        if hevc:
            cmd += ["-tag:v", "hvc1"]  # nécessaire pour la lecture HEVC dans QuickTime / Apple
    cmd += ["-max_muxing_queue_size", "1024", "-progress", "pipe:1", "-nostats", str(dst)]
    return cmd


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    n = 1
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


class Cancelled(Exception):
    pass


def run_ffmpeg(cmd: list[str], duration: float, on_progress: Callable[[float, float], None], cancel: threading.Event) -> None:
    """Lance FFmpeg et appelle on_progress(fraction, vitesse) au fil de l'eau."""
    with tempfile.TemporaryFile(mode="w+") as errfile:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errfile, text=True, creationflags=creationflags)
        speed = 0.0
        assert proc.stdout is not None
        for line in proc.stdout:
            if cancel.is_set():
                proc.terminate()
                break
            key, _, value = line.strip().partition("=")
            if key == "speed" and value.endswith("x"):
                try:
                    speed = float(value[:-1])
                except ValueError:
                    pass
            elif key == "out_time_us" and duration > 0:
                try:
                    on_progress(min(int(value) / 1e6 / duration, 0.999), speed)
                except ValueError:
                    pass
        proc.wait()
        if cancel.is_set():
            raise Cancelled()
        if proc.returncode != 0:
            errfile.seek(0)
            lines = [l for l in errfile.read().strip().splitlines() if l.strip()]
            raise RuntimeError("\n".join(lines[-6:]) or f"FFmpeg a échoué (code {proc.returncode})")
        on_progress(1.0, speed)


@dataclass
class Job:
    name: str
    input_path: Path
    fmt: str
    codec: str
    quality: str
    backend: str = "auto"
    encoder: str = ""  # encodeur imposé (pour les tests) ; vide = choix automatique
    delete_input: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = "queued"  # queued, running, done, error, cancelled
    progress: float = 0.0
    speed: float = 0.0
    encoder_used: str = ""
    accelerator: str = ""
    fallback: bool = False
    message: str = ""
    output_path: Path | None = None
    started_at: float = 0.0
    finished_at: float = 0.0
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_dict(self) -> dict:
        elapsed = (self.finished_at or time.time()) - self.started_at if self.started_at else 0.0
        eta = elapsed * (1 - self.progress) / self.progress if self.status == "running" and self.progress > 0.01 else None
        return {
            "id": self.id,
            "name": self.name,
            "format": self.fmt,
            "codec": self.codec,
            "quality": self.quality,
            "status": self.status,
            "progress": round(self.progress, 4),
            "speed": self.speed,
            "encoder": self.encoder_used,
            "accelerator": self.accelerator,
            "fallback": self.fallback,
            "message": self.message,
            "output": str(self.output_path) if self.output_path else None,
            "output_name": self.output_path.name if self.output_path else None,
            "elapsed": round(elapsed, 1),
            "eta": round(eta, 1) if eta is not None else None,
        }


def convert(job: Job, caps: Capabilities, output_dir: Path) -> None:
    """Convertit `job`, avec repli automatique sur le CPU si l'encodeur matériel échoue."""
    job.status = "running"
    job.started_at = time.time()
    try:
        info = probe_source(job.input_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(job.name).stem or "video"
        job.output_path = unique_path(output_dir / f"{stem}.{job.fmt}")

        if job.codec == "copy":
            encoders = ["copy"]
        else:
            first = job.encoder or caps.pick(job.codec, job.backend)
            encoders = [first]
            if backend_of(first) is not None:
                encoders.append(caps.pick(job.codec, "cpu"))

        def on_progress(fraction: float, speed: float) -> None:
            job.progress, job.speed = fraction, speed

        for i, encoder in enumerate(encoders):
            backend = backend_of(encoder)
            job.encoder_used = encoder
            job.accelerator = BACKENDS[backend]["label"] if backend else ("Aucun (copie)" if encoder == "copy" else "CPU")
            job.progress = 0.0
            cmd = build_command(job.input_path, job.output_path, job.fmt, job.codec, job.quality, encoder, info)
            try:
                run_ffmpeg(cmd, info.duration, on_progress, job.cancel_event)
                break
            except RuntimeError as exc:
                if i + 1 < len(encoders):
                    job.fallback = True
                    job.message = f"{encoder} a échoué, repli sur l'encodage CPU. ({exc.__str__().splitlines()[-1][:200]})"
                    continue
                raise
        job.status = "done"
        job.progress = 1.0
    except Cancelled:
        job.status = "cancelled"
        job.message = "Conversion annulée."
        _remove(job.output_path)
    except Exception as exc:  # noqa: BLE001 - on remonte le message à l'interface
        job.status = "error"
        job.message = str(exc)
        _remove(job.output_path)
    finally:
        job.finished_at = time.time()
        if job.delete_input:
            _remove(job.input_path)


def _remove(path: Path | None) -> None:
    if path is not None:
        try:
            os.remove(path)
        except OSError:
            pass


class JobQueue:
    """File d'attente : une conversion à la fois (les encodeurs matériels ont des sessions limitées)."""

    def __init__(self, caps: Capabilities, output_dir: Path):
        self.caps = caps
        self.output_dir = output_dir
        self.jobs: dict[str, Job] = {}
        self._queue: queue.Queue[Job] = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def submit(self, job: Job) -> Job:
        self.jobs[job.id] = job
        self._queue.put(job)
        return job

    def cancel(self, job_id: str) -> Job | None:
        job = self.jobs.get(job_id)
        if job and job.status in ("queued", "running"):
            job.cancel_event.set()
            if job.status == "queued":
                job.status = "cancelled"
                job.message = "Conversion annulée."
        return job

    def clear_finished(self) -> None:
        for job_id in [j.id for j in self.jobs.values() if j.status in ("done", "error", "cancelled")]:
            del self.jobs[job_id]

    def _worker(self) -> None:
        while True:
            job = self._queue.get()
            if job.cancel_event.is_set():
                if job.delete_input:
                    _remove(job.input_path)
                continue
            convert(job, self.caps, self.output_dir)
