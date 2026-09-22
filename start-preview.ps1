$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$runtimePython = Join-Path $PSScriptRoot '../../work/venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $runtimePython)) {
    $runtimePython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
}
if (-not (Test-Path -LiteralPath $runtimePython)) {
    Write-Error 'Install the local runtime using the steps in README.md first.'
}
if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) {
    Push-Location frontend
    try { npm ci; npm run build } finally { Pop-Location }
}
Write-Host 'Tradersecho is available at http://127.0.0.1:8000. Keep this window open.'
& $runtimePython -m uvicorn backend.service:app --host 127.0.0.1 --port 8000
