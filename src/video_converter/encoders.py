"""Détection des encodeurs matériels et construction des arguments FFmpeg.

Chaque encodeur matériel est validé par un vrai petit encodage de test : un
encodeur peut être compilé dans FFmpeg sans que la machine dispose du matériel
(ou du pilote) correspondant. Si aucun encodeur matériel ne fonctionne, on
utilise l'encodage CPU (libx264, libx265, SVT-AV1, libvpx-vp9).
"""

from __future__ import annotations

import glob
import os
import platform
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

QUALITIES = {
    "high": "Haute qualité",
    "balanced": "Équilibré",
    "small": "Petit fichier",
}

CODECS = {
    "h264": "H.264 (le plus compatible)",
    "hevc": "H.265 / HEVC (plus compact)",
    "av1": "AV1 (très compact, récent)",
    "vp9": "VP9",
    "mpeg4": "MPEG-4 Part 2 (Xvid)",
    "copy": "Copier la vidéo (sans réencodage, très rapide)",
}

# Formats de sortie : extension, codecs vidéo autorisés (le premier est le
# défaut) et codec audio.
FORMATS = {
    "mp4": {"label": "MP4", "codecs": ["h264", "hevc", "av1", "copy"], "audio": "aac"},
    "mkv": {"label": "MKV", "codecs": ["h264", "hevc", "av1", "vp9", "copy"], "audio": "aac"},
    "mov": {"label": "MOV", "codecs": ["h264", "hevc", "copy"], "audio": "aac"},
    "webm": {"label": "WebM", "codecs": ["vp9", "av1"], "audio": "libopus"},
    "avi": {"label": "AVI", "codecs": ["mpeg4", "h264"], "audio": "libmp3lame"},
}

# Back-ends matériels, dans l'ordre de préférence pour le mode « Auto ».
BACKENDS = {
    "videotoolbox": {
        "label": "Apple VideoToolbox",
        "encoders": {"h264": "h264_videotoolbox", "hevc": "hevc_videotoolbox"},
    },
    "nvenc": {
        "label": "NVIDIA NVENC",
        "encoders": {"h264": "h264_nvenc", "hevc": "hevc_nvenc", "av1": "av1_nvenc"},
    },
    "qsv": {
        "label": "Intel Quick Sync (QSV)",
        "encoders": {"h264": "h264_qsv", "hevc": "hevc_qsv", "av1": "av1_qsv", "vp9": "vp9_qsv"},
    },
    "amf": {
        "label": "AMD AMF",
        "encoders": {"h264": "h264_amf", "hevc": "hevc_amf", "av1": "av1_amf"},
    },
    "vaapi": {
        "label": "VAAPI (Intel / AMD sous Linux)",
        "encoders": {"h264": "h264_vaapi", "hevc": "hevc_vaapi", "av1": "av1_vaapi", "vp9": "vp9_vaapi"},
    },
}

# Encodeurs CPU de repli, par ordre de préférence.
CPU_ENCODERS = {
    "h264": ["libx264"],
    "hevc": ["libx265"],
    "av1": ["libsvtav1", "libaom-av1"],
    "vp9": ["libvpx-vp9"],
    "mpeg4": ["mpeg4"],
}

AUDIO_BITRATES = {
    "aac": ["192k", "160k", "128k"],
    "libopus": ["160k", "128k", "96k"],
    "libmp3lame": ["192k", "160k", "128k"],
}


def ffmpeg_path() -> str:
    path = os.environ.get("VC_FFMPEG") or shutil.which("ffmpeg")
    if not path:
        raise FileNotFoundError(
            "FFmpeg est introuvable. Installez-le (voir le README) ou indiquez "
            "son chemin avec la variable d'environnement VC_FFMPEG."
        )
    return path


def ffprobe_path() -> str:
    path = os.environ.get("VC_FFPROBE") or shutil.which("ffprobe")
    if not path:
        sibling = os.path.join(os.path.dirname(ffmpeg_path()), "ffprobe" + (".exe" if sys.platform == "win32" else ""))
        if os.path.exists(sibling):
            return sibling
        raise FileNotFoundError("ffprobe est introuvable (il est normalement installé avec FFmpeg).")
    return path


def backend_of(encoder: str) -> str | None:
    for name, backend in BACKENDS.items():
        if encoder in backend["encoders"].values():
            return name
    return None


def codec_of(encoder: str) -> str | None:
    for backend in BACKENDS.values():
        for codec, enc in backend["encoders"].items():
            if enc == encoder:
                return codec
    for codec, encs in CPU_ENCODERS.items():
        if encoder in encs:
            return codec
    return None


@dataclass
class VideoArgs:
    """Arguments FFmpeg pour un encodeur : avant l'entrée (-i) et après."""

    pre_input: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)


def _vaapi_device() -> str:
    devices = sorted(glob.glob("/dev/dri/renderD*"))
    return os.environ.get("VC_VAAPI_DEVICE") or (devices[0] if devices else "/dev/dri/renderD128")


def _target_bitrate(codec: str, q: int, width: int, height: int, fps: float) -> str:
    """Débit cible pour les encodeurs qui n'ont pas de mode qualité constante."""
    bits_per_pixel = [0.10, 0.07, 0.04][q]
    if codec in ("hevc", "av1", "vp9"):
        bits_per_pixel *= 0.65
    kbps = max(500, int(width * height * (fps or 30) * bits_per_pixel / 1000))
    return f"{kbps}k"


