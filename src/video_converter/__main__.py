"""Point d'entrée : `video-converter` (interface web), `video-converter encoders`, `video-converter convert`."""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

from .converter import Job, convert
from .encoders import BACKENDS, FORMATS, QUALITIES, detect


def default_output_dir() -> Path:
    home = Path.home()
    base = home / ("Movies" if sys.platform == "darwin" else "Videos")
    return (base if base.is_dir() else home) / "Video Converter"


def print_capabilities(caps) -> None:
    if caps.forced_cpu:
        print("Accélération matérielle désactivée (VC_FORCE_CPU / --cpu).")
    if caps.hardware:
        for name, encs in caps.hardware.items():
            print(f"✓ {BACKENDS[name]['label']} : {', '.join(encs.values())}")
    else:
        print("Aucun encodeur matériel utilisable : encodage CPU.")
    print(f"  Encodeurs CPU de repli : {', '.join(caps.cpu.values())}")


def cmd_serve(args) -> None:
    import uvicorn

    from .server import create_app

    print("Détection des encodeurs matériels…")
    caps = detect(force_cpu=True if args.cpu else None)
    print_capabilities(caps)
    output = Path(args.output).expanduser() if args.output else default_output_dir()
    print(f"Dossier de sortie : {output}")
    url = f"http://{args.host}:{args.port}"
    print(f"\nInterface : {url}  (Ctrl+C pour quitter)\n")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(caps, output), host=args.host, port=args.port, log_level="warning")


def cmd_encoders(args) -> None:
    print_capabilities(detect(force_cpu=True if args.cpu else None))


def cmd_convert(args) -> int:
    caps = detect(force_cpu=True if args.cpu else None)
    output = Path(args.output).expanduser() if args.output else default_output_dir()
    codec = args.codec or FORMATS[args.format]["codecs"][0]
    if codec not in FORMATS[args.format]["codecs"]:
        print(f"Le codec {codec} n'est pas proposé pour {args.format} ({', '.join(FORMATS[args.format]['codecs'])}).")
        return 2
    failures = 0
    for file in args.files:
        path = Path(file)
        job = Job(name=path.name, input_path=path, fmt=args.format, codec=codec, quality=args.quality,
                  backend="cpu" if args.cpu else args.backend, encoder=args.encoder or "")
        done = threading.Event()
        worker = threading.Thread(target=lambda: (convert(job, caps, output), done.set()), daemon=True)
        worker.start()
        try:
            while not done.wait(0.5):
                if job.status == "running":
                    print(f"\r{path.name} → {job.fmt} [{job.encoder_used}] {job.progress * 100:5.1f} %  {job.speed:.1f}x",
                          end="", flush=True)
        except KeyboardInterrupt:
            job.cancel_event.set()
            done.wait()
        print()
        if job.fallback:
            print(f"  ⚠ {job.message}")
        if job.status == "done":
            print(f"  ✓ {job.output_path}  ({job.accelerator}, {job.encoder_used}, {job.to_dict()['elapsed']} s)")
        else:
            failures += 1
            print(f"  ✗ {job.status} : {job.message}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> None:
    # Options communes, acceptées avant ou après la sous-commande.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--cpu", action="store_true", default=argparse.SUPPRESS, help="désactiver l'accélération matérielle")
    common.add_argument("-o", "--output", default=argparse.SUPPRESS, help="dossier de sortie")

    parser = argparse.ArgumentParser(prog="video-converter", parents=[common],
                                     description="Convertisseur vidéo local avec accélération matérielle.")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", parents=[common], help="lancer l'interface web (par défaut)")
    for p in (parser, serve):
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=8765)
        p.add_argument("--no-browser", action="store_true", help="ne pas ouvrir le navigateur")

    sub.add_parser("encoders", parents=[common], help="afficher les encodeurs détectés")

    conv = sub.add_parser("convert", parents=[common], help="convertir des fichiers en ligne de commande")
    conv.add_argument("files", nargs="+")
    conv.add_argument("-f", "--format", required=True, choices=list(FORMATS))
    conv.add_argument("-c", "--codec", help="codec vidéo (par défaut : celui du format)")
    conv.add_argument("-q", "--quality", default="balanced", choices=list(QUALITIES))
    conv.add_argument("--backend", default="auto", choices=["auto", "cpu", *BACKENDS])
    conv.add_argument("--encoder", help="imposer un encodeur FFmpeg précis (ex. h264_nvenc)")

    args = parser.parse_args(argv)
    args.cpu = getattr(args, "cpu", False)
    args.output = getattr(args, "output", None)
    if args.command == "encoders":
        cmd_encoders(args)
    elif args.command == "convert":
        sys.exit(cmd_convert(args))
    else:
        cmd_serve(args)


if __name__ == "__main__":
    main()
