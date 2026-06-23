# Windows Tesseract vendor directory

PyInstaller bundles files from this directory into `_internal/tesseract/` inside
the desktop build. Populate it before running `pyinstaller aud_it.spec`.

## Quick setup

From the repo root on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stage_tesseract_win.ps1
```

This copies `tesseract.exe`, DLL dependencies, and `eng.traineddata` from a
system Tesseract install (Chocolatey/winget/manual) into this folder.

## Expected layout

```
vendor/tesseract/win64/
  tesseract.exe
  *.dll                 # e.g. leptonica-*.dll, libtesseract-*.dll
  tessdata/
    eng.traineddata
```

## Manual install sources

- [UB Mannheim Tesseract for Windows](https://github.com/UB-Mannheim/tesseract/wiki)
- [tessdata eng.traineddata](https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata)

## License

Tesseract is licensed under the Apache License 2.0. Tessdata files carry their
own licenses — see the tessdata repository.

Binary files in this directory are **not committed** to git (see `.gitignore`).
CI and release builds stage them at build time.
