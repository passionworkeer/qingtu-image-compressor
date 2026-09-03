# 轻图：图片压缩

Windows / macOS 本地桌面应用。可拖入单图、同一目录中的多张图片，或一个完整文件夹。文件夹会遍历所有子目录并保留目录结构；原图只读。默认 1 MB = 1,000,000 字节。

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

当前没有 Apple Developer ID 证书，因此不是 Apple 公证包。从浏览器下载后，首次启动可能需要在 Finder 中右键应用并选“打开”；正式做到首次直接双击无 Gatekeeper 提示，需要提供 Apple Developer Program 的 Developer ID Application 证书并执行 notarization。

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

JPEG/WebP 使用质量 60–95 搜索；达到下限仍超限时，按目标与实际字节数的平方根估算缩放比例，使用 LANCZOS 重采样，并重新搜索质量。PNG 保留透明度，以无损编码和必要的缩放满足体积要求。原始像素用于每次缩放，避免重复 JPEG 解码损失。支持文件只逐张处理，不把整批解码到内存。

原文件写权限永不需要；输出目录通过独占 mkdir 防止重复运行冲突。转换格式时预留所有源文件名和目录名。图片先写临时文件，完成后重命名发布。Windows 的 rename 不覆盖已存在目标。软链接与 Windows 重解析点不跟随，错误在逐项报告中可见。

## 技术资料

- [Pillow 官方图像格式与编码参数](https://github.com/python-pillow/Pillow/blob/main/docs/handbook/image-file-formats.rst)
- [微软 JPEG 压缩质量说明](https://learn.microsoft.com/en-us/dotnet/desktop/winforms/advanced/how-to-set-jpeg-compression-level)

运行时依赖 Pillow、pillow-heif（含 libheif 编解码器）、tkinterdnd2（含 tkdnd）、Python/Tcl/Tk；打包使用 PyInstaller。发布时请一并保留交付包中的第三方许可说明。
