# QingTu · Batch Image Compressor (轻图)

<p align="center">
  <b>Lightweight · High Quality · Privacy-First · Cross-Platform Local Batch Image Compressor</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT">
  <img src="https://img.shields.io/badge/Python-3.11%2B-brightgreen.svg" alt="Python: 3.11+">
  <img src="https://img.shields.io/badge/Platform-macOS%20%7C%20Windows-lightgrey.svg" alt="Platform: macOS | Windows">
  <img src="https://img.shields.io/badge/Tests-70%20Passed-success.svg" alt="Tests">
</p>

<p align="center">
  <a href="README.md">简体中文</a> | <a href="README_EN.md">English</a>
</p>

---

## 📖 Introduction

**QingTu (轻图)** is a fast, reliable, privacy-focused desktop and CLI image compression tool designed for photographers, designers, content creators, and everyday office workflows on **macOS** and **Windows**.

Often, you need to batch compress hundreds or thousands of photos, screenshots, or high-resolution images down to a target size (e.g., around **1 MB**) for web display, email attachments, documentation, or upload forms. Traditional online tools risk leaking sensitive personal or corporate data by uploading images to remote servers. Meanwhile, standard offline scripts frequently flatten directory trees, overwrite originals, or produce blurry text due to aggressive downsampling.

QingTu executes **100% locally and offline**. It preserves folder hierarchy, keeps source files read-only, protects image fidelity and ICC color profiles, and provides smooth drag-and-drop desktop interaction alongside a scriptable headless CLI.

---

## ✨ Key Features

- 🔒 **100% Local & Privacy Guaranteed**: All image decoding, compression, and file operations remain on your machine. Zero network connections, zero telemetry.
- 📁 **Preserves Complex Directory Structures**: Supports deeply nested folders (tested up to 28 levels deep). Generates an exact 1:1 mirror of the source tree.
- 🛡️ **Source Read-Only & Safe Atomicity**:
  - Source files are opened strictly in read-only mode and never modified.
  - Supports exporting alongside the original folder or directly to a designated drive (ideal for reading from external HDDs and writing to fast internal SSDs).
  - Uses staging files and atomic filesystem replacement (Windows rename / POSIX hard links fallback) to prevent corrupted partial files during power loss or unplugs.
- 🎨 **Adaptive High-Fidelity Compression**:
  - **Quality Search**: Bisection search for JPEG and WebP between quality 82 and 95 rather than blindly slashing quality.
  - **Chroma Preservation**: JPEG encoding forces 4:4:4 chroma subsampling, preventing color bleed and blur on fine text, receipts, barcodes, and UI edges.
  - **Transparency & Color Management**: Keeps PNG/WebP alpha channels intact and preserves embedded ICC profiles and EXIF orientation.
  - **Lanczos Resampling**: If quality tuning alone exceeds target size, downscaling factor is accurately estimated via square roots and resampled with Lanczos filtering from original decoded pixels.
- 🍏 **Tailored for macOS & External Storage**:
  - Automatically identifies and ignores AppleDouble metadata files (`._*.jpg`) common on exFAT/FAT32 external drives without misreporting them as broken images.
  - Filters out system metadata files like `.DS_Store`, `.Spotlight-V100`, `$RECYCLE.BIN`, and non-image files.
  - Recognizes true image files even without extensions or with mismatched extensions via magic bytes.
- 📊 **Detailed CSV Audit Reports**: Every batch automatically outputs `_压缩报告.csv` containing original paths, output sizes, space saved, and elapsed time.
- 💻 **Dual Mode: Modern GUI + Headless CLI**:
  - **Desktop GUI**: Clean card-based Tkinter interface with drag-and-drop, progress bar, and instant output folder opening.
  - **CLI Mode**: Automated batch processing via `--batch` with structured JSON output and standardized exit codes.

---

## 🖼️ Supported Formats

| Format | Suffixes | Strategy & Highlights |
| :--- | :--- | :--- |
| **JPEG** | `.jpg`, `.jpeg`, `.jfif` | 4:4:4 sampling, 82–95 bisection quality search; Lanczos downscaling if needed |
| **PNG** | `.png` | Lossless palette/transparency optimization first; adaptive scaling if oversized |
| **WebP** | `.webp` | Lossless attempt first; high-quality lossy compression fallback |
| **HEIC / HEIF** | `.heic`, `.heif` | Native `libheif` support; detects and safeguards high bit-depth |
| **AVIF** | `.avif` | Modern high-efficiency decoding and quality optimization |
| **TIFF / BMP** | `.tif`, `.tiff`, `.bmp` | Scans and bitmaps optimized to modern formats |
| **GIF / Multi-frame** | `.gif` | Multi-frame animations and multi-page documents are safely preserved as-is |

