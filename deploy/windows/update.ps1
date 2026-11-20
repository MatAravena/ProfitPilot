<#
.SYNOPSIS
  Brings the installed ProfitPilot up to date: code, Python packages, frontend build, restart.

.DESCRIPTION
  Code comes from one of two places:
    -Source <dir>  mirror a directory into this install (used by the GitHub deploy workflow:
                   the runner checks the repo out, this copies it in — the box needs no GitHub
                   credentials). Your data, settings and logs live in C:\ProfitPilot, not here.
    (default)      `git pull --ff-only` in this install.
    -SkipPull      neither (first install, or testing).
  Then: create the venv if missing, install backend/requirements.txt, `npm ci` + `npm run build`,
  restart the "ProfitPilot" scheduled task if it exists, and wait for /api/v1/health.
  Exits non-zero on any failure so a deploy job goes red.
#>
param(
    [string]$AppDir = "",   # the install to update; default = the repo this script sits in
    [string]$Source = "",
    [switch]$SkipPull,
    [string]$Python = "python",
    [int]$Port = 8000,
    [string]$TaskName = "ProfitPilot",
    [string]$Home_ = "C:\ProfitPilot"
)
$ErrorActionPreference = "Stop"
# The deploy workflow runs the NEW copy of this script (from its fresh checkout) with -AppDir
# pointing at the install, so script fixes ship in the same deploy.
$repo = if ($AppDir) { (Resolve-Path $AppDir).Path } else { (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }
$backend  = Join-Path $repo "backend"
$frontend = Join-Path $repo "frontend"
$venvPy   = Join-Path $backend ".venv\Scripts\python.exe"

function Step([string]$msg) { Write-Host "==> $msg" }
function Invoke-Native([string]$what, [scriptblock]$cmd) {
    & $cmd
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit $LASTEXITCODE)" }
}

if ($Source) {
    Step "Copying code from $Source"
    # /MIR mirrors, but never touch build outputs, installed packages or git metadata here.
    robocopy $Source $repo /MIR /NFL /NDL /NJH /NJS /NP `
        /XD .git .venv node_modules dist graphify-out .claude __pycache__ .pytest_cache `
        /XF profitpilot.db .env | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed (exit $LASTEXITCODE)" }   # 0-7 = success
    $global:LASTEXITCODE = 0
} elseif (-not $SkipPull) {
    Step "git pull"
    Invoke-Native "git pull" { git -C $repo pull --ff-only }
}

function Install-PythonPackages {
    Step "Installing Python packages"
    Invoke-Native "pip install" { & $venvPy -m pip install --disable-pip-version-check -q -r (Join-Path $backend "requirements.txt") }
}

if (-not (Test-Path $venvPy)) {
    Step "Creating Python venv with '$Python'"
    Invoke-Native "venv creation" { & $Python -m venv (Join-Path $backend ".venv") }
}

# The frontend builds while the bots keep running (only the web page blinks for a few seconds).
Step "Building the frontend"
Push-Location $frontend
try {
    Invoke-Native "npm ci" { npm ci --no-audit --no-fund --loglevel=error }
    Invoke-Native "npm run build" { npm run build }
} finally { Pop-Location }

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Install-PythonPackages
    Step "No '$TaskName' task registered - not restarting (run install.ps1 once)."
    exit 0
}

# Everything below happens with the app stopped, and the app is ALWAYS started again (finally):
#  - pip must run while it is stopped — Windows locks the .pyd/.dll files of a running Python, so
#    upgrading numpy/pydantic under a live app fails half-way;
#  - a failed update must never leave the bots down: they come back on whatever code is in place.
# Continuity is in the database (strategies, paper accounts, positions, risk high-water marks),
# so the restarted app resumes every paper/live strategy where it was.
Step "Stopping the '$TaskName' task"
Stop-ScheduledTask -TaskName $TaskName
# Stopping the task ends run.ps1; make sure the server it started goes too.
Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
    if ($p -and $p.Path -eq $venvPy) { Stop-Process -Id $p.Id -Force }
}
try {
    $db = Join-Path $Home_ "data\profitpilot.db"
    if (Test-Path $db) {
        # Snapshot right before new code (and its migrations) touch the database — the way back
        # if an update ever damages data. Separate folder, so the daily backups' retention
        # can't rotate these out.
        Step "Snapshotting the database"
        $url = "sqlite+aiosqlite:///" + $db.Replace("\", "/")
        $dest = Join-Path $Home_ "backups\pre-update"
        Push-Location $backend
        try {
            Invoke-Native "database snapshot" {
                & $venvPy -c "import sys; from app.db.backup import backup_sqlite; print(backup_sqlite(sys.argv[1], sys.argv[2], keep=10))" $url $dest
            }
        } finally { Pop-Location }
    }
    Install-PythonPackages
} finally {
    Step "Starting the '$TaskName' task"
    Start-ScheduledTask -TaskName $TaskName
}

Step "Waiting for health"
# Same address run.ps1 binds to (PROFITPILOT_BIND in the env file, default loopback).
$bind = "127.0.0.1"
$envFile = Join-Path $Home_ "profitpilot.env"
if (Test-Path $envFile) {
    $m = Select-String -Path $envFile -Pattern '^\s*PROFITPILOT_BIND\s*=\s*(\S+)' | Select-Object -First 1
    if ($m) { $bind = $m.Matches[0].Groups[1].Value.Trim('"', "'") }
}
for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-RestMethod -Uri "http://${bind}:$Port/api/v1/health" -TimeoutSec 3
        if ($r.status -eq "ok") { Step "Healthy."; exit 0 }
    } catch { }
}
throw "ProfitPilot did not become healthy within 90s - see C:\ProfitPilot\logs"
