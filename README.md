# 轻图 · 批量图片压缩 (QingTu Image Compressor)

<p align="center">
  <b>轻量 · 高效 · 隐私第一 · 跨平台本地批量图片压缩桌面工具</b>
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

## 📖 项目简介

**轻图（QingTu）** 是一款面向摄影师、设计工作者、自媒体创作者及普通办公用户的本地跨平台批量图片压缩工具（支持 macOS 与 Windows）。

在日常工作和生活中，我们经常需要将单张或数万张数码照片、截图、扫描件统一压缩到 **1 MB 左右**，以便用于网页展示、邮件附件、文档插入或系统上传。市面上的工具往往需要将照片上传到云端服务器（存在隐私泄露风险），或者在处理多层目录时容易破坏文件夹结构，甚至覆盖损坏原图。

轻图坚持 **100% 纯本地离线处理**，在最大程度保留原图画质、色彩配置（ICC Profile）与透明通道的前提下，提供丝滑的拖拽操作和极致的安全防护。

---

## ✨ 核心特性

- 🔒 **100% 纯本地运行 · 零隐私泄漏**：所有编解码与文件读写均在本地计算机完成，不发送任何网络请求，企业敏感资料与私人照片安全无虞。
- 📁 **完整保留多层目录结构**：支持拖入数十层嵌套的超大文件夹，自动遍历所有子目录，并 1:1 复刻输出目录树。
- 🛡️ **原图只读保护 · 异常安全回退**：
  - 源文件严格以只读方式打开，绝不改动原图一字节。
  - 支持“同级生成副本”或“自定义导出到指定磁盘”（例如：直接从移动固态硬盘读取，压缩输出到本机高速 SSD）。
  - 采用临时文件写入 + 系统级原子发布（Windows rename / POSIX hardlink 回退），杜绝因断电、存储拔出或磁盘满产生半成品。
- 🎨 **自适应高品质压缩算法**：
  - **画质优先**：JPEG / WebP 默认在质量 82–95 之间进行智能二分搜索，杜绝一刀切式的重度有损压缩。
  - **文字与色彩保护**：JPEG 强制采用 4:4:4 无子采样（Chroma Subsampling），避免海报、UI 截图及含小字账单的边缘发糊或发红。
  - **透明度与色彩管理**：完整保留 PNG / WebP 透明通道，自动应用并保留 ICC Profile 及 EXIF 旋转方向。
  - **智能重采样**：图片超出目标体积时，基于目标与实际字节数平方根精确估算缩放比，采用 Lanczos 高阶重采样插值。
- 🍏 **深度适配 macOS 与外接设备**：
  - 自动识别并过滤 exFAT 等外接盘生成的 AppleDouble（`._*.jpg`）元数据文件，不误报损坏。
  - 自动忽略 `.DS_Store`、`.Spotlight-V100`、`$RECYCLE.BIN` 等系统文件和废纸篓目录。
  - 自动跳过视频、文档等非图片内容，无后缀或错后缀的真实图片依然能按二进制魔数正常识别并压缩。
- 📊 **合规级 CSV 审计报告**：每次任务结束后均在结果根目录下生成 `_压缩报告.csv`，记录每张图片的原路径、状态、压缩前后字节数、节省率与耗时。
- 💻 **双模交互：现代 GUI + Headless CLI**：
  - **桌面 GUI**：Tkinter 现代卡片式风格，支持文件/文件夹拖拽、实时进度与结果即时预览。
  - **命令行 CLI**：支持 `--batch` 静默批处理并输出结构化 JSON 结果，便于脚本整合与自动化运维。

---

## 🖼️ 支持格式全景

| 格式 | 扩展名 | 压缩策略与说明 |
| :--- | :--- | :--- |
| **JPEG** | `.jpg`, `.jpeg`, `.jfif` | 4:4:4 色度采样，82–95 画质自适应搜索；超限时 Lanczos 缩放 |
| **PNG** | `.png` | 优先保留调色板、透明度与 Gamma 做原尺寸无损压缩；必要时平滑降维 |
| **WebP** | `.webp` | 优先尝试无损编码；必要时启用高质量有损压缩与缩放 |
| **HEIC / HEIF** | `.heic`, `.heif` | 基于原生 `libheif` 解码，自动检测高位深并安全保留 |
| **AVIF** | `.avif` | 现代高压缩比格式支持，高质量编码 |
| **TIFF / BMP** | `.tif`, `.tiff`, `.bmp` | 扫描件、位图体积优化并转为现代通用格式 |
| **GIF / 动图** | `.gif` | 自动检测多帧动图与多页图片，保留原件并明确提示，避免破坏帧动画 |

> **安全上限**：单帧安全上限设为 1.2 亿像素（120,000,000 像素），严防伪造的恶意超大解压炸弹图片占用耗尽系统内存。

---

## 🚀 快速开始

### 方式一：直接下载使用（推荐）

