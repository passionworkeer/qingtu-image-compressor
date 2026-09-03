# 轻图：图片压缩

Windows / macOS 本地桌面应用。可拖入单图、同一目录中的多张图片，或一个完整文件夹。文件夹会遍历所有子目录并保留目录结构；原图只读。默认 1 MB = 1,000,000 字节。

视频、文档等非图片文件不复制到结果目录，CSV 记录为“非图片已跳过”，不算异常，也不计入压缩节省量。图片仍按内容识别，无后缀或错后缀图片不会仅因文件名被忽略；不支持的图片格式仍保留原件并提示。只有非图片的文件夹会明确显示“没有可处理的图片”。

## 开发

使用 Python 3.11。Windows 10/11 与 macOS 15（Apple 芯片及 Intel）分别构建。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe app.py
```

## 测试与打包

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\build.ps1 -Python '.\.venv\Scripts\python.exe'
```

build.ps1 使用 UTF-8 BOM，兼容 Windows PowerShell 的中文脚本读取。生成 dist/图片压缩工具.exe，一个文件即可分发。

Mac 必须在对应架构的 Mac 上构建，不能从 Windows 交叉打包：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-build.txt
PYTHON_BIN=.venv/bin/python bash build-macos.sh
python mac_smoke.py
```

GitHub Actions 工作流 `.github/workflows/build-macos.yml` 会在 `macos-15`（arm64）和 `macos-15-intel`（x86_64）分别执行全部测试、打包、ad-hoc codesign、命令行压缩烟测和 GUI 启动烟测。输出两个按 CPU 区分的 ZIP。

当前没有 Apple Developer ID 证书，因此不是 Apple 公证包。首次启动如被拦截，先尝试打开应用，再到“系统设置 → 隐私与安全性 → 仍要打开”确认（公司管理的 Mac 可能需 IT 放行）。正式做到首次直接双击无 Gatekeeper 提示，需要 Developer ID Application 证书并执行 notarization。参见 [Apple 官方说明](https://support.apple.com/en-us/102445)。

界面测试会短暂打开 Tk 窗口，覆盖 Tcl 格式的文件夹/单图拖入、跨目录多图拒绝、开始按钮、后台处理、620–880 像素窗口高度和结果状态。核心测试覆盖 20 MB 大图、28 层目录 56 张图片、无后缀及错后缀图片、原件哈希、透明度、旋转、ICC、GIF/多页保留、HEIC/AVIF/WebP/TIFF、云盘 reparse、exFAT 发布回退、同名冲突、磁盘满停止、坏图继续及取消。

命令行验收入口（窗口版 EXE 不输出控制台，请指定 JSON）：

```powershell
Start-Process -FilePath '.\dist\图片压缩工具.exe' -ArgumentList '--batch "D:\图片" --target-mb 1 --result-json "D:\验收结果.json"' -Wait -WindowStyle Hidden
```

退出码：0 全部正常完成；2 含保留未压缩/跳过/异常或写入中止；1 启动级错误。

## 文件结构

- app.py：Tkinter 窗口、拖放、后台事件、命令行入口。
- compressor.py：递归扫描、图片编码、无覆盖文件写入、CSV 报告。
- tests/：行为测试和界面集成测试。
- build.ps1：先运行测试，再用 PyInstaller 打包。
- app.ico：应用图标。

应用流程为本项目编写，未复制某个 GitHub 压图应用。底层使用 Pillow 的 JPEG/libjpeg、WebP/libwebp、PNG 等编解码器，以及 pillow-heif/libheif。Windows 和 Mac 使用同一份 compressor.py，只有系统路径、文件发布方式、字体、文件夹打开方式与构建方式不同；底层二进制库差异可能导致结果字节数略有差别。

JPEG/WebP 默认在质量 82–95 之间搜索；JPEG 使用 4:4:4 采样，减少彩色细线/文字的色彩损失。质量值不是保真百分比。PNG 先保留调色板、透明度、ICC/gamma 等色彩信息做原尺寸无损优化，WebP 先尝试无损编码。仍超限时，按目标与实际字节数的平方根估算缩放比例，使用 LANCZOS 重采样，并重新搜索质量。每次缩放取自原始解码像素，避免重复 JPEG 解码损失。只逐张处理，不把整批解码到内存。

较高质量下限可能需要更小的输出尺寸，这是编码失真与空间细节的取舍，不保证每张图的主观观感都优于旧版。20 MB 压到 1 MB 不能承诺无损；含小字的账单、条码应检查压后可读性，必要时把目标改为 2–3 MB。

检测到的高位深 PNG/TIFF/HEIF 保留原件并提示，避免简单降到 8 位使色阶截断。AVIF 当前按 Pillow 的 8 位 RGB(A) 解码路径处理，不保证保留 HDR/高位深；专业 HDR/印刷流程应使用原图。动图、多页图也保留原件，因此这些项可能超过目标大小。

输出目录通过独占 mkdir 防止重复运行冲突，转换文件名统一按 NFC/casefold 预留。Windows 内部 I/O 使用扩展长路径，界面和报告保持普通路径。软链接/目录联接不跟随；普通云文件可读。图片先写临时文件，Windows rename/POSIX hardlink 发布不覆盖旧文件；exFAT 等不支持硬链接时使用独占创建复制，异常/取消会清理半成品（该回退不具备断电原子性）。

## 技术资料

- [Pillow 官方图像格式与编码参数](https://github.com/python-pillow/Pillow/blob/main/docs/handbook/image-file-formats.rst)
- [微软 JPEG 压缩质量说明](https://learn.microsoft.com/en-us/dotnet/desktop/winforms/advanced/how-to-set-jpeg-compression-level)

运行时依赖 Pillow、pillow-heif（含 libheif 编解码器）、tkinterdnd2（含 tkdnd）、Python/Tcl/Tk；打包使用 PyInstaller。发布时请一并保留交付包中的第三方许可说明。
