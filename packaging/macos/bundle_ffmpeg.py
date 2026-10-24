"""Copie ffmpeg, ffprobe et leurs bibliothèques Homebrew dans un dossier autonome.

Utilisation : python3 bundle_ffmpeg.py DOSSIER
Résultat : DOSSIER/bin/{ffmpeg,ffprobe} et DOSSIER/lib/*.dylib, avec des chemins
relatifs (@executable_path / @loader_path) et une signature ad hoc.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

PREFIXES = ("/opt/homebrew/", "/usr/local/")


def deps(path: Path) -> list[str]:
    out = subprocess.run(["otool", "-L", str(path)], capture_output=True, text=True, check=True).stdout
    names = [line.strip().split(" (")[0] for line in out.splitlines()[1:]]
    return [n for n in names if n.startswith(PREFIXES)]


def main(dest: Path) -> None:
    bin_dir, lib_dir = dest / "bin", dest / "lib"
    shutil.rmtree(dest, ignore_errors=True)
    bin_dir.mkdir(parents=True)
    lib_dir.mkdir()

    binaries = []
    for name in ("ffmpeg", "ffprobe"):
        src = shutil.which(name)
        if not src:
            sys.exit(f"{name} introuvable : brew install ffmpeg")
        target = bin_dir / name
        shutil.copy2(os.path.realpath(src), target)
        binaries.append(target)

    # Copie récursive des dylibs Homebrew
    copied: dict[str, Path] = {}  # chemin d'origine (tel que référencé) -> copie
    todo = list(binaries)
    while todo:
        for ref in deps(todo.pop()):
            real = os.path.realpath(ref)
            if ref in copied:
                continue
            target = lib_dir / Path(real).name
            if not target.exists():
                shutil.copy2(real, target)
                todo.append(target)
            copied[ref] = target

    for f in [*binaries, *lib_dir.iterdir()]:
        f.chmod(0o755)
        is_lib = f.parent == lib_dir
        args = ["install_name_tool"]
        if is_lib:
            args += ["-id", f"@loader_path/{f.name}"]
        for ref in deps(f):
            name = Path(os.path.realpath(ref)).name
            prefix = "@loader_path" if is_lib else "@executable_path/../lib"
            args += ["-change", ref, f"{prefix}/{name}"]
        if len(args) > 1:
            subprocess.run([*args, str(f)], check=True, capture_output=True)
        subprocess.run(["codesign", "--force", "--sign", "-", str(f)], check=True, capture_output=True)

    leftovers = [f"{f.name}: {d}" for f in [*binaries, *lib_dir.iterdir()] for d in deps(f)]
    if leftovers:
        sys.exit("Références Homebrew restantes :\n" + "\n".join(leftovers))
    size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file()) // 1_000_000
    print(f"FFmpeg intégré : {len(list(lib_dir.iterdir()))} bibliothèques, {size} Mo")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