def video_args(encoder: str, quality: str, width: int = 1920, height: int = 1080, fps: float = 30.0) -> VideoArgs:
    """Construit les arguments vidéo pour `encoder` et le préréglage `quality`."""
    q = list(QUALITIES).index(quality)
    codec = codec_of(encoder)
    backend = backend_of(encoder)
    out = VideoArgs(args=["-c:v", encoder])
    a = out.args

    if backend is None:  # Encodage CPU
        if encoder == "libx264":
            a += ["-preset", "medium", "-crf", str([18, 23, 28][q])]
        elif encoder == "libx265":
            a += ["-preset", "medium", "-crf", str([20, 26, 30][q]), "-x265-params", "log-level=error"]
        elif encoder == "libsvtav1":
            a += ["-preset", "8", "-crf", str([26, 34, 42][q])]
        elif encoder == "libaom-av1":
            a += ["-cpu-used", "6", "-row-mt", "1", "-crf", str([26, 34, 42][q]), "-b:v", "0"]
        elif encoder == "libvpx-vp9":
            a += ["-crf", str([28, 34, 40][q]), "-b:v", "0", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4"]
        elif encoder == "mpeg4":
            a += ["-q:v", str([2, 4, 7][q]), "-vtag", "xvid"]
        a += ["-pix_fmt", "yuv420p"]

    elif backend == "videotoolbox":
        if platform.machine() == "arm64":
            # Qualité constante : disponible sur Apple Silicon (M1 à M5).
            a += ["-q:v", str(([75, 60, 45] if codec == "h264" else [70, 56, 42])[q])]
        else:
            a += ["-b:v", _target_bitrate(codec, q, width, height, fps)]
        a += ["-pix_fmt", "nv12"]

    elif backend == "nvenc":
        cq = ([24, 30, 36] if codec == "av1" else [19, 24, 29])[q]
        a += ["-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", str(cq), "-b:v", "0", "-pix_fmt", "yuv420p"]

    elif backend == "qsv":
        a += ["-preset", "medium", "-global_quality", str([20, 25, 30][q]), "-pix_fmt", "nv12"]

    elif backend == "amf":
        qp = ([100, 125, 150] if codec == "av1" else [20, 25, 30])[q]
        a += ["-rc", "cqp", "-qp_i", str(qp), "-qp_p", str(qp)]
        if codec == "h264":
            a += ["-qp_b", str(qp)]
        a += ["-pix_fmt", "nv12"]

    elif backend == "vaapi":
        out.pre_input += ["-vaapi_device", _vaapi_device()]
        gq = ([100, 125, 150] if codec in ("av1", "vp9") else [20, 25, 30])[q]
        a += ["-vf", "format=nv12,hwupload", "-rc_mode", "CQP", "-global_quality", str(gq)]

    return out


def audio_args(audio_codec: str, quality: str) -> list[str]:
    q = list(QUALITIES).index(quality)
    return ["-c:a", audio_codec, "-b:a", AUDIO_BITRATES[audio_codec][q]]


def compiled_encoders() -> set[str]:
    out = subprocess.run(
        [ffmpeg_path(), "-hide_banner", "-encoders"],
        capture_output=True, text=True, timeout=30,
    ).stdout
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "VAS":
            names.add(parts[1])
    return names


def probe_encoder(encoder: str) -> bool:
    """Vrai si `encoder` arrive réellement à encoder quelques images ici."""
    va = video_args(encoder, "balanced", 640, 360, 30)
    cmd = [
        ffmpeg_path(), "-hide_banner", "-nostdin", "-loglevel", "error",
        *va.pre_input,
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=0.5",
        *va.args, "-f", "null", "-",
    ]
    try:
        return subprocess.run(cmd, capture_output=True, timeout=30).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


@dataclass
class Capabilities:
    hardware: dict[str, dict[str, str]]  # back-end -> {codec: encodeur} qui fonctionnent
    cpu: dict[str, str]  # codec -> encodeur CPU disponible
    forced_cpu: bool = False

    def pick(self, codec: str, backend: str = "auto") -> str:
        """Choisit l'encodeur pour `codec` : matériel si possible, sinon CPU."""
        if backend != "cpu":
            names = list(self.hardware) if backend == "auto" else [backend]
            for name in names:
                enc = self.hardware.get(name, {}).get(codec)
                if enc:
                    return enc
        if codec not in self.cpu:
            raise RuntimeError(f"Aucun encodeur disponible pour {CODECS.get(codec, codec)} dans cette version de FFmpeg.")
        return self.cpu[codec]

    def to_dict(self) -> dict:
        return {
            "hardware": [
                {"id": name, "label": BACKENDS[name]["label"], "codecs": sorted(encs)}
                for name, encs in self.hardware.items()
            ],
            "cpu": self.cpu,
            "forced_cpu": self.forced_cpu,
        }


def detect(force_cpu: bool | None = None) -> Capabilities:
    if force_cpu is None:
        force_cpu = os.environ.get("VC_FORCE_CPU", "") not in ("", "0")
    compiled = compiled_encoders()
    cpu = {}
    for codec, candidates in CPU_ENCODERS.items():
        for enc in candidates:
            if enc in compiled:
                cpu[codec] = enc
                break

    hardware: dict[str, dict[str, str]] = {}
    if not force_cpu:
        candidates = [
            (name, codec, enc)
            for name, backend in BACKENDS.items()
            for codec, enc in backend["encoders"].items()
            if enc in compiled and (name != "vaapi" or sys.platform.startswith("linux"))
        ]
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda c: probe_encoder(c[2]), candidates))
        for (name, codec, enc), ok in zip(candidates, results):
            if ok:
                hardware.setdefault(name, {})[codec] = enc
    return Capabilities(hardware=hardware, cpu=cpu, forced_cpu=force_cpu)
