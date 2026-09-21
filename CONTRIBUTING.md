# Contributing to 轻图 (QingTu Image Compressor)

感谢你对 **轻图** 的关注与支持！我们欢迎各种形式的贡献，包括但不限于报告 Bug、提交功能建议、补充测试用例、优化算法以及改进文档。

---

## 开发环境搭建

本项目基于 Python 3.11 构建，支持 Windows 和 macOS。

### 1. 克隆代码仓库
```bash
git clone https://github.com/passionworkeer/qingtu-image-compressor.git
cd qingtu-image-compressor
```

### 2. 创建并激活虚拟环境

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-build.txt
```

> **注意 (macOS)**：若通过 Homebrew 安装的 Python 提示缺少 `_tkinter`，请先执行 `brew install python-tk@3.11`。

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-build.txt
```

---

## 本地测试

在提交代码前，请确保全套自动化测试通过：

```bash
pytest -q
```

核心测试用例覆盖：
- 格式兼容性（JPEG / PNG / WebP / HEIC / AVIF / TIFF / BMP 等）
- 大图缩放、Lanczos 重采样与画质搜索
- ICC Profile 与透明度通道保留
- 异常图片容错、系统隐藏文件与 AppleDouble 元数据过滤
- 磁盘空间不足中断、设备拔出容错与取消机制

---

## 打包验证

### macOS 打包
```bash
bash build-macos.sh
python mac_smoke.py
```

### Windows 打包
```powershell
.\build.ps1 -Python '.\.venv\Scripts\python.exe'
```

---

## 提交规范

1. **分支管理**：建议从 `main` 分支拉取新的特性分支（如 `feature/your-feature` 或 `fix/issue-description`）。
2. **Commit 规范**：建议遵循语义化提交规范（Conventional Commits），例如：
   - `feat: 增加对某种新图片格式的支持`
   - `fix: 修复特定条件下的路径处理异常`
   - `docs: 更新 README 使用说明`
   - `test: 补充针对超大分辨率图片的测试用例`
3. **隐私与安全**：提交前请检查个人敏感信息（如个人手机号、API Key、本地私有绝对路径等）。

---

## 报告问题与建议

如果发现 Bug 或有新功能想法，请通过 [GitHub Issues](https://github.com/passionworkeer/qingtu-image-compressor/issues) 提交。请尽量提供：
- 操作系统版本（如 macOS 15.1 / Windows 11 23H2）
- 涉及的原图格式与大致大小
- 详细复现步骤与错误日志
