param(
    [string]$Python = "python",
    [string]$OutputDir = (Join-Path $PSScriptRoot "dist")
)
$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    & $Python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "测试未通过" }
    & $Python -m PyInstaller --noconfirm --clean --onefile --windowed --name "轻图图片压缩" --icon app.ico --add-data "app.ico;." --add-data "app_icon.png;." --collect-all tkinterdnd2 --collect-all pillow_heif --exclude-module numpy --exclude-module pandas --exclude-module matplotlib --exclude-module scipy --exclude-module IPython --distpath $OutputDir --workpath .build app.py
    if ($LASTEXITCODE -ne 0) { throw "打包失败" }
    Write-Host "打包完成：$OutputDir\轻图图片压缩.exe"
} finally {
    Pop-Location
}
