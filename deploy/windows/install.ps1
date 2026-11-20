<#
.SYNOPSIS
  One-time setup of ProfitPilot on an always-on Windows PC (no Docker).

.DESCRIPTION
  Run from an *administrator* PowerShell, inside the cloned repo:
      powershell -ExecutionPolicy Bypass -File deploy\windows\install.ps1

  It:
    1. checks Python (3.11+), Node and git are installed;
    2. creates C:\ProfitPilot\{data,backups,logs} and C:\ProfitPilot\profitpilot.env
       (from backend\.env.example, with a freshly generated SECRET_KEY) — kept outside the repo;
    3. runs update.ps1 -SkipPull (venv, packages, frontend build);
    4. registers a scheduled task "ProfitPilot" that runs run.ps1 at boot, whether or not anyone
       is logged in, as YOUR account (asks for your Windows password once — Task Scheduler needs
       it to start the task before you log in). Not as SYSTEM: the Builder page runs pasted code
       and that must not have full machine rights.
    5. starts it and waits for /api/v1/health.
  Safe to re-run: an existing env file is never overwritten.
#>
param(
    [string]$Python = "python",
    [string]$Home_ = "C:\ProfitPilot",
    [string]$TaskName = "ProfitPilot",
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
function Step([string]$msg) { Write-Host "==> $msg" }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw "Run this from an administrator PowerShell (registering a boot task needs it)." }

Step "Checking prerequisites"
$pyVersion = & $Python -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ($LASTEXITCODE -ne 0) { throw "Python not found as '$Python'. Install Python 3.11+ (python.org) or pass -Python." }
if ([version]$pyVersion -lt [version]"3.11") { throw "Python $pyVersion found; 3.11 or newer is required." }
foreach ($tool in @("node", "npm", "git")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool not found. Install Node.js LTS and Git for Windows." }
}
Write-Host "    Python $pyVersion, Node $(node --version), $(git --version)"

Step "Creating $Home_"
foreach ($d in @("data", "backups", "logs")) { New-Item -ItemType Directory -Force -Path (Join-Path $Home_ $d) | Out-Null }
$envFile = Join-Path $Home_ "profitpilot.env"
if (Test-Path $envFile) {
    Write-Host "    $envFile exists - left unchanged"
} else {
    $secret = & $Python -c "import secrets; print(secrets.token_hex(32))"
    $lines = Get-Content (Join-Path $repo "backend\.env.example") | ForEach-Object {
        if ($_ -match '^SECRET_KEY=') { "SECRET_KEY=$secret" }
        elseif ($_ -match '^DEBUG=') { "DEBUG=false" }
        else { $_ }
    }
    $lines += @("", "# Where the app listens. Loopback only by default (there is no login).",
                "# For remote access put this PC's Tailscale IP here - never 0.0.0.0.",
                "# PROFITPILOT_BIND=100.x.y.z")
    Set-Content -Path $envFile -Value $lines -Encoding UTF8
    Write-Host "    wrote $envFile with a new SECRET_KEY - add TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID there"
}

Step "Installing packages and building (update.ps1 -SkipPull)"
& (Join-Path $PSScriptRoot "update.ps1") -SkipPull -Python $Python -TaskName "__none__" -Port $Port
if ($LASTEXITCODE -ne 0) { throw "update.ps1 failed" }

Step "Registering the '$TaskName' boot task"
$cred = Get-Credential -UserName "$env:USERDOMAIN\$env:USERNAME" -Message "Your Windows password, so ProfitPilot can start at boot before you log in"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$(Join-Path $PSScriptRoot 'run.ps1')`" -Home_ `"$Home_`" -Port $Port"
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -User $cred.UserName -Password $cred.GetNetworkCredential().Password -RunLevel Limited -Force | Out-Null

Step "Starting"
Start-ScheduledTask -TaskName $TaskName
for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 2
    try {
        if ((Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/health" -TimeoutSec 3).status -eq "ok") {
            Step "ProfitPilot is running: http://127.0.0.1:$Port"
            Write-Host "    Next: start the paper lineup ->"
            Write-Host "      backend\.venv\Scripts\python.exe backend\scripts\paper_lineup.py"
            exit 0
        }
    } catch { }
}
throw "Not healthy within 90s - check $Home_\logs"
