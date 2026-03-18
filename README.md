# PDF Rearranger GUI

PDF Rearranger — a small PyQt5 desktop GUI for reordering, extracting, and saving pages in PDF files (uses PyMuPDF and Pillow); includes macOS packaging scripts to build a signed .app and DMG.

PDF Rearranger is a lightweight desktop application (built with PyQt5) for quickly rearranging pages in PDF documents using PyMuPDF for PDF manipulation and Pillow for image handling. This repository contains the source entrypoint (`main.py`), dependency list (`requirements.txt`), developer scripts (`run.sh`, `Makefile`), and macOS packaging artifacts and helpers (`build_dmg.sh`, `create_icns.sh`, `codesign_and_notarize.sh`, and the `dmg_staging` folder) to produce a standalone, signed .app and distributable DMG.

Version: 0.2.1

Simple drag-and-drop GUI to import PDFs, rearrange pages, delete pages, and save the result as a single PDF.

Requirements
- Python 3.8+
- Install dependencies:

```bash
pip install -r "requirements.txt"
```

Run

```bash
python "main.py"
```

Build a macOS DMG
 - Install build deps:

```bash
pip install -r requirements.txt
```

- Build the .app and .dmg (macOS only):

```bash
./build_dmg.sh
```

This script uses `pyinstaller` to create an application bundle and `hdiutil` to package it into a `.dmg`. You may need to `chmod +x build_dmg.sh` before running.

Codesigning and notarization
 - To distribute outside your machine, macOS requires a Developer ID signing certificate and notarization by Apple. You can sign and notarize locally or via CI.

Local notes:
- Create an App icon `icon.png` (preferably 1024x1024) and run:

```bash
./scripts/create_icns.sh icon.png app.icns
# copy app.icns into the .app/Contents/Resources and set CFBundleIconFile in Info.plist before signing
```

- Import your signing certificate (.p12) into the login keychain and set environment variables:

```bash
export P12_PATH=/path/to/cert.p12
export P12_PASSWORD=your_p12_password
export SIGNING_ID="Developer ID Application: Your Name (TEAMID)"
export APPLE_ID="your@apple.id"
export APPLE_PASSWORD="app-specific-password"
export TEAM_ID="YOUR_TEAM_ID"
```

- After building the DMG with `./build_dmg.sh`, run:

```bash
./scripts/codesign_and_notarize.sh dist/PDF\ Rearranger.app
```

CI notes (GitHub Actions):
- The workflow `.github/workflows/macos_build.yml` demonstrates how to decode a base64-encoded signing certificate (stored as `CERT_P12` secret), import it into a temporary keychain, build, sign and notarize using the `APPLE_ID` and `APPLE_PASSWORD` secrets.
- Required repository secrets (examples): `CERT_P12` (base64), `CERT_P12_PASSWORD`, `SIGNING_ID`, `APPLE_ID`, `APPLE_PASSWORD`, `TEAM_ID`.

Building a Windows executable
----------------------------

There are two recommended ways to produce a Windows `.exe`:

- Local on Windows: run the included PyInstaller command (requires Python + PyInstaller installed):

```bash
# on Windows (PowerShell / cmd)
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --windowed --name "PDF Rearranger" main.py
```

- From macOS/Linux using Docker (uses a Wine-based PyInstaller image):

```bash
./scripts/build_windows_exe.sh
```

This script uses the `cdrx/pyinstaller-windows` Docker image to run PyInstaller inside a Wine environment and will place the resulting artifacts under `dist/` on the host.

CI (recommended): use the provided GitHub Actions workflow `.github/workflows/build-windows.yml` which builds the exe on a Windows runner and uploads the `dist/` folder as a workflow artifact.


Usage
- Drag one or more PDF files onto the window, or click "Import PDFs".
- Reorder pages by dragging items in the list.
- Select items and click "Delete Selected" to remove pages.
- Click "Save As PDF" to export the rearranged pages into one PDF.

Optional OCR (searchable PDF)
- The app supports optional OCR when saving: enable "Enable OCR" in the toolbar and choose a language.
- `ocrmypdf` is used to produce searchable PDFs (it embeds invisible text while preserving layout).
- Requirements: Tesseract OCR and Ghostscript must be installed on your system.

Installation examples (macOS):
```bash
brew install tesseract ghostscript
pip install -r requirements.txt
```

Linux (Debian/Ubuntu):
```bash
sudo apt install tesseract-ocr ghostscript
pip install -r requirements.txt
```

If `ocrmypdf` is not available the app will save a normal (non-searchable) PDF instead.
