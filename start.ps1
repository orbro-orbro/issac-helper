$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "未找到 Python。请安装 Python 3.10 或更高版本后重试。"
}

$version = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python $version 版本过低。请安装 Python 3.10 或更高版本。"
}
Write-Host "Isaac Helper · Python $version"
Write-Host "正在启动本地页面……"
python -m app.server --open
exit $LASTEXITCODE
