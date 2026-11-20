<#
.SYNOPSIS
  Runs ProfitPilot (API + built frontend on one port) and restarts it whenever it exits.

.DESCRIPTION
  Started at boot by the "ProfitPilot" scheduled task that install.ps1 registers; can also be run
  by hand. Settings come from the env file (KEY=VALUE lines, same keys as backend/.env.example).
  This script sets the parts that depend on where things live on this machine — the database,
  backups, the built frontend — and forces DEBUG off; values for those in the env file are ignored.

  Never binds to 0.0.0.0 unless you set it: there is no login in Phase 1. For remote access set
  PROFITPILOT_BIND in the env file to this PC's Tailscale IP.
#>
param(
    [string]$Home_ = "C:\ProfitPilot",
    [int]$Port = 8000
)
$ErrorActionPreference = "Continue"   # native stderr must not abort the restart loop

$repo     = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$backend  = Join-Path $repo "backend"
$python   = Join-Path $backend ".venv\Scripts\python.exe"
$envFile  = Join-Path $Home_ "profitpilot.env"
$dataDir  = Join-Path $Home_ "data"
$logDir   = Join-Path $Home_ "logs"
foreach ($d in @($dataDir, $logDir)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }

function Write-RunLog([string]$msg) {
    $line = "{0} [run.ps1] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path (Join-Path $logDir ("profitpilot-{0}.log" -f (Get-Date -Format "yyyyMMdd"))) -Value $line
}

if (-not (Test-Path $python)) { Write-RunLog "venv missing at $python - run update.ps1 first"; exit 1 }
if (-not (Test-Path $envFile)) { Write-RunLog "env file missing at $envFile - run install.ps1 first"; exit 1 }

# Load KEY=VALUE pairs (comments and blank lines skipped; surrounding quotes stripped).
foreach ($raw in Get-Content $envFile) {
    $line = $raw.Trim()
    if ($line -eq "" -or $line.StartsWith("#") -or -not $line.Contains("=")) { continue }
    $key, $value = $line.Split("=", 2)
    [Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim().Trim('"').Trim("'"), "Process")
}

# Machine-layout settings: always ours, never the env file's.
$env:DATABASE_URL      = "sqlite+aiosqlite:///" + (Join-Path $dataDir "profitpilot.db").Replace("\", "/")
$env:FRONTEND_DIST_DIR = Join-Path $repo "frontend\dist"
$env:DEBUG             = "false"
if (-not $env:BACKUP_DIR) { $env:BACKUP_DIR = Join-Path $Home_ "backups" }
$bind = if ($env:PROFITPILOT_BIND) { $env:PROFITPILOT_BIND } else { "127.0.0.1" }

while ($true) {
    # A copy left over from a killed task would hold the port and make the new one fail to bind.
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
        if ($p -and $p.Path -eq $python) {
            Write-RunLog "stopping stale ProfitPilot process $($p.Id) holding port $Port"
            Stop-Process -Id $p.Id -Force
        }
    }
    $log = Join-Path $logDir ("profitpilot-{0}.log" -f (Get-Date -Format "yyyyMMdd"))
    Write-RunLog "starting on ${bind}:$Port"
    # cmd /c: plain byte redirection (PowerShell 5.1 would wrap every stderr line as an error).
    # One worker on purpose: the strategy executor is an in-process singleton.
    Push-Location $backend
    cmd /c "`"$python`" -m uvicorn app.main:app --host $bind --port $Port >> `"$log`" 2>&1"
    $code = $LASTEXITCODE
    Pop-Location
    Write-RunLog "exited with code $code - restarting in 10s"
    Start-Sleep -Seconds 10
}
