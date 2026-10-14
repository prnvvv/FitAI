<#
.SYNOPSIS
  Start the FitAI backend and frontend locally (Windows / PowerShell).

.DESCRIPTION
  Reads BACKEND_HOST and BACKEND_PORT from backend\.env (the single source of
  truth), refuses to start with a clear message when the port is unavailable,
  starts uvicorn and Vite, and stops both child processes on exit.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
#>
[CmdletBinding()]
param(
  [switch]$BackendOnly,
  [switch]$FrontendOnly
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $Root 'backend'
$FrontendDir = Join-Path $Root 'frontend'

function Get-EnvValue([string]$Path, [string]$Key, [string]$Default) {
  if (-not (Test-Path $Path)) { return $Default }
  $match = Select-String -Path $Path -Pattern "^$Key=(.*)$" | Select-Object -First 1
  if (-not $match) { return $Default }
  $value = $match.Matches[0].Groups[1].Value.Trim()
  if (-not $value) { return $Default }
  return $value
}

$EnvFile = Join-Path $BackendDir '.env'
$Host_ = Get-EnvValue $EnvFile 'BACKEND_HOST' '127.0.0.1'
$Port_ = [int](Get-EnvValue $EnvFile 'BACKEND_PORT' '8000')

function Test-PortInUse([int]$Port) {
  $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  return $null -ne $conn
}

function Show-PortHelp([int]$Port) {
  Write-Host ""
  Write-Host "Cannot start the backend: port $Port is not available." -ForegroundColor Yellow
  Write-Host ""
  Write-Host "Check what is holding it:" -ForegroundColor Yellow
  Write-Host "  Get-NetTCPConnection -LocalPort $Port | Select-Object -ExpandProperty OwningProcess"
  Write-Host "  Get-Process -Id <PID>"
  Write-Host ""
  Write-Host "Windows also reserves ranges that cannot be bound:"
  Write-Host "  netsh interface ipv4 show excludedportrange protocol=tcp"
  Write-Host ""
  Write-Host "To use a different port, set one value in backend\.env:"
  Write-Host "  BACKEND_PORT=8765" -ForegroundColor Cyan
  Write-Host "The Vite proxy and this script both read that value." -ForegroundColor Cyan
}

if (-not $FrontendOnly) {
  if (Test-PortInUse $Port_) {
    Show-PortHelp $Port_
    exit 1
  }

  # Warn when the port falls inside a Windows reserved range (Hyper-V / WSL / Docker).
  $excluded = netsh interface ipv4 show excludedportrange protocol=tcp | Select-Object -Skip 3
  foreach ($line in $excluded) {
    if ($line -match '^\s*(\d+)\s+(\d+)') {
      $start = [int]$Matches[1]; $end = [int]$Matches[2]
      if ($Port_ -ge $start -and $Port_ -le $end) {
        Write-Host "Port $Port_ is inside the Windows excluded range $start-$end." -ForegroundColor Yellow
        Write-Host "Choose another port and set BACKEND_PORT in backend\.env." -ForegroundColor Yellow
        exit 1
      }
    }
  }
}

$jobs = @()
$python = Join-Path $BackendDir '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }

if (-not $FrontendOnly) {
  Write-Host "Backend  -> http://${Host_}:${Port_}" -ForegroundColor Cyan
  Push-Location $BackendDir
  $jobs += Start-Process -FilePath $python `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--reload', '--reload-dir', 'app', '--host', $Host_, '--port', $Port_ `
    -NoNewWindow -PassThru
  Pop-Location
}

if (-not $BackendOnly) {
  Write-Host "Frontend -> http://127.0.0.1:5173" -ForegroundColor Cyan
  Push-Location $FrontendDir
  $jobs += Start-Process -FilePath 'npm.cmd' -ArgumentList 'run', 'dev' -NoNewWindow -PassThru
  Pop-Location
}

Write-Host ""
Write-Host "Running. Press Ctrl+C to stop both." -ForegroundColor Green

try {
  while ($true) {
    Start-Sleep -Seconds 2
    $alive = $jobs | Where-Object { -not $_.HasExited }
    if ($alive.Count -eq 0) { break }
  }
}
finally {
  foreach ($job in $jobs) {
    if ($job -and -not $job.HasExited) {
      # Stop the whole process tree (uvicorn --reload spawns a child).
      & taskkill.exe /PID $job.Id /T /F | Out-Null
    }
  }
  Write-Host ""
  Write-Host "Stopped." -ForegroundColor Green
}
