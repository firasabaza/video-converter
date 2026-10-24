"""Petite application web locale (FastAPI) : envoi des fichiers, file d'attente, progression."""

from __future__ import annotations

import atexit
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from .converter import Job, JobQueue
from .encoders import CODECS, FORMATS, QUALITIES, Capabilities, ffmpeg_path

STATIC = Path(__file__).parent / "static"


def safe_name(name: str) -> str:
    name = Path(name.replace("\\", "/")).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name or "video"


def ffmpeg_version() -> str:
    try:
        out = subprocess.run([ffmpeg_path(), "-hide_banner", "-version"], capture_output=True, text=True, timeout=10).stdout
        return out.split("\n", 1)[0].replace("ffmpeg version ", "").split(" ")[0]
    except Exception:  # noqa: BLE001
        return "?"


def open_folder(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    elif sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)])


def create_app(caps: Capabilities, output_dir: Path) -> FastAPI:
    app = FastAPI(title="Convertisseur vidéo")
    jobs = JobQueue(caps, output_dir)
    app.state.jobs = jobs
    upload_dir = Path(tempfile.mkdtemp(prefix="video-converter-"))
    atexit.register(shutil.rmtree, upload_dir, ignore_errors=True)
    version = ffmpeg_version()

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/api/info")
    def info() -> dict:
        return {
            "formats": FORMATS,
            "codecs": CODECS,
            "qualities": QUALITIES,
            "capabilities": caps.to_dict(),
            "default_encoders": {codec: caps.pick(codec) for codec in caps.cpu},
            "output_dir": str(output_dir),
            "ffmpeg_version": version,
        }

    @app.post("/api/jobs")
    async def create_job(
        request: Request, name: str, format: str, codec: str, quality: str = "balanced", backend: str = "auto"
    ) -> dict:
        if format not in FORMATS:
            raise HTTPException(400, f"Format inconnu : {format}")
        if codec not in FORMATS[format]["codecs"]:
            raise HTTPException(400, f"Le codec {codec} n'est pas proposé pour le format {format}.")
        if quality not in QUALITIES:
            raise HTTPException(400, f"Préréglage inconnu : {quality}")
        if backend not in ("auto", "cpu") and backend not in caps.hardware:
            raise HTTPException(400, f"Accélération indisponible : {backend}")
        name = safe_name(name)
        job = Job(name=name, input_path=Path(), fmt=format, codec=codec, quality=quality, backend=backend, delete_input=True)
        job.input_path = upload_dir / f"{job.id}{Path(name).suffix}"
        try:
            with open(job.input_path, "wb") as f:
                async for chunk in request.stream():
                    f.write(chunk)
        except Exception:
            job.input_path.unlink(missing_ok=True)
            raise
        return jobs.submit(job).to_dict()

    @app.get("/api/jobs")
    def list_jobs() -> list[dict]:
        return [j.to_dict() for j in jobs.jobs.values()]

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict:
        job = jobs.cancel(job_id)
        if job is None:
            raise HTTPException(404, "Conversion introuvable")
        return job.to_dict()

    @app.post("/api/jobs/clear")
    def clear_jobs() -> dict:
        jobs.clear_finished()
        return {"ok": True}

    @app.get("/api/jobs/{job_id}/download")
    def download(job_id: str) -> FileResponse:
        job = jobs.jobs.get(job_id)
        if job is None or job.status != "done" or job.output_path is None or not job.output_path.exists():
            raise HTTPException(404, "Fichier converti introuvable")
        return FileResponse(job.output_path, filename=job.output_path.name)

    @app.post("/api/open-output")
    def open_output() -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        open_folder(output_dir)
        return {"ok": True}

    return app
