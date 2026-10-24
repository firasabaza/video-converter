# Convertisseur vidéo

Un convertisseur vidéo qui tourne **entièrement sur votre ordinateur** : déposez vos fichiers dans une petite page web locale, choisissez le format et la qualité, et suivez la progression. Les conversions sont faites par [FFmpeg](https://ffmpeg.org) avec **l'accélération matérielle de votre machine** quand elle existe, et un repli automatique sur le processeur sinon.

- **Formats de sortie** : MP4, MKV, MOV, WebM, AVI
- **Formats d'entrée** : tout ce que FFmpeg sait lire (MKV, MP4, MOV, AVI, WebM, FLV, WMV, TS, M2TS, 3GP…)
- **Codecs** : H.264, H.265/HEVC, AV1, VP9, MPEG-4 (Xvid), ou copie de la vidéo sans réencodage
- **Préréglages** : Haute qualité, Équilibré, Petit fichier
- Glisser-déposer de plusieurs fichiers, file d'attente, barre de progression avec vitesse et temps restant, annulation

## Accélération matérielle

Au démarrage, l'application teste réellement chaque encodeur matériel présent dans FFmpeg avec un court encodage d'essai, puis garde ceux qui fonctionnent :

| Matériel | Technologie | Système | Codecs |
|---|---|---|---|
| Apple Silicon M1 à M5 (et Mac Intel) | VideoToolbox | macOS | H.264, HEVC |
| NVIDIA (GeForce, RTX, Quadro) | NVENC | Windows, Linux | H.264, HEVC, AV1* |
| Intel (iGPU, Arc) | Quick Sync (QSV) | Windows, Linux | H.264, HEVC, AV1*, VP9* |
| AMD (Radeon) | AMF | Windows | H.264, HEVC, AV1* |
| Intel / AMD | VAAPI | Linux | H.264, HEVC, AV1*, VP9* |

\* selon la génération du matériel.

Si aucun encodeur matériel n'est disponible pour le codec choisi, l'application utilise le CPU : **libx264** (H.264), **libx265** (HEVC), **SVT-AV1** (AV1), **libvpx-vp9** (VP9). Si un encodeur matériel échoue en cours de conversion (pilote absent, format non pris en charge…), la conversion est **relancée automatiquement sur le CPU** et l'interface le signale.

Le format WebM utilise toujours VP9 ou AV1 ; AVI utilise MPEG-4 (Xvid) par défaut pour rester lisible par les anciens lecteurs, ou H.264.

## Installation

Il faut **FFmpeg** et **[uv](https://docs.astral.sh/uv/)** (qui installe Python 3.10+ et les dépendances tout seul). Les scripts ci-dessous installent ce qui manque.

Téléchargez le projet (`git clone` ou bouton **Code → Download ZIP** sur GitHub), puis :

### macOS

Il faut [Homebrew](https://brew.sh). Dans le Terminal, depuis le dossier du projet :

```bash
./install.sh
```

### Windows 10 / 11

Double-cliquez sur **`install.bat`**. Le script utilise `winget` pour installer FFmpeg (version complète de Gyan, avec NVENC, Quick Sync et AMF) et uv.

Pour l'accélération matérielle, gardez les pilotes de la carte graphique à jour (NVIDIA, Intel ou AMD).

### Linux

```bash
./install.sh
```

Le script installe FFmpeg avec `apt`, `dnf`, `pacman` ou `zypper` (votre mot de passe `sudo` est demandé). Pour l'accélération matérielle :

- **Intel / AMD (VAAPI)** : installez le pilote VA-API (`intel-media-va-driver` ou `mesa-va-drivers` sur Debian/Ubuntu, `intel-media-driver` ou `libva-mesa-driver` sur Arch/Fedora) et vérifiez que votre utilisateur fait partie du groupe `render`.
- **Intel Quick Sync** : en plus du pilote ci-dessus, le runtime oneVPL (`libmfx-gen1` / `libvpl2`).
- **NVIDIA** : le pilote propriétaire NVIDIA.
- **Fedora** : le paquet `ffmpeg` complet (avec x264/x265/NVENC) vient de [RPM Fusion](https://rpmfusion.org) ; sans RPM Fusion, `ffmpeg-free` a moins d'encodeurs.

## Utilisation

| Système | Lancer l'application |
|---|---|
| macOS | double-cliquez sur `start.command`, ou `./start.sh` |
| Windows | double-cliquez sur `start.bat` |
| Linux | `./start.sh` |

La page **http://127.0.0.1:8765** s'ouvre dans votre navigateur. Le badge en haut à droite indique l'accélération détectée. Déposez vos vidéos, choisissez le format, le codec et la qualité ; les fichiers convertis arrivent dans :

- macOS : `~/Movies/Video Converter`
- Windows et Linux : `~/Videos/Video Converter`

Le bouton **Ouvrir le dossier** l'ouvre directement, et chaque conversion terminée peut aussi être téléchargée depuis la page. Fermez la fenêtre du terminal (ou `Ctrl+C`) pour arrêter l'application.

La page n'écoute que sur `127.0.0.1` : elle n'est pas accessible depuis les autres machines du réseau, et aucun fichier ne quitte votre ordinateur.

### Options

```bash
./start.sh --port 9000             # autre port
./start.sh -o ~/Bureau/Converties  # autre dossier de sortie
./start.sh --cpu                   # désactiver l'accélération matérielle
./start.sh --no-browser            # ne pas ouvrir le navigateur
```

(Sous Windows, mêmes options avec `start.bat`.)

### En ligne de commande

```bash
uv run video-converter encoders                                 # afficher l'accélération détectée
uv run video-converter convert film.mkv -f mp4                  # MKV → MP4 (H.264, accélération auto)
uv run video-converter convert *.avi -f mkv -c hevc -q small    # plusieurs fichiers en HEVC compact
uv run video-converter convert clip.mov -f webm                 # WebM (VP9)
uv run video-converter --cpu convert film.mkv -f mp4            # forcer le CPU
```

### Variables d'environnement

| Variable | Rôle |
|---|---|
| `VC_FFMPEG`, `VC_FFPROBE` | chemin de FFmpeg / ffprobe s'ils ne sont pas dans le `PATH` |
| `VC_FORCE_CPU=1` | désactiver l'accélération matérielle |
| `VC_VAAPI_DEVICE` | périphérique VAAPI (par défaut le premier `/dev/dri/renderD*`) |

## Bon à savoir

- **Copier la vidéo (sans réencodage)** change seulement le conteneur (par exemple MKV → MP4) : c'est quasi instantané et sans perte, mais le codec d'origine doit être accepté par le format de sortie.
- Les encodeurs matériels sont beaucoup plus rapides, mais à qualité égale ils produisent des fichiers un peu plus gros que libx264/libx265. Choisissez **CPU uniquement** dans « Accélération » si la taille compte plus que la vitesse.
- La sortie est en 8 bits (yuv420p / nv12) pour une compatibilité maximale : les vidéos HDR 10 bits sont converties en SDR 8 bits sans mappage de tons.
- Les sous-titres et pistes de données ne sont pas conservés ; toutes les pistes audio le sont.
- Une seule conversion tourne à la fois (les autres attendent dans la file), car les encodeurs matériels limitent le nombre de sessions simultanées.

## Développement

```bash
uv sync            # dépendances, y compris pytest
uv run pytest      # tests unitaires et vraies conversions avec le FFmpeg installé
```

Les tests vérifient chaque format de sortie, l'utilisation de l'encodeur matériel quand il existe, et le repli sur le CPU (en imposant un encodeur matériel absent de la machine). Ils tournent aussi sur GitHub Actions sous Linux, Windows et macOS.

Structure :

```
src/video_converter/
  encoders.py    détection des encodeurs et réglages FFmpeg par encodeur / qualité
  converter.py   conversion, progression, repli CPU, file d'attente
  server.py      API web locale (FastAPI)
  static/        interface (une seule page HTML)
  __main__.py    ligne de commande
```

## Licence

MIT. FFmpeg est distribué séparément sous sa propre licence (LGPL/GPL).
