"""App macOS (.app) : serveur local en arrière-plan et icône dans la barre des menus.

L'icône propose d'ouvrir l'interface, d'ouvrir le dossier des vidéos converties
et de quitter. Relancer l'app depuis le Finder ouvre de nouveau l'interface.
"""

from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import AppKit
import objc
import uvicorn

from .__main__ import default_output_dir
from .encoders import detect
from .server import create_app, open_folder

LOG_FILE = Path.home() / "Library" / "Logs" / "Video Converter.log"


def free_port(preferred: int = 8765) -> int:
    for port in [preferred, *range(preferred + 1, preferred + 50), 0]:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("Aucun port libre")


def alert(title: str, text: str) -> None:
    AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    box = AppKit.NSAlert.alloc().init()
    box.setMessageText_(title)
    box.setInformativeText_(text)
    box.runModal()


class AppDelegate(AppKit.NSObject):
    def initWithServer_url_output_(self, server, url, output):
        self = objc.super(AppDelegate, self).init()
        self.server, self.url, self.output = server, url, output
        return self

    def applicationDidFinishLaunching_(self, _notification):
        bar = AppKit.NSStatusBar.systemStatusBar()
        self.item = bar.statusItemWithLength_(AppKit.NSVariableStatusItemLength)
        image = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_("film", "Convertisseur vidéo")
        if image is not None:
            image.setTemplate_(True)
            self.item.button().setImage_(image)
        else:
            self.item.button().setTitle_("🎬")
        self.item.button().setToolTip_("Convertisseur vidéo")

        menu = AppKit.NSMenu.alloc().init()
        for title, action, key in [
            ("Ouvrir le convertisseur", "openUI:", "o"),
            ("Ouvrir le dossier des vidéos converties", "openFolder:", ""),
            (None, None, None),
            ("Quitter le convertisseur vidéo", "quit:", "q"),
        ]:
            if title is None:
                menu.addItem_(AppKit.NSMenuItem.separatorItem())
                continue
            entry = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
            entry.setTarget_(self)
            menu.addItem_(entry)
        self.item.setMenu_(menu)
        self.openUI_(None)

    def applicationShouldHandleReopen_hasVisibleWindows_(self, _app, _flag):
        self.openUI_(None)  # double-clic sur l'app déjà lancée
        return False

    def openUI_(self, _sender):
        webbrowser.open(self.url)

    def openFolder_(self, _sender):
        self.output.mkdir(parents=True, exist_ok=True)
        open_folder(self.output)

    def quit_(self, _sender):
        AppKit.NSApplication.sharedApplication().terminate_(None)

    def applicationWillTerminate_(self, _notification):
        # Arrête proprement les conversions en cours (et leurs processus FFmpeg).
        jobs = self.server.config.app.state.jobs
        jobs.cancel_all()
        deadline = time.time() + 5
        while time.time() < deadline and any(j.status == "running" for j in jobs.jobs.values()):
            time.sleep(0.1)
        self.server.should_exit = True


def main() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log = open(LOG_FILE, "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stderr = log
    print(f"\n--- Démarrage {time.strftime('%Y-%m-%d %H:%M:%S')} ---")

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    try:
        caps = detect()
    except FileNotFoundError as exc:
        alert("FFmpeg est introuvable", f"{exc}\n\nAvec Homebrew : brew install ffmpeg")
        sys.exit(1)
    print("Accélération :", caps.to_dict())

    output = default_output_dir()
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(create_app(caps, output), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.time() + 15
    while not server.started:
        if time.time() > deadline:
            alert("Le convertisseur n'a pas pu démarrer", f"Consultez le journal : {LOG_FILE}")
            sys.exit(1)
        time.sleep(0.05)
    print("Interface :", url)

    delegate = AppDelegate.alloc().initWithServer_url_output_(server, url, output)
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
