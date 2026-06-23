# Stage Tesseract binaries for Windows desktop bundling.
#
# Copies tesseract.exe, DLLs, and eng.traineddata into vendor/tesseract/win64/
# so PyInstaller can bundle them (see aud_it.spec).
#
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File scripts\stage_tesseract_win.ps1
#
# Requires Tesseract installed, e.g.:
#   choco install tesseract -y
#   winget install UB-Mannheim.TesseractOCR

$ErrorActionPreference = "Stop"

$dest = Join-Path $PSScriptRoot "..\vendor\tesseract\win64"
$dest = [System.IO.Path]::GetFullPath($dest)
$tessdataDest = Join-Path $dest "tessdata"

New-Item -ItemType Directory -Force -Path $tessdataDest | Out-Null

$candidates = @(
    "C:\Program Files\Tesseract-OCR",
    "C:\Program Files (x86)\Tesseract-OCR"
)

$source = $null
foreach ($path in $candidates) {
    if (Test-Path (Join-Path $path "tesseract.exe")) {
        $source = $path
        break
    }
}

if (-not $source) {
    Write-Error @"
Tesseract not found. Install it first, then re-run this script.

  choco install tesseract -y
  winget install UB-Mannheim.TesseractOCR

Or install from https://github.com/UB-Mannheim/tesseract/wiki
"@
}

Write-Host "Staging Tesseract from $source -> $dest"

Copy-Item -Force (Join-Path $source "tesseract.exe") $dest

Get-ChildItem -Path $source -Filter "*.dll" | ForEach-Object {
    Copy-Item -Force $_.FullName $dest
}

$eng = Join-Path $source "tessdata\eng.traineddata"
if (-not (Test-Path $eng)) {
    Write-Host "Downloading eng.traineddata from tessdata repo..."
    $url = "https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata"
    Invoke-WebRequest -Uri $url -OutFile (Join-Path $tessdataDest "eng.traineddata")
} else {
    Copy-Item -Force $eng $tessdataDest
}

Write-Host "Done. vendor/tesseract/win64 is ready for pyinstaller aud_it.spec"