前往 [Releases 页面](https://github.com/passionworkeer/qingtu-image-compressor/releases) 下载适合您操作系统的预编译包：
- **macOS**：下载 `轻图图片压缩-macOS-arm64.zip`（Apple Silicon）或 `轻图图片压缩-macOS-x86_64.zip`（Intel）。
- **Windows**：下载 `轻图图片压缩.exe`，无需安装，双击即可直接运行。

> **macOS 首次打开提示“无法打开”？**
> 由于本应用暂未购买昂贵的 Apple Developer ID 证书公证，首次双击如被 Gatekeeper 拦截：
> 1. 请打开 **“系统设置” → “隐私与安全性”**；
> 2. 向下滚动找到轻图，点击 **“仍要打开”** 即可正常使用。详细原因参见 [Apple 官方支持文档](https://support.apple.com/en-us/102445)。

---

### 方式二：从源码运行（开发者）

#### 环境准备
- Python 3.11 或更高版本
- Git

#### 1. 克隆代码
```bash
git clone https://github.com/passionworkeer/qingtu-image-compressor.git
cd qingtu-image-compressor
```

#### 2. 创建并激活虚拟环境

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-build.txt
```
> *注：macOS 若提示缺少 `_tkinter`，可先运行 `brew install python-tk@3.11`。*

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-build.txt
```

#### 3. 启动应用
```bash
python app.py
```

---

## ⚙️ 命令行使用 (CLI)

轻图支持在无界面环境下作为批处理工具运行，可无缝集成至工作流脚本中：

```bash
# 基本用法：指定目标大小（单位 MB，默认 1）与输出目录
python app.py --batch "/path/to/source" --target-mb 1.5 --output-dir "/path/to/output" --result-json "/path/to/result.json"
```

### Windows 编译后 EXE 示例：
```powershell
Start-Process -FilePath '.\dist\轻图图片压缩.exe' -ArgumentList '--batch "E:\摄影原图" --output-dir "D:\压缩备份" --target-mb 1 --result-json "D:\result.json"' -Wait -WindowStyle Hidden
```

### CLI 参数表：

| 参数 | 说明 | 示例 |
| :--- | :--- | :--- |
| `--batch` | 要处理的源文件夹或单张图片路径 | `--batch "/Users/name/Photos"` |
| `--target-mb` | 目标大小上限（兆字节，支持小数，默认 `1`） | `--target-mb 0.8` |
| `--output-dir` | 指定导出的父级目录（将在其下自动创建 `xxx_已压缩`） | `--output-dir "/Volumes/SSD/Export"` |
| `--result-json` | 将最终统计结果以 JSON 格式写入指定文件 | `--result-json "./summary.json"` |

### 进程退出码：
- `0`：全部文件正常完成。
- `2`：包含跳过项、未压缩保留项或部分异常，任务完成。
- `1`：启动级致命错误（例如输入路径不存在）。

---

## 🛠️ 测试与打包构建

### 运行全套单元与回归测试
```bash
pytest -q
```
测试集涵盖 70 项严格用例，包含 20MB 高噪点大图、100MP 相机照片、28 层极深嵌套目录、损坏 ICC、畸变文件头、截断动图、外接盘硬链接回退与高并发取消机制。

### macOS 本地打包
```bash
# 执行测试、生成 .app 并打为 zip 包
bash build-macos.sh

# 运行真实 App 内嵌环境烟雾测试
python mac_smoke.py
```

### Windows 本地打包
```powershell
# 在 Windows PowerShell 下执行
.\build.ps1 -Python python
```
生成单一独立可分发文件 `dist\轻图图片压缩.exe`。

---

## 📂 项目结构

```text
qingtu-image-compressor/
├── app.py                     # Tkinter 桌面图形界面、拖放事件与 CLI 解析入口
├── compressor.py              # 核心压缩引擎：文件扫描、图像处理、安全原子写入与 CSV 生成
├── app_icon.png               # 应用图标 (PNG 格式)
├── app.ico                    # 应用图标 (Windows ICO 格式)
├── build-macos.sh             # macOS 自动化构建与代码签名脚本
├── build.ps1                  # Windows PowerShell 一键打包脚本
├── mac_smoke.py               # macOS 交付包内编解码与 GUI 启动验证脚本
├── requirements.txt           # 生产运行依赖 (Pillow, pillow-heif, tkinterdnd2)
├── requirements-build.txt     # 构建与测试依赖 (PyInstaller, pytest)
├── pyproject.toml             # 项目元数据与打包构建配置
├── pytest.ini                 # 测试配置
├── tests/                     # 自动化测试用例集
│   ├── test_adversarial.py    # 恶意构造、系统文件与异常容错测试
│   ├── test_app.py            # GUI 交互与生命周期测试
│   ├── test_compressor.py     # 核心压缩流程与大图测试
│   ├── test_formats.py        # 图像格式兼容性与 CSV 注入防护测试
│   ├── test_platform.py       # 跨平台路径与系统调用测试
│   ├── test_quality.py        # 画质自适应与无损保留测试
│   └── test_release_edges.py  # 磁盘满、硬链接与边界条件测试
└── .github/workflows/         # GitHub Actions 跨平台持续集成流
    ├── build-macos.yml        # macOS (arm64 + x86_64) 双架构自动化构建
    └── build-windows.yml      # Windows x64 自动化构建
```

---

## 🤝 参与贡献

欢迎提交 Issue 和 Pull Request！在贡献代码之前，请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 📄 开源协议

本项目采用 [MIT 许可证](LICENSE)。

第三方依赖声明：
- [Pillow](https://github.com/python-pillow/Pillow) (HPND License)
- [pillow-heif](https://github.com/bigcat88/pillow_heif) (LGPL / Apache License)
- [tkinterdnd2](https://github.com/petasis/tkinterdnd2) (BSD License)
- [PyInstaller](https://www.pyinstaller.org/) (GPLv2 with exception)
