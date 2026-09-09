$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python was not found. Install Python 3.10 or newer and try again."
}

$version = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python $version is too old. Install Python 3.10 or newer."
}
Write-Host "Isaac Helper - Python $version"
Write-Host "Starting the local page..."
python -m app.server --open
exit $LASTEXITCODE