> **Safety Threshold**: High-resolution safety limit is set to 120,000,000 pixels (120 MP) per frame to prevent malicious decompression bombs from exhausting RAM.

---

## 🚀 Quick Start

### Option 1: Download Pre-built Binaries (Recommended)

Download the executable for your platform from [Releases](https://github.com/passionworkeer/qingtu-image-compressor/releases):
- **macOS**: `轻图图片压缩-macOS-arm64.zip` (Apple Silicon) or `轻图图片压缩-macOS-x86_64.zip` (Intel).
- **Windows**: `轻图图片压缩.exe` (Single standalone executable, no installation needed).

> **macOS Gatekeeper Note**:
> Because the application is not notarized with a paid Apple Developer ID certificate, macOS might show a warning on first launch.
> 1. Go to **System Settings → Privacy & Security**.
> 2. Scroll to Security and click **Open Anyway**.
> Refer to [Apple Support](https://support.apple.com/en-us/102445) for details.

---

### Option 2: Run from Source

#### Prerequisites
- Python 3.11+
- Git

#### 1. Clone the repository
```bash
git clone https://github.com/passionworkeer/qingtu-image-compressor.git
cd qingtu-image-compressor
```

#### 2. Create and activate a virtual environment

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-build.txt
```
> *Note for macOS Homebrew Python: If `_tkinter` is missing, install it via `brew install python-tk@3.11`.*

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-build.txt
```

#### 3. Run the GUI app
```bash
python app.py
```

---

## ⚙️ Command Line Interface (CLI)

Run batch jobs in headless environments or automated pipelines:

```bash
python app.py --batch "/path/to/source" --target-mb 1.5 --output-dir "/path/to/output" --result-json "/path/to/result.json"
```

### Windows Packaged EXE Example:
```powershell
Start-Process -FilePath '.\dist\轻图图片压缩.exe' -ArgumentList '--batch "E:\Photos" --output-dir "D:\Compressed" --target-mb 1 --result-json "D:\result.json"' -Wait -WindowStyle Hidden
```

### CLI Arguments:

| Argument | Description | Example |
| :--- | :--- | :--- |
| `--batch` | Path to source directory or single image file | `--batch "/path/to/folder"` |
| `--target-mb` | Maximum file size target in MB (decimals supported, default: `1`) | `--target-mb 1.2` |
| `--output-dir` | Parent directory for results (creates `xxx_已压缩` inside) | `--output-dir "/Volumes/SSD/Out"` |
| `--result-json` | Path to save JSON summary report | `--result-json "./report.json"` |

### Exit Codes:
- `0`: All files compressed/processed successfully.
- `2`: Completed with skipped files, preserved originals, or non-fatal errors.
- `1`: Startup or fatal invocation error.

---

## 🛠️ Testing & Building

### Run Automated Tests
```bash
pytest -q
```
Runs 70 test cases validating formats, adversarial cases, deep directories, ICC profiles, memory limits, and cancellations.

### Build macOS App Bundle
```bash
bash build-macos.sh
python mac_smoke.py
```

### Build Windows Executable
```powershell
.\build.ps1 -Python python
```

---

## 📂 Project Structure

```text
qingtu-image-compressor/
├── app.py                     # Tkinter GUI, drag-drop handling, and CLI entry point
├── compressor.py              # Compression engine, scan, atomic writes & CSV reporting
├── app_icon.png               # Application icon (PNG)
├── app.ico                    # Application icon (ICO)
├── build-macos.sh             # macOS bundle & codesign script
├── build.ps1                  # Windows PyInstaller script
├── mac_smoke.py               # macOS packaged app integration & GUI smoke test
├── requirements.txt           # Production dependencies (Pillow, pillow-heif, tkinterdnd2)
├── requirements-build.txt     # Build and test dependencies (PyInstaller, pytest)
├── pyproject.toml             # Modern project metadata & configuration
├── pytest.ini                 # Pytest configuration
├── tests/                     # Comprehensive test suite (70 test cases)
└── .github/workflows/         # CI/CD Workflows for macOS and Windows
```

---

## 🤝 Contributing

Contributions are warmly welcomed! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting Pull Requests.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
