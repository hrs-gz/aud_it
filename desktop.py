"""Desktop entry point for aud_it.

Runs the in-process FastAPI app under uvicorn on a loopback port (background
daemon thread) and opens a native PyWebView window pointed at it. This keeps
100% of the existing web stack while shipping as a native desktop app.

IMPORTANT: This module sets the AUD_IT_* environment variables that
backend.config.Settings reads BEFORE importing backend.main. Under a frozen
PyInstaller build the bundled project_root is read-only, so storage/data must
live in a per-user writable app-data directory.
"""

import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


def _bundle_root() -> Path | None:
    """PyInstaller extraction root, or None when running from source."""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else None


def _user_data_dir() -> Path:
    """Per-user writable app-data directory, by platform."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "aud_it"
    elif os.name == "nt":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) / "aud_it" if appdata else Path.home() / "aud_it"
    else:  # linux / other unix
        xdg = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg) / "aud_it" if xdg else Path.home() / ".local" / "share" / "aud_it"
    return base


def _configure_writable_dirs() -> None:
    """Point backend.config.Settings at a writable per-user location."""
    if not getattr(sys, "frozen", False):
        return

    base = _user_data_dir()
    storage_dir = base / "storage"
    data_dir = base / "data"
    storage_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("AUD_IT_STORAGE_DIR", str(storage_dir))
    os.environ.setdefault("AUD_IT_DATA_DIR", str(data_dir))
    os.environ.setdefault(
        "AUD_IT_DATABASE_URL", f"sqlite:///{data_dir / 'aud_it.db'}"
    )
    # Disable hard reset in shipped desktop builds unless explicitly enabled.
    os.environ.setdefault("AUD_IT_ALLOW_HARD_RESET", "0")


def _configure_bundled_tesseract() -> None:
    """Wire bundled Tesseract into PATH and TESSDATA_PREFIX when present."""
    root = _bundle_root()
    if root is None:
        return

    tess_dir = root / "tesseract"
    tessdata = tess_dir / "tessdata"
    if not tessdata.is_dir():
        return

    os.environ.setdefault("TESSDATA_PREFIX", str(tessdata))

    if os.name == "nt":
        exe = tess_dir / "tesseract.exe"
        if exe.is_file():
            os.environ["PATH"] = str(tess_dir) + os.pathsep + os.environ.get("PATH", "")
            os.environ.setdefault("TESSERACT_CMD", str(exe))


def _show_error(message: str) -> None:
    """Show a fatal error to the user (windowed builds have no console)."""
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
                0, message, "aud_it", 0x10
            )
            return
        except Exception:
            pass
    print(message, file=sys.stderr)


def _free_port() -> int:
    """Ask the OS for a free TCP port on the loopback interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run_server(port: int) -> None:
    """Run uvicorn serving backend.main:app (called on a daemon thread)."""
    import uvicorn

    from backend.main import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def _wait_until_ready(port: int, timeout: float = 120.0) -> bool:
    """Poll the server until it answers or the timeout elapses."""
    url = f"http://127.0.0.1:{port}/api/projects"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status:
                    return True
        except urllib.error.HTTPError:
            return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.2)
    return False


def main() -> int:
    _configure_writable_dirs()
    _configure_bundled_tesseract()

    import webview

    port = _free_port()

    server_thread = threading.Thread(
        target=_run_server, args=(port,), daemon=True
    )
    server_thread.start()

    if not _wait_until_ready(port):
        _show_error(
            "aud_it could not start its local server in time.\n\n"
            "The detection engine may still be loading. Try again, or check "
            "that no other aud_it instance is already running."
        )
        return 1

    webview.create_window(
        "aud_it",
        f"http://127.0.0.1:{port}/",
        width=1400,
        height=900,
    )
    webview.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
