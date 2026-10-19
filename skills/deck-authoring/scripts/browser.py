"""Resolve a locally installed browser; never download or disable its sandbox."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys


def find_chrome(explicit: str | None = None) -> str:
    selected = explicit or os.environ.get("DECK_CHROME")
    if selected:
        candidate = shutil.which(selected) or str(Path(selected).expanduser())
        if Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
        raise RuntimeError(f"Configured Chrome is unavailable: {selected}; fix DECK_CHROME or --chrome")
    candidates = [shutil.which(name) for name in
                  ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "msedge")]
    if sys.platform == "darwin":
        candidates += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                       str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                       "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    if sys.platform == "win32":
        for name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = os.environ.get(name)
            if root:
                candidates += [str(Path(root) / "Google/Chrome/Application/chrome.exe"),
                               str(Path(root) / "Microsoft/Edge/Application/msedge.exe")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    raise RuntimeError("Chrome/Chromium not found. Install a local browser or set DECK_CHROME to its executable.")


def diagnose() -> dict:
    """Discovery only: presence is not proof that CDP or rendering succeeds."""
    try:
        browser = {"path": find_chrome(), "error": None}
    except RuntimeError as exc:
        browser = {"path": None, "error": str(exc)}
    modules = {name: importlib.util.find_spec(name) is not None for name in ("PIL", "websockets", "pptx")}
    pdfinfo = os.environ.get("DECK_PDFINFO") or "pdfinfo"
    return {"python": sys.version.split()[0], "browser": browser, "modules": modules,
            "pdfinfo": shutil.which(pdfinfo),
            "mp4_encoder_available": sys.platform == "darwin" and bool(shutil.which("swiftc")),
            "scope": "Dependency discovery only; run a real render to verify browser access, fonts and export quality."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doctor", action="store_true", help="Report dependencies without starting a browser")
    args = parser.parse_args()
    if args.doctor:
        print(json.dumps(diagnose(), ensure_ascii=False, indent=2))
    else:
        try:
            print(find_chrome())
        except RuntimeError as exc:
            parser.exit(1, str(exc) + "\n")
