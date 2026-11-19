# Copy the laptop's athlete data to the cloud VM.
#
# Run this ON THE LAPTOP, after deploy/cloud/install.sh has run on the VM:
#
#   powershell -ExecutionPolicy Bypass -File deploy\cloud\migrate-to-cloud.ps1 `
#       -Target coach@203.0.113.10 -Key $env:USERPROFILE\.ssh\oracle.key
#
# It builds one archive in %TEMP%, copies it over SSH, extracts it into
# /srv/coach-dashboard/data (and dashboard/index.html into the checkout), then
# deletes both copies. Nothing secret is printed, and no secret is written into
# the repository.
#
# Safe to re-run: files are copied over the old ones. It never deletes anything
# on the VM that it did not send.

#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Target,

    # Path to the private key for the VM. Omit to use the SSH agent or the
    # default key names.
    [string]$Key = "",

    # The laptop's GARMIN_DATA_DIR. Defaults to Downloads, which is what
    # paths.py uses when GARMIN_DATA_DIR is unset.
    [string]$DataDir = (Join-Path $env:USERPROFILE 'Downloads'),

    # The git checkout on the laptop. Defaults to the repository this script is
    # in.
    [string]$RepoDir = ""
)

$ErrorActionPreference = 'Stop'

if ($Target -match '\s') { throw "Target must look like user@host, got: $Target" }
if (-not $RepoDir) {
    $RepoDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}

foreach ($tool in 'tar.exe', 'scp.exe', 'ssh.exe') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "$tool was not found. Install the Windows OpenSSH client."
    }
}

$dataFiles = @(
    '.coach_dash_auth',
    '.coach_dash_sessionkey',
    '.coach_dash_token',
    'nutrition_log.csv',
    'nutrition_log.records.json',
    'nutrition_log.hook-token',
    'manual_runs.json',
    'garmin_last_sync.json',
    'garmin_sleep.csv',
    'garmin_hr.csv',
    'garmin_tokens.json'
)
$dataDirs = @('garmin_fit', '.garmin_tokens')

$stage = Join-Path $env:TEMP ("coach-cloud-" + [guid]::NewGuid().ToString('N'))
$archive = Join-Path $env:TEMP 'coach-dashboard-migrate.tar.gz'
$copied = New-Object System.Collections.Generic.List[string]

try {
    $stageData = Join-Path $stage 'data'
    $stageDash = Join-Path $stage 'dashboard'
    New-Item -ItemType Directory -Path $stageData -Force | Out-Null
    New-Item -ItemType Directory -Path $stageDash -Force | Out-Null

    foreach ($name in $dataDirs) {
        $src = Join-Path $DataDir $name
        if (Test-Path $src) {
            Copy-Item -Path $src -Destination (Join-Path $stageData $name) -Recurse -Force
            $copied.Add("$name/")
        }
    }

    foreach ($name in $dataFiles) {
        $src = Join-Path $DataDir $name
        if (Test-Path $src) {
            Copy-Item -Path $src -Destination (Join-Path $stageData $name) -Force
            $copied.Add($name)
        }
    }

    # The database lives in the checkout on the laptop, not in Downloads.
    $db = Join-Path $RepoDir 'trainloop.db'
    if (Test-Path $db) {
        Copy-Item -Path $db -Destination (Join-Path $stageData 'trainloop.db') -Force
        $copied.Add('trainloop.db')
    } else {
        Write-Warning "No trainloop.db in $RepoDir. The VM will rebuild it from FIT files on the first sync."
    }

    # The classic page is gitignored (it embeds exact coordinates), so it is not
    # in the clone. Copy it privately so /classic keeps working on the VM.
    $classic = Join-Path $RepoDir 'dashboard\index.html'
    if (Test-Path $classic) {
        Copy-Item -Path $classic -Destination (Join-Path $stageDash 'index.html') -Force
        $copied.Add('dashboard/index.html')
    }

    $apply = Join-Path $PSScriptRoot 'migrate-apply.sh'
    if (-not (Test-Path $apply)) { throw "Missing $apply" }
    Copy-Item -Path $apply -Destination (Join-Path $stage 'migrate.sh') -Force

    if (-not (Test-Path (Join-Path $stageData '.coach_dash_auth'))) {
        Write-Warning 'No dashboard password file found. The public URL would be open until you set one.'
    }
    if ($copied.Count -eq 0) { throw "Nothing to copy from $DataDir" }

    Write-Host "Archiving $($copied.Count) item(s)..."
    & tar.exe -czf $archive -C $stage data dashboard migrate.sh
    if ($LASTEXITCODE -ne 0) { throw "tar failed with exit code $LASTEXITCODE" }

    $sshOptions = @('-o', 'StrictHostKeyChecking=accept-new', '-o', 'ConnectTimeout=20')
    if ($Key) { $sshOptions = @('-i', $Key) + $sshOptions }

    Write-Host "Copying to ${Target}:/tmp ..."
    & scp.exe @sshOptions $archive "${Target}:/tmp/coach-dashboard-migrate.tar.gz"
    if ($LASTEXITCODE -ne 0) { throw "scp failed with exit code $LASTEXITCODE" }

    Write-Host 'Extracting on the VM...'
    $remote = 'sudo mkdir -p /tmp/coach-migrate && ' +
              'sudo tar -xzf /tmp/coach-dashboard-migrate.tar.gz -C /tmp/coach-migrate && ' +
              'sudo bash /tmp/coach-migrate/migrate.sh'
    & ssh.exe @sshOptions $Target $remote
    if ($LASTEXITCODE -ne 0) { throw "remote apply failed with exit code $LASTEXITCODE" }

    Write-Host ''
    Write-Host 'Copied:'
    foreach ($name in $copied) { Write-Host "  $name" }
    Write-Host ''
    Write-Host 'Next: on the VM, refresh the export so splits appear immediately:'
    Write-Host '  sudo -u coach /opt/coach-dashboard/venv/bin/python /opt/coach-dashboard/app/deploy/cloud/refresh_export.py'
}
finally {
    if (Test-Path $stage) { Remove-Item -Path $stage -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path $archive) { Remove-Item -Path $archive -Force -ErrorAction SilentlyContinue }
}
