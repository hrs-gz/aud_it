# Desktop build (PyWebView + PyInstaller)

aud_it ships as a native desktop app by running the existing in-process FastAPI
app under uvicorn on a loopback port and pointing a native PyWebView window at
it. No application logic changes — it's the same web stack in a window.

## Prerequisites

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_lg    # the NLP model presidio uses
```

On macOS/Linux dev runs, system Tesseract is still used for OCR when not frozen
(e.g. `brew install tesseract`).

## Dev run (no build)

```bash
python desktop.py
```

This finds a free loopback port, starts uvicorn (`backend.main:app`) on a daemon
thread, waits until the server answers, then opens the window. In dev mode the
storage/data dirs stay at their normal repo-relative defaults from
`backend/config.py`.

## Build a desktop app

### macOS / Linux (local dev build)

```bash
pyinstaller aud_it.spec
```

### Windows

PyInstaller must run **on Windows** to produce `aud_it.exe`.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_lg

# Stage bundled Tesseract (see vendor/tesseract/win64/README.md)
powershell -ExecutionPolicy Bypass -File scripts\stage_tesseract_win.ps1

pyinstaller aud_it.spec
```

Output:

```
dist\aud_it\            <- distributable folder
dist\aud_it\aud_it.exe  <- the launcher
```

Ship the whole `dist\aud_it\` folder, or wrap it with the Inno Setup script in
`install/aud_it.iss`.

## Windows prerequisites for end users

- **Edge WebView2 Runtime** (Evergreen) — required by PyWebView on Windows.
  Most Windows 10/11 systems already have it. If missing, install from
  [Microsoft WebView2](https://developer.microsoft.com/en-us/microsoft-edge/webview2/).
  The Inno Setup script can optionally run the WebView2 bootstrapper.

- **OCRmyPDF** is not bundled on Windows v1. Scanned PDF OCR uses the bundled
  Tesseract fallback via PyMuPDF.

## Bundled Tesseract (Windows)

Windows desktop builds bundle `tesseract.exe`, required DLLs, and `eng.traineddata`
under `_internal/tesseract/` inside the PyInstaller output. At startup,
`desktop.py` sets `PATH`, `TESSDATA_PREFIX`, and `TESSERACT_CMD` before the
server starts.

Stage vendor files before building:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stage_tesseract_win.ps1
```

See [vendor/tesseract/win64/README.md](../vendor/tesseract/win64/README.md) for
licensing (Apache 2.0) and manual staging.

## Where user data lives at runtime

Under a frozen (PyInstaller) build the bundled project root is **read-only**, so
`desktop.py` redirects storage/data to a per-user writable app-data dir by
setting these env vars *before* importing `backend.main`:

| Env var                | Field in config.py | Path (under app-data base)        |
| ---------------------- | ------------------ | --------------------------------- |
| `AUD_IT_STORAGE_DIR`   | `storage_dir`      | `<base>/storage`                  |
| `AUD_IT_DATA_DIR`      | `data_dir`         | `<base>/data`                     |
| `AUD_IT_DATABASE_URL`  | `database_url`     | `sqlite:///<base>/data/aud_it.db` |

App-data base per OS:

- macOS: `~/Library/Application Support/aud_it`
- Windows: `%APPDATA%\aud_it`
- Linux: `$XDG_DATA_HOME/aud_it` or `~/.local/share/aud_it`

Hard reset is **disabled** in frozen desktop builds by default
(`AUD_IT_ALLOW_HARD_RESET=0`).

## CI build (Windows)

GitHub Actions workflow `.github/workflows/desktop-win.yml` builds on
`windows-latest`, stages Tesseract, runs PyInstaller, and uploads
`dist/aud_it/` as an artifact.

## Installer (Inno Setup)

```powershell
# After pyinstaller
iscc install\aud_it.iss
```

Produces `dist/installer/aud_it-setup.exe` installing to
`%LOCALAPPDATA%\Programs\aud_it\` with Start Menu shortcut. User data remains in
`%APPDATA%\aud_it\`.

## Honest size caveat

Bundle size is dominated by the ML/runtime dependencies, **not** the UI shell:

- `en_core_web_lg` spaCy model (~560 MB)
- PyMuPDF native binaries
- Tesseract tessdata + binaries (~15–20 MB)

Expect ~700 MB–1 GB total. Levers to shrink:

- Use a smaller spaCy model (`en_core_web_sm` / `_md`) — edit
  `backend/presidio/registry.py` and the spec's `_add("en_core_web_lg")`.
- Lazy-download the model on first run instead of bundling it.

PyWebView is the lightest windowing path for this stack; Electron/Tauri would
still require the same Python/ML payload as a sidecar.
